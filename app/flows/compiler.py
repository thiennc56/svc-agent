"""Kiểm tra hợp lệ + biên dịch flow (đồ thị node) → kế hoạch chạy (plan) cho runtime.

Lỗi (`errors`) chặn lưu/kích hoạt; cảnh báo (`warnings`) chỉ hiển thị. Mỗi issue gắn `node`/`edge` để editor tô đỏ.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.core.config import settings
from app.flows.catalog import KINDS, LLM_KINDS, defaults_for, port
from app.flows.schema import FlowDocument

GROQ_KEY_PREFIX = "gsk_"


@dataclass
class Issue:
    level: str  # error | warning
    code: str
    message: str
    node: str | None = None
    edge: str | None = None

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class ModelSpec:
    kind: str
    node: str
    config: dict


@dataclass
class ToolSource:
    node: str
    name: str
    server: str
    include: list[str]
    max_result_chars: int


@dataclass
class Plan:
    channels: list[str]
    system_prompt: str
    max_rounds: int
    max_tool_calls: int
    keyword_routing: bool
    keyword_preroute: bool
    history: int
    models: list[ModelSpec]
    sources: list[ToolSource]
    include_links: bool
    max_links: int
    agent_node: str = "agent"
    trigger_node: str = "trigger"
    reply_node: str = "reply"


@dataclass
class CompileResult:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    plan: Plan | None = None

    @property
    def ok(self) -> bool:
        return not self.errors

    def report(self) -> dict:
        return {"valid": self.ok, "errors": [i.as_dict() for i in self.errors], "warnings": [i.as_dict() for i in self.warnings]}


def _cfg(node, kind: str) -> dict:
    return {**defaults_for(kind), **(node.config or {})}


def _int(v: Any, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def parse(doc: dict | FlowDocument) -> tuple[FlowDocument | None, list[Issue]]:
    if isinstance(doc, FlowDocument):
        return doc, []
    try:
        return FlowDocument.model_validate(doc), []
    except ValidationError as exc:
        issues = []
        for e in exc.errors()[:20]:
            loc = ".".join(str(p) for p in e.get("loc", ()))
            issues.append(Issue("error", "schema", f"{loc}: {e.get('msg')}"))
        return None, issues


@dataclass
class Graph:
    nodes: dict
    active: dict
    incoming: dict[tuple[str, str], list[str]]
    outgoing: dict[tuple[str, str], list[str]]
    by_kind: dict[str, list]


def _check_graph(flow: FlowDocument, res: CompileResult) -> Graph:
    """Node hợp lệ, cạnh đúng cổng/kiểu, đủ node bắt buộc. Trả về chỉ mục cạnh (bỏ node bị tắt)."""
    err = lambda code, msg, **kw: res.errors.append(Issue("error", code, msg, **kw))  # noqa: E731
    nodes: dict = {}
    for n in flow.nodes:
        if n.id in nodes:
            err("duplicate_node", f"Trùng mã node '{n.id}'", node=n.id)
        elif n.kind not in KINDS:
            err("unknown_kind", f"Loại node không hỗ trợ: {n.kind}", node=n.id)
        else:
            nodes[n.id] = n
    active = {k: n for k, n in nodes.items() if not n.disabled}

    incoming: dict[tuple[str, str], list[str]] = {}
    outgoing: dict[tuple[str, str], list[str]] = {}
    seen: set[tuple] = set()
    edge_ids: set[str] = set()
    for e in flow.edges:
        if e.id in edge_ids:
            err("duplicate_edge", f"Trùng mã cạnh '{e.id}'", edge=e.id)
            continue
        edge_ids.add(e.id)
        s, t = nodes.get(e.source.node), nodes.get(e.target.node)
        if not s or not t:
            err("dangling_edge", "Cạnh nối tới node không tồn tại", edge=e.id)
            continue
        if s.id == t.id:
            err("self_loop", "Không được nối node vào chính nó", edge=e.id, node=s.id)
            continue
        sp, tp = port(s.kind, "out", e.source.port), port(t.kind, "in", e.target.port)
        if not sp or not tp:
            err("bad_port", f"Cổng không hợp lệ: {s.name or s.id}.{e.source.port} → {t.name or t.id}.{e.target.port}", edge=e.id)
            continue
        if sp["type"] != tp["type"]:
            err("type_mismatch", f"Không nối được cổng '{sp['type']}' vào cổng '{tp['type']}'", edge=e.id)
            continue
        key = (s.id, e.source.port, t.id, e.target.port)
        if key in seen:
            res.warnings.append(Issue("warning", "duplicate_link", "Cạnh bị trùng", edge=e.id))
            continue
        seen.add(key)
        if s.disabled or t.disabled:
            continue
        incoming.setdefault((t.id, e.target.port), []).append(s.id)
        outgoing.setdefault((s.id, e.source.port), []).append(t.id)

    by_kind: dict[str, list] = {}
    for n in active.values():
        by_kind.setdefault(n.kind, []).append(n)
    for kind, spec in KINDS.items():
        found = by_kind.get(kind, [])
        if spec.get("required") and not found:
            err("missing_node", f"Thiếu node bắt buộc: {spec['label']}")
        if spec.get("max") and len(found) > spec["max"]:
            for extra in found[spec["max"]:]:
                err("too_many", f"Chỉ được có {spec['max']} node '{spec['label']}'", node=extra.id)
    return Graph(nodes, active, incoming, outgoing, by_kind)



def _models(g: Graph, agent, res: CompileResult) -> list[ModelSpec]:
    model_ids = g.incoming.get((agent.id, "ai_model"), [])
    if not model_ids:
        res.errors.append(Issue("error", "missing_model", "AI Agent chưa nối Mô hình AI (Groq / Ollama / Model doanh nghiệp)", node=agent.id))
    out: list[ModelSpec] = []
    for mid in model_ids:  # thứ tự cạnh = thứ tự ưu tiên; model thứ 2 là dự phòng
        m = g.active[mid]
        c = _cfg(m, m.kind)
        if m.kind == "llm.groq":
            if not str(c.get("model") or "").strip():
                res.errors.append(Issue("error", "missing_field", "Groq: chưa chọn model", node=m.id))
            key = str(c.get("apiKey") or "")
            if key and key != "********" and not key.startswith(GROQ_KEY_PREFIX):
                res.warnings.append(Issue("warning", "key_format", "API key Groq thường bắt đầu bằng gsk_", node=m.id))
        if m.kind == "llm.ollama":
            url = str(c.get("baseUrl") or "").strip()
            if url and not url.startswith(("http://", "https://")):
                res.errors.append(Issue("error", "bad_url", "Ollama: Base URL phải bắt đầu bằng http:// hoặc https://", node=m.id))
        out.append(ModelSpec(m.kind, m.id, c))
    return out


def _sources(g: Graph, agent, app: str, res: CompileResult) -> list[ToolSource]:
    out: list[ToolSource] = []
    used: set[str] = set()
    for tid in g.incoming.get((agent.id, "ai_tool"), []):
        t = g.active[tid]
        c = _cfg(t, t.kind)
        server = str(c.get("server") or "")
        if not server:
            res.errors.append(Issue("error", "missing_field", "Nguồn MCP: chưa chọn máy chủ", node=t.id))
            continue
        meta = settings.mcp_servers.get(server)
        if meta is None:
            res.errors.append(Issue("error", "unknown_server", f"Máy chủ MCP '{server}' không có trong danh sách cho phép của svc-agent", node=t.id))
            continue
        apps = (meta or {}).get("apps") or []
        if app and apps and app not in apps:
            res.errors.append(Issue("error", "server_forbidden", f"Ứng dụng '{app}' không được dùng máy chủ MCP '{server}'", node=t.id))
            continue
        if server in used:
            res.warnings.append(Issue("warning", "duplicate_source", f"Máy chủ MCP '{server}' được nối nhiều lần – công cụ trùng chỉ lấy một lần", node=t.id))
        used.add(server)
        include = c.get("include")
        include = [str(x) for x in include] if isinstance(include, list) else ["*"]
        if not include:
            res.warnings.append(Issue("warning", "empty_source", "Nguồn MCP không bật công cụ nào", node=t.id))
        out.append(ToolSource(t.id, t.name or server, server, include, _int(c.get("maxResultChars"), 500, 12000, 3500)))
    if not out:
        res.warnings.append(Issue("warning", "no_tools", "AI Agent chưa nối nguồn dữ liệu nào – chỉ trả lời chung, không tra cứu được dữ liệu", node=agent.id))
    return out


def compile_flow(doc: dict | FlowDocument, app: str = "") -> CompileResult:
    res = CompileResult()
    flow, issues = parse(doc)
    if flow is None:
        res.errors.extend(issues)
        return res
    g = _check_graph(flow, res)
    if res.errors:
        return res

    trigger, agent, reply = g.by_kind["trigger.chat"][0], g.by_kind["agent.tools"][0], g.by_kind["output.reply"][0]
    if agent.id not in g.outgoing.get((trigger.id, "main"), []):
        res.errors.append(Issue("error", "not_connected", "Kênh chat phải nối vào AI Agent", node=trigger.id))
    if reply.id not in g.outgoing.get((agent.id, "main"), []):
        res.errors.append(Issue("error", "not_connected", "AI Agent phải nối tới node Trả lời", node=agent.id))
    for p in KINDS["agent.tools"]["inputs"]:
        if p.get("max") and len(g.incoming.get((agent.id, p["name"]), [])) > p["max"]:
            res.errors.append(Issue("error", "too_many_links", f"Cổng '{p.get('label', p['name'])}' chỉ nhận tối đa {p['max']} kết nối", node=agent.id))

    models = _models(g, agent, res)
    sources = _sources(g, agent, app, res)
    memory_ids = g.incoming.get((agent.id, "ai_memory"), [])
    history = _int(_cfg(g.active[memory_ids[0]], "memory.window").get("size"), 1, 20, 8) if memory_ids else 8

    feeds_agent = {src for (src, _), targets in g.outgoing.items() if agent.id in targets}
    for n in g.active.values():
        if n.kind in ("trigger.chat", "agent.tools", "output.reply") or n.id in feeds_agent:
            continue
        res.warnings.append(Issue("warning", "orphan", f"Node '{n.name or n.id}' chưa nối vào AI Agent – sẽ không được dùng", node=n.id))

    tc, ac, rc = _cfg(trigger, trigger.kind), _cfg(agent, agent.kind), _cfg(reply, reply.kind)
    channels = [c for c in (tc.get("channels") or []) if c in ("web", "mobile", "test")]
    if not channels:
        res.errors.append(Issue("error", "missing_field", "Kênh chat: chọn ít nhất một kênh", node=trigger.id))
    if res.errors:
        return res
    res.plan = Plan(
        channels=channels,
        system_prompt=str(ac.get("systemPrompt") or "")[:6000],
        max_rounds=_int(ac.get("maxRounds"), 1, 6, 3),
        max_tool_calls=_int(ac.get("maxToolCalls"), 1, 6, 3),
        keyword_routing=bool(ac.get("keywordRouting", True)),
        keyword_preroute=bool(ac.get("keywordPreroute", True)),
        history=history,
        models=models,
        sources=sources,
        include_links=bool(rc.get("includeLinks", True)),
        max_links=_int(rc.get("maxLinks"), 0, 8, 4),
        agent_node=agent.id, trigger_node=trigger.id, reply_node=reply.id,
    )
    return res


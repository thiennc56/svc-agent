"""Ghép flow đã biên dịch với cấu hình LLM của tenant + công cụ MCP thật (đã lọc theo quyền người hỏi).

`llm` (do app gửi trong body, KHÔNG lưu ở svc-agent) = cấu hình hiệu lực ở tab "AI & trợ lý":
  {"provider": "groq|ollama", "groqApiKey", "groqModel", "groqBaseUrl", "ollamaBaseUrl", "assistantModel",
   "numCtx", "numPredict", "temperature"}
"""
from __future__ import annotations

import asyncio
import fnmatch
import logging

from app.flows.compiler import ModelSpec, Plan
from app.runtime.llm import LLMTarget
from app.runtime.mcp_client import McpError, McpTool, list_tools

logger = logging.getLogger("svc_agent.resolve")


def _num(v, default: float) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def tenant_target(llm: dict, provider: str | None = None, node: str = "") -> LLMTarget | None:
    p = provider or str(llm.get("provider") or "ollama")
    temp = _num(llm.get("temperature"), 0.2)
    if p == "groq":
        return LLMTarget("groq", str(llm.get("groqModel") or "openai/gpt-oss-20b"), temp,
                         int(_num(llm.get("numPredict"), 512)), base_url=str(llm.get("groqBaseUrl") or ""),
                         api_key=str(llm.get("groqApiKey") or ""), node=node)
    return LLMTarget("ollama", str(llm.get("assistantModel") or ""), temp, int(_num(llm.get("numPredict"), 512)),
                     int(_num(llm.get("numCtx"), 4096)), base_url=str(llm.get("ollamaBaseUrl") or ""), node=node)


def model_targets(models: list[ModelSpec], llm: dict) -> list[LLMTarget]:
    """Node model → đích gọi. Trường để trống trong node = lấy từ cấu hình tenant."""
    out: list[LLMTarget] = []
    for m in models:
        c = m.config
        if m.kind == "llm.auto":
            t = tenant_target(llm, node=m.node)
        elif m.kind == "llm.groq":
            base = tenant_target(llm, "groq", m.node)
            key = str(c.get("apiKey") or "")
            t = LLMTarget("groq", str(c.get("model") or base.model), _num(c.get("temperature"), base.temperature),
                          int(_num(c.get("maxTokens"), 1024)), base_url=base.base_url,
                          api_key=key if key and key != "********" else base.api_key, node=m.node)
        else:
            base = tenant_target(llm, "ollama", m.node)
            t = LLMTarget("ollama", str(c.get("model") or base.model), _num(c.get("temperature"), base.temperature),
                          int(_num(c.get("numPredict"), base.max_tokens)), int(_num(c.get("numCtx"), base.num_ctx)),
                          base_url=str(c.get("baseUrl") or base.base_url), node=m.node)
        if t and t.model and all(x.label != t.label for x in out):
            out.append(t)
    return out


def _included(name: str, include: list[str]) -> bool:
    return any(p == "*" or fnmatch.fnmatchcase(name, p) for p in include)


async def resolve_tools(plan: Plan, app: str, auth) -> tuple[list[McpTool], dict[str, int], list[str]]:
    """Gọi tools/list song song cho các nguồn; nguồn lỗi bị bỏ qua (ghi cảnh báo), không làm hỏng cả lượt chat."""
    results = await asyncio.gather(*(list_tools(s.server, app, auth) for s in plan.sources), return_exceptions=True)
    tools: list[McpTool] = []
    limits: dict[str, int] = {}
    problems: list[str] = []
    seen: set[str] = set()
    for src, res in zip(plan.sources, results):
        if isinstance(res, Exception):
            msg = str(res) if isinstance(res, McpError) else type(res).__name__
            logger.warning("mcp tools/list failed server=%s: %s", src.server, msg)
            problems.append(f"{src.name}: {msg}")
            continue
        for t in res:
            if t.name in seen or not _included(t.name, src.include):
                continue
            seen.add(t.name)
            tools.append(t)
            limits[t.name] = src.max_result_chars
    return tools, limits, problems

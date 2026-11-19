"""Client MCP (Model Context Protocol) qua HTTP JSON-RPC 2.0 (transport "streamable HTTP", phản hồi JSON).

Mỗi request gửi kèm:
  X-Agent-Context: <JWT RS256 svc-agent ký, 120 s, aud=<mã nguồn>> – ai đang hỏi (sub, email, tenant, act=user|service,
                   permissions mcp:<nguồn>:*). Phân hệ verify qua JWKS {AGENT_ISSUER}/.well-known/jwks.json
  Authorization:   <JWT SOPBase người hỏi> – chỉ khi nguồn bật forward_user_jwt và người hỏi là người dùng (không phải bot)
  tenant-id:       <tenant>
  X-Agent-Token:   <token riêng của nguồn | token của app> → phân hệ chỉ nhận lời gọi từ svc-agent
Giai đoạn C: nguồn require_grant → chỉ công cụ có quyền mcp:<nguồn>:<công cụ> (HRM) mới được liệt kê / gọi.
Chỉ gọi server trong registry (ConfigMap + nguồn khai báo trên HRM), không bao giờ gọi URL do người dùng nhập.
"""
from __future__ import annotations

import itertools
import logging
import time
from dataclasses import dataclass, field

import httpx

from app.core.config import settings
from app.core import perms as P
from app.core.security import UserAuth, service_token_for
from app.core.signing import SigningKeyMissing, sign_context
from app.sources import registry
from app.sources.crypto import decrypt

logger = logging.getLogger(__name__)
PROTOCOL_VERSION = "2025-06-18"
_ids = itertools.count(1)
_cache: dict[tuple, tuple[float, list["McpTool"]]] = {}


class McpError(Exception):
    pass


@dataclass
class McpTool:
    server: str
    name: str
    description: str
    input_schema: dict
    meta: dict = field(default_factory=dict)  # x-dns: title, group, permissions, roles, keywords, suggestion...

    def schema(self) -> dict:
        params = self.input_schema or {"type": "object", "properties": {}}
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": params}}

    def public(self) -> dict:
        return {"server": self.server, "name": self.name, "description": self.description,
                "inputSchema": self.input_schema, **{k: v for k, v in self.meta.items() if k not in ("keywords",)},
                "keywords": self.meta.get("keywords") or []}


def agent_token_for(server: str, app: str) -> str:
    """X-Agent-Token gửi tới MCP server: token riêng của nguồn (MCP_TOKENS / token mã hoá trong DB) nếu có,
    không thì token của app (tương thích svc-hrm)."""
    if settings.mcp_tokens.get(server):
        return settings.mcp_tokens[server]
    meta = registry.get(server) or {}
    return decrypt(meta.get("token_enc")) or service_token_for(app)


def server_meta(server: str) -> dict:
    meta = registry.get(server)
    if meta is None:
        raise McpError(f"MCP server '{server}' không có trong danh sách cho phép")
    return meta


async def _rpc(server: str, app: str, auth: UserAuth, method: str, params: dict | None = None) -> dict:
    meta = server_meta(server)
    url = meta.get("url")
    if not url:
        raise McpError(f"MCP server '{server}' chưa khai báo url")
    if meta.get("source") == "db" and (reason := registry.check_url(url)):  # nguồn động: kiểm lại allowlist mỗi lần gọi
        raise McpError(f"MCP '{server}': {reason}")
    timeout = float(meta.get("timeout") or settings.mcp_timeout_seconds)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PROTOCOL_VERSION,
        "tenant-id": auth.tenant_id,
        "X-Agent-Token": agent_token_for(server, app),
        "X-Agent-App": app,
    }
    # JWT SOPBase của người hỏi: chỉ nguồn còn bật "chuyển tiếp JWT" (mặc định, tương thích hướng dẫn v1.1).
    # Bot (kind=service) không có JWT người dùng → chỉ dùng signed_context.
    if meta.get("forward_user_jwt", True) and auth.kind == "user":
        headers["Authorization"] = auth.authorization
    try:  # signed_context: ai đang hỏi, ký bởi svc-agent, aud = mã nguồn (phân hệ verify qua JWKS)
        headers["X-Agent-Context"] = sign_context(server, sub=auth.user_id, email=auth.email, tenant=auth.tenant_id,
                                                  app=app, act=auth.kind, name=auth.name, permissions=auth.permissions)
    except SigningKeyMissing as exc:
        logger.error("signed_context: %s", exc)
    if "Authorization" not in headers and "X-Agent-Context" not in headers:
        raise McpError(f"MCP '{server}': không có danh tính người hỏi để gửi (thiếu AGENT_SIGNING_KEY)")
    body = {"jsonrpc": "2.0", "id": next(_ids), "method": method, "params": params or {}}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=5.0), follow_redirects=False) as client:
            resp = await client.post(url, json=body, headers=headers)
    except httpx.HTTPError as exc:
        raise McpError(f"Không kết nối được MCP '{server}': {type(exc).__name__}") from exc
    if resp.status_code in (401, 403):
        raise McpError(f"MCP '{server}' từ chối truy cập ({resp.status_code})")
    if resp.status_code >= 400:
        raise McpError(f"MCP '{server}' lỗi HTTP {resp.status_code}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise McpError(f"MCP '{server}' trả dữ liệu không hợp lệ") from exc
    if data.get("error"):
        raise McpError(f"MCP '{server}': {(data['error'] or {}).get('message', 'error')}")
    return data.get("result") or {}


def requires_grant(server: str) -> bool:
    """Nguồn yêu cầu quyền mcp:<nguồn>:<công cụ> từ HRM (lớp 1). Nguồn hạ tầng ConfigMap (vd. hrm) tự kiểm quyền → False."""
    return bool((registry.get(server) or {}).get("require_grant", False))


def tool_allowed(server: str, tool: str, auth: UserAuth) -> bool:
    return not requires_grant(server) or P.can_use_tool(auth.permissions, server, tool)


async def list_tools(server: str, app: str, auth: UserAuth, use_cache: bool = True,
                     filter_grants: bool = True) -> list[McpTool]:
    """tools/list (phân hệ đã lọc theo quyền của nó – lớp 2) → lọc thêm theo quyền mcp:* của HRM (lớp 1). Cache theo người."""
    if filter_grants and requires_grant(server) and not P.can_use_source(auth.permissions, server):
        return []  # không có quyền nào với nguồn → không gọi phân hệ
    key = (server, app, auth.tenant_id, auth.user_id or auth.email or auth.authorization[-24:], auth.kind)
    now = time.monotonic()
    hit = _cache.get(key)
    if use_cache and hit and now - hit[0] < settings.tools_cache_seconds:
        tools = hit[1]
    else:
        result = await _rpc(server, app, auth, "tools/list")
        tools = [
            McpTool(server, t.get("name", ""), t.get("description") or t.get("title") or "", t.get("inputSchema") or {},
                    {**(t.get("x-dns") or {}), "title": t.get("title") or (t.get("x-dns") or {}).get("title") or t.get("name")})
            for t in result.get("tools") or [] if t.get("name")
        ]
        if len(_cache) > 2000:
            _cache.clear()
        _cache[key] = (now, tools)
    return [t for t in tools if tool_allowed(server, t.name, auth)] if filter_grants else tools


async def call_tool(server: str, app: str, auth: UserAuth, name: str, arguments: dict, channel: str = "") -> dict:
    """tools/call → dict kết quả (structuredContent nếu có, không thì text JSON). Lỗi → {"error": ...}. Luôn ghi audit."""
    from app.sources import audit

    started = time.perf_counter()

    def log(status: str, error: str | None = None) -> None:
        audit.record(app=app, auth=auth, server=server, tool=name, status=status, error=error, channel=channel,
                     duration_ms=int((time.perf_counter() - started) * 1000))

    if not tool_allowed(server, name, auth):  # kiểm lại lúc gọi (không tin danh sách đã lọc / model)
        log("denied", "no_grant")
        return {"error": "not_permitted", "message": "Bạn chưa được cấp quyền dùng công cụ này (Phân quyền vai trò → Trợ lý AI)."}
    try:
        result = await _rpc(server, app, auth, "tools/call", {"name": name, "arguments": arguments or {}})
    except McpError as exc:
        logger.warning("mcp call failed server=%s tool=%s: %s", server, name, exc)
        log("error", "unavailable")
        return {"error": "unavailable", "message": str(exc)[:200]}
    log("error" if result.get("isError") else "ok",
        (result.get("structuredContent") or {}).get("error") if result.get("isError") and isinstance(result.get("structuredContent"), dict) else None)
    if isinstance(result.get("structuredContent"), dict):
        data = result["structuredContent"]
    else:
        import json

        text = "".join(c.get("text", "") for c in result.get("content") or [] if c.get("type") == "text")
        try:
            data = json.loads(text) if text else {}
        except ValueError:
            data = {"text": text[:4000]}
    if result.get("isError") and isinstance(data, dict) and "error" not in data:
        data = {"error": "tool_error", **data}
    return data if isinstance(data, dict) else {"result": data}


async def ping(server: str, app: str, auth: UserAuth) -> dict:
    started = time.perf_counter()
    info = await _rpc(server, app, auth, "initialize", {
        "protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": "svc-agent", "version": "1.0.0"}})
    return {"ok": True, "latencyMs": int((time.perf_counter() - started) * 1000), "serverInfo": info.get("serverInfo") or {},
            "instructions": info.get("instructions") or ""}

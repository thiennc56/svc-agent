"""Client MCP (Model Context Protocol) qua HTTP JSON-RPC 2.0 (transport "streamable HTTP", phản hồi JSON).

Mỗi request gửi kèm:
  Authorization: <JWT người hỏi>   → phân hệ kiểm RBAC như REST API của nó
  tenant-id:     <tenant>
  X-Agent-Token: <service token của app> → phân hệ chỉ nhận lời gọi từ svc-agent
Chỉ gọi server trong allowlist MCP_SERVERS (theo key), không bao giờ gọi URL do người dùng nhập.
"""
from __future__ import annotations

import itertools
import logging
import time
from dataclasses import dataclass, field

import httpx

from app.core.config import settings
from app.core.security import UserAuth, service_token_for

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


def server_meta(server: str) -> dict:
    meta = settings.mcp_servers.get(server)
    if meta is None:
        raise McpError(f"MCP server '{server}' không có trong danh sách cho phép")
    return meta


async def _rpc(server: str, app: str, auth: UserAuth, method: str, params: dict | None = None) -> dict:
    meta = server_meta(server)
    url = meta.get("url")
    if not url:
        raise McpError(f"MCP server '{server}' chưa khai báo url")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PROTOCOL_VERSION,
        "Authorization": auth.authorization,
        "tenant-id": auth.tenant_id,
        "X-Agent-Token": service_token_for(app),
        "X-Agent-App": app,
    }
    body = {"jsonrpc": "2.0", "id": next(_ids), "method": method, "params": params or {}}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.mcp_timeout_seconds, connect=5.0)) as client:
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


async def list_tools(server: str, app: str, auth: UserAuth, use_cache: bool = True) -> list[McpTool]:
    """tools/list đã được phân hệ lọc theo quyền người hỏi → cache theo người dùng."""
    key = (server, app, auth.tenant_id, auth.user_id or auth.email or auth.authorization[-24:])
    now = time.monotonic()
    hit = _cache.get(key)
    if use_cache and hit and now - hit[0] < settings.tools_cache_seconds:
        return hit[1]
    result = await _rpc(server, app, auth, "tools/list")
    tools = [
        McpTool(server, t.get("name", ""), t.get("description") or t.get("title") or "", t.get("inputSchema") or {},
                {**(t.get("x-dns") or {}), "title": t.get("title") or (t.get("x-dns") or {}).get("title") or t.get("name")})
        for t in result.get("tools") or [] if t.get("name")
    ]
    if len(_cache) > 2000:
        _cache.clear()
    _cache[key] = (now, tools)
    return tools


async def call_tool(server: str, app: str, auth: UserAuth, name: str, arguments: dict) -> dict:
    """tools/call → dict kết quả (structuredContent nếu có, không thì text JSON). Lỗi → {"error": ...}."""
    try:
        result = await _rpc(server, app, auth, "tools/call", {"name": name, "arguments": arguments or {}})
    except McpError as exc:
        logger.warning("mcp call failed server=%s tool=%s: %s", server, name, exc)
        return {"error": "unavailable", "message": str(exc)[:200]}
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

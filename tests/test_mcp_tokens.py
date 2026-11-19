"""X-Agent-Token theo từng nguồn MCP (MCP_TOKENS) – phân hệ A không bao giờ nhận token dùng cho phân hệ B."""
import asyncio

import httpx

from app.core.config import settings
from app.core.security import UserAuth
from app.runtime import mcp_client

AUTH = UserAuth("Bearer user-jwt", "00000000-0000-0000-0000-000000000010", "u1", "a@test.vn")


def test_agent_token_per_server(monkeypatch):
    monkeypatch.setattr(settings, "mcp_tokens", {"kho": "tok-kho-only"})
    assert mcp_client.agent_token_for("kho", "erp") == "tok-kho-only"
    assert mcp_client.agent_token_for("hrm", "hrm") == "tok-hrm"  # không khai báo → token của app (tương thích cũ)


def test_rpc_sends_server_token_and_user_context(monkeypatch):
    monkeypatch.setattr(settings, "mcp_tokens", {"kho": "tok-kho-only"})
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(url=str(request.url), headers=dict(request.headers))
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(mcp_client.httpx, "AsyncClient", lambda **kw: real_client(transport=transport, **kw))
    asyncio.run(mcp_client._rpc("kho", "erp", AUTH, "ping"))
    assert seen["url"] == "http://svc-kho.test/mcp"
    assert seen["headers"]["x-agent-token"] == "tok-kho-only"
    assert seen["headers"]["authorization"] == "Bearer user-jwt"
    assert seen["headers"]["tenant-id"] == AUTH.tenant_id
    assert seen["headers"]["mcp-protocol-version"] == mcp_client.PROTOCOL_VERSION

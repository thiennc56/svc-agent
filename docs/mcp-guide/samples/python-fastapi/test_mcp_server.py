"""Bộ test nghiệm thu tối thiểu cho MCP server phân hệ – sao chép & sửa cho phân hệ của bạn.

Không cần mạng: tự sinh cặp khoá RSA, ký JWT giống SOPBase, thay JWKS bằng khoá test.
Chạy: pytest -q
"""
from __future__ import annotations

import base64
import json
import os
import time

os.environ["MCP_AGENT_TOKEN"] = "agent-tok-crm"
os.environ["OIDC_ISSUER"] = "https://sopbase.test/auth"
os.environ["OIDC_ACCEPTED_AUDIENCES"] = "hrm-web-client,hrm-mobile-client"

import pytest  # noqa: E402
from authlib.jose import JsonWebKey, jwt  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import mcp_server  # noqa: E402

KEY = JsonWebKey.generate_key("RSA", 2048, is_private=True, options={"kid": "test-kid"})
OTHER_KEY = JsonWebKey.generate_key("RSA", 2048, is_private=True, options={"kid": "test-kid"})


def make_token(email="sale1@test.com", aud="hrm-web-client", iss="https://sopbase.test/auth", exp_in=300, key=KEY):
    now = int(time.time())
    claims = {"sub": "11111111-1111-1111-1111-111111111111", "email": email, "iss": iss, "aud": aud,
              "iat": now, "exp": now + exp_in}
    return jwt.encode({"alg": "RS256", "kid": "test-kid"}, claims, key).decode()


@pytest.fixture(autouse=True)
def _jwks(monkeypatch):
    async def fake_fetch():
        return {"keys": [KEY.as_dict(is_private=False)]}

    mcp_server._jwks_cache.update({"at": 0.0, "keys": None})
    monkeypatch.setattr(mcp_server, "_fetch_jwks", fake_fetch)


@pytest.fixture
def client():
    return TestClient(mcp_server.app)


def headers(token=None, agent="agent-tok-crm", tenant="t1"):
    return {"Authorization": f"Bearer {token or make_token()}", "tenant-id": tenant, "X-Agent-Token": agent,
            "MCP-Protocol-Version": "2025-06-18"}


def rpc(client, method, params=None, rid=1, **kw):
    return client.post("/mcp", json={"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}, headers=headers(**kw))


def call(client, name, arguments, **kw):
    return rpc(client, "tools/call", {"name": name, "arguments": arguments}, **kw).json()["result"]


# ───────── Giao thức ─────────
def test_initialize_and_ping(client):
    res = rpc(client, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t"}}).json()
    assert res["result"]["protocolVersion"] == "2025-06-18"
    assert "tools" in res["result"]["capabilities"]
    assert rpc(client, "ping").json()["result"] == {}


def test_notification_returns_202(client):
    r = client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=headers())
    assert r.status_code == 202


def test_unknown_method(client):
    assert rpc(client, "resources/list").json()["error"]["code"] == -32601


def test_tools_have_dns_profile(client):
    tools = rpc(client, "tools/list").json()["result"]["tools"]
    assert tools
    for t in tools:
        assert t["inputSchema"]["type"] == "object"
        assert t["annotations"]["readOnlyHint"] is True
        assert t["x-dns"]["readOnly"] is True and t["x-dns"]["permissions"]
        assert t["name"].startswith("crm_")


def test_batch(client):
    body = [{"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    out = client.post("/mcp", json=body, headers=headers()).json()
    assert [r["id"] for r in out] == [1, 2]


# ───────── Xác thực ─────────
@pytest.mark.parametrize("agent", ["", "wrong"])
def test_rejects_without_agent_token(client, agent):
    assert rpc(client, "ping", agent=agent).status_code == 401


@pytest.mark.parametrize("token", [
    make_token(exp_in=-120),                   # hết hạn
    make_token(aud="other-app-client"),        # token cấp cho client khác (vd. client riêng của phân hệ khác)
    make_token(iss="https://evil.test/auth"),  # issuer lạ
    make_token(key=OTHER_KEY),                 # chữ ký sai
    "not-a-jwt",
])
def test_rejects_bad_user_token(client, token):
    r = rpc(client, "ping", token=token)
    assert r.status_code == 401
    assert "WWW-Authenticate" in r.headers


def test_rejects_alg_none(client):
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    payload = {"sub": "x", "email": "manager@test.com", "iss": "https://sopbase.test/auth", "aud": "hrm-web-client",
               "exp": int(time.time()) + 300}
    forged = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64(payload)}."
    assert rpc(client, "ping", token=forged).status_code == 401


def test_rejects_user_outside_tenant(client):
    assert rpc(client, "ping", tenant="t2").status_code == 403


# ───────── Phân quyền dữ liệu ─────────
def test_tools_list_filtered_by_permission(client):
    assert rpc(client, "tools/list", token=make_token("guest@test.com")).json()["result"]["tools"] == []


def test_call_not_permitted_tool(client):
    res = call(client, "crm_search_customers", {"query": "an"}, token=make_token("guest@test.com"))
    assert res["isError"] is True and res["structuredContent"]["error"] == "not_permitted_or_unknown_tool"


def test_sales_sees_only_own_customers_in_own_tenant(client):
    data = call(client, "crm_search_customers", {"query": "an"})["structuredContent"]
    assert {i["code"] for i in data["items"]} == {"KH001", "KH003"}  # không có KH002 (người khác) và KH900 (tenant khác)
    assert all("link" in i for i in data["items"])


def test_manager_sees_all_in_tenant(client):
    data = call(client, "crm_search_customers", {"query": "kh0"}, token=make_token("manager@test.com"))["structuredContent"]
    assert {i["code"] for i in data["items"]} == {"KH001", "KH002", "KH003"}


def test_no_existence_leak(client):
    res = call(client, "crm_get_customer", {"code": "KH002"})
    assert res["structuredContent"]["error"] == "not_found"


@pytest.mark.parametrize("args", [{}, {"query": ""}, {"query": "a", "tenant": "t2"}, {"query": "a", "limit": 999},
                                  {"query": 5}, {"query": "a", "limit": True}])
def test_invalid_arguments(client, args):
    res = call(client, "crm_search_customers", args)
    assert res["isError"] is True and res["structuredContent"]["error"] == "invalid_arguments"


def test_get_not_allowed(client):
    assert client.get("/mcp").status_code == 405


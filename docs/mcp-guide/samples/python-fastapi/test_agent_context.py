"""Xác thực bằng X-Agent-Context (signed_context, hướng dẫn v1.2) – JWT RS256 do svc-agent ký, aud = mã nguồn."""
from __future__ import annotations

import os
import time

import pytest
from authlib.jose import JsonWebKey, jwt
from fastapi.testclient import TestClient

KEY = JsonWebKey.generate_key("RSA", 2048, is_private=True, options={"kid": "agent-kid"})
ISS = "https://hrmapi.test/agent"


def ctx_token(email="sale1@test.com", aud="crm", tenant="t1", act="user", iss=ISS, exp_in=120, key=KEY):
    now = int(time.time())
    claims = {"iss": iss, "aud": [aud], "sub": "u1", "email": email, "tenant": tenant, "app": "hrm", "act": act,
              "permissions": ["mcp:crm:*"], "iat": now, "nbf": now - 5, "exp": now + exp_in, "jti": "j"}
    return jwt.encode({"alg": "RS256", "kid": "agent-kid"}, claims, key).decode()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MCP_AGENT_TOKEN", "agent-tok-crm")
    monkeypatch.setenv("AGENT_ISSUER", ISS)
    monkeypatch.setenv("AGENT_JWKS_URL", "http://svc-agent.test/.well-known/jwks.json")
    monkeypatch.setenv("MCP_SOURCE_KEY", "crm")
    import agent_context
    import mcp_server

    async def fake_fetch():
        return {"keys": [KEY.as_dict(is_private=False)]}

    agent_context._cache.update({"at": 0.0, "keys": None})
    monkeypatch.setattr(agent_context, "_fetch", fake_fetch)
    return TestClient(mcp_server.app)


def call(client, token, tenant="t1", method="tools/list"):
    h = {"X-Agent-Token": "agent-tok-crm", "tenant-id": tenant}
    if token:
        h["X-Agent-Context"] = token
    return client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": {}}, headers=h)


def test_user_context_ok_without_sopbase_jwt(client):
    r = call(client, ctx_token())
    assert r.status_code == 200 and {t["name"] for t in r.json()["result"]["tools"]} >= {"crm_search_customers"}


def test_bot_context_uses_bot_permissions(client):
    names = {t["name"] for t in call(client, ctx_token(email="bot-bao-cao@hrm.bot", act="service")).json()["result"]["tools"]}
    assert names == {"crm_my_opportunities"}  # bot chỉ được quyền tối thiểu phân hệ cấp


@pytest.mark.parametrize("token", [
    None, ctx_token(aud="kho"), ctx_token(iss="https://evil/agent"), ctx_token(exp_in=-60),
    ctx_token(key=JsonWebKey.generate_key("RSA", 2048, is_private=True, options={"kid": "agent-kid"})),
])
def test_bad_context_rejected(client, token):
    assert call(client, token).status_code == 401


def test_tenant_must_match_signed_context(client):
    assert call(client, ctx_token(tenant="t1"), tenant="t2").status_code == 403


def teardown_module():
    for k in ("AGENT_ISSUER", "AGENT_JWKS_URL", "MCP_SOURCE_KEY"):
        os.environ.pop(k, None)

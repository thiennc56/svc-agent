"""Giai đoạn C: signed_context (JWT RS256 + JWKS), lọc quyền mcp:*, audit, bot không gửi JWT người dùng."""
import asyncio
import json

import httpx
from authlib.jose import JsonWebKey, jwt

from app.core import perms as P
from app.core.security import UserAuth
from app.runtime import mcp_client
from app.sources import audit, registry
from tests.conftest import HEADERS

BASE = "/v1/apps/hrm/sources"
CRM = {"key": "crm", "title": "CRM", "url": "http://svc-crm.erp.svc.cluster.local:8000/mcp", "apps": ["hrm"]}
TOOLS = [{"name": "crm_search_customers", "description": "Tìm khách hàng", "inputSchema": {"type": "object", "properties": {}}},
         {"name": "crm_revenue", "description": "Doanh thu", "inputSchema": {"type": "object", "properties": {}}}]


def _mock(monkeypatch, seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.headers))
        msg = json.loads(request.content)
        result = {"tools": TOOLS} if msg["method"] == "tools/list" else {"structuredContent": {"ok": 1}}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": msg["id"], "result": result})

    real = httpx.AsyncClient
    monkeypatch.setattr(mcp_client.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    mcp_client._cache.clear()


def test_perm_matching():
    assert P.has(["mcp:crm:*"], "mcp:crm:crm_revenue") and P.has(["*"], "mcp:x:y") and P.has(["mcp:*"], "mcp:x:y")
    assert not P.has(["mcp:kho:*"], "mcp:crm:crm_revenue") and not P.has(["mcp:crm:a"], "mcp:crm:b")
    assert P.can_use_source(["mcp:crm:crm_revenue"], "crm") and not P.can_use_source(["mcp:kho:*"], "crm")
    assert P.clean(["mcp:crm:*", "app:roles:read", "drop table", "wf:report:run"]) == ("mcp:crm:*", "wf:report:run")


def test_jwks_and_signed_context_verifiable(client):
    keys = client.get("/.well-known/jwks.json").json()
    assert keys["keys"][0]["kty"] == "RSA" and "d" not in keys["keys"][0]  # chỉ khoá công khai
    from app.core.signing import sign_context
    token = sign_context("crm", sub="u1", email="a@x.vn", tenant="t1", app="hrm", act="service",
                         permissions=["mcp:crm:*", "mcp:kho:*", "wf:x:run"])
    claims = jwt.decode(token, JsonWebKey.import_key_set(keys),
                        claims_options={"aud": {"essential": True, "values": ["crm"]}, "iss": {"essential": True}})
    claims.validate()
    assert claims["act"] == "service" and claims["tenant"] == "t1" and claims["permissions"] == ["mcp:crm:*"]
    assert claims["exp"] - claims["iat"] <= 600


def test_grants_filter_list_and_call_and_audit(client, monkeypatch):
    client.post(BASE, headers=HEADERS, json=CRM)  # requireGrant mặc định bật
    seen: list = []
    _mock(monkeypatch, seen)
    nobody = UserAuth("Bearer u", "t1", "u1", "a@x.vn", ())
    assert asyncio.run(mcp_client.list_tools("crm", "hrm", nobody)) == [] and not seen  # không quyền → không gọi phân hệ
    one = UserAuth("Bearer u", "t1", "u1", "a@x.vn", ("mcp:crm:crm_search_customers",))
    names = [t.name for t in asyncio.run(mcp_client.list_tools("crm", "hrm", one))]
    assert names == ["crm_search_customers"]
    denied = asyncio.run(mcp_client.call_tool("crm", "hrm", one, "crm_revenue", {}, channel="web"))
    assert denied["error"] == "not_permitted"
    ok = asyncio.run(mcp_client.call_tool("crm", "hrm", one, "crm_search_customers", {}, channel="web"))
    assert ok == {"ok": 1}
    rows = audit.query("hrm", "t1")
    assert [(r["tool"], r["status"]) for r in rows] == [("crm_search_customers", "ok"), ("crm_revenue", "denied")]
    assert rows[0]["actor"] == "a@x.vn" and rows[0]["channel"] == "web"
    hdr = seen[-1]
    assert hdr["authorization"] == "Bearer u" and hdr["x-agent-context"].count(".") == 2  # tương thích: JWT + context


def test_bot_never_forwards_user_jwt_and_hrm_source_needs_no_grant(client, monkeypatch):
    client.post(BASE, headers=HEADERS, json={**CRM, "forwardUserJwt": True})
    seen: list = []
    _mock(monkeypatch, seen)
    bot = UserAuth("Bearer svc", "t1", "bot-1", "bot@hrm", ("mcp:crm:*",), "Bot báo cáo", "service")
    asyncio.run(mcp_client.call_tool("crm", "hrm", bot, "crm_revenue", {}, channel="workflow"))
    assert "authorization" not in seen[-1] and "x-agent-context" in seen[-1]
    assert audit.query("hrm", "t1")[0]["actorKind"] == "service"
    assert not mcp_client.requires_grant("hrm")  # nguồn ConfigMap tự kiểm RBAC – không đòi mcp:*
    assert registry.get("crm")["require_grant"] is True


def test_audit_api_and_permissions_header(client, monkeypatch):
    client.post(BASE, headers=HEADERS, json=CRM)
    seen: list = []
    _mock(monkeypatch, seen)
    h = {**HEADERS, "X-User-Permissions": "mcp:crm:*,app:roles:read"}
    assert client.get("/v1/apps/hrm/registry?refresh=true", headers=h).json()["servers"]
    r = client.get(f"{BASE}/tool-catalog", headers=HEADERS).json()  # không có mcp:* vẫn thấy đủ công cụ để cấp quyền
    assert [t["name"] for t in r["sources"][0]["tools"]] == ["crm_search_customers", "crm_revenue"]
    assert client.get("/v1/apps/hrm/audit", headers=HEADERS).json() == {"items": [], "nextBeforeId": None}

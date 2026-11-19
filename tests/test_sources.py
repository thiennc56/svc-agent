"""Nguồn MCP động: CRUD, token 1 lần + mã hoá, chống SSRF, dùng ngay trong flow/registry, test kết nối, kiểm tra chuẩn."""
import httpx

from app.runtime import mcp_client
from app.sources import registry
from app.sources.crypto import decrypt
from app.sources.models import AgentMcpSource
from tests.conftest import HEADERS
from tests.helpers import fake_mcp  # noqa: F401

BASE = "/v1/apps/hrm/sources"
CRM = {"key": "crm", "title": "CRM – Khách hàng", "description": "Khách hàng, cơ hội", "icon": "pi pi-briefcase",
       "color": "#0ea5e9", "url": "http://svc-crm.erp.svc.cluster.local:8000/mcp", "apps": ["hrm"]}


def test_create_returns_token_once_and_stores_encrypted(client):
    r = client.post(BASE, headers=HEADERS, json=CRM)
    assert r.status_code == 201
    body = r.json()
    token = body["token"]
    assert len(token) == 48 and body["tokenHint"] == token[-4:] and body["editable"] and body["source"] == "db"
    from app.core.db import SessionLocal
    with SessionLocal() as db:
        row = db.get(AgentMcpSource, "crm")
        assert row.token_enc and token not in row.token_enc and decrypt(row.token_enc) == token
    listed = client.get(BASE, headers=HEADERS).json()
    crm = next(i for i in listed["items"] if i["key"] == "crm")
    assert "token" not in crm and crm["hasToken"] and crm["tokenHint"] == token[-4:]
    assert {i["key"]: i["editable"] for i in listed["items"]}["hrm"] is False  # ConfigMap: chỉ đọc
    assert mcp_client.agent_token_for("crm", "hrm") == token


def test_new_source_usable_in_catalog_and_flow_immediately(client):
    client.post(BASE, headers=HEADERS, json=CRM)
    keys = [s["key"] for s in client.get("/v1/apps/hrm/catalog", headers=HEADERS).json()["mcpServers"]]
    assert "crm" in keys
    doc = client.get("/v1/apps/hrm/flow", headers=HEADERS).json()["document"]
    doc["nodes"].append({"id": "crm", "kind": "tool.mcp", "name": "CRM", "position": {"x": 0, "y": 500},
                         "config": {"server": "crm", "include": ["*"], "maxResultChars": 3500}})
    doc["edges"].append({"id": "e_crm", "source": {"node": "crm", "port": "ai_tool"}, "target": {"node": "agent", "port": "ai_tool"}})
    assert client.post("/v1/apps/hrm/flow/validate", headers=HEADERS, json={"document": doc}).json()["valid"]
    client.put(f"{BASE}/crm", headers=HEADERS, json={**CRM, "enabled": False})
    report = client.post("/v1/apps/hrm/flow/validate", headers=HEADERS, json={"document": doc}).json()
    assert not report["valid"] and any(e["code"] == "unknown_server" for e in report["errors"])


def test_ssrf_and_validation(client):
    for url in ("http://169.254.169.254/latest/meta-data", "file:///etc/passwd", "http://evil.example.com/mcp",
                "http://user:pw@svc-crm/mcp", "http://svc-crm/mcp?x=1"):
        r = client.post(BASE, headers=HEADERS, json={**CRM, "url": url})
        assert r.status_code == 422, url
    assert client.post(BASE, headers=HEADERS, json={**CRM, "key": "Bad Key"}).status_code == 422
    assert client.post(BASE, headers=HEADERS, json={**CRM, "key": "hrm"}).status_code == 409  # trùng ConfigMap
    assert client.put(f"{BASE}/hrm", headers=HEADERS, json=CRM).status_code == 409  # ConfigMap chỉ đọc
    assert client.delete(f"{BASE}/hrm", headers=HEADERS).status_code == 409
    assert client.post(BASE, headers={**HEADERS, "X-Service-Token": "x"}, json=CRM).status_code == 401


def test_rotate_and_delete(client):
    first = client.post(BASE, headers=HEADERS, json=CRM).json()["token"]
    second = client.post(f"{BASE}/crm/rotate-token", headers=HEADERS).json()["token"]
    assert second != first and mcp_client.agent_token_for("crm", "hrm") == second
    assert client.delete(f"{BASE}/crm", headers=HEADERS).status_code == 204
    assert registry.get("crm") is None
    assert client.delete(f"{BASE}/crm", headers=HEADERS).status_code == 404


def test_test_connection_uses_source_token(client, monkeypatch):
    token = client.post(BASE, headers=HEADERS, json=CRM).json()["token"]
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("x-agent-token"))
        method = __import__("json").loads(request.content)["method"]
        result = {"serverInfo": {"name": "svc-crm"}} if method == "initialize" else {"tools": [
            {"name": "crm_search_customers", "title": "Tìm khách hàng", "description": "Tìm khách hàng", "inputSchema": {}}]}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})

    real = httpx.AsyncClient
    monkeypatch.setattr(mcp_client.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    r = client.post(f"{BASE}/crm/test", headers=HEADERS).json()
    assert r["ok"] and r["toolCount"] == 1 and r["serverInfo"]["name"] == "svc-crm"
    assert set(seen) == {token}


def test_check_reports_auth_failures(client, monkeypatch):
    client.post(BASE, headers=HEADERS, json=CRM)

    def handler(request: httpx.Request) -> httpx.Response:  # server "lỏng": không kiểm token nào cả
        method = __import__("json").loads(request.content)["method"]
        result = {"capabilities": {"tools": {}}, "serverInfo": {"name": "x"}} if method == "initialize" else {"tools": []}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})

    from app.sources import checks
    real = httpx.AsyncClient
    monkeypatch.setattr(checks.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    rep = client.post(f"{BASE}/crm/check", headers=HEADERS).json()
    assert rep["ok"] is False and rep["fail"] >= 4
    failed = {i["check"] for i in rep["items"] if i["level"] == "fail"}
    assert "Thiếu X-Agent-Token bị từ chối" in failed and "JWT alg=none bị từ chối" in failed

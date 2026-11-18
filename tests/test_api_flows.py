"""Xác thực service token + quản trị flow (version, rollback, tenant) + catalog/registry."""
from tests.conftest import HEADERS
from tests.helpers import fake_mcp  # noqa: F401  (fixture)


def test_requires_valid_service_token(client):
    assert client.get("/v1/apps/hrm/flow", headers={**HEADERS, "X-Service-Token": "wrong"}).status_code == 401
    assert client.get("/v1/apps/crm/flow", headers=HEADERS).status_code == 403
    no_user = {k: v for k, v in HEADERS.items() if k != "X-User-Authorization"}
    assert client.get("/v1/apps/hrm/flow", headers=no_user).status_code == 401


def test_default_flow_then_save_versions_and_rollback(client):
    r = client.get("/v1/apps/hrm/flow", headers=HEADERS).json()
    assert r["isDefault"] and r["version"] is None and r["validation"]["valid"]
    doc = r["document"]
    doc["nodes"][1]["config"]["maxRounds"] = 2
    saved = client.put("/v1/apps/hrm/flow", headers=HEADERS, json={"document": doc, "note": "giảm vòng"}).json()
    assert saved["version"] == 1 and saved["updatedBy"] == "admin@test.vn"
    doc["nodes"][1]["config"]["maxRounds"] = 4
    assert client.put("/v1/apps/hrm/flow", headers=HEADERS, json={"document": doc}).json()["version"] == 2
    versions = client.get("/v1/apps/hrm/flow/versions", headers=HEADERS).json()["items"]
    assert [v["version"] for v in versions] == [2, 1] and versions[0]["active"]
    back = client.post("/v1/apps/hrm/flow/versions/1/activate", headers=HEADERS).json()
    assert back["version"] == 3 and back["document"]["nodes"][1]["config"]["maxRounds"] == 2
    reset = client.post("/v1/apps/hrm/flow/reset", headers=HEADERS).json()
    assert reset["version"] == 4 and reset["document"]["nodes"][1]["config"]["maxRounds"] == 3


def test_invalid_flow_rejected_with_node_errors(client):
    doc = client.get("/v1/apps/hrm/flow", headers=HEADERS).json()["document"]
    doc["edges"] = [e for e in doc["edges"] if e["id"] != "e_model_agent"]
    r = client.put("/v1/apps/hrm/flow", headers=HEADERS, json={"document": doc})
    assert r.status_code == 422
    errors = r.json()["detail"]["errors"]
    assert any(e["code"] == "missing_model" and e["node"] == "agent" for e in errors)
    assert client.post("/v1/apps/hrm/flow/validate", headers=HEADERS, json={"document": doc}).json()["valid"] is False


def test_tenant_isolation(client):
    doc = client.get("/v1/apps/hrm/flow", headers=HEADERS).json()["document"]
    client.put("/v1/apps/hrm/flow", headers=HEADERS, json={"document": doc})
    other = {**HEADERS, "X-Tenant-Id": "00000000-0000-0000-0000-000000000001"}
    assert client.get("/v1/apps/hrm/flow", headers=other).json()["isDefault"] is True


def test_secret_in_flow_never_returned(client):
    doc = client.get("/v1/apps/hrm/flow", headers=HEADERS).json()["document"]
    doc["nodes"].append({"id": "groq", "kind": "llm.groq", "config": {"apiKey": "gsk_secret", "model": "openai/gpt-oss-20b"}})
    doc["edges"].append({"id": "e_groq", "source": {"node": "groq", "port": "ai_model"}, "target": {"node": "agent", "port": "ai_model"}})
    r = client.put("/v1/apps/hrm/flow", headers=HEADERS, json={"document": doc})
    assert "gsk_secret" not in r.text
    again = client.get("/v1/apps/hrm/flow", headers=HEADERS).json()["document"]
    client.put("/v1/apps/hrm/flow", headers=HEADERS, json={"document": again})  # gửi lại '********' = giữ key
    from app.core.db import SessionLocal
    from app.flows.service import FlowService

    with SessionLocal() as db:
        stored = FlowService(db).active("hrm", HEADERS["X-Tenant-Id"]).document
    assert next(n for n in stored["nodes"] if n["id"] == "groq")["config"]["apiKey"] == "gsk_secret"


def test_catalog_and_registry(client, fake_mcp):  # noqa: F811
    cat = client.get("/v1/apps/hrm/catalog", headers=HEADERS).json()
    assert cat["format"] == "dns.agent-flow/v1"
    assert {k["kind"] for k in cat["nodeKinds"]} >= {"llm.groq", "llm.ollama", "tool.mcp", "agent.tools"}
    assert [s["key"] for s in cat["mcpServers"]] == ["hrm"]  # 'kho' chỉ dành cho app erp
    reg = client.get("/v1/apps/hrm/registry", headers=HEADERS).json()
    assert reg["servers"][0]["status"] == "ok"
    assert reg["servers"][0]["tools"][0]["permissions"] == ["app:leave_requests:read"]
    assert fake_mcp[-1]["auth"] == "Bearer user-jwt"  # JWT người xem được chuyển tiếp cho MCP
    assert client.get("/v1/apps/hrm/mcp/hrm/ping", headers=HEADERS).json()["ok"] is True
    assert client.get("/v1/apps/hrm/mcp/kho/ping", headers=HEADERS).json()["ok"] is False

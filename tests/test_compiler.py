import copy

from app.flows.compiler import compile_flow
from app.flows.defaults import default_flow
from app.flows.service import SECRET_MASK, mask_secrets, merge_secrets


def codes(res):
    return {i.code for i in res.errors}


def test_default_flow_is_valid_and_uses_tenant_model_and_hrm_mcp():
    res = compile_flow(default_flow("hrm"), "hrm")
    assert res.ok and not res.warnings
    plan = res.plan
    assert plan.channels == ["web", "mobile", "test"]
    assert [m.kind for m in plan.models] == ["llm.auto"]
    assert [(s.server, s.include) for s in plan.sources] == [("hrm", ["*"])]
    assert plan.history == 8 and plan.max_rounds == 3 and plan.keyword_preroute


def test_missing_required_nodes_and_model():
    doc = default_flow("hrm")
    doc["nodes"] = [n for n in doc["nodes"] if n["kind"] not in ("output.reply", "llm.auto")]
    doc["edges"] = [e for e in doc["edges"] if e["target"]["node"] != "reply" and e["source"]["node"] != "model"]
    res = compile_flow(doc, "hrm")
    assert "missing_node" in codes(res)


def test_agent_without_model_is_error():
    doc = default_flow("hrm")
    doc["edges"] = [e for e in doc["edges"] if e["id"] != "e_model_agent"]
    res = compile_flow(doc, "hrm")
    assert "missing_model" in codes(res)
    assert any(i.node == "agent" for i in res.errors)


def test_port_type_mismatch_rejected():
    doc = default_flow("hrm")
    doc["edges"].append({"id": "bad", "source": {"node": "mcp_main", "port": "ai_tool"}, "target": {"node": "agent", "port": "ai_model"}})
    res = compile_flow(doc, "hrm")
    assert "type_mismatch" in codes(res)


def test_unknown_or_foreign_mcp_server_rejected():
    doc = default_flow("hrm")
    doc["nodes"][-1]["config"]["server"] = "kho"  # chỉ app erp được dùng
    assert "server_forbidden" in codes(compile_flow(doc, "hrm"))
    doc["nodes"][-1]["config"]["server"] = "http://evil.example/mcp"
    assert "unknown_server" in codes(compile_flow(doc, "hrm"))


def test_disabled_tool_node_is_skipped_with_warning():
    doc = default_flow("hrm")
    doc["nodes"][-1]["disabled"] = True
    res = compile_flow(doc, "hrm")
    assert res.ok and res.plan.sources == []
    assert any(w.code == "no_tools" for w in res.warnings)


def test_orphan_node_warning_and_fallback_model_order():
    doc = default_flow("hrm")
    doc["nodes"].append({"id": "groq", "kind": "llm.groq", "name": "Groq dự phòng", "position": {"x": 0, "y": 0},
                         "config": {"model": "openai/gpt-oss-120b"}})
    res = compile_flow(doc, "hrm")
    assert any(w.code == "orphan" and w.node == "groq" for w in res.warnings)
    doc["edges"].append({"id": "e_groq", "source": {"node": "groq", "port": "ai_model"}, "target": {"node": "agent", "port": "ai_model"}})
    res = compile_flow(doc, "hrm")
    assert [m.kind for m in res.plan.models] == ["llm.auto", "llm.groq"]


def test_schema_errors_are_reported_not_raised():
    res = compile_flow({"format": "other/v9", "nodes": "x"}, "hrm")
    assert not res.ok and all(i.code == "schema" for i in res.errors)


def test_secret_is_masked_and_preserved_on_save():
    doc = default_flow("hrm")
    doc["nodes"].append({"id": "groq", "kind": "llm.groq", "config": {"apiKey": "gsk_real", "model": "openai/gpt-oss-20b"}})
    masked = mask_secrets(doc)
    assert next(n for n in masked["nodes"] if n["id"] == "groq")["config"]["apiKey"] == SECRET_MASK
    assert "gsk_real" not in str(masked)
    merged = merge_secrets(copy.deepcopy(masked), doc)
    assert next(n for n in merged["nodes"] if n["id"] == "groq")["config"]["apiKey"] == "gsk_real"

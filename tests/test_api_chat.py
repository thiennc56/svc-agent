"""Chat end-to-end: định tuyến từ khoá → MCP, tool calling, model dự phòng, kênh tắt, chạy thử bản nháp."""
from app.runtime.llm import LLMUnavailable
from tests.conftest import HEADERS
from tests.helpers import fake_mcp, sse, use_llm  # noqa: F401

GROQ = {"provider": "groq", "groqApiKey": "gsk_x", "groqModel": "openai/gpt-oss-20b"}
ASK_LEAVE = [{"role": "user", "content": "Tôi còn bao nhiêu ngày phép?"}]


def _flow(client):
    return client.get("/v1/apps/hrm/flow", headers=HEADERS).json()["document"]


def test_keyword_preroute_calls_mcp_and_streams(client, monkeypatch, fake_mcp):  # noqa: F811
    llm = use_llm(monkeypatch, [[{"message": {"content": "Bạn còn **9** ngày phép."}}]])
    body = {"messages": ASK_LEAVE, "channel": "web", "llm": GROQ,
            "context": {"user": "Lan", "role": "nhân viên", "linkLabels": {"/leave-registration": "Đăng ký nghỉ phép"}}}
    r = client.post("/v1/apps/hrm/chat", headers=HEADERS, json=body)
    assert r.status_code == 200
    events = sse(r)
    types = [e["type"] for e in events]
    assert types[0] == "meta" and "tool" in types and "token" in types and types[-1] == "done"
    assert any(e["type"] == "links" and e["items"][0]["label"] == "Đăng ký nghỉ phép" for e in events)
    call = next(c for c in fake_mcp if c["method"] == "tools/call")
    assert call["params"]["name"] == "get_my_leave_summary" and call["tenant"] == HEADERS["X-Tenant-Id"]
    target = llm.seen[0]["target"]
    assert (target.provider, target.model, target.api_key) == ("groq", "openai/gpt-oss-20b", "gsk_x")
    assert "Lan" in llm.seen[0]["messages"][0]["content"]


def test_tool_calling_round_filters_unknown_args(client, monkeypatch, fake_mcp):  # noqa: F811
    use_llm(monkeypatch, [
        [{"message": {"content": "", "tool_calls": [
            {"id": "c1", "function": {"name": "search_employee", "arguments": "{\"query\": \"Lan\", \"x\": 1}"}}]}}],
        [{"message": {"content": "Lan ở phòng Nhân sự."}}],
    ])
    body = {"messages": [{"role": "user", "content": "Lan làm ở đâu"}], "stream": False, "llm": GROQ}
    r = client.post("/v1/apps/hrm/chat", headers=HEADERS, json=body).json()
    assert r["content"] == "Lan ở phòng Nhân sự." and r["tools"] == ["search_employee"]
    call = next(c for c in fake_mcp if c["method"] == "tools/call")
    assert call["params"]["arguments"] == {"query": "Lan"}


def test_unknown_tool_from_model_is_refused(client, monkeypatch, fake_mcp):  # noqa: F811
    use_llm(monkeypatch, [
        [{"message": {"content": "", "tool_calls": [{"id": "c1", "function": {"name": "delete_everything", "arguments": "{}"}}]}}],
        [{"message": {"content": "Không có quyền."}}],
    ])
    body = {"messages": [{"role": "user", "content": "xoá hết"}], "stream": False, "llm": GROQ}
    r = client.post("/v1/apps/hrm/chat", headers=HEADERS, json=body).json()
    assert r["content"] == "Không có quyền."
    assert not any(c["method"] == "tools/call" for c in fake_mcp)


def test_fallback_model_used_when_primary_unavailable(client, monkeypatch, fake_mcp):  # noqa: F811
    doc = _flow(client)
    doc["nodes"].append({"id": "backup", "kind": "llm.ollama", "name": "Ollama",
                         "config": {"baseUrl": "http://o:11434", "model": "qwen2.5:7b"}})
    doc["edges"].append({"id": "e_backup", "source": {"node": "backup", "port": "ai_model"}, "target": {"node": "agent", "port": "ai_model"}})
    assert client.put("/v1/apps/hrm/flow", headers=HEADERS, json={"document": doc}).status_code == 200
    llm = use_llm(monkeypatch, [LLMUnavailable("down"), [{"message": {"content": "Xin chào"}}]])
    body = {"messages": [{"role": "user", "content": "chào bạn"}], "stream": False, "llm": GROQ}
    r = client.post("/v1/apps/hrm/chat", headers=HEADERS, json=body).json()
    assert r["content"] == "Xin chào" and r["model"] == "ollama:qwen2.5:7b"
    assert [s["target"].provider for s in llm.seen] == ["groq", "ollama"]


def test_channel_disabled_and_llm_down(client, monkeypatch, fake_mcp):  # noqa: F811
    doc = _flow(client)
    doc["nodes"][0]["config"]["channels"] = ["web"]
    client.put("/v1/apps/hrm/flow", headers=HEADERS, json={"document": doc})
    body = {"messages": [{"role": "user", "content": "hi"}], "channel": "mobile", "llm": GROQ}
    r = client.post("/v1/apps/hrm/chat", headers=HEADERS, json=body)
    assert r.status_code == 503 and r.json()["code"] == "assistant_channel_disabled"
    use_llm(monkeypatch, [LLMUnavailable("down")])
    r = client.post("/v1/apps/hrm/chat", headers=HEADERS, json={**body, "channel": "web"})
    assert r.status_code == 503 and r.json()["code"] == "llm_unavailable"


def test_draft_flow_without_sources_does_not_call_mcp(client, monkeypatch, fake_mcp):  # noqa: F811
    doc = _flow(client)
    doc["nodes"] = [n for n in doc["nodes"] if n["kind"] != "tool.mcp"]
    doc["edges"] = [e for e in doc["edges"] if e["id"] != "e_mcp_agent"]
    llm = use_llm(monkeypatch, [[{"message": {"content": "Không có dữ liệu"}}]])
    body = {"messages": ASK_LEAVE, "stream": False, "flow": doc, "llm": GROQ}
    r = client.post("/v1/apps/hrm/chat", headers=HEADERS, json=body).json()
    assert r["draft"] is True and r["tools"] == [] and llm.seen[0]["tools"] is None
    assert not any(c["method"] == "tools/call" for c in fake_mcp)


def test_tool_include_filter(client, monkeypatch, fake_mcp):  # noqa: F811
    doc = _flow(client)
    next(n for n in doc["nodes"] if n["kind"] == "tool.mcp")["config"]["include"] = ["search_employee"]
    client.put("/v1/apps/hrm/flow", headers=HEADERS, json={"document": doc})
    llm = use_llm(monkeypatch, [[{"message": {"content": "ok"}}], [{"message": {"content": "ok"}}]])
    body = {"messages": ASK_LEAVE, "stream": False, "llm": GROQ}
    r = client.post("/v1/apps/hrm/chat", headers=HEADERS, json=body).json()
    assert r["tools"] == []  # get_my_leave_summary bị loại khỏi flow → không định tuyến tới
    assert [t["function"]["name"] for t in llm.seen[0]["tools"]] == ["search_employee"]


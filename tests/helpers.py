import json

import pytest

from app.runtime import mcp_client

TOOLS = [
    {"name": "get_my_leave_summary", "title": "Ngày phép của tôi", "description": "Số ngày phép còn lại",
     "inputSchema": {"type": "object", "properties": {}},
     "x-dns": {"group": "Nghỉ phép", "keywords": [r"\bphep\b"], "priority": 50, "permissions": ["app:leave_requests:read"]}},
    {"name": "search_employee", "title": "Danh bạ", "description": "Tìm nhân viên",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
     "x-dns": {"keywords": [r"\bso dien thoai\b"], "queryArg": "query", "priority": 10}},
]


@pytest.fixture
def fake_mcp(monkeypatch):
    calls = []

    async def rpc(server, app, auth, method, params=None):
        calls.append({"server": server, "app": app, "method": method, "params": params,
                      "auth": auth.authorization, "tenant": auth.tenant_id})
        if method == "tools/list":
            return {"tools": TOOLS}
        if method == "tools/call":
            return {"structuredContent": {"remaining": 9, "link": {"web": "/leave-registration", "mobile": "/leave"}}}
        if method == "initialize":
            return {"serverInfo": {"name": "svc-hrm"}}
        return {}

    mcp_client._cache.clear()
    monkeypatch.setattr(mcp_client, "_rpc", rpc)
    return calls


class FakeLLM:
    def __init__(self, script):
        self.script, self.seen = script, []

    async def chat_stream(self, target, messages, tools=None):
        self.seen.append({"target": target, "messages": messages, "tools": tools})
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        for chunk in step:
            yield chunk


def use_llm(monkeypatch, script):
    fake = FakeLLM(script)
    monkeypatch.setattr("app.runtime.agent.client_for", lambda t: fake)
    return fake


def sse(resp):
    return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: {")]

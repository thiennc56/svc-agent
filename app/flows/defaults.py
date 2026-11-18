"""Flow mặc định: chatbot chạy giống hệt trước khi tách svc-agent.

Kênh chat → AI Agent (prompt + định tuyến từ khoá của app) → Trả lời
             ├─ Model doanh nghiệp (provider/key ở tab "AI & trợ lý")
             ├─ Nguồn MCP của app (mọi công cụ, phân hệ tự lọc theo quyền)
             └─ Bộ nhớ 8 tin nhắn
"""
from __future__ import annotations

from app.core.config import settings
from app.flows.catalog import FORMAT


def default_mcp_server(app: str) -> str:
    """MCP server mặc định của app: server trùng tên app, hoặc server đầu tiên khai báo app đó."""
    servers = settings.mcp_servers
    if app in servers:
        return app
    for key, meta in servers.items():
        if app in (meta.get("apps") or []):
            return key
    return ""


def default_flow(app: str) -> dict:
    server = default_mcp_server(app)
    title = (settings.mcp_servers.get(server) or {}).get("title") or server.upper() or "Nguồn dữ liệu"
    return {
        "format": FORMAT,
        "name": "Trợ lý mặc định",
        "description": "Luồng chuẩn: AI đọc câu hỏi, tra cứu dữ liệu qua MCP đúng quyền người hỏi rồi trả lời.",
        "nodes": [
            {"id": "trigger", "kind": "trigger.chat", "name": "Kênh chat", "position": {"x": 40, "y": 160},
             "config": {"channels": ["web", "mobile", "test"]}},
            {"id": "agent", "kind": "agent.tools", "name": "AI Agent", "position": {"x": 340, "y": 140},
             "config": {"systemPrompt": "", "maxRounds": 3, "maxToolCalls": 3, "keywordRouting": True, "keywordPreroute": True}},
            {"id": "reply", "kind": "output.reply", "name": "Trả lời", "position": {"x": 680, "y": 160},
             "config": {"includeLinks": True, "maxLinks": 4}},
            {"id": "model", "kind": "llm.auto", "name": "Model doanh nghiệp", "position": {"x": 200, "y": 400}, "config": {}},
            {"id": "memory", "kind": "memory.window", "name": "Bộ nhớ hội thoại", "position": {"x": 420, "y": 400},
             "config": {"size": 8}},
            {"id": "mcp_main", "kind": "tool.mcp", "name": title, "position": {"x": 640, "y": 400},
             "config": {"server": server, "include": ["*"], "maxResultChars": 3500}},
        ],
        "edges": [
            {"id": "e_trigger_agent", "source": {"node": "trigger", "port": "main"}, "target": {"node": "agent", "port": "main"}},
            {"id": "e_agent_reply", "source": {"node": "agent", "port": "main"}, "target": {"node": "reply", "port": "main"}},
            {"id": "e_model_agent", "source": {"node": "model", "port": "ai_model"}, "target": {"node": "agent", "port": "ai_model"}},
            {"id": "e_memory_agent", "source": {"node": "memory", "port": "ai_memory"}, "target": {"node": "agent", "port": "ai_memory"}},
            {"id": "e_mcp_agent", "source": {"node": "mcp_main", "port": "ai_tool"}, "target": {"node": "agent", "port": "ai_tool"}},
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }

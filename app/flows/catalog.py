"""Danh mục loại node (node kinds) – nguồn sự thật cho editor (bảng node bên phải) và compiler.

Định dạng flow chuẩn: `dns.agent-flow/v1` (xem docs/flow-format.md). Mỗi node: {id, kind, name, position, config}.
Cổng (port) có kiểu: `main` (luồng tin nhắn), `ai_model`, `ai_tool`, `ai_memory`. Cạnh chỉ hợp lệ khi cùng kiểu.
"""
from __future__ import annotations

FORMAT = "dns.agent-flow/v1"

# Danh mục nhóm (thứ tự hiển thị trong bảng node)
CATEGORIES = [
    {"key": "trigger", "label": "Kích hoạt"},
    {"key": "agent", "label": "AI Agent"},
    {"key": "model", "label": "Mô hình AI"},
    {"key": "tool", "label": "Nguồn dữ liệu (MCP)"},
    {"key": "memory", "label": "Bộ nhớ"},
    {"key": "output", "label": "Đầu ra"},
]

_AI_TAB = "tab \"AI & trợ lý\""

# Kiểu field cấu hình cho form động: text | textarea | number | boolean | select | multiselect | secret | tools
NODE_KINDS: list[dict] = [
    {
        "kind": "trigger.chat", "category": "trigger", "label": "Kênh chat", "icon": "pi pi-comments", "color": "#0ea5e9",
        "description": "Điểm vào: tin nhắn từ widget web, trang Trợ lý trên app mobile hoặc ô Thử trợ lý.",
        "inputs": [], "outputs": [{"name": "main", "type": "main"}], "max": 1, "required": True,
        "fields": [
            {"key": "channels", "label": "Kênh nhận tin", "type": "multiselect", "default": ["web", "mobile", "test"],
             "options": [{"value": "web", "label": "Web"}, {"value": "mobile", "label": "Mobile"},
                         {"value": "test", "label": "Thử trợ lý"}]},
        ],
    },
    {
        "kind": "agent.tools", "category": "agent", "label": "AI Agent", "icon": "pi pi-sparkles", "color": "#8b5cf6",
        "description": "Bộ não: đọc câu hỏi, chọn công cụ MCP phù hợp (đúng quyền người hỏi), tổng hợp câu trả lời.",
        "inputs": [
            {"name": "main", "type": "main"},
            {"name": "ai_model", "type": "ai_model", "label": "Model", "required": True, "max": 2},
            {"name": "ai_tool", "type": "ai_tool", "label": "Dữ liệu"},
            {"name": "ai_memory", "type": "ai_memory", "label": "Bộ nhớ", "max": 1},
        ],
        "outputs": [{"name": "main", "type": "main"}], "max": 1, "required": True,
        "fields": [
            {"key": "systemPrompt", "label": "Chỉ dẫn hệ thống (system prompt)", "type": "textarea", "default": "",
             "help": "Biến: {user}, {role}, {today}. Để trống = dùng chỉ dẫn mặc định của ứng dụng."},
            {"key": "maxRounds", "label": "Số vòng gọi công cụ tối đa", "type": "number", "default": 3, "min": 1, "max": 6},
            {"key": "maxToolCalls", "label": "Số công cụ tối đa mỗi vòng", "type": "number", "default": 3, "min": 1, "max": 6},
            {"key": "keywordRouting", "label": "Định tuyến theo từ khoá (model nhỏ hay bỏ qua công cụ)", "type": "boolean", "default": True},
            {"key": "keywordPreroute", "label": "Tra cứu trước khi hỏi AI khi khớp từ khoá (nhanh hơn 1 vòng)", "type": "boolean", "default": True},
        ],
    },
]

NODE_KINDS += [
    {
        "kind": "llm.auto", "category": "model", "label": "Model doanh nghiệp", "icon": "pi pi-building", "color": "#10b981",
        "description": f"Dùng provider/model/API key đã cấu hình ở {_AI_TAB} (theo tenant). Khuyến nghị.",
        "inputs": [], "outputs": [{"name": "ai_model", "type": "ai_model"}],
        "fields": [],
    },
    {
        "kind": "llm.groq", "category": "model", "label": "Groq", "icon": "pi pi-bolt", "color": "#f97316",
        "description": "Groq cloud (OpenAI-compatible, rất nhanh, hỗ trợ gọi công cụ).",
        "inputs": [], "outputs": [{"name": "ai_model", "type": "ai_model"}],
        "fields": [
            {"key": "model", "label": "Model", "type": "select", "default": "openai/gpt-oss-20b", "allowCustom": True,
             "options": [{"value": "openai/gpt-oss-20b", "label": "openai/gpt-oss-20b (khuyến nghị)"},
                         {"value": "openai/gpt-oss-120b", "label": "openai/gpt-oss-120b"},
                         {"value": "llama-3.3-70b-versatile", "label": "llama-3.3-70b-versatile"}]},
            {"key": "apiKey", "label": "API key", "type": "secret", "default": "",
             "help": f"Để trống = dùng key Groq đã lưu ở {_AI_TAB}."},
            {"key": "temperature", "label": "Temperature", "type": "number", "default": 0.2, "min": 0, "max": 2, "step": 0.1},
            {"key": "maxTokens", "label": "Số token trả lời tối đa", "type": "number", "default": 1024, "min": 64, "max": 8192},
        ],
    },
    {
        "kind": "llm.ollama", "category": "model", "label": "Ollama", "icon": "pi pi-server", "color": "#64748b",
        "description": "Model tự host trong mạng nội bộ (dữ liệu không ra ngoài).",
        "inputs": [], "outputs": [{"name": "ai_model", "type": "ai_model"}],
        "fields": [
            {"key": "baseUrl", "label": "Base URL", "type": "text", "default": "", "placeholder": "http://ollama:11434",
             "help": f"Để trống = dùng URL Ollama ở {_AI_TAB}."},
            {"key": "model", "label": "Model", "type": "text", "default": "", "placeholder": "qwen2.5:7b",
             "help": f"Để trống = dùng model Ollama ở {_AI_TAB}."},
            {"key": "temperature", "label": "Temperature", "type": "number", "default": 0.2, "min": 0, "max": 2, "step": 0.1},
            {"key": "numCtx", "label": "numCtx", "type": "number", "default": 4096, "min": 256, "max": 32768},
            {"key": "numPredict", "label": "numPredict", "type": "number", "default": 512, "min": 16, "max": 4096},
        ],
    },
    {
        "kind": "tool.mcp", "category": "tool", "label": "Nguồn MCP", "icon": "pi pi-database", "color": "#2563eb",
        "description": "Kết nối một phân hệ (HRM, Kho, CRM, Bán hàng, Dự án…) qua giao thức MCP. Phân hệ tự kiểm quyền người hỏi.",
        "inputs": [], "outputs": [{"name": "ai_tool", "type": "ai_tool"}],
        "fields": [
            {"key": "server", "label": "Máy chủ MCP", "type": "select", "default": "", "options": "mcpServers"},
            {"key": "include", "label": "Công cụ được dùng", "type": "tools", "default": ["*"],
             "help": "* = tất cả công cụ của nguồn (kể cả công cụ phân hệ bổ sung sau). Bỏ chọn để không cho AI dùng."},
            {"key": "maxResultChars", "label": "Giới hạn ký tự kết quả gửi cho AI", "type": "number", "default": 3500, "min": 500, "max": 12000},
        ],
    },
    {
        "kind": "memory.window", "category": "memory", "label": "Bộ nhớ hội thoại", "icon": "pi pi-history", "color": "#a855f7",
        "description": "Giữ N tin nhắn gần nhất của cuộc hội thoại làm ngữ cảnh (không nối = 8).",
        "inputs": [], "outputs": [{"name": "ai_memory", "type": "ai_memory"}],
        "fields": [{"key": "size", "label": "Số tin nhắn", "type": "number", "default": 8, "min": 1, "max": 20}],
    },
    {
        "kind": "output.reply", "category": "output", "label": "Trả lời", "icon": "pi pi-send", "color": "#16a34a",
        "description": "Trả câu trả lời (Markdown) về kênh, kèm nút mở màn hình liên quan.",
        "inputs": [{"name": "main", "type": "main"}], "outputs": [], "max": 1, "required": True,
        "fields": [
            {"key": "includeLinks", "label": "Gắn nút mở màn hình liên quan", "type": "boolean", "default": True},
            {"key": "maxLinks", "label": "Số nút tối đa", "type": "number", "default": 4, "min": 0, "max": 8},
        ],
    },
]

KINDS: dict[str, dict] = {k["kind"]: k for k in NODE_KINDS}
LLM_KINDS = {"llm.auto", "llm.groq", "llm.ollama"}
PORT_TYPES = ("main", "ai_model", "ai_tool", "ai_memory")


def defaults_for(kind: str) -> dict:
    spec = KINDS.get(kind) or {}
    return {f["key"]: f.get("default") for f in spec.get("fields", [])}


def port(kind: str, side: str, name: str) -> dict | None:
    spec = KINDS.get(kind) or {}
    return next((p for p in spec.get("inputs" if side == "in" else "outputs", []) if p["name"] == name), None)


def public_catalog() -> dict:
    return {"format": FORMAT, "categories": CATEGORIES, "nodeKinds": NODE_KINDS, "portTypes": list(PORT_TYPES)}


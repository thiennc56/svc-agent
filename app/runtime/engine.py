"""Chạy flow đã biên dịch: AI Agent (tool calling qua MCP) – streaming events.

Events: {type: tool|token|links|error|done}. Giữ tương thích với event của svc-hrm cũ (web/mobile không đổi).
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date
from typing import AsyncIterator

from app.flows.compiler import Plan
from app.runtime.llm import LLMTarget, LLMUnavailable, client_for
from app.runtime.mcp_client import McpTool, call_tool
from app.runtime.routing import fallback_args, route
from app.runtime.think_filter import ThinkFilter, strip_think

logger = logging.getLogger("svc_agent.engine")
MAX_CONTENT = 2000

DEFAULT_PROMPT = (
    "Bạn là trợ lý nội bộ của doanh nghiệp. Luôn trả lời ngắn gọn bằng tiếng Việt, dùng gạch đầu dòng khi liệt kê. "
    "Người hỏi: {user} – vai trò: {role}. "
    "Chỉ dùng số liệu lấy từ công cụ; tuyệt đối không bịa số, tên người hay đường dẫn. "
    "Chỉ được tra cứu bằng các công cụ đã cung cấp – đó là phạm vi quyền của người hỏi; "
    "nếu câu hỏi vượt quyền hoặc không có công cụ phù hợp, nói rõ là bạn không có quyền/không có dữ liệu. "
    "Nếu kết quả công cụ có trường error/message thì giải thích đúng nội dung message đó cho người hỏi. "
    "Không chép JSON, không in đường dẫn: hệ thống sẽ tự gắn nút mở màn hình liên quan dưới câu trả lời. "
    "Hôm nay là {today}."
)


@dataclass
class RunContext:
    app: str
    auth: object  # UserAuth
    user: str = ""
    role: str = "người dùng"
    app_prompt: str = ""  # prompt mặc định do app gửi (flow để trống systemPrompt)
    link_labels: dict = field(default_factory=dict)
    channel: str = ""  # web | mobile | test | workflow – ghi audit


def render_prompt(template: str, ctx: RunContext) -> str:
    values = {"user": ctx.user or "người dùng", "role": ctx.role, "today": date.today().isoformat()}
    out = template
    for k, v in values.items():
        out = out.replace("{" + k + "}", v)
    return out


def build_messages(history: list[dict], prompt: str, limit: int) -> list[dict]:
    msgs = [{"role": "system", "content": prompt}]
    for m in history[-limit:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            msgs.append({"role": m["role"], "content": str(m["content"])[:MAX_CONTENT]})
    return msgs


def compact(data, limit: int) -> str:
    return json.dumps(_strip_links(data), ensure_ascii=False, separators=(",", ":"), default=str)[:limit]


def _strip_links(value):
    if isinstance(value, dict):
        return {k: _strip_links(v) for k, v in value.items() if k != "link"}
    if isinstance(value, list):
        return [_strip_links(v) for v in value]
    return value


def collect_links(result, out: list[dict], labels: dict, limit: int) -> None:
    """Gom {web, mobile} trong kết quả công cụ → nút mở màn hình (không trùng)."""
    if isinstance(result, dict):
        lk = result.get("link")
        name = result.get("name") or result.get("employee")
        if isinstance(lk, dict) and lk.get("web") and len(out) < limit and all(o["web"] != lk["web"] for o in out):
            label = lk.get("label") or (name if name and "/employee" in lk["web"] else labels.get(lk["web"], "Mở chi tiết"))
            out.append({"web": lk["web"], "mobile": lk.get("mobile") or lk["web"], "label": label})
        for v in result.values():
            if isinstance(v, (dict, list)):
                collect_links(v, out, labels, limit)
    elif isinstance(result, list):
        for v in result[:5]:
            collect_links(v, out, labels, limit)

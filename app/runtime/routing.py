"""Định tuyến theo từ khoá (cho model nhỏ hay bỏ qua tool call).

Không còn hard-code theo HRM: mỗi công cụ MCP tự khai báo `x-dns.keywords` (regex trên chuỗi đã bỏ dấu, thứ tự ưu tiên
`x-dns.priority` nhỏ hơn = ưu tiên hơn) và `x-dns.queryArg` (tham số nhận phần tên/từ khoá trích từ câu hỏi).
"""
from __future__ import annotations

import re
import unicodedata

from app.runtime.mcp_client import McpTool


def norm(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").lower()).replace("đ", "d")
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def route(question: str, tools: list[McpTool]) -> McpTool | None:
    q = norm(question)
    ranked = sorted(
        (t for t in tools if t.meta.get("keywords")),
        key=lambda t: (int(t.meta.get("priority", 100)), t.name),
    )
    for t in ranked:
        for pattern in t.meta.get("keywords") or []:
            try:
                if re.search(pattern, q):
                    return t
            except re.error:
                continue
    return None


_STOP = {"tim", "tra", "cuu", "so", "dien", "thoai", "sdt", "email", "cua", "nhan", "vien", "cho", "toi", "thong", "tin",
         "phong", "ban", "giup", "xem", "la", "gi", "nao", "o", "dau", "anh", "chi", "hay", "voi", "lien", "he",
         "ho", "ve", "mot", "chuc", "quan", "ly", "hop", "dong", "bo", "phan"}


def extract_query(question: str) -> str:
    words = re.findall(r"[\w@.+]+", question or "")
    return " ".join(w for w in words if norm(w) not in _STOP)[:80]


def fallback_args(tool: McpTool, question: str) -> dict:
    arg = tool.meta.get("queryArg")
    return {arg: extract_query(question)} if arg else {}

"""LLM clients (streaming). Chuẩn hoá mọi provider về dạng chunk Ollama: {"message": {"content", "tool_calls"}}.

LLMTarget = cấu hình cuối cùng của 1 model trong flow (đã ghép node + cấu hình tenant do app gửi).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import AsyncIterator

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMUnavailable(Exception):
    pass


@dataclass
class LLMTarget:
    provider: str  # groq | ollama
    model: str
    temperature: float = 0.2
    max_tokens: int = 512
    num_ctx: int = 4096
    base_url: str = ""
    api_key: str = ""
    node: str = ""

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"


def _keep_alive():
    v = settings.ollama_keep_alive
    try:
        return int(v)
    except ValueError:
        return v


class OllamaClient:
    """Async client for Ollama /api/chat (streaming NDJSON)."""

    async def chat_stream(self, t: LLMTarget, messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[dict]:
        if not t.base_url:
            raise LLMUnavailable("Ollama base URL chưa được cấu hình")
        body = {
            "model": t.model, "messages": messages, "stream": True, "think": False, "keep_alive": _keep_alive(),
            "options": {"num_ctx": t.num_ctx, "num_predict": t.max_tokens, "temperature": t.temperature},
        }
        if tools:
            body["tools"] = tools
        timeout = httpx.Timeout(settings.llm_timeout_seconds, connect=5.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", f"{t.base_url.rstrip('/')}/api/chat", json=body) as resp:
                    if resp.status_code >= 400:
                        detail = (await resp.aread()).decode("utf-8", "ignore")[:200]
                        raise LLMUnavailable(f"Ollama HTTP {resp.status_code}: {detail}")
                    async for line in resp.aiter_lines():
                        if line.strip():
                            yield json.loads(line)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
            raise LLMUnavailable(str(exc) or type(exc).__name__) from exc


def to_openai_message(m: dict) -> dict:
    """Ollama-style history → OpenAI chat format (tool_calls with ids, tool results with tool_call_id)."""
    role = m.get("role")
    if role == "assistant" and m.get("tool_calls"):
        return {"role": "assistant", "content": m.get("content") or None, "tool_calls": [
            {"id": c.get("id") or f"call_{i}", "type": "function",
             "function": {"name": (c.get("function") or {}).get("name", ""),
                          "arguments": _args_str((c.get("function") or {}).get("arguments"))}}
            for i, c in enumerate(m["tool_calls"])
        ]}
    if role == "tool":
        return {"role": "tool", "tool_call_id": m.get("tool_call_id") or "call_0", "content": m.get("content") or ""}
    return {"role": role, "content": m.get("content") or ""}


def _args_str(args) -> str:
    if isinstance(args, str):
        return args or "{}"
    return json.dumps(args or {}, ensure_ascii=False)


_ollama = OllamaClient()


def client_for(t: LLMTarget):
    from app.runtime.llm_groq import GROQ

    return GROQ if t.provider == "groq" else _ollama

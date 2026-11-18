"""Groq OpenAI-compatible /chat/completions (SSE) → chunk dạng Ollama."""
from __future__ import annotations

import json
from typing import AsyncIterator

import httpx

from app.core.config import settings
from app.runtime.llm import LLMTarget, LLMUnavailable, to_openai_message

DEFAULT_BASE = "https://api.groq.com/openai/v1"


class GroqClient:
    async def chat_stream(self, t: LLMTarget, messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[dict]:
        if not t.api_key:
            raise LLMUnavailable("Groq API key chưa được cấu hình")
        body = {
            "model": t.model, "messages": [to_openai_message(m) for m in messages], "stream": True,
            "temperature": t.temperature,
            "max_completion_tokens": max(t.max_tokens, 512),  # gpt-oss tiêu tốn token cho reasoning
        }
        if t.model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"
            body["include_reasoning"] = False
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        headers = {"Authorization": f"Bearer {t.api_key}", "Content-Type": "application/json"}
        base = (t.base_url or DEFAULT_BASE).rstrip("/")
        timeout = httpx.Timeout(settings.llm_timeout_seconds, connect=10.0)
        calls: dict[int, dict] = {}
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", f"{base}/chat/completions", json=body, headers=headers) as resp:
                    if resp.status_code >= 400:
                        detail = (await resp.aread()).decode("utf-8", "ignore")[:300]
                        raise LLMUnavailable(f"Groq HTTP {resp.status_code}: {detail}")
                    async for line in resp.aiter_lines():
                        chunk = _parse(line)
                        if chunk is None:
                            continue
                        if chunk == "DONE":
                            break
                        for choice in chunk.get("choices") or []:
                            delta = choice.get("delta") or {}
                            for tc in delta.get("tool_calls") or []:
                                slot = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "arguments": ""})
                                slot["id"] = tc.get("id") or slot["id"]
                                fn = tc.get("function") or {}
                                slot["name"] += fn.get("name") or ""
                                slot["arguments"] += fn.get("arguments") or ""
                            if delta.get("content"):
                                yield {"message": {"content": delta["content"]}}
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
            raise LLMUnavailable(str(exc) or type(exc).__name__) from exc
        if calls:
            yield {"message": {"content": "", "tool_calls": [
                {"id": c["id"], "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}} for _, c in sorted(calls.items())
            ]}}


def _parse(line: str):
    line = line.strip()
    if not line.startswith("data:"):
        return None
    data = line[5:].strip()
    if data == "[DONE]":
        return "DONE"
    try:
        return json.loads(data)
    except ValueError:
        return None


GROQ = GroqClient()

"""AI Agent: một lượt chat với tool calling qua MCP + model dự phòng + định tuyến từ khoá."""
from __future__ import annotations

import json
import logging
import time
from typing import AsyncIterator

from app.flows.compiler import Plan
from app.runtime.engine import DEFAULT_PROMPT, RunContext, build_messages, collect_links, compact, render_prompt
from app.runtime.llm import LLMTarget, LLMUnavailable, client_for
from app.runtime.mcp_client import McpTool, call_tool
from app.runtime.routing import fallback_args, route
from app.runtime.think_filter import ThinkFilter, strip_think

logger = logging.getLogger("svc_agent.agent")


class Agent:
    """`tools` = công cụ MCP đã lọc theo flow + quyền người hỏi; `targets` = model theo thứ tự ưu tiên."""

    def __init__(self, plan: Plan, ctx: RunContext, tools: list[McpTool], targets: list[LLMTarget], limits: dict[str, int]):
        self.plan, self.ctx, self.tools, self.targets = plan, ctx, tools, targets
        self.by_name = {t.name: t for t in tools}
        self.limits = limits  # tool name → maxResultChars của nguồn
        self.links: list[dict] = []
        self.called: list[str] = []
        self.model_used = targets[0].label if targets else ""

    async def stream(self, messages: list[dict], tools: list[dict] | None) -> AsyncIterator[dict]:
        """Thử model chính → dự phòng; chỉ chuyển model khi lỗi xảy ra TRƯỚC chunk đầu tiên."""
        if not self.targets:
            raise LLMUnavailable("Chưa cấu hình mô hình AI")
        for i, t in enumerate(self.targets):
            got = False
            try:
                async for chunk in client_for(t).chat_stream(t, messages, tools):
                    got = True
                    self.model_used = t.label
                    yield chunk
                return
            except LLMUnavailable as exc:
                if got or i == len(self.targets) - 1:
                    raise
                logger.warning("llm %s unavailable, falling back: %s", t.label, exc)

    async def run_tool(self, name: str, args: dict) -> dict:
        tool = self.by_name.get(name)
        if tool is None:
            return {"error": "not_permitted_or_unknown_tool"}
        props = (tool.input_schema or {}).get("properties") or {}
        args = {k: v for k, v in (args or {}).items() if k in props}
        result = await call_tool(tool.server, self.ctx.app, self.ctx.auth, name, args)
        if self.plan.include_links:
            collect_links(result, self.links, self.ctx.link_labels, self.plan.max_links)
        return result

    def _lookup_msg(self, tool: McpTool, result: dict, question: str) -> dict:
        data = compact(result, self.limits.get(tool.name, 3500))
        return {"role": "user", "content": f"Thông tin tra cứu ({tool.name}), chỉ dùng để trả lời, không chép lại JSON: "
                                           f"{data}\n\nCâu hỏi: {question}\nTrả lời ngắn gọn bằng câu tiếng Việt."}

    async def _fallback(self, tool: McpTool, question: str) -> AsyncIterator[dict]:
        self.called.append(tool.name + "*")
        yield {"type": "tool", "name": tool.name, "fallback": True}
        result = await self.run_tool(tool.name, fallback_args(tool, question))
        yield {"type": "_lookup", "message": self._lookup_msg(tool, result, question)}

    async def _tool_calls(self, calls: list[dict], messages: list[dict]) -> AsyncIterator[dict]:
        messages.append({"role": "assistant", "content": "", "tool_calls": calls})
        for call in calls[: self.plan.max_tool_calls]:
            fn = call.get("function") or {}
            name, args = fn.get("name", ""), fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            self.called.append(name)
            yield {"type": "tool", "name": name}
            result = await self.run_tool(name, args if isinstance(args, dict) else {})
            messages.append({"role": "tool", "tool_name": name, "tool_call_id": call.get("id") or "",
                             "content": compact(result, self.limits.get(name, 3500))})

    async def run(self, history: list[dict]) -> AsyncIterator[dict]:
        """Events: tool | token | links | done (giống svc-hrm cũ → web/mobile không đổi)."""
        started = time.perf_counter()
        plan = self.plan
        schemas = [t.schema() for t in self.tools]
        question = next((m.get("content", "") for m in reversed(history) if m.get("role") == "user"), "")
        fallback = route(question, self.tools) if plan.keyword_routing else None
        prompt = render_prompt(plan.system_prompt or self.ctx.app_prompt or DEFAULT_PROMPT, self.ctx)
        messages = build_messages(history, prompt, plan.history)
        used_fallback = False
        first_token_ms = None

        if fallback and plan.keyword_preroute:
            used_fallback = True
            async for ev in self._fallback(fallback, question):
                if ev["type"] == "_lookup":
                    messages[-1] = ev["message"]
                else:
                    yield ev

        for rnd in range(plan.max_rounds):
            offer = schemas if (schemas and rnd < plan.max_rounds - 1 and not used_fallback) else None
            # Model có thể trả lời "không biết" thay vì gọi công cụ → giữ lại, nếu cần sẽ chạy công cụ theo từ khoá
            buffer_mode = bool(fallback) and not self.called and offer is not None
            buffered: list[str] = []
            calls: list[dict] = []
            filt = ThinkFilter()
            async for chunk in self.stream(messages, offer):
                msg = chunk.get("message") or {}
                if msg.get("tool_calls"):
                    calls.extend(msg["tool_calls"])
                text = filt.feed(msg.get("content") or "")
                if not text:
                    continue
                if buffer_mode or calls:
                    buffered.append(text)
                else:
                    first_token_ms = first_token_ms or int((time.perf_counter() - started) * 1000)
                    yield {"type": "token", "content": text}
            tail = filt.flush()
            if tail:
                if buffer_mode or calls:
                    buffered.append(tail)
                else:
                    yield {"type": "token", "content": tail}

            if calls:
                async for ev in self._tool_calls(calls, messages):
                    yield ev
                continue
            if fallback and not self.called:
                used_fallback = True
                async for ev in self._fallback(fallback, question):
                    if ev["type"] == "_lookup":
                        messages.append(ev["message"])
                    else:
                        yield ev
                continue
            text = strip_think("".join(buffered))
            if text:
                first_token_ms = first_token_ms or int((time.perf_counter() - started) * 1000)
                yield {"type": "token", "content": text}
            break

        if self.links:
            yield {"type": "links", "items": self.links}
        total_ms = int((time.perf_counter() - started) * 1000)
        logger.info("agent chat app=%s q=%r tools=%s first_token_ms=%s total_ms=%s model=%s",
                    self.ctx.app, question[:120], self.called, first_token_ms, total_ms, self.model_used)
        yield {"type": "done", "tools": self.called, "latency_ms": total_ms, "first_token_ms": first_token_ms,
               "model": self.model_used, "links": self.links}


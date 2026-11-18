"""POST /v1/apps/{app}/chat – chạy flow đang hoạt động (hoặc bản nháp) cho 1 lượt chat. SSE hoặc JSON."""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.api.schemas import AgentChatRequest
from app.core.db import get_db
from app.core.security import UserAuth, require_app, user_auth
from app.flows.compiler import compile_flow
from app.flows.service import FlowService, merge_secrets
from app.runtime.agent import Agent
from app.runtime.engine import RunContext
from app.runtime.llm import LLMUnavailable
from app.runtime.resolve import model_targets, resolve_tools

logger = logging.getLogger("svc_agent.chat")
router = APIRouter(prefix="/v1/apps/{app}", tags=["Chat"])

UNAVAILABLE_MSG = "Trợ lý AI tạm thời không khả dụng (không kết nối được máy chủ mô hình). Vui lòng thử lại sau."
CHANNEL_OFF_MSG = "Trợ lý AI chưa được bật trên kênh này (web/mobile)."
FLOW_INVALID_MSG = "Luồng trợ lý (flow) đang lỗi cấu hình. Quản trị viên vui lòng kiểm tra tại Cấu hình Chatbot."


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _error(status: int, code: str, detail: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail, "code": code, **extra})


@router.post("/chat")
async def chat(body: AgentChatRequest, app: str = Depends(require_app), auth: UserAuth = Depends(user_auth),
               db: Session = Depends(get_db)):
    service = FlowService(db)
    active_doc, version = service.active_document(app, auth.tenant_id)
    doc = merge_secrets(body.flow, active_doc) if body.flow is not None else active_doc
    compiled = compile_flow(doc, app)
    if not compiled.ok:
        logger.warning("flow invalid app=%s tenant=%s errors=%s", app, auth.tenant_id, [e.code for e in compiled.errors])
        return _error(503, "flow_invalid", FLOW_INVALID_MSG, **compiled.report())
    plan = compiled.plan
    if body.channel and body.channel not in plan.channels:
        return _error(503, "assistant_channel_disabled", CHANNEL_OFF_MSG)

    llm = body.llm.model_dump()
    targets = model_targets(plan.models, llm)
    tools, limits, problems = await resolve_tools(plan, app, auth)
    ctx = RunContext(app=app, auth=auth, user=body.context.user, role=body.context.role,
                     app_prompt=body.context.systemPrompt, link_labels=body.context.linkLabels)
    agent = Agent(plan, ctx, tools, targets, limits)
    history = [m.model_dump() for m in body.messages]
    meta = {"flowVersion": version, "draft": body.flow is not None, "sourceErrors": problems}

    if body.stream:
        events = agent.run(history)
        try:  # lấy event đầu sớm → model không kết nối được thì trả 503 sạch thay vì stream lỗi
            first = await events.__anext__()
        except LLMUnavailable as exc:
            logger.warning("llm unavailable app=%s: %s", app, exc)
            return _error(503, "llm_unavailable", UNAVAILABLE_MSG)
        except StopAsyncIteration:
            first = None

        async def gen():
            yield _sse({"type": "meta", **meta})
            if first:
                yield _sse(first)
            try:
                async for ev in events:
                    yield _sse(ev)
            except LLMUnavailable:
                yield _sse({"type": "error", "message": UNAVAILABLE_MSG})
            except asyncio.CancelledError:
                raise
            yield "data: [DONE]\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    parts, done = [], {}
    try:
        async for ev in agent.run(history):
            if ev["type"] == "token":
                parts.append(ev["content"])
            elif ev["type"] == "done":
                done = ev
    except LLMUnavailable as exc:
        logger.warning("llm unavailable app=%s: %s", app, exc)
        return _error(503, "llm_unavailable", UNAVAILABLE_MSG)
    return {"content": "".join(parts).strip(), "tools": done.get("tools", []), "latency_ms": done.get("latency_ms", 0),
            "model": done.get("model", ""), "links": done.get("links", []), **meta}

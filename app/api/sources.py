"""Quản trị nguồn MCP động (màn "Nguồn MCP" trong HRM). App gọi (svc-hrm) đã kiểm quyền QUẢN TRỊ NỀN TẢNG trước khi proxy.

- Token X-Agent-Token sinh tự động, mã hoá at-rest, chỉ trả về **1 lần** (tạo / xoay) để bàn giao cho đội phân hệ.
- URL phải thuộc MCP_ALLOWED_HOSTS (chống SSRF); nguồn khai báo ở ConfigMap chỉ đọc.
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.security import UserAuth, actor, require_app, service_token_for, user_auth
from app.runtime import mcp_client
from app.sources import registry
from app.sources.checks import run_check
from app.sources.crypto import CredentialKeyMissing, decrypt, encrypt, new_token
from app.sources.models import AgentMcpSource

router = APIRouter(prefix="/v1/apps/{app}/sources", tags=["MCP sources"])
KEY_PATTERN = r"^[a-z][a-z0-9_-]{1,39}$"


class SourceIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=300)
    icon: str = Field(default="pi pi-database", pattern=r"^pi pi-[a-z0-9-]{1,40}$")
    color: str = Field(default="#2563eb", pattern=r"^#[0-9a-fA-F]{6}$")
    url: str = Field(min_length=8, max_length=300)
    apps: list[str] = Field(default_factory=list, max_length=20)
    enabled: bool = True
    timeoutSeconds: int = Field(default=20, ge=2, le=60)
    # Giai đoạn C: chỉ hiện công cụ được cấp quyền mcp:<key>:<tool> trong HRM (khuyến nghị bật)
    requireGrant: bool = True
    # Chuyển tiếp JWT SOPBase người hỏi (tương thích phân hệ làm theo hướng dẫn v1.1). Tắt khi phân hệ đã verify X-Agent-Context.
    forwardUserJwt: bool = True


class SourceCreate(SourceIn):
    key: str = Field(pattern=KEY_PATTERN)


def _public(s: AgentMcpSource | None, key: str, meta: dict) -> dict:
    """Không bao giờ trả token – chỉ 4 ký tự cuối để đối chiếu."""
    return {
        "key": key, "title": meta.get("title") or key, "description": meta.get("description") or "",
        "icon": meta.get("icon") or "pi pi-database", "color": meta.get("color") or "#2563eb", "url": meta.get("url") or "",
        "apps": list(meta.get("apps") or []), "enabled": bool(meta.get("enabled", True)),
        "timeoutSeconds": int(meta.get("timeout") or settings.mcp_timeout_seconds),
        "source": meta.get("source", "db"), "editable": meta.get("source") == "db",
        "requireGrant": bool(meta.get("require_grant", False)), "forwardUserJwt": bool(meta.get("forward_user_jwt", True)),
        "hasToken": bool(s and s.token_enc) or key in settings.mcp_tokens,
        "tokenHint": (s.token_hint if s else None), "updatedBy": s.updated_by if s else None,
        "updatedAt": s.updated_at.isoformat() if s and s.updated_at else None,
    }


def _validate(body: SourceIn) -> None:
    if reason := registry.check_url(body.url):
        raise HTTPException(status_code=422, detail={"field": "url", "message": reason})
    for a in body.apps:
        if a not in settings.service_tokens and not settings.is_dev:
            raise HTTPException(status_code=422, detail={"field": "apps", "message": f"Ứng dụng '{a}' chưa đăng ký với svc-agent"})


def _row(db: Session, key: str) -> AgentMcpSource:
    row = db.get(AgentMcpSource, key)
    if row is None:
        if key in settings.mcp_servers:
            raise HTTPException(status_code=409, detail="Nguồn khai báo ở ConfigMap (MCP_SERVERS) – sửa qua hạ tầng, không sửa ở đây")
        raise HTTPException(status_code=404, detail="Không tìm thấy nguồn MCP")
    return row


def _changed() -> None:
    registry.invalidate()
    mcp_client._cache.clear()


@router.get("")
def list_sources(app: str = Depends(require_app), db: Session = Depends(get_db)):
    rows = {r.key: r for r in db.query(AgentMcpSource).all()}
    servers = registry.all_servers(include_disabled=True)
    items = [_public(rows.get(k), k, m) for k, m in sorted(servers.items())]
    return {"items": items, "allowedHosts": settings.mcp_allowed_hosts, "apps": sorted(settings.service_tokens) or [app]}


@router.post("", status_code=201)
def create_source(body: SourceCreate, app: str = Depends(require_app), who: str = Depends(actor), db: Session = Depends(get_db)):
    _validate(body)
    if body.key in registry.all_servers(include_disabled=True) or db.get(AgentMcpSource, body.key):
        raise HTTPException(status_code=409, detail={"field": "key", "message": f"Mã nguồn '{body.key}' đã tồn tại"})
    token = new_token()
    try:
        enc = encrypt(token)
    except CredentialKeyMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    row = AgentMcpSource(key=body.key, title=body.title, description=body.description, icon=body.icon, color=body.color,
                         url=body.url.strip(), apps=body.apps, enabled=body.enabled, timeout_seconds=body.timeoutSeconds,
                         require_grant=body.requireGrant, forward_user_jwt=body.forwardUserJwt,
                         token_enc=enc, token_hint=token[-4:], created_by=who, updated_by=who)
    db.add(row)
    db.commit()
    _changed()
    return {**_public(row, row.key, registry.all_servers(include_disabled=True)[row.key]), "token": token}


@router.put("/{key}")
def update_source(key: str, body: SourceIn, app: str = Depends(require_app), who: str = Depends(actor), db: Session = Depends(get_db)):
    _validate(body)
    row = _row(db, key)
    row.title, row.description, row.icon, row.color = body.title, body.description, body.icon, body.color
    row.url, row.apps, row.enabled, row.timeout_seconds = body.url.strip(), body.apps, body.enabled, body.timeoutSeconds
    row.require_grant, row.forward_user_jwt = body.requireGrant, body.forwardUserJwt
    row.updated_by = who
    db.commit()
    _changed()
    return _public(row, key, registry.all_servers(include_disabled=True)[key])


@router.delete("/{key}", status_code=204)
def delete_source(key: str, app: str = Depends(require_app), db: Session = Depends(get_db)):
    db.delete(_row(db, key))
    db.commit()
    _changed()


@router.post("/{key}/rotate-token")
def rotate_token(key: str, app: str = Depends(require_app), who: str = Depends(actor), db: Session = Depends(get_db)):
    row = _row(db, key)
    token = new_token()
    try:
        row.token_enc = encrypt(token)
    except CredentialKeyMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    row.token_hint, row.updated_by = token[-4:], who
    db.commit()
    _changed()
    return {"key": key, "token": token, "tokenHint": row.token_hint}


@router.post("/{key}/test")
async def test_source(key: str, app: str = Depends(require_app), auth: UserAuth = Depends(user_auth)):
    """initialize + tools/list bằng JWT của người bấm → độ trễ, số công cụ (đã lọc theo quyền người bấm)."""
    if registry.get(key) is None:
        return {"ok": False, "error": "Nguồn đang tắt hoặc không tồn tại"}
    started = time.perf_counter()
    try:
        info = await mcp_client.ping(key, app, auth)
        tools = await mcp_client.list_tools(key, app, auth, use_cache=False, filter_grants=False)
    except mcp_client.McpError as exc:
        return {"ok": False, "error": str(exc), "latencyMs": int((time.perf_counter() - started) * 1000)}
    return {"ok": True, "latencyMs": info.get("latencyMs"), "serverInfo": info.get("serverInfo"), "toolCount": len(tools),
            "tools": [{"name": t.name, "title": t.meta.get("title") or t.name} for t in tools][:100]}


@router.post("/{key}/check")
async def check_source(key: str, app: str = Depends(require_app), auth: UserAuth = Depends(user_auth)):
    """Kiểm tra chuẩn (xác thực 2 lớp, initialize, schema công cụ, x-dns, chỉ đọc) – như tools/mcp_check.py."""
    meta = registry.all_servers(include_disabled=True).get(key)
    if meta is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy nguồn MCP")
    if meta.get("source") == "db" and (reason := registry.check_url(meta["url"])):
        return {"ok": False, "pass": 0, "warn": 0, "fail": 1, "tools": 0, "items": [{"level": "fail", "check": "URL", "detail": reason}]}
    token = settings.mcp_tokens.get(key) or decrypt(meta.get("token_enc")) or service_token_for(app)
    return await run_check(meta["url"], token, auth, float(meta.get("timeout") or settings.mcp_timeout_seconds))



@router.get("/tool-catalog")
async def tool_catalog(app: str = Depends(require_app), auth: UserAuth = Depends(user_auth)):
    """Danh mục công cụ của các nguồn cần cấp quyền (require_grant) → HRM sinh nhóm quyền mcp:<nguồn>:<công cụ>
    trong màn Phân quyền vai trò. Gọi bằng danh tính người quản trị, KHÔNG lọc theo quyền mcp:* (để cấp được)."""
    import asyncio

    servers = {k: m for k, m in registry.servers_for(app).items() if m.get("require_grant")}

    async def one(key: str, meta: dict) -> dict:
        try:
            tools = await mcp_client.list_tools(key, app, auth, use_cache=True, filter_grants=False)
            return {"key": key, "title": meta.get("title") or key, "status": "ok",
                    "tools": [{"name": t.name, "title": t.meta.get("title") or t.name, "group": t.meta.get("group") or "",
                               "description": t.description[:200]} for t in tools]}
        except mcp_client.McpError as exc:
            return {"key": key, "title": meta.get("title") or key, "status": "error", "error": str(exc)[:200], "tools": []}

    return {"sources": list(await asyncio.gather(*(one(k, m) for k, m in sorted(servers.items()))))}


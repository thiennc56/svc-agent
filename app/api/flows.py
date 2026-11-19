"""Quản trị flow + registry (rule hiện tại) cho editor. App gọi (svc-hrm) đã kiểm quyền quản trị trước khi proxy."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.schemas import SaveFlowRequest, ValidateRequest
from app.core.db import get_db
from app.core.security import UserAuth, actor, require_app, user_auth
from app.flows.catalog import public_catalog
from app.flows.compiler import compile_flow
from app.flows.defaults import default_flow
from app.flows.service import FlowService, mask_secrets, merge_secrets
from app.runtime.mcp_client import McpError, list_tools, ping
from app.sources import registry as sources_registry

router = APIRouter(prefix="/v1/apps/{app}", tags=["Flows"])


def _servers_for(app: str) -> list[dict]:
    out = []
    for key, meta in sources_registry.servers_for(app).items():
        out.append({"key": key, "title": meta.get("title") or key, "description": meta.get("description") or "",
                    "icon": meta.get("icon") or "pi pi-database", "color": meta.get("color") or "#2563eb"})
    return out


def _flow_payload(row_doc: dict, version: int | None, row=None) -> dict:
    report = compile_flow(row_doc).report()
    return {
        "document": mask_secrets(row_doc), "version": version, "isDefault": version is None,
        "updatedAt": row.created_at.isoformat() if row else None, "updatedBy": row.created_by if row else None,
        "validation": report,
    }


@router.get("/catalog")
def catalog(app: str = Depends(require_app)):
    """Loại node (bảng node bên phải) + máy chủ MCP được phép cho app."""
    return {**public_catalog(), "mcpServers": _servers_for(app)}


@router.get("/flow")
def get_flow(app: str = Depends(require_app), auth: UserAuth = Depends(user_auth), db: Session = Depends(get_db)):
    service = FlowService(db)
    row = service.active(app, auth.tenant_id)
    return _flow_payload(row.document, row.version, row) if row else _flow_payload(default_flow(app), None)


@router.put("/flow")
def save_flow(body: SaveFlowRequest, app: str = Depends(require_app), auth: UserAuth = Depends(user_auth),
              who: str = Depends(actor), db: Session = Depends(get_db)):
    row, result = FlowService(db).save(app, auth.tenant_id, body.document, who, body.note)
    return {**_flow_payload(row.document, row.version, row), "validation": result.report()}


@router.post("/flow/validate")
def validate_flow(body: ValidateRequest, app: str = Depends(require_app), auth: UserAuth = Depends(user_auth),
                  db: Session = Depends(get_db)):
    current = FlowService(db).active(app, auth.tenant_id)
    doc = merge_secrets(body.document, current.document if current else None)
    return compile_flow(doc, app).report()


@router.get("/flow/default")
def get_default_flow(app: str = Depends(require_app)):
    return _flow_payload(default_flow(app), None)


@router.post("/flow/reset")
def reset_flow(app: str = Depends(require_app), auth: UserAuth = Depends(user_auth), who: str = Depends(actor),
               db: Session = Depends(get_db)):
    row = FlowService(db).reset(app, auth.tenant_id, who)
    return _flow_payload(row.document, row.version, row)


@router.get("/flow/versions")
def versions(app: str = Depends(require_app), auth: UserAuth = Depends(user_auth), db: Session = Depends(get_db)):
    rows = FlowService(db).versions(app, auth.tenant_id)
    return {"items": [{"version": r.version, "active": r.is_active, "note": r.note, "createdBy": r.created_by,
                       "createdAt": r.created_at.isoformat(), "nodes": len(r.document.get("nodes") or [])} for r in rows]}


@router.post("/flow/versions/{version}/activate")
def activate(version: int, app: str = Depends(require_app), auth: UserAuth = Depends(user_auth),
             who: str = Depends(actor), db: Session = Depends(get_db)):
    row = FlowService(db).activate(app, auth.tenant_id, version, who)
    return _flow_payload(row.document, row.version, row)


@router.get("/registry")
async def registry(app: str = Depends(require_app), auth: UserAuth = Depends(user_auth),
                   refresh: bool = Query(default=False)):
    """Rule hiện tại: mọi công cụ của các máy chủ MCP được phép (đã lọc theo quyền người xem) + metadata phân quyền."""
    servers = _servers_for(app)

    async def one(s: dict) -> dict:
        try:
            tools = await list_tools(s["key"], app, auth, use_cache=not refresh)
            return {**s, "status": "ok", "tools": [t.public() for t in tools]}
        except McpError as exc:
            return {**s, "status": "error", "error": str(exc), "tools": []}

    return {"servers": await asyncio.gather(*(one(s) for s in servers))}


@router.get("/mcp/{server}/ping")
async def ping_server(server: str, app: str = Depends(require_app), auth: UserAuth = Depends(user_auth)):
    if server not in {s["key"] for s in _servers_for(app)}:
        return {"ok": False, "error": "Máy chủ MCP không được phép cho ứng dụng này"}
    try:
        return await ping(server, app, auth)
    except McpError as exc:
        return {"ok": False, "error": str(exc)}

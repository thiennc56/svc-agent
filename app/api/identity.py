"""JWKS công khai cho signed_context + nhật ký gọi công cụ (audit) cho màn quản trị."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from app.core.security import UserAuth, require_app, user_auth
from app.core.signing import SigningKeyMissing, issuer, jwks
from app.sources import audit

public = APIRouter(tags=["Identity"])
router = APIRouter(prefix="/v1/apps/{app}", tags=["Audit"])


@public.get("/.well-known/jwks.json")
def jwks_json(response: Response):
    """Khoá công khai để phân hệ verify X-Agent-Context (RS256). Không cần xác thực. Cache 1 giờ."""
    response.headers["Cache-Control"] = "public, max-age=3600"
    try:
        return jwks()
    except SigningKeyMissing:
        response.status_code = 503
        return {"keys": [], "error": "signing_key_missing"}


@public.get("/.well-known/agent-context")
def context_info():
    """Mô tả signed_context (cho đội phân hệ cấu hình verify)."""
    return {"issuer": issuer(), "jwks_uri": issuer() + "/.well-known/jwks.json", "header": "X-Agent-Context",
            "alg": "RS256", "audience": "<mã nguồn MCP>", "claims": ["sub", "email", "name", "tenant", "app", "act",
                                                                     "permissions", "iat", "nbf", "exp", "jti"]}


@router.get("/audit")
def tool_audit(app: str = Depends(require_app), auth: UserAuth = Depends(user_auth),
               limit: int = Query(default=100, ge=1, le=500), server: str | None = Query(default=None, max_length=40),
               actor: str | None = Query(default=None, max_length=80), status: str | None = Query(default=None, max_length=16),
               before_id: int | None = Query(default=None, alias="beforeId")):
    """Nhật ký gọi công cụ của tenant hiện tại (app gọi đã kiểm quyền quản trị)."""
    items = audit.query(app, auth.tenant_id, limit=limit, server=server, actor=actor, status=status, before_id=before_id)
    return {"items": items, "nextBeforeId": items[-1]["id"] if len(items) == limit else None}

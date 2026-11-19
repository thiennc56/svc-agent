"""Xác thực service-to-service + ngữ cảnh người dùng được app gọi chuyển tiếp.

- Mọi route /v1/apps/{app}/... yêu cầu header X-Service-Token khớp SERVICE_TOKENS[app].
- svc-agent KHÔNG tự kiểm JWT người dùng: nó chuyển tiếp nguyên JWT (X-User-Authorization) + tenant tới MCP server
  của phân hệ; phân hệ kiểm RBAC đúng như REST API của nó.
"""
import hmac
from dataclasses import dataclass

from fastapi import Header, HTTPException, Path

from app.core.config import settings

APP_PATTERN = r"^[a-z][a-z0-9-]{1,39}$"


def require_app(
    app: str = Path(pattern=APP_PATTERN),
    x_service_token: str | None = Header(default=None, alias="X-Service-Token"),
) -> str:
    tokens = settings.service_tokens
    expected = tokens.get(app)
    if not expected:
        # Dev chưa khai báo token nào → cho phép (chạy local). Production luôn phải có SERVICE_TOKENS.
        if settings.is_dev and not tokens:
            return app
        raise HTTPException(status_code=403, detail=f"Ứng dụng '{app}' chưa được đăng ký với svc-agent")
    if not x_service_token or not hmac.compare_digest(expected.encode(), x_service_token.encode()):
        raise HTTPException(status_code=401, detail="X-Service-Token không hợp lệ")
    return app


@dataclass(frozen=True)
class UserAuth:
    """JWT người hỏi + tenant – chỉ để chuyển tiếp cho MCP server, không lưu, không log."""

    authorization: str
    tenant_id: str
    user_id: str = ""
    email: str = ""
    # Quyền mcp:* / wf:* (HRM tính, app gửi qua X-User-Permissions) + tên hiển thị + loại danh tính (user | service = bot)
    permissions: tuple[str, ...] = ()
    name: str = ""
    kind: str = "user"


def user_auth(
    x_user_authorization: str | None = Header(default=None, alias="X-User-Authorization"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    x_user_permissions: str | None = Header(default=None, alias="X-User-Permissions"),
    x_user_name: str | None = Header(default=None, alias="X-User-Name"),
) -> UserAuth:
    if not x_user_authorization or not x_user_authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Thiếu X-User-Authorization (Bearer token của người dùng)")
    if not x_tenant_id or len(x_tenant_id) > 64:
        raise HTTPException(status_code=400, detail="Thiếu hoặc sai X-Tenant-Id")
    from app.core.perms import clean

    perms = clean((x_user_permissions or "")[:8000].split(","))
    return UserAuth(x_user_authorization, x_tenant_id, (x_user_id or "")[:64], (x_user_email or "")[:160], perms,
                    (x_user_name or "")[:160])


def actor(
    x_user_email: str | None = Header(default=None, alias="X-User-Email"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> str:
    """Người thao tác (ghi lịch sử flow) – do app gọi điền sau khi đã kiểm quyền."""
    return (x_user_email or x_user_id or "unknown")[:160]


def service_token_for(app: str) -> str:
    return settings.service_tokens.get(app, "")

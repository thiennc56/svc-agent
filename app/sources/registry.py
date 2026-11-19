"""Registry máy chủ MCP = ConfigMap `MCP_SERVERS` (tĩnh, chỉ đọc) + bảng `agent_mcp_sources` (động, sửa trên trang HRM).

Mọi nơi cần danh sách máy chủ (compiler, catalog, mcp_client, flow mặc định) đều đi qua đây.
Cache 10 s trong tiến trình; ghi qua API quản trị gọi `invalidate()` → hiệu lực ngay ở pod đó, pod khác ≤ 10 s.
"""
from __future__ import annotations

import fnmatch
import ipaddress
import logging
import time
from urllib.parse import urlsplit

from app.core.config import settings

logger = logging.getLogger(__name__)
TTL_SECONDS = 10.0
_cache: dict[str, object] = {"at": 0.0, "db": {}}


def _load_db() -> dict[str, dict]:
    from app.core.db import SessionLocal
    from app.sources.models import AgentMcpSource

    out: dict[str, dict] = {}
    try:
        with SessionLocal() as db:
            for s in db.query(AgentMcpSource).all():
                out[s.key] = {"url": s.url, "title": s.title, "description": s.description, "icon": s.icon, "color": s.color,
                              "apps": list(s.apps or []), "enabled": bool(s.enabled), "timeout": s.timeout_seconds,
                              "token_enc": s.token_enc, "source": "db", "require_grant": bool(s.require_grant),
                              "forward_user_jwt": bool(s.forward_user_jwt)}
    except Exception as exc:  # noqa: BLE001 – bảng chưa migrate / DB lỗi: vẫn chạy với ConfigMap
        logger.warning("mcp sources: không đọc được DB (%s) – chỉ dùng MCP_SERVERS", type(exc).__name__)
    return out


def invalidate() -> None:
    _cache["at"] = 0.0


def _db_sources() -> dict[str, dict]:
    now = time.monotonic()
    if now - float(_cache["at"]) > TTL_SECONDS:
        _cache["db"] = _load_db()
        _cache["at"] = now
    return _cache["db"]  # type: ignore[return-value]


def all_servers(include_disabled: bool = False) -> dict[str, dict]:
    """key → meta. ConfigMap thắng nếu trùng key (nguồn DB không được ghi đè nguồn hạ tầng)."""
    out = {k: v for k, v in _db_sources().items() if include_disabled or v.get("enabled", True)}
    for k, v in settings.mcp_servers.items():
        # Nguồn hạ tầng (vd. hrm): tự kiểm quyền RBAC của nó, nhận JWT người hỏi → mặc định không cần cấp mcp:*
        out[k] = {"require_grant": False, "forward_user_jwt": True, **v, "source": "config", "enabled": True}
    return out


def get(key: str) -> dict | None:
    return all_servers().get(key)


def servers_for(app: str) -> dict[str, dict]:
    return {k: v for k, v in all_servers().items() if not v.get("apps") or app in v["apps"]}


# ─────────────────────────── chống SSRF ───────────────────────────
_BLOCKED_NETS = [ipaddress.ip_network(n) for n in ("169.254.0.0/16", "0.0.0.0/8", "224.0.0.0/4", "fe80::/10", "::/128")]


def check_url(url: str) -> str | None:
    """None = hợp lệ; chuỗi = lý do từ chối. Chỉ http(s), không userinfo, host thuộc MCP_ALLOWED_HOSTS, chặn metadata IP."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return "URL không hợp lệ"
    if parts.scheme not in ("http", "https"):
        return "Chỉ hỗ trợ http:// hoặc https://"
    if parts.username or parts.password:
        return "URL không được chứa user/mật khẩu"
    host = (parts.hostname or "").lower()
    if not host:
        return "Thiếu host"
    try:
        ip = ipaddress.ip_address(host)
        if any(ip in net for net in _BLOCKED_NETS):
            return "Địa chỉ IP bị chặn (link-local / metadata)"
    except ValueError:
        pass
    if not any(fnmatch.fnmatch(host, pat.lower()) for pat in settings.mcp_allowed_hosts):
        return f"Host '{host}' không thuộc danh sách cho phép (MCP_ALLOWED_HOSTS: {', '.join(settings.mcp_allowed_hosts)})"
    if parts.query or parts.fragment:
        return "URL không được chứa query / fragment"
    return None

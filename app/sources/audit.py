"""Ghi nhật ký gọi công cụ (audit) – không chặn luồng chat khi DB lỗi; không lưu tham số/kết quả/token."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.db import SessionLocal
from app.sources.models import AgentToolAudit

logger = logging.getLogger(__name__)
_last_prune = {"at": datetime.min.replace(tzinfo=timezone.utc)}


def record(*, app: str, auth, server: str, tool: str, status: str, error: str | None, duration_ms: int, channel: str = "") -> None:
    try:
        with SessionLocal() as db:
            db.add(AgentToolAudit(app=app, tenant_id=auth.tenant_id, actor=(auth.email or auth.user_id or "")[:160],
                                  actor_kind=getattr(auth, "kind", "user"), channel=channel[:20], server=server[:40],
                                  tool=tool[:80], status=status[:16], error=(error or None) and str(error)[:80],
                                  duration_ms=max(0, int(duration_ms))))
            now = datetime.now(timezone.utc)
            if now - _last_prune["at"] > timedelta(hours=6):  # dọn bản ghi cũ theo AUDIT_RETENTION_DAYS
                _last_prune["at"] = now
                db.query(AgentToolAudit).filter(
                    AgentToolAudit.at < now - timedelta(days=settings.audit_retention_days)).delete(synchronize_session=False)
            db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("audit: không ghi được (%s)", type(exc).__name__)


def query(app: str, tenant: str, *, limit: int = 100, server: str | None = None, actor: str | None = None,
          status: str | None = None, before_id: int | None = None) -> list[dict]:
    with SessionLocal() as db:
        q = db.query(AgentToolAudit).filter(AgentToolAudit.app == app, AgentToolAudit.tenant_id == tenant)
        if server:
            q = q.filter(AgentToolAudit.server == server)
        if actor:
            q = q.filter(AgentToolAudit.actor.ilike(f"%{actor[:80]}%"))
        if status:
            q = q.filter(AgentToolAudit.status == status)
        if before_id:
            q = q.filter(AgentToolAudit.id < before_id)
        rows = q.order_by(AgentToolAudit.id.desc()).limit(max(1, min(limit, 500))).all()
        return [{"id": r.id, "at": r.at.isoformat(), "actor": r.actor, "actorKind": r.actor_kind, "channel": r.channel,
                 "server": r.server, "tool": r.tool, "status": r.status, "error": r.error, "durationMs": r.duration_ms}
                for r in rows]

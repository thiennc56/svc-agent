"""Bảng lưu flow theo (app, tenant). Mỗi lần lưu = 1 phiên bản mới (immutable) → xem lịch sử / khôi phục."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, Column, DateTime, Index, Integer, String

from app.core.db import Base


def _now():
    return datetime.now(timezone.utc)


class AgentFlowVersion(Base):
    __tablename__ = "agent_flow_versions"
    __table_args__ = (
        Index("uq_agent_flow_version", "app", "tenant_id", "version", unique=True),
        Index("ix_agent_flow_active", "app", "tenant_id", "is_active"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    app = Column(String(40), nullable=False)
    tenant_id = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False)
    document = Column(JSON, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)
    note = Column(String(300), nullable=True)
    created_by = Column(String(160), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

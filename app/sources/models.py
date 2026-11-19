"""Nguồn MCP động: quản trị nền tảng khai báo trên trang HRM (không sửa ConfigMap, không restart).

Token X-Agent-Token của nguồn mã hoá at-rest (Fernet), chỉ hiển thị 1 lần khi tạo / xoay.
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text

from app.core.db import Base


def _now():
    return datetime.now(timezone.utc)


class AgentMcpSource(Base):
    __tablename__ = "agent_mcp_sources"

    key = Column(String(40), primary_key=True)
    title = Column(String(120), nullable=False)
    description = Column(String(300), nullable=False, default="")
    icon = Column(String(60), nullable=False, default="pi pi-database")
    color = Column(String(20), nullable=False, default="#2563eb")
    url = Column(String(300), nullable=False)
    apps = Column(JSON, nullable=False, default=list)
    enabled = Column(Boolean, nullable=False, default=True)
    timeout_seconds = Column(Integer, nullable=False, default=20)
    token_enc = Column(Text, nullable=True)
    token_hint = Column(String(8), nullable=True)
    created_by = Column(String(160), nullable=True)
    updated_by = Column(String(160), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

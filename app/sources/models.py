"""Nguồn MCP động: quản trị nền tảng khai báo trên trang HRM (không sửa ConfigMap, không restart).

Token X-Agent-Token của nguồn mã hoá at-rest (Fernet), chỉ hiển thị 1 lần khi tạo / xoay.
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, Index, Integer, String, Text

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
    # Giai đoạn C: chỉ hiện công cụ người hỏi được cấp quyền mcp:<key>:<tool> trong HRM
    require_grant = Column(Boolean, nullable=False, default=True)
    # Gửi kèm JWT SOPBase của người hỏi (Authorization) – tương thích phân hệ làm theo hướng dẫn v1.1.
    # Tắt = chỉ gửi X-Agent-Context (signed_context) – khuyến nghị, không chuyển tiếp token.
    forward_user_jwt = Column(Boolean, nullable=False, default=True)
    token_enc = Column(Text, nullable=True)
    token_hint = Column(String(8), nullable=True)
    created_by = Column(String(160), nullable=True)
    updated_by = Column(String(160), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class AgentToolAudit(Base):
    """Nhật ký mỗi lần gọi công cụ MCP: ai (người/bot), công cụ, tenant, kết quả, thời gian.
    KHÔNG lưu tham số, kết quả, token (dữ liệu cá nhân)."""
    __tablename__ = "agent_tool_audit"
    __table_args__ = (
        Index("ix_agent_tool_audit_tenant_at", "app", "tenant_id", "at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    at = Column(DateTime(timezone=True), nullable=False, default=_now)
    app = Column(String(40), nullable=False)
    tenant_id = Column(String(64), nullable=False)
    actor = Column(String(160), nullable=False, default="")
    actor_kind = Column(String(16), nullable=False, default="user")
    channel = Column(String(20), nullable=False, default="")
    server = Column(String(40), nullable=False)
    tool = Column(String(80), nullable=False)
    status = Column(String(16), nullable=False)
    error = Column(String(80), nullable=True)
    duration_ms = Column(Integer, nullable=False, default=0)


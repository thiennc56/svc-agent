"""giai đoạn C: cờ quyền/danh tính cho nguồn MCP + bảng audit gọi công cụ

Revision ID: 202611200001
Revises: 202611190001
Create Date: 2026-11-20
"""
from alembic import op
import sqlalchemy as sa

revision = "202611200001"
down_revision = "202611190001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nguồn đã tạo trước giai đoạn C: giữ hành vi cũ (không đòi quyền mcp:*, vẫn chuyển tiếp JWT) → không gãy
    op.add_column("agent_mcp_sources", sa.Column("require_grant", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("agent_mcp_sources", sa.Column("forward_user_jwt", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table(
        "agent_tool_audit",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("app", sa.String(40), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(160), nullable=False, server_default=""),
        sa.Column("actor_kind", sa.String(16), nullable=False, server_default="user"),
        sa.Column("channel", sa.String(20), nullable=False, server_default=""),
        sa.Column("server", sa.String(40), nullable=False),
        sa.Column("tool", sa.String(80), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.String(80), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_agent_tool_audit_tenant_at", "agent_tool_audit", ["app", "tenant_id", "at"])


def downgrade() -> None:
    op.drop_index("ix_agent_tool_audit_tenant_at", table_name="agent_tool_audit")
    op.drop_table("agent_tool_audit")
    op.drop_column("agent_mcp_sources", "forward_user_jwt")
    op.drop_column("agent_mcp_sources", "require_grant")

"""agent_flow_versions

Revision ID: 202611180001
Revises:
Create Date: 2026-11-18
"""
from alembic import op
import sqlalchemy as sa

revision = "202611180001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_flow_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("app", sa.String(40), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("created_by", sa.String(160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("uq_agent_flow_version", "agent_flow_versions", ["app", "tenant_id", "version"], unique=True)
    op.create_index("ix_agent_flow_active", "agent_flow_versions", ["app", "tenant_id", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_agent_flow_active", table_name="agent_flow_versions")
    op.drop_index("uq_agent_flow_version", table_name="agent_flow_versions")
    op.drop_table("agent_flow_versions")

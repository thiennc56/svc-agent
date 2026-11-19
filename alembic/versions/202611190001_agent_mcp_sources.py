"""agent_mcp_sources – nguồn MCP động (màn Nguồn MCP trong HRM)

Revision ID: 202611190001
Revises: 202611180001
Create Date: 2026-11-19
"""
from alembic import op
import sqlalchemy as sa

revision = "202611190001"
down_revision = "202611180001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_mcp_sources",
        sa.Column("key", sa.String(40), primary_key=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.String(300), nullable=False, server_default=""),
        sa.Column("icon", sa.String(60), nullable=False, server_default="pi pi-database"),
        sa.Column("color", sa.String(20), nullable=False, server_default="#2563eb"),
        sa.Column("url", sa.String(300), nullable=False),
        sa.Column("apps", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("token_enc", sa.Text(), nullable=True),
        sa.Column("token_hint", sa.String(8), nullable=True),
        sa.Column("created_by", sa.String(160), nullable=True),
        sa.Column("updated_by", sa.String(160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("agent_mcp_sources")

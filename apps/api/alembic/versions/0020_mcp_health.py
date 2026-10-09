"""Bounded MCP health provenance and operation identity (no credential changes)."""

import sqlalchemy as sa
from alembic import op

revision = "0020_mcp_health"
down_revision = "0019_instrument_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mcp_connections", sa.Column("health_since", sa.DateTime(timezone=True)))
    op.add_column("mcp_connections", sa.Column("last_failure_at", sa.DateTime(timezone=True)))
    op.add_column("mcp_connections", sa.Column("last_failure_kind", sa.String(40)))
    op.add_column(
        "mcp_connections",
        sa.Column("consecutive_failure_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("mcp_operations", sa.Column("tool_name", sa.String(128)))
    op.add_column("mcp_operations", sa.Column("health_outcome", sa.String(40)))


def downgrade() -> None:
    op.drop_column("mcp_operations", "health_outcome")
    op.drop_column("mcp_operations", "tool_name")
    for name in (
        "consecutive_failure_count",
        "last_failure_kind",
        "last_failure_at",
        "health_since",
    ):
        op.drop_column("mcp_connections", name)

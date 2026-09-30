"""Preserve auth intent and ambiguous finalization across worker loss."""

import sqlalchemy as sa
from alembic import op

revision = "0011_mcp_durable_reconciliation"
down_revision = "0010_mcp_provider_outcome"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mcp_connections",
        sa.Column(
            "auth_invalidation_pending", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "mcp_operations",
        sa.Column(
            "reconciliation_required", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT (SELECT COUNT(*) FROM mcp_connections "
            "WHERE auth_invalidation_pending = true) + "
            "(SELECT COUNT(*) FROM mcp_operations "
            "WHERE reconciliation_required = true OR state != 'COMPLETE')"
        )
    ):
        raise RuntimeError("Resolve MCP recovery obligations before downgrade")
    op.drop_column("mcp_operations", "reconciliation_required")
    op.drop_column("mcp_connections", "auth_invalidation_pending")

"""Separate provider evidence from the authoritative operation outcome."""

import sqlalchemy as sa
from alembic import op

revision = "0010_mcp_provider_outcome"
down_revision = "0009_mcp_operation_permits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mcp_operations", sa.Column("provider_outcome", sa.String(40)))


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT (SELECT COUNT(*) FROM mcp_operations WHERE state != 'COMPLETE') + "
            "(SELECT COUNT(*) FROM mcp_connections WHERE state = 'REAUTH_DRAINING')"
        )
    ):
        raise RuntimeError("Resolve outstanding MCP operation permits before downgrade")
    op.drop_column("mcp_operations", "provider_outcome")

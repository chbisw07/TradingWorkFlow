"""Serialize MCP provider cleanup against new authentication authority."""

import sqlalchemy as sa
from alembic import op

revision = "0008_mcp_cleanup_claim"
down_revision = "0007_mcp_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mcp_connections", sa.Column("cleanup_until", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("mcp_connections", "cleanup_until")

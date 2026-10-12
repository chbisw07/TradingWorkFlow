"""Persist completed-session F&O liquidity observations and ranked membership."""

import sqlalchemy as sa
from alembic import op

revision = "0021_fno_liquidity_cache"
down_revision = "0020_mcp_health"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fno_liquidity_cache",
        sa.Column("key", sa.String(32), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("fno_liquidity_cache")

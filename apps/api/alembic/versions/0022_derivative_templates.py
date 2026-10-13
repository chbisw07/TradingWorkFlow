"""Owner-scoped, configuration-only derivatives scan templates."""

import sqlalchemy as sa
from alembic import op

revision = "0022_derivative_templates"
down_revision = "0021_fno_liquidity_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scanner_v2_derivative_templates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_scanner_v2_derivative_templates_owner_id",
        "scanner_v2_derivative_templates",
        ["owner_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scanner_v2_derivative_templates_owner_id", table_name="scanner_v2_derivative_templates"
    )
    op.drop_table("scanner_v2_derivative_templates")

"""Short-lived, single-use OE-2 manual preview envelopes."""

import sqlalchemy as sa
from alembic import op

revision = "0024_manual_order_previews"
down_revision = "0023_twf_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manual_order_previews",
        sa.Column("preview_id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_hash", sa.String(64), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("selection_digest", sa.String(64), nullable=False),
        sa.Column("instrument", sa.JSON(), nullable=False),
        sa.Column("terms", sa.JSON(), nullable=False),
        sa.Column("notes", sa.String(2000), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("order_id", sa.Uuid(), sa.ForeignKey("twf_orders.twf_order_id")),
        sa.Column("validation", sa.JSON()),
        sa.UniqueConstraint("order_id", name="uq_manual_order_previews_order_id"),
        sa.CheckConstraint(
            "(consumed_at IS NULL AND order_id IS NULL AND validation IS NULL) OR "
            "(consumed_at IS NOT NULL AND order_id IS NOT NULL AND validation IS NOT NULL)",
            name="ck_manual_order_previews_consumed_has_order",
        ),
    )
    op.create_index(
        "ix_manual_order_previews_owner_expiry", "manual_order_previews", ["owner_id", "expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_manual_order_previews_owner_expiry", table_name="manual_order_previews")
    op.drop_table("manual_order_previews")

"""OE-1 broker-neutral current orders and append-only event history."""

import sqlalchemy as sa
from alembic import op

revision = "0023_twf_orders"
down_revision = "0022_derivative_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "twf_orders",
        sa.Column("twf_order_id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state_reason_code", sa.String(64)),
        sa.Column("state_reason", sa.String(512)),
        sa.CheckConstraint("version > 0", name="ck_twf_orders_version_positive"),
        sa.UniqueConstraint("twf_order_id", "owner_id", name="uq_twf_orders_id_owner"),
    )
    op.create_index("ix_twf_orders_owner_created", "twf_orders", ["owner_id", "created_at"])
    op.create_table(
        "twf_order_events",
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column("twf_order_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("order_version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("from_state", sa.String(32)),
        sa.Column("to_state", sa.String(32)),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("authority", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(64)),
        sa.Column("reason", sa.String(512)),
        sa.Column("correlation_id", sa.String(128)),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["twf_order_id", "owner_id"],
            ["twf_orders.twf_order_id", "twf_orders.owner_id"],
            ondelete="RESTRICT",
            name="fk_twf_order_events_order_owner",
        ),
    )
    op.create_index(
        "ix_twf_order_events_owner_order_seq",
        "twf_order_events",
        ["owner_id", "twf_order_id", "sequence"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_twf_order_events_owner_order_seq", table_name="twf_order_events")
    op.drop_table("twf_order_events")
    op.drop_index("ix_twf_orders_owner_created", table_name="twf_orders")
    op.drop_table("twf_orders")

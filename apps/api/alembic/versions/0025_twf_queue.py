"""OE-3 durable TWF Queue admission and history; no broker execution."""

import sqlalchemy as sa
from alembic import op

revision = "0025_twf_queue"
down_revision = "0024_manual_order_previews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "twf_queue_entries",
        sa.Column("queue_entry_id", sa.Uuid(), primary_key=True),
        sa.Column("twf_order_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("queue_state", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("admitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("reason_code", sa.String(64)),
        sa.Column("reason_message", sa.String(512)),
        sa.ForeignKeyConstraint(
            ["twf_order_id", "owner_id"],
            ["twf_orders.twf_order_id", "twf_orders.owner_id"],
            ondelete="RESTRICT",
            name="fk_twf_queue_entries_order_owner",
        ),
        sa.UniqueConstraint("twf_order_id", name="uq_twf_queue_entries_order"),
        sa.UniqueConstraint(
            "queue_entry_id", "twf_order_id", "owner_id", name="uq_twf_queue_entries_identity"
        ),
        sa.CheckConstraint("version > 0", name="ck_twf_queue_entries_version_positive"),
        sa.CheckConstraint(
            "queue_state IN ('READY', 'HELD')", name="ck_twf_queue_entries_active_state"
        ),
    )
    op.create_index(
        "ix_twf_queue_entries_owner_fifo",
        "twf_queue_entries",
        ["owner_id", "admitted_at", "queue_entry_id"],
    )
    op.create_table(
        "twf_queue_events",
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column("queue_entry_id", sa.Uuid(), nullable=False),
        sa.Column("twf_order_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("queue_version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("from_state", sa.String(32)),
        sa.Column("to_state", sa.String(32), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("reason_code", sa.String(64)),
        sa.Column("reason_message", sa.String(512)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["queue_entry_id", "twf_order_id", "owner_id"],
            [
                "twf_queue_entries.queue_entry_id",
                "twf_queue_entries.twf_order_id",
                "twf_queue_entries.owner_id",
            ],
            ondelete="RESTRICT",
            name="fk_twf_queue_events_entry_order_owner",
        ),
    )
    op.create_index(
        "ix_twf_queue_events_owner_entry_seq",
        "twf_queue_events",
        ["owner_id", "queue_entry_id", "sequence"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_twf_queue_events_owner_entry_seq", table_name="twf_queue_events")
    op.drop_table("twf_queue_events")
    op.drop_index("ix_twf_queue_entries_owner_fifo", table_name="twf_queue_entries")
    op.drop_table("twf_queue_entries")

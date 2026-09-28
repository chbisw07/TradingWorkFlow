"""Add the manual order-intent ledger; no changes to accepted broker records."""

import sqlalchemy as sa
from alembic import op

revision = "0006_order_intents"
down_revision = "0005_credential_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "broker_order_intents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("broker_accounts.id"), nullable=False),
        sa.Column("account_name", sa.String(80), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("session_hash", sa.String(64), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("broker_identity", sa.String(64), nullable=False),
        sa.Column("instrument_json", sa.Text(), nullable=False),
        sa.Column("order_json", sa.Text(), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("execution_authority", sa.String(32), nullable=False),
        sa.Column("tag", sa.String(20), nullable=False, unique=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("broker_order_id", sa.String(160)),
        sa.Column("provider_status", sa.String(160)),
        sa.Column("failure", sa.String(240)),
    )
    op.create_index("ix_broker_order_intents_user_id", "broker_order_intents", ["user_id"])
    op.create_index("ix_broker_order_intents_account_id", "broker_order_intents", ["account_id"])


def downgrade() -> None:
    op.drop_table("broker_order_intents")

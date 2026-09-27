"""Broker V1 configuration, encrypted secrets and one-time authentication attempts."""

import sqlalchemy as sa
from alembic import op

revision = "0004_broker_v1"
down_revision = "0003_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "broker_secrets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ciphertext", sa.Text(), nullable=False),
    )
    op.create_table(
        "broker_accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("identity", sa.String(64)),
        sa.Column("secret_id", sa.Uuid(), sa.ForeignKey("broker_secrets.id"), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("health", sa.String(16), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_read_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "provider", "identity"),
    )
    op.create_index("ix_broker_accounts_user_id", "broker_accounts", ["user_id"])
    op.create_table(
        "broker_attempts",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("broker_accounts.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_hash", sa.String(64), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_broker_attempts_account_id", "broker_attempts", ["account_id"])


def downgrade() -> None:
    op.drop_table("broker_attempts")
    op.drop_table("broker_accounts")
    op.drop_table("broker_secrets")

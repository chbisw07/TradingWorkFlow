"""BW-2.2 authentication correlation and secret cleanup

Revision ID: 0005_broker_auth
Revises: 0004_broker_foundation
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_broker_auth"
down_revision: str | Sequence[str] | None = "0004_broker_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "broker_auth_attempts",
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("broker_account_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("session_hash", sa.String(length=64), nullable=False),
        sa.Column("provider_id", sa.String(length=48), nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalize_hash", sa.String(length=64), nullable=True),
        sa.Column("pending_reference", sa.String(length=128), nullable=True),
        sa.Column("verified_subject", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(
            ["broker_account_id"],
            ["broker_accounts.id"],
            name=op.f("fk_broker_auth_attempts_broker_account_id_broker_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_broker_auth_attempts_owner_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["session_hash"],
            ["auth_sessions.token_hash"],
            name=op.f("fk_broker_auth_attempts_session_hash_auth_sessions"),
        ),
        sa.PrimaryKeyConstraint("state_hash", name=op.f("pk_broker_auth_attempts")),
        sa.UniqueConstraint("finalize_hash", name=op.f("uq_broker_auth_attempts_finalize_hash")),
    )
    op.create_index(
        op.f("ix_broker_auth_attempts_broker_account_id"),
        "broker_auth_attempts",
        ["broker_account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_broker_auth_attempts_expires_at"),
        "broker_auth_attempts",
        ["expires_at"],
        unique=False,
    )
    op.create_table(
        "broker_auth_configurations",
        sa.Column("broker_account_id", sa.Uuid(), nullable=False),
        sa.Column("api_key", sa.String(length=128), nullable=False),
        sa.Column("secret_reference", sa.String(length=128), nullable=False),
        sa.Column("secret_generation", sa.Integer(), nullable=False),
        sa.Column("credential_revision", sa.Integer(), nullable=False),
        sa.Column("bound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_auth_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["broker_account_id"],
            ["broker_accounts.id"],
            name=op.f("fk_broker_auth_configurations_broker_account_id_broker_accounts"),
        ),
        sa.PrimaryKeyConstraint("broker_account_id", name=op.f("pk_broker_auth_configurations")),
    )
    op.create_table(
        "broker_secret_lifecycle",
        sa.Column("reference", sa.String(length=128), nullable=False),
        sa.Column("broker_account_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.String(length=48), nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=24), nullable=False),
        sa.Column("context", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleanup_attempts", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["broker_account_id"],
            ["broker_accounts.id"],
            name=op.f("fk_broker_secret_lifecycle_broker_account_id_broker_accounts"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_broker_secret_lifecycle_owner_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("reference", name=op.f("pk_broker_secret_lifecycle")),
    )
    op.create_index(
        op.f("ix_broker_secret_lifecycle_broker_account_id"),
        "broker_secret_lifecycle",
        ["broker_account_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_broker_secret_lifecycle_broker_account_id"), table_name="broker_secret_lifecycle"
    )
    op.drop_table("broker_secret_lifecycle")
    op.drop_table("broker_auth_configurations")
    op.drop_index(op.f("ix_broker_auth_attempts_expires_at"), table_name="broker_auth_attempts")
    op.drop_index(
        op.f("ix_broker_auth_attempts_broker_account_id"), table_name="broker_auth_attempts"
    )
    op.drop_table("broker_auth_attempts")

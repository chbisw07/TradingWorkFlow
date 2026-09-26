"""BW-2.1 provider/account foundation; no provider credentials or connectivity."""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0004_broker_foundation"
down_revision = "0003_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "broker_provider_configurations",
        sa.Column("provider_id", sa.String(48), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("configured", sa.Boolean(), nullable=False),
        sa.Column("configuration_revision", sa.Integer(), nullable=False),
        sa.Column("secret_reference", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "configuration_revision >= 1",
            name="ck_broker_provider_configurations_provider_configuration_revision_positive",
        ),
        sa.PrimaryKeyConstraint("provider_id", name="pk_broker_provider_configurations"),
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        sa.table(
            "broker_provider_configurations",
            sa.column("provider_id", sa.String),
            sa.column("enabled", sa.Boolean),
            sa.column("configured", sa.Boolean),
            sa.column("configuration_revision", sa.Integer),
            sa.column("secret_reference", sa.String),
            sa.column("created_at", sa.DateTime(timezone=True)),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        ),
        [
            {
                "provider_id": "zerodha",
                "enabled": False,
                "configured": False,
                "configuration_revision": 1,
                "secret_reference": None,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )
    op.create_table(
        "broker_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.String(48), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False),
        sa.Column("provider_account_id", sa.String(128), nullable=True),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("configured", sa.Boolean(), nullable=False),
        sa.Column("configuration_revision", sa.Integer(), nullable=False),
        sa.Column("connection_generation", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "configuration_revision >= 1",
            name="ck_broker_accounts_configuration_revision_positive",
        ),
        sa.CheckConstraint(
            "connection_generation >= 0",
            name="ck_broker_accounts_connection_generation_nonnegative",
        ),
        sa.CheckConstraint("mode = 'LIVE'", name="ck_broker_accounts_mode_live"),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], name="fk_broker_accounts_owner_user_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["broker_provider_configurations.provider_id"],
            name="fk_broker_accounts_provider_id_broker_provider_configurations",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_broker_accounts"),
        sa.UniqueConstraint(
            "provider_id",
            "environment",
            "provider_account_id",
            name="uq_broker_accounts_provider_environment_external",
        ),
        sa.UniqueConstraint(
            "owner_user_id",
            "provider_id",
            "label",
            name="uq_broker_accounts_owner_provider_label",
        ),
    )
    op.create_index("ix_broker_accounts_owner_user_id", "broker_accounts", ["owner_user_id"])
    op.create_index("ix_broker_accounts_provider_id", "broker_accounts", ["provider_id"])
    op.create_table(
        "broker_connections",
        sa.Column("broker_account_id", sa.Uuid(), nullable=False),
        sa.Column("authentication_state", sa.String(24), nullable=False),
        sa.Column("read_health", sa.String(24), nullable=False),
        sa.Column("applied_configuration_revision", sa.Integer(), nullable=False),
        sa.Column("secret_reference", sa.String(128), nullable=True),
        sa.Column("secret_version", sa.String(64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "applied_configuration_revision >= 0",
            name="ck_broker_connections_applied_revision_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["broker_account_id"],
            ["broker_accounts.id"],
            name="fk_broker_connections_broker_account_id_broker_accounts",
        ),
        sa.PrimaryKeyConstraint("broker_account_id", name="pk_broker_connections"),
    )
    op.create_table(
        "broker_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("broker_account_id", sa.Uuid(), nullable=True),
        sa.Column("provider_id", sa.String(48), nullable=False),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("configuration_revision", sa.Integer(), nullable=False),
        sa.Column("connection_generation", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=True),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "configuration_revision >= 0",
            name="ck_broker_audit_events_configuration_revision_nonnegative",
        ),
        sa.CheckConstraint(
            "connection_generation >= 0",
            name="ck_broker_audit_events_connection_generation_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], name="fk_broker_audit_events_owner_user_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["broker_account_id"],
            ["broker_accounts.id"],
            name="fk_broker_audit_events_broker_account_id_broker_accounts",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_broker_audit_events"),
    )
    op.create_index(
        "ix_broker_audit_events_owner_user_id", "broker_audit_events", ["owner_user_id"]
    )
    op.create_index(
        "ix_broker_audit_events_account_created",
        "broker_audit_events",
        ["broker_account_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_broker_audit_events_account_created", table_name="broker_audit_events")
    op.drop_index("ix_broker_audit_events_owner_user_id", table_name="broker_audit_events")
    op.drop_table("broker_audit_events")
    op.drop_table("broker_connections")
    op.drop_index("ix_broker_accounts_provider_id", table_name="broker_accounts")
    op.drop_index("ix_broker_accounts_owner_user_id", table_name="broker_accounts")
    op.drop_table("broker_accounts")
    op.drop_table("broker_provider_configurations")

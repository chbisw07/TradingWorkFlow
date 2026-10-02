"""Add owner-scoped encrypted Dhan market-data credentials."""

import sqlalchemy as sa
from alembic import op

revision = "0016_dhan_market_data_credentials"
down_revision = "0015_discovery_evidence_series"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dhan_market_data_secrets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("algorithm", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_dhan_market_data_secrets_owner_id",
        "dhan_market_data_secrets",
        ["owner_id"],
    )
    op.create_table(
        "dhan_market_data_connections",
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column(
            "secret_id",
            sa.Uuid(),
            sa.ForeignKey("dhan_market_data_secrets.id"),
            nullable=True,
        ),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_error", sa.String(40), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("dhan_market_data_connections")
    op.drop_table("dhan_market_data_secrets")

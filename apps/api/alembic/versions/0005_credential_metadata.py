"""Add credential metadata without changing existing ciphertext or account references."""

import sqlalchemy as sa
from alembic import op

revision = "0005_credential_metadata"
down_revision = "0004_broker_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "broker_secrets",
        sa.Column("algorithm", sa.String(32), nullable=False, server_default="fernet-v1"),
    )
    for name in ("created_at", "updated_at"):
        op.add_column(
            "broker_secrets",
            sa.Column(
                name,
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("'1970-01-01 00:00:00'"),
            ),
        )
    # Legacy rows had no lifecycle timestamps: record migration time, without
    # decrypting or rewriting tokens. SQLite needs constant ADD COLUMN defaults.
    op.execute(
        sa.text(
            "UPDATE broker_secrets SET created_at = CURRENT_TIMESTAMP, "
            "updated_at = CURRENT_TIMESTAMP"
        )
    )


def downgrade() -> None:
    # Both supported runtimes (modern SQLite and PostgreSQL 16) support DROP COLUMN.
    for name in ("updated_at", "created_at", "algorithm"):
        op.drop_column("broker_secrets", name)

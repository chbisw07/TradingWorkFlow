"""Scanner V2 saved configurations and immutable runs; historical S&D preserved."""

import sqlalchemy as sa
from alembic import op

revision = "0018_scanner_v2"
down_revision = "0017_watchlists"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table, payload in (("scanner_v2_saved", "config"), ("scanner_v2_runs", "payload")):
        extra = (
            [
                sa.Column("archived", sa.Boolean(), nullable=False),
                sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            ]
            if table.endswith("saved")
            else []
        )
        op.create_table(
            table,
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column(payload, sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            *extra,
        )
        op.create_index(f"ix_{table}_owner_id", table, ["owner_id"])


def downgrade() -> None:
    op.drop_table("scanner_v2_runs")
    op.drop_table("scanner_v2_saved")

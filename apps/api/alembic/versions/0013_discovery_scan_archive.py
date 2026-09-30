"""Add reversible owner-scoped discovery scan archival."""

import sqlalchemy as sa
from alembic import op

revision = "0013_discovery_scan_archive"
down_revision = "0012_sprint2_scan_discover"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "discovery_scan_runs",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_discovery_scan_runs_archived_at",
        "discovery_scan_runs",
        ["archived_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_discovery_scan_runs_archived_at",
        table_name="discovery_scan_runs",
    )
    op.drop_column("discovery_scan_runs", "archived_at")

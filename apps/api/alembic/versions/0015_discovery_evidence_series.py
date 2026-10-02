"""Retain bounded immutable evidence series for matched scan results."""

import sqlalchemy as sa
from alembic import op

revision = "0015_discovery_evidence_series"
down_revision = "0014_discovery_temporal_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discovery_scan_evidence_series",
        sa.Column(
            "match_id",
            sa.Uuid(),
            sa.ForeignKey("discovery_scan_matches.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("discovery_scan_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("user_id", "run_id", "match_id", name="uq_discovery_chart_identity"),
    )
    for column in ("user_id", "run_id", "instrument_id"):
        op.create_index(
            f"ix_discovery_scan_evidence_series_{column}",
            "discovery_scan_evidence_series",
            [column],
        )


def downgrade() -> None:
    op.drop_table("discovery_scan_evidence_series")

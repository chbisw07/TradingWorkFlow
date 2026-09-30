"""Persist Sprint-2 scans, context, candidates, immutable history and explanations."""

import sqlalchemy as sa
from alembic import op

revision = "0012_sprint2_scan_discover"
down_revision = "0011_mcp_durable_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discovery_settings",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("values", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "discovery_scan_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("match_count", sa.Integer(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    for column in ("user_id", "provider", "status", "started_at"):
        op.create_index(f"ix_discovery_scan_runs_{column}", "discovery_scan_runs", [column])
    op.create_table(
        "discovery_scan_matches",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("discovery_scan_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    for column in ("user_id", "run_id", "instrument_id"):
        op.create_index(f"ix_discovery_scan_matches_{column}", "discovery_scan_matches", [column])
    op.create_table(
        "discovery_market_context",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("discovery_scan_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    for column in ("user_id", "run_id", "observed_at"):
        op.create_index(
            f"ix_discovery_market_context_{column}", "discovery_market_context", [column]
        )
    op.create_table(
        "discovery_episodes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("intent_key", sa.String(48), nullable=False),
        sa.Column("horizon_key", sa.String(24), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot_count", sa.Integer(), nullable=False),
        sa.Column("previous_episode_id", sa.Uuid(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("candidate_id", name="uq_discovery_episodes_candidate_identity"),
    )
    for column in (
        "user_id",
        "instrument_id",
        "intent_key",
        "horizon_key",
        "state",
        "opened_at",
        "updated_at",
    ):
        op.create_index(f"ix_discovery_episodes_{column}", "discovery_episodes", [column])
    op.create_index(
        "ix_discovery_episode_active_key",
        "discovery_episodes",
        ["user_id", "instrument_id", "intent_key", "horizon_key", "state"],
    )
    op.create_table(
        "discovery_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "episode_id",
            sa.Uuid(),
            sa.ForeignKey("discovery_episodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "episode_id", "sequence", name="uq_discovery_snapshots_episode_sequence"
        ),
    )
    for column in ("episode_id", "user_id", "observed_at"):
        op.create_index(f"ix_discovery_snapshots_{column}", "discovery_snapshots", [column])
    op.create_table(
        "discovery_transitions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "episode_id",
            sa.Uuid(),
            sa.ForeignKey("discovery_episodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    for column in ("episode_id", "user_id", "occurred_at"):
        op.create_index(f"ix_discovery_transitions_{column}", "discovery_transitions", [column])
    op.create_table(
        "discovery_llm_explanations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column(
            "snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("discovery_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    for column in ("candidate_id", "snapshot_id", "user_id", "generated_at"):
        op.create_index(
            f"ix_discovery_llm_explanations_{column}", "discovery_llm_explanations", [column]
        )


def downgrade() -> None:
    op.drop_table("discovery_llm_explanations")
    op.drop_table("discovery_transitions")
    op.drop_table("discovery_snapshots")
    op.drop_table("discovery_episodes")
    op.drop_table("discovery_market_context")
    op.drop_table("discovery_scan_matches")
    op.drop_table("discovery_scan_runs")
    op.drop_table("discovery_settings")

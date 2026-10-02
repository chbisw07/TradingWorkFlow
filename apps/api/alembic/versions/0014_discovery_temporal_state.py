"""Add scan-driven temporal observation state without rewriting legacy history."""

import sqlalchemy as sa
from alembic import op

revision = "0014_discovery_temporal_state"
down_revision = "0013_discovery_scan_archive"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discovery_comparison_scopes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("descriptor", sa.JSON(), nullable=False),
        sa.UniqueConstraint("user_id", "digest", name="uq_discovery_scope_owner_digest"),
    )
    op.create_index(
        "ix_discovery_comparison_scopes_user_id", "discovery_comparison_scopes", ["user_id"]
    )
    op.create_table(
        "discovery_temporal_lanes",
        sa.Column(
            "scope_id",
            sa.Uuid(),
            sa.ForeignKey("discovery_comparison_scopes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("next_sequence", sa.Integer(), nullable=False),
        sa.Column("finalized_sequence", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("last_as_of", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_discovery_temporal_lanes_user_id", "discovery_temporal_lanes", ["user_id"])
    op.create_table(
        "discovery_scan_admissions",
        sa.Column("run_id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "scope_id",
            sa.Uuid(),
            sa.ForeignKey("discovery_comparison_scopes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("admitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_digest", sa.String(64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("scope_id", "sequence", name="uq_discovery_admission_scope_sequence"),
        sa.UniqueConstraint("user_id", "request_key", name="uq_discovery_admission_request"),
    )
    op.create_index(
        "ix_discovery_scan_admissions_user_id", "discovery_scan_admissions", ["user_id"]
    )
    op.create_index(
        "ix_discovery_scan_admissions_scope_id", "discovery_scan_admissions", ["scope_id"]
    )
    op.create_index(
        "ix_discovery_admission_owner_status",
        "discovery_scan_admissions",
        ["user_id", "status"],
    )
    with op.batch_alter_table("discovery_episodes") as batch_op:
        batch_op.add_column(
            sa.Column(
                "comparison_scope_id",
                sa.Uuid(),
                sa.ForeignKey("discovery_comparison_scopes.id"),
                nullable=True,
            )
        )
        batch_op.create_index("ix_discovery_episodes_comparison_scope_id", ["comparison_scope_id"])
    op.create_table(
        "discovery_active_slots",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column(
            "scope_id",
            sa.Uuid(),
            sa.ForeignKey("discovery_comparison_scopes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("instrument_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "episode_id",
            sa.Uuid(),
            sa.ForeignKey("discovery_episodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.UniqueConstraint("episode_id", name="uq_discovery_active_slot_episode"),
    )
    op.create_table(
        "discovery_observations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "scope_id", sa.Uuid(), sa.ForeignKey("discovery_comparison_scopes.id"), nullable=False
        ),
        sa.Column(
            "episode_id",
            sa.Uuid(),
            sa.ForeignKey("discovery_episodes.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("candidate_id", sa.Uuid(), nullable=True),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("run_sequence", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_data_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_sample_key", sa.String(128), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "user_id",
            "scope_id",
            "instrument_id",
            "run_id",
            name="uq_discovery_observation_idempotency",
        ),
    )
    for column in (
        "user_id",
        "scope_id",
        "episode_id",
        "candidate_id",
        "run_id",
        "instrument_id",
        "kind",
        "observed_at",
    ):
        op.create_index(f"ix_discovery_observations_{column}", "discovery_observations", [column])
    op.create_index(
        "ix_discovery_observation_episode_sequence",
        "discovery_observations",
        ["user_id", "episode_id", "run_sequence"],
    )
    op.create_index(
        "ix_discovery_observation_run",
        "discovery_observations",
        ["user_id", "run_id", "instrument_id"],
    )
    op.create_table(
        "discovery_projection_checkpoints",
        sa.Column(
            "episode_id",
            sa.Uuid(),
            sa.ForeignKey("discovery_episodes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("through_sequence", sa.Integer(), nullable=False),
        sa.Column("prefix_digest", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_discovery_projection_checkpoints_user_id",
        "discovery_projection_checkpoints",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_table("discovery_projection_checkpoints")
    op.drop_table("discovery_observations")
    op.drop_table("discovery_active_slots")
    with op.batch_alter_table("discovery_episodes") as batch_op:
        batch_op.drop_index("ix_discovery_episodes_comparison_scope_id")
        batch_op.drop_column("comparison_scope_id")
    op.drop_table("discovery_scan_admissions")
    op.drop_table("discovery_temporal_lanes")
    op.drop_table("discovery_comparison_scopes")

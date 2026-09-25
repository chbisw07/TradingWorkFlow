"""Personal preferences and profiles; downgrade deletes only settings data."""

import sqlalchemy as sa
from alembic import op

revision = "0003_preferences"
down_revision = "0002_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "preference_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("values", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_preference_profiles"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_preference_profiles_user_id_users"
        ),
    )
    op.create_index("ix_preference_profiles_user_id", "preference_profiles", ["user_id"])
    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("values", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("active_profile_id", sa.Uuid(), nullable=True),
        sa.Column("applied_profile_revision", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id", name="pk_user_preferences"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_preferences_user_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["active_profile_id"],
            ["preference_profiles.id"],
            name="fk_user_preferences_active_profile_id_preference_profiles",
        ),
    )
    op.create_table(
        "preference_changes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("target", sa.String(64), nullable=False),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_preference_changes"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_preference_changes_user_id_users"
        ),
    )
    op.create_index("ix_preference_changes_user_id", "preference_changes", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_preference_changes_user_id", table_name="preference_changes")
    op.drop_table("preference_changes")
    op.drop_table("user_preferences")
    op.drop_index("ix_preference_profiles_user_id", table_name="preference_profiles")
    op.drop_table("preference_profiles")

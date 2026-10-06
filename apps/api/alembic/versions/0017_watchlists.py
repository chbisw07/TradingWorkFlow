"""Owner-scoped watchlists, canonical items, notes and activity."""

import sqlalchemy as sa
from alembic import op

revision = "0017_watchlists"
down_revision = "0016_dhan_market_data_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlists",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.String(240), nullable=False),
        sa.Column("favorite", sa.Boolean(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("ordering", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_watchlists_owner_id", "watchlists", ["owner_id"])
    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("watchlist_id", sa.Uuid(), sa.ForeignKey("watchlists.id"), nullable=False),
        sa.Column("instrument_id", sa.Uuid(), nullable=False),
        sa.Column("instrument", sa.JSON(), nullable=False),
        sa.Column("source", sa.JSON(), nullable=False),
        sa.Column("ordering", sa.Integer(), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("watchlist_id", "instrument_id"),
    )
    op.create_table(
        "watchlist_notes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("watchlist_id", sa.Uuid(), sa.ForeignKey("watchlists.id"), nullable=False),
        sa.Column("text", sa.String(2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "watchlist_activity",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("watchlist_id", sa.Uuid(), sa.ForeignKey("watchlists.id"), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for table in ("watchlist_items", "watchlist_notes", "watchlist_activity"):
        op.create_index(f"ix_{table}_watchlist_id", table, ["watchlist_id"])


def downgrade() -> None:
    for table in ("watchlist_activity", "watchlist_notes", "watchlist_items", "watchlists"):
        op.drop_table(table)

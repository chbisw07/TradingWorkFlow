"""Durable generation-bound MCP operation admission and drain records."""

import sqlalchemy as sa
from alembic import op

revision = "0009_mcp_operation_permits"
down_revision = "0008_mcp_cleanup_claim"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_operations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("connection_id", sa.Uuid(), sa.ForeignKey("mcp_connections.id"), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("session_hash", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("worker_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("cleanup_state", sa.String(24), nullable=False),
        sa.Column("outcome", sa.String(40)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_mcp_operations_connection_id", "mcp_operations", ["connection_id"])


def downgrade() -> None:
    # Never erase evidence that an old worker may still be using credentials.
    if op.get_bind().scalar(
        sa.text("SELECT COUNT(*) FROM mcp_operations WHERE state != 'COMPLETE'")
    ):
        raise RuntimeError("Resolve outstanding MCP operation permits before downgrade")
    op.drop_index("ix_mcp_operations_connection_id", table_name="mcp_operations")
    op.drop_table("mcp_operations")

"""Add generic MCP connection and encrypted authentication records."""

import sqlalchemy as sa
from alembic import op

revision = "0007_mcp_connections"
down_revision = "0006_order_intents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_connections",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider_id", sa.String(64), nullable=False),
        sa.Column("config_fingerprint", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("health", sa.String(16), nullable=False),
        sa.Column("secret_id", sa.Uuid(), nullable=True),
        sa.Column("tools_json", sa.Text(), nullable=False),
        sa.Column("error", sa.String(40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_mcp_connections_owner_id", "mcp_connections", ["owner_id"])
    op.create_table(
        "mcp_secrets",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("connection_id", sa.Uuid(), sa.ForeignKey("mcp_connections.id"), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("revoke_pending", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_mcp_secrets_connection_id", "mcp_secrets", ["connection_id"])
    op.create_table(
        "mcp_oauth_attempts",
        sa.Column("state_hash", sa.String(64), primary_key=True, nullable=False),
        sa.Column("connection_id", sa.Uuid(), sa.ForeignKey("mcp_connections.id"), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_hash", sa.String(64), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("verifier_ciphertext", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_mcp_oauth_attempts_connection_id", "mcp_oauth_attempts", ["connection_id"])


def downgrade() -> None:
    op.drop_table("mcp_oauth_attempts")
    op.drop_table("mcp_secrets")
    op.drop_table("mcp_connections")

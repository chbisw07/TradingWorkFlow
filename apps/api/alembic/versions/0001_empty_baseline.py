"""Establish migration history without creating business tables.

Revision ID: 0001_empty_baseline
Revises: None
"""

revision: str = "0001_empty_baseline"
down_revision: str | None = None
branch_labels: tuple[str, ...] | None = None
depends_on: str | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

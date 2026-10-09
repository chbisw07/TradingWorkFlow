"""System-global instrument metadata current state and refresh audit history."""

import sqlalchemy as sa
from alembic import op

revision = "0019_instrument_metadata"
down_revision = "0018_scanner_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instrument_metadata",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("exchange", sa.String(16), nullable=False),
        sa.Column("symbol", sa.String(128), nullable=False),
        sa.Column("series", sa.String(32), nullable=False),
        sa.Column("isin", sa.String(32), nullable=False),
        sa.Column("company_name", sa.String(256), nullable=False),
        sa.Column("listing_date", sa.Date(), nullable=True),
        sa.Column("metadata_schema_version", sa.String(16), nullable=False),
        sa.Column("dataset_run_id", sa.String(64), nullable=False),
        sa.Column("dataset_generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("instrument_kind", sa.String(32), nullable=False),
        sa.Column("underlying_symbol", sa.String(128), nullable=True),
        sa.Column("underlying_resolution_method", sa.String(64), nullable=True),
        sa.Column("macro_sector_code", sa.String(32), nullable=True),
        sa.Column("macro_sector", sa.String(128), nullable=True),
        sa.Column("sector_code", sa.String(32), nullable=True),
        sa.Column("basic_industry_code", sa.String(32), nullable=True),
        sa.Column("basic_industry", sa.String(128), nullable=True),
        sa.Column("nse_classification_source", sa.String(64), nullable=True),
        sa.Column("nse_classification_as_of", sa.Date(), nullable=True),
        sa.Column("sector", sa.String(128), nullable=True),
        sa.Column("sector_source", sa.String(64), nullable=True),
        sa.Column("sector_as_of", sa.Date(), nullable=True),
        sa.Column("industry_code", sa.String(32), nullable=True),
        sa.Column("industry", sa.String(160), nullable=True),
        sa.Column("industry_source", sa.String(64), nullable=True),
        sa.Column("industry_as_of", sa.Date(), nullable=True),
        sa.Column("market_cap", sa.BigInteger(), nullable=True),
        sa.Column("market_cap_currency", sa.String(8), nullable=True),
        sa.Column("market_cap_source", sa.String(64), nullable=True),
        sa.Column("market_cap_as_of", sa.Date(), nullable=True),
        sa.Column("market_cap_rank", sa.Integer(), nullable=True),
        sa.Column("market_cap_category", sa.String(16), nullable=True),
        sa.Column("market_cap_category_method", sa.String(96), nullable=True),
        sa.Column("twf_cap_tier", sa.String(16), nullable=True),
        sa.Column("twf_cap_tier_method", sa.String(96), nullable=True),
        sa.Column("context_benchmark", sa.String(128), nullable=True),
        sa.Column("context_benchmark_symbol", sa.String(64), nullable=True),
        sa.Column("benchmark_mapping_source", sa.String(64), nullable=True),
        sa.Column("benchmark_mapping_basis", sa.String(192), nullable=True),
        sa.Column("resolution_status", sa.String(32), nullable=False),
        sa.Column("classification_completeness", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Numeric(6, 5), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("present_in_latest_snapshot", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("exchange", "symbol"),
        sa.UniqueConstraint("isin"),
        sa.CheckConstraint("market_cap IS NULL OR market_cap > 0", name="market_cap_positive"),
        sa.CheckConstraint("market_cap_rank IS NULL OR market_cap_rank > 0", name="rank_positive"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )
    op.create_index(
        "ix_instrument_metadata_dataset_run_id", "instrument_metadata", ["dataset_run_id"]
    )
    op.create_index("ix_instrument_metadata_sector", "instrument_metadata", ["sector"])
    op.create_index("ix_instrument_metadata_industry", "instrument_metadata", ["industry"])
    op.create_index(
        "ix_instrument_metadata_market_cap_category", "instrument_metadata", ["market_cap_category"]
    )
    op.create_index("ix_instrument_metadata_twf_cap_tier", "instrument_metadata", ["twf_cap_tier"])
    op.create_index(
        "ix_instrument_metadata_context_benchmark",
        "instrument_metadata",
        ["context_benchmark_symbol"],
    )
    op.create_index(
        "ix_instrument_metadata_present", "instrument_metadata", ["present_in_latest_snapshot"]
    )

    op.create_table(
        "instrument_metadata_refreshes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("metadata_schema_version", sa.String(16), nullable=True),
        sa.Column("dataset_run_id", sa.String(64), nullable=True),
        sa.Column("dataset_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("import_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("import_completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_file", sa.String(512), nullable=False),
        sa.Column("source_summary_file", sa.String(512), nullable=True),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("imported_rows", sa.Integer(), nullable=False),
        sa.Column("inserted_rows", sa.Integer(), nullable=False),
        sa.Column("updated_rows", sa.Integer(), nullable=False),
        sa.Column("unchanged_rows", sa.Integer(), nullable=False),
        sa.Column("removed_or_missing_rows", sa.Integer(), nullable=False),
        sa.Column("unresolved_rows", sa.Integer(), nullable=False),
        sa.Column("sector_coverage", sa.Numeric(6, 2), nullable=False),
        sa.Column("industry_coverage", sa.Numeric(6, 2), nullable=False),
        sa.Column("market_cap_coverage", sa.Numeric(6, 2), nullable=False),
        sa.Column("validation_status", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_summary", sa.String(512), nullable=True),
    )
    op.create_index(
        "ix_instrument_metadata_refreshes_status", "instrument_metadata_refreshes", ["status"]
    )
    op.create_index(
        "ix_instrument_metadata_refresh_dataset_status",
        "instrument_metadata_refreshes",
        ["dataset_run_id", "status"],
    )
    op.create_index(
        "ix_instrument_metadata_refresh_completed",
        "instrument_metadata_refreshes",
        ["import_completed_at"],
    )


def downgrade() -> None:
    op.drop_table("instrument_metadata_refreshes")
    op.drop_table("instrument_metadata")

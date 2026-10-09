# TWF NSE Instrument Metadata Harvester

## Purpose

TradingWorkFlow needs durable, provider-neutral instrument metadata for future
sector context, instrument discovery, Watchlist enrichment, and Scanner metadata
joins. This utility creates a validated offline snapshot. It is not part of the
API request path and does not make Yahoo Finance a runtime dependency of Scanner
or Watchlists.

The project-owned V3.2 implementation was derived from the independently run
`nse_instrument_metadata_v3_1.py` utility. The stable executable deliberately has
no version suffix; format evolution is recorded in `metadata_schema_version` and
this document.

## Data model

Every row preserves NSE identity (`exchange`, `symbol`, `series`, `isin`, company
name and listing date), instrument relationship data, metadata attributes,
attribute-specific provenance, resolution state, retrieval time, and notes.

Important fields:

- `sector` and `industry` are the practical classification used by TWF.
- `market_cap` is the raw positive market-cap fact with currency, source, and
  as-of date.
- `market_cap_rank` is a full-snapshot relative rank. It is absent on `--limit`
  runs.
- `market_cap_category` is the familiar relative-rank grouping described below.
- `twf_cap_tier` is TWF analytical metadata with an additional micro-cap tier.
- `context_benchmark` is an exact analytical mapping for sector context. It is
  not official index membership.
- `metadata_schema_version`, `dataset_run_id`, and `dataset_generated_at`
  identify one generated snapshot. Every row in the snapshot has the same
  values.
- Source/as-of dates such as `sector_as_of`, `industry_as_of`, and
  `market_cap_as_of` remain independent of dataset identity; `retrieved_at` is
  an offset-aware operational timestamp.

Attribute provenance is not collapsed into a generic source. The output retains
`sector_source/sector_as_of`, `industry_source/industry_as_of`,
`market_cap_source/market_cap_as_of`, NSE classification source/as-of, and
benchmark mapping source/basis.

Operational timezone is `Asia/Kolkata`. Dataset, retrieval, checkpoint, summary,
and console-log timestamps are offset-aware and human-readable for TWF
operations. Date-only source/as-of fields use the India local calendar date.
Historical offset-aware UTC snapshots remain valid inputs.

## Sources

1. The official NSE bulk equity list owns the universe, symbol, and ISIN
   identity.
2. An optional NSE/NSE Indices bulk classification CSV may provide
   authoritative classification, matched by ISIN first and symbol second.
3. Yahoo Finance is an optional offline fallback/enrichment source for sector,
   industry, market cap, and market-cap currency.
4. Missing information remains explicit `UNKNOWN`/`UNRESOLVED` data.

The NSE per-symbol quote-equity endpoint is intentionally not used. It is not
reliable for bulk automation. Yahoo failures are recorded per row and do not
terminate the complete run.

Install the standalone network dependencies in a dedicated environment:

```bash
python -m pip install -r tools/market_metadata/requirements.txt
```

Tests and local input processing do not require live Yahoo or NSE access.

## Market-cap semantics

`market_cap_category` is **not claimed to be an official AMFI-sourced
classification**. It is calculated from the snapshot's relative market-cap rank:

|    Rank | Category |
| ------: | -------- |
|   1–100 | `LARGE`  |
| 101–250 | `MID`    |
|    251+ | `SMALL`  |

The stored method is `RELATIVE_RANK_1_100_101_250_251_PLUS`.

`twf_cap_tier` uses:

|     Rank | TWF tier |
| -------: | -------- |
|    1–100 | `LARGE`  |
|  101–250 | `MID`    |
| 251–1000 | `SMALL`  |
|    1001+ | `MICRO`  |

Rights-entitlement instruments inherit company market-cap metadata and full-run
rank/category/tier from their resolved underlying. They do not receive an
independent company rank.

A run using `--limit` is a partial sample. Rank, category, and tier fields remain
blank, and the summary records `relative_ranking_applied: false`.

## Context benchmark

`context_benchmark` is a TWF analytical benchmark for future sector-context
assessment. It is not a statement that an instrument belongs to an official
index. Mapping uses exact normalized sector or industry values only; industry
mapping has priority. Loose substring matching is prohibited. For example,
`Credit Services` maps to `NIFTY FINANCIAL SERVICES` and can never be captured by
an `IT Services` substring rule.

## Runbook

Commands below are run from the repository root. Operational outputs default to
`var/market_metadata/` and are ignored by Git.

### Offline smoke test

```bash
python tools/market_metadata/nse_instrument_metadata.py \
  --input-csv tools/market_metadata/tests/fixtures/nse_equity_universe.csv \
  --classification-csv tools/market_metadata/tests/fixtures/nse_classification.csv \
  --limit 5
```

### Small live smoke test

```bash
python tools/market_metadata/nse_instrument_metadata.py --limit 20 --use-yahoo
```

A limited run intentionally produces no relative ranks.

### Full monthly refresh

```bash
python tools/market_metadata/nse_instrument_metadata.py --use-yahoo
```

The full run must pass the default universe floor and coverage checks before the
canonical CSV is replaced.

### Resume an interrupted run

```bash
python tools/market_metadata/nse_instrument_metadata.py --use-yahoo --resume
```

Checkpoint and partial CSV writes are atomic. Resume preserves the existing
`dataset_run_id`, loads each canonical row once, and skips completed identities.
Final post-processing and inherited-note insertion are idempotent.

### Market-cap-only refresh

```bash
python tools/market_metadata/nse_instrument_metadata.py \
  --seed-csv var/market_metadata/nse_instrument_metadata.csv \
  --refresh-market-cap-only \
  --use-yahoo
```

This preserves seed classification metadata, refreshes market caps, and
recomputes relative ranks after a full-universe refresh. A seed is mandatory.
The summary reports rows added/removed, changed sector/industry/market-cap,
changed category/tier, and newly resolved/unresolved rows.

### Optional authoritative classification

```bash
python tools/market_metadata/nse_instrument_metadata.py \
  --classification-csv /path/to/nse-classification.csv \
  --use-yahoo
```

## Outputs

The default output directory contains:

- `nse_instrument_metadata.csv` — canonical successful snapshot;
- `nse_instrument_unresolved.csv` — unresolved subset using the same schema;
- `nse_instrument_metadata_summary.json` — run identity, coverage, counts,
  validation, methods, source notes, and seed change summary;
- `.nse_instrument_metadata_checkpoint.json` — completed canonical identities
  plus the dataset run identity;
- `.nse_instrument_metadata.csv.partial` — atomic resume data while a run is in
  progress; removed after a successful final write.

The CSV and summary are operational artifacts and are not tracked. The small
fixtures under `tests/fixtures/` are the only checked-in data samples.

## Validation

Before replacing the final CSV, the utility validates:

- configurable full-universe row floor (default 2001, meaning greater than
  2000);
- unique symbols and unique non-empty ISINs;
- configurable sector and market-cap coverage;
- positive populated market caps;
- contiguous ranks and exact category/tier transitions;
- absence of rank/category/tier fields on partial runs;
- one complete dataset identity across all rows;
- absence of duplicate notes;
- exact context-benchmark derivation, including the Credit Services regression.

Unresolved records are reported as warnings rather than causing failure. A
failed final validation writes a resumable partial snapshot and a failure summary
but does not replace the canonical final CSV.

Coverage thresholds may be adjusted explicitly for controlled fixtures or known
source conditions:

```bash
--minimum-universe-size 2001 \
--min-sector-coverage 80 \
--min-market-cap-coverage 75
```

## Troubleshooting

- **NSE download failure:** download `EQUITY_L.csv` manually and pass
  `--input-csv`. Do not substitute the per-symbol quote API.
- **Yahoo missing:** install `yfinance` from the standalone requirements file.
- **Yahoo throttling or row failure:** retain the checkpoint, reduce request
  rate with `--yahoo-pause`, and resume. Failures remain in row notes.
- **Interrupted run:** use the same arguments and `--resume`. Do not delete the
  partial CSV or checkpoint.
- **Validation failure:** inspect `validation.errors` in the summary. The prior
  canonical CSV is preserved.
- **Seed migration:** V3/V3.1 `official_cap_category` fields are accepted as
  input aliases and emitted under the V3.2 `market_cap_category` names.

## Runtime database import

Harvesting and importing remain separate stages. After reviewing a successful
snapshot summary and applying API migration `0019_instrument_metadata`, import
the canonical snapshot explicitly from the API directory. Running here ensures
`Settings` loads the same `apps/api/.env` and database used by the API:

```bash
cd apps/api
.venv/bin/python -m twf.instrument_metadata.import_snapshot \
  ../../var/market_metadata/nse_instrument_metadata.csv \
  --summary ../../var/market_metadata/nse_instrument_metadata_summary.json
```

The importer independently validates schema version, required columns, row
identity, run identity, timestamps, market-cap values, ranks, categories, tiers,
and summary agreement before opening the database transaction. The snapshot is
upserted into system-global `instrument_metadata`; missing instruments are
retained with `present_in_latest_snapshot = false`. Replaying an already imported
`dataset_run_id` is idempotent. Every attempt is represented in
`instrument_metadata_refreshes` when database storage is available.

Authenticated bounded reads are available at:

- `GET /api/v1/instrument-metadata/status`;
- `GET /api/v1/instrument-metadata/{exchange}/{symbol}`;
- `GET /api/v1/instrument-metadata/by-isin/{isin}`;
- `POST /api/v1/instrument-metadata/lookup` for at most 100 unique symbols.

The normal monthly workflow is: run the harvester, inspect its summary, run the
importer, then inspect the status endpoint and representative symbol lookups.
Scanner, Watchlists, Discovery, and Market Context may consume the read service
in later increments; this foundation does not change those products yet.

## Version history

| Utility | Schema      | Change                                                                                                                                                                                                     |
| ------- | ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| V3.2    | 1           | Project-owned stable executable; neutral market-cap field names; dataset identity; idempotent inheritance notes; atomic partial/final output; validation and seed change audit                             |
| V3.1    | Pre-project | External source implementation retained as the V3.2 lineage: bulk NSE universe, optional classification/Yahoo enrichment, exact benchmark mapping, rights inheritance, rank guard, seed and resume support |

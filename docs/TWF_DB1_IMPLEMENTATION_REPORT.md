# DB-1 implementation and migration report

Current status: **R1/R2 fixes pass focused validation; overall remediation acceptance FAIL because the full SQLite gate remains red**. The original implementation and its scorecard below are historical; independent review subsequently failed R1/R2. See the [remediation report](TWF_DB1_REMEDIATION_REPORT.md) for the corrective pass. This does not freeze DB-1/OE-3 or authorize OE-4.

## A. Preflight

2026-10-15, branch `main`, HEAD `603131d07cf0d704d2dcd681fcab4456c4595b82`.
The initial worktree already contained the OE-3 Queue implementation and Trade UX amendment. Those changes were preserved. No commit, tag, or push was made. Preflight mapped Settings, SQLAlchemy sessions, Alembic 0001–0025, runtime SQLite, Order/Preview/Queue transactions, test fixtures, deployment and documentation before platform edits.

## B. Existing database architecture

The synchronous SQLAlchemy application previously defaulted to `sqlite+pysqlite:///./twf.db`; the active database was `apps/api/twf.db`. PostgreSQL/psycopg and dialect-portable migrations already existed, but prior PostgreSQL evidence was offline-only. Ordinary startup and `/ready` did not validate persistence/head compatibility. Several generic persistence fixtures forced SQLite even when a PostgreSQL URL was supplied.

## C. New database-role policy

PostgreSQL is the primary/default authoritative runtime. SQLite requires an explicit fallback URL. No default SQLite filename, automatic outage failover, dual-write, replication, or reverse synchronization exists. Missing configuration fails clearly. No Order/Queue lifecycle, authorization, inference, provider or Broker execution semantics changed.

## D. PostgreSQL configuration

Retains `TWF_DATABASE_URL` and synchronous `postgresql+psycopg`; existing dependency/lock policy is unchanged. Pool 5 + overflow 5, pool timeout 10s, connect timeout 5s, pre-ping, hidden parameters, READ COMMITTED. Each connection sets UTC explicitly. Live validation exposed that the PostgreSQL cluster inherited Asia/Kolkata; infrastructure now prevents this from changing TWF timestamp semantics.

Local runtime: Compose project `twf-db1`, service `postgres`, container `twf-db1-postgres-1`, PostgreSQL 16.13, loopback port 55432, persistent named volume `twf-db1_twf_postgres`. API role `twf_app` is not superuser and cannot create databases/roles. Bootstrap administrator and application credentials are separate, random, private, ignored and not reproduced here. Isolated gates use live PostgreSQL 16.15 via private Unix sockets; both are PostgreSQL 16.

## E. SQLite fallback policy

An explicitly configured SQLite URL remains supported and labelled `SQLite fallback` in readiness. The retained pre-cutover snapshot is a recovery point, not a current replica. No automatic PostgreSQL → SQLite exporter is implemented. After new PostgreSQL writes, reverting only the connection string would lose state and is not an acceptable rollback.

## F. PostgreSQL schema/migrations

Fresh live Alembic upgrade from zero reached `0025_twf_queue`. Isolated tests exercise downgrade to base/re-upgrade and recent Order/Preview/Queue migrations. Actual runtime schema inspection covers 46 tables including Alembic version, PKs/FKs/composite FKs, unique/check constraints, nullability, indexes and column types. No manual application schema bootstrap or historical migration rewrite was used. The existing pending 0025 Queue migration remains unchanged by DB-1.

## G. SQLite backup

The API/reload writer was stopped before backup; source SQLite was retained. Backup and manifest are mode 0400 with the filesystem immutable `i` flag, verified using `lsattr`.

- Source: `apps/api/twf.db`.
- Immutable backup: `var/backups/db1/20261015T065401Z/twf-pre-postgres.sqlite`.
- Manifest: same directory, `manifest.json`.
- Size: 100,544,512 bytes.
- SHA-256: `26d95bead54fba479e982965335d12ecc8a2d68f0b06ed6eefa96b26c1950f4f`.
- Integrity: `ok`; FK anomalies: 0; revision: `0025_twf_queue`.
- Retained original file hash before cutover: `1c63f76686fd845a0c5368218c94f47909ed2a96db05aec62eeeb0e5cd47b4bc`.

A SQLite backup file can have a different binary hash from its source because the backup API produces a new database image. Content, counts and keys—not equality of those two file hashes—establish migration fidelity. Each file's own hash is tracked separately.

## H. Data migration implementation

`twf.infrastructure.sqlite_backup` makes a new verified snapshot after explicit writer-stop acknowledgment. `twf.infrastructure.sqlite_migration` accepts an explicit snapshot/manifest and PostgreSQL destination from an environment variable. It validates the complete schema/table set and source constraints, requires an empty destination, locks destination tables, imports in FK dependency order, verifies every table and resets any integer sequences inside one transaction. Row failures abort without skipping, deduplication or partial acceptance.

Dry-run inventories without writing. Verify-only compares an imported/restored database in a read-only repeatable-read transaction. Table progress excludes secrets. Report files are created mode 0600 before importing. If report I/O fails after database commit, verify-only regenerates evidence; the tool does not incorrectly promise a filesystem/database distributed transaction. A restart after an import failure requires an empty destination; a successful import cannot accidentally be repeated.

## I. Real data verification

**45 application tables, 4,052 rows: all counts and canonical content hashes match.** All owner counts, null counts and canonical keys match too. No FK/unique violations were found. Full private inventories/hashes are in `var/db1/real-dry-run.json`, `var/db1/real-import-verification.json` and `var/db1/final-precutover-verification.json`; reports contain owner metadata and remain ignored.

| Table | SQLite rows | PostgreSQL rows | Content |
| --- | ---: | ---: | --- |
| `auth_sessions` | 49 | 49 | Match |
| `broker_accounts` | 1 | 1 | Match |
| `broker_attempts` | 1 | 1 | Match |
| `broker_order_intents` | 10 | 10 | Match |
| `broker_secrets` | 1 | 1 | Match |
| `dhan_market_data_connections` | 1 | 1 | Match |
| `dhan_market_data_secrets` | 1 | 1 | Match |
| `discovery_active_slots` | 17 | 17 | Match |
| `discovery_comparison_scopes` | 18 | 18 | Match |
| `discovery_episodes` | 53 | 53 | Match |
| `discovery_llm_explanations` | 0 | 0 | Match |
| `discovery_market_context` | 52 | 52 | Match |
| `discovery_observations` | 264 | 264 | Match |
| `discovery_projection_checkpoints` | 18 | 18 | Match |
| `discovery_scan_admissions` | 51 | 51 | Match |
| `discovery_scan_evidence_series` | 35 | 35 | Match |
| `discovery_scan_matches` | 89 | 89 | Match |
| `discovery_scan_runs` | 52 | 52 | Match |
| `discovery_settings` | 0 | 0 | Match |
| `discovery_snapshots` | 32 | 32 | Match |
| `discovery_temporal_lanes` | 18 | 18 | Match |
| `discovery_transitions` | 5 | 5 | Match |
| `fno_liquidity_cache` | 1 | 1 | Match |
| `instrument_metadata` | 2603 | 2603 | Match |
| `instrument_metadata_refreshes` | 1 | 1 | Match |
| `manual_order_previews` | 0 | 0 | Match |
| `mcp_connections` | 23 | 23 | Match |
| `mcp_oauth_attempts` | 7 | 7 | Match |
| `mcp_operations` | 458 | 458 | Match |
| `mcp_secrets` | 12 | 12 | Match |
| `preference_changes` | 0 | 0 | Match |
| `preference_profiles` | 0 | 0 | Match |
| `scanner_v2_derivative_templates` | 1 | 1 | Match |
| `scanner_v2_runs` | 135 | 135 | Match |
| `scanner_v2_saved` | 0 | 0 | Match |
| `twf_order_events` | 0 | 0 | Match |
| `twf_orders` | 0 | 0 | Match |
| `twf_queue_entries` | 0 | 0 | Match |
| `twf_queue_events` | 0 | 0 | Match |
| `user_preferences` | 0 | 0 | Match |
| `users` | 1 | 1 | Match |
| `watchlist_activity` | 24 | 24 | Match |
| `watchlist_items` | 14 | 14 | Match |
| `watchlist_notes` | 0 | 0 | Match |
| `watchlists` | 4 | 4 | Match |

Real Order/Preview/Queue tables were empty. This is recorded honestly; no artificial trading records were inserted into the user's runtime to make the migration appear more complete. Representative isolated fixtures cover Equity/Futures/Option Orders, READY/QUEUED states, READY/HELD Queue entries, used/unused Previews, histories and watchlists. Real scanner history is covered by the full-content comparison.

## J. Numeric/date/JSON fidelity

UUID identities and opaque IDs/links are preserved. NUMERIC is read through decimal text and Decimal, never a new Python binary-float conversion. Integer values must be integral; fractional SQLite values cause refusal. PostgreSQL precision/scale changes fail content comparison. Expiry dates are copied as exchange-calendar dates without timezone conversion. Naive persisted timestamps are UTC under existing TWF conventions; aware timestamps retain their instant. JSON uses semantic comparisons with arbitrary-precision numeric parsing; arrays, nulls, booleans, strings and nested content are preserved. SQL NULL is distinct from JSON null. Encrypted strings are copied unchanged with the existing master key retained.

The live synthetic migration fixture exercises precise Decimal values, option/futures identity and expiry, microsecond timestamps, large JSON integers/fractions, rollback/restart, non-empty destination rejection and a SERIAL ID of 42 followed by a generated ID of 43. Production PKs are UUID/text; there were no production sequences to reset.

## K. PostgreSQL OE-1 validation

The actual OE-1 suite now runs against the selected live PostgreSQL fixture. Ownership, actor/source authority, trusted exact identity, expiry, numeric bounds, READY immutability, CAS and state/event rollback remain unchanged and covered. The fault-injection test uses a PostgreSQL trigger on PostgreSQL, rather than executing SQLite trigger syntax. No frozen OE-1 runtime/domain file changed.

## L. PostgreSQL OE-2 validation

Preview ownership, exact terms/identity binding, TTL, single-use, catalog-change detection, rollback and atomic Preview → Order linkage run on PostgreSQL. The 50-round same-Preview race uses concurrent API requests/separate sessions and requires exactly one durable linked Order per Preview. Distinct-Preview global idempotency remains deferred. No frozen OE-2 runtime/domain file changed.

## M. PostgreSQL OE-3 validation

Existing admission, owner authority, one-entry-per-Order, READY → QUEUED atomicity, Hold/Release/version conflict and event tests run on PostgreSQL. Added independent service/session races inspect persisted Orders, Queue entries and both histories. Existing pending OE-3 cross-table coherence, event immutability and pagination findings remain a separate hardening task; DB-1 does not claim to resolve or freeze them.

## N. Concurrency results

Focused live PostgreSQL gate: 171 tests passed before the final importer test addition. It includes 50 same-Preview rounds, the existing 52 Queue API rounds plus 55 independent-service Queue admission rounds, and 10 rounds each of Hold/Hold, Hold/Release and Release/Release with stale-version checks. Exact one-Order/one-Entry outcomes and rollback assertions hold. READ COMMITTED and CAS/uniqueness suffice; no deadlock was observed in these probes. This is bounded evidence, not a claim that every future workload is deadlock-free. PostgreSQL FOR UPDATE/SKIP LOCKED was verified without adding worker logic.

## O. SQLite fallback validation

Full explicit SQLite fallback: **1,455 passed, 4 PostgreSQL-specific probes skipped**, 491.55s. This includes the SQLite-only BEGIN IMMEDIATE test skipped by the primary gate. Startup, authentication, migrations, Orders, Previews, Queue and other core paths remain covered.

## P. No-auto-failover proof

An unavailable PostgreSQL endpoint causes startup failure with initialization false, a safe error and no SQLite file. Missing URL fails configuration. Schema-behind-head fails startup until explicit upgrade. `/ready` reports PostgreSQL or explicit SQLite fallback, and returns 503 when persistence/head is unavailable. `/health` remains liveness only. No domain code or database utility implements dual-write/fallback selection.

## Q. Cutover procedure and observed runtime

Completed at 2026-10-15 08:00 UTC (13:30 IST), after both backend gates, frontend/browser checks and data/restore verification. Only `TWF_DATABASE_URL` changed in private `apps/api/.env`; all other parsed settings, including credential master key, were compared and preserved. Previous private configuration is retained mode 0400 at `var/backups/db1/apps-api-env-pre-db1`.

The API and web dev processes were restarted. Observed `/ready`: HTTP 200, `database_backend=PostgreSQL`, `database_status=ready`, `database_checked=true`. `/health`, API status and web login return 200. Database session timezone is UTC; application role is not superuser. Read-only runtime checks find four watchlists and 135 scanner runs; original empty Order/Queue tables remain empty. Original SQLite SHA-256 is unchanged after PostgreSQL startup/read checks.

Evidence: `var/db1/runtime-cutover-verification.json`, `var/db1/runtime-pids.json`, private runtime logs. The new-order/write/reload journeys use isolated PostgreSQL and synthetic providers, so no test trade intent or live broker order contaminates the migrated user database. Normal local app is available at `http://localhost:3000`.

## R. Rollback procedure

Before PostgreSQL accepts writes, keep the original SQLite authority if import/gates fail, using an explicit operator decision. After any PostgreSQL writes, stop writers, preserve a fresh PostgreSQL dump and repair/restore PostgreSQL at a verified recovery point. Do not switch to stale SQLite. An explicit SQLite recovery mode requires reconciliation and a working copy of the recovery snapshot, never writing the immutable backup. See the runbook for exact commands and boundaries.

## S. Backup strategy and restore rehearsal

`var/backups/db1/postgres-before-cutover.dump` is a private custom-format pg_dump. It was restored with pg_restore --exit-on-error into separate `twf_db1_restore`, owned by the application role. Verify-only compared all 45 restored tables to the immutable SQLite snapshot: all 4,052 rows/content hashes match. Evidence: `var/db1/postgres-restore-verification.json` and `var/db1/final-restore-verification.json`. Final verification uses type-tagged canonical hashes to distinguish JSON numbers from lookalike objects/arrays. Existing encrypted credentials require separate custody of the unchanged master key. Local manual dumps are not HA, PITR, off-host retention or automated disaster recovery; those remain deployment work.

## T. Performance and indexes

Seven isolated API rounds per backend, median milliseconds, synthetic providers and real persistence. These are rough local baselines, not a controlled throughput benchmark.

| Operation | SQLite | PostgreSQL |
| --- | ---: | ---: |
| Preview | 29.105 | 17.182 |
| Create READY | 47.747 | 37.148 |
| Queue admission | 21.292 | 15.998 |
| Hold | 19.692 | 14.433 |
| Release | 18.800 | 12.573 |
| Orders list | 13.896 | 10.017 |
| Queue list | 13.008 | 10.375 |
| Watchlists read | 15.441 | 10.707 |
| Scanner history read | 9.288 | 6.973 |

No unacceptable regression appears in this sample. ANALYZE/EXPLAIN on migrated data finds owner-created Orders, owner-FIFO Queue, owner/order/sequence history, owner/entry/sequence history and watchlist-owner indexes eligible. With current empty Order/Queue tables and four watchlists the optimizer appropriately chooses sequential scans. With sequential scans disabled for inspection only, all five expected indexes are used; production planner settings remain unchanged. No speculative indexes were added. Private schema/query-plan evidence is `var/db1/postgres-schema-and-plans.json`.

## U. Exact DB-1 files changed

- `.gitignore`
- `README.md`
- `compose.yaml`
- `apps/api/.env.example`
- `apps/api/src/twf/config/settings.py`
- `apps/api/src/twf/infrastructure/database.py`
- `apps/api/src/twf/infrastructure/sqlite_backup.py`
- `apps/api/src/twf/infrastructure/sqlite_migration.py`
- `apps/api/src/twf/main.py`
- `apps/api/src/twf/api/routes.py`
- `apps/api/src/twf/schemas.py`
- `apps/api/tests/conftest.py`
- `apps/api/tests/mcp_support.py`
- `apps/api/tests/test_backend_shell.py`
- `apps/api/tests/test_database_foundation.py`
- `apps/api/tests/test_database_db1.py`
- `apps/api/tests/test_fno_liquidity.py`
- `apps/api/tests/test_foundation.py`
- `apps/api/tests/test_instrument_metadata.py`
- `apps/api/tests/test_market_summary.py`
- `apps/api/tests/test_mcp_permits.py`
- `apps/api/tests/test_mcp_recovery.py`
- `apps/api/tests/test_service_scenarios.py`
- `apps/api/tests/test_twf_orders.py`
- `apps/web/playwright.config.ts`
- `apps/web/tests/browser/auth-test-server.mjs`
- `tools/test-postgres.sh`
- `docs/TWF_DATABASE_ARCHITECTURE.md`
- `docs/TWF_SQLITE_TO_POSTGRES_MIGRATION_RUNBOOK.md`
- `docs/TWF_DB1_IMPLEMENTATION_REPORT.md`
- `docs/TWF_DOCUMENTATION_INDEX.md`
- `docs/TWF_LOCAL_DEVELOPMENT_SETUP_LINUX.md`

Private deployment files: `.env.db1`, the runtime database URL in `apps/api/.env`, backup/evidence files under ignored `var/backups/db1` and `var/db1`. Credentials are not part of the source diff.

Pre-existing OE-3/Trade files in the worktree are not DB-1 changes. In particular, 0025, Queue service/contracts, Trade components/routes and their earlier tests were preserved. Generated next-env.d.ts is restored to its pre-task content after validation.

## V. Backend/frontend/browser gates

| Gate | Result |
| --- | --- |
| Full live PostgreSQL | 1,457 passed; 1 SQLite-specific BEGIN IMMEDIATE probe skipped; 630.81s |
| OE-focused PostgreSQL | 171 passed before the last importer additions |
| Final DB-1 platform/fidelity/concurrency suite | 13 passed; 32.35s (includes the final JSON-type fingerprint check) |
| Full explicit SQLite fallback | 1,455 passed; 4 PostgreSQL-specific probes skipped; 491.55s |
| Frontend unit tests | 294 passed |
| Frontend production build | Passed |
| PostgreSQL-backed Chromium browser smoke | 12 passed; widths 390 and 1440 |
| Changed-file mypy | 21 files, passed |
| Repository mypy | 15 pre-existing errors in 3 unchanged test files |
| Ruff / format | Passed; 230 files formatted |
| Python compileall / pip check | Passed |
| TypeScript / ESLint / Prettier | Passed |
| git diff --check | Passed |

Passing gate logs and benchmark evidence are retained privately in `var/db1/gates/`.
Browser smoke covers login/startup, Watchlists, Scanner watchlist selection, Trade Orders,
New Order → READY, Queue admission/Hold/Release, Positions reads and the retained Broker
New Order path. Providers are synthetic; the database is real PostgreSQL. The final
13-test platform run was repeated after the type-preserving hash refinement; it is
listed separately rather than double-counted into the earlier full-suite total.

Repository mypy has 15 pre-existing errors in unchanged `test_option_chain.py`, `test_derivative_relative_volume.py`, and `test_derivative_templates.py`. They are not fixed in DB-1. New DB-1 typing must pass separately. The first PostgreSQL run exposed the host-timezone assumption and a test expecting an unmigrated fixture; both are corrected. Two MCP timing fixtures needed enough time for PostgreSQL round-trips to reach their intended assertions; stale-generation versus deadline tests remain distinct and production timeouts are untouched. Failed/interrupted exploratory runs are not counted as acceptance.

## W. Documentation

README database authority/setup/test instructions; database architecture; operator migration/backup/restore/cutover/fallback runbook; documentation index; local Linux guide policy override. Historical prior-phase SQLite/offline-PG evidence remains historical. OE-1/OE-2 remain frozen, OE-3 remains pending hardening, and OE-4/Queue worker/Broker handoff remain unimplemented.

## X. Required scorecard

```text
DB1_POSTGRES_PRIMARY = PASS
POSTGRES_DEFAULT_RUNTIME = PASS
SQLITE_EXPLICIT_FALLBACK = PASS
NO_AUTOMATIC_FAILOVER = PASS
NO_DUAL_WRITE = PASS
DATABASE_URL_CONFIG = PASS
POSTGRES_DRIVER = PASS
POOL_CONFIGURATION = PASS
SAFE_CREDENTIAL_HANDLING = PASS
FRESH_POSTGRES_ALEMBIC_UPGRADE = PASS
POSTGRES_MIGRATION_DOWNGRADE = PASS
ALEMBIC_HEAD_CHECK = PASS
SQLITE_BACKUP_CREATED = PASS
SQLITE_BACKUP_CHECKSUM = PASS
SQLITE_SOURCE_INVENTORY = PASS
SQLITE_TO_POSTGRES_DATA_MIGRATION = PASS
ROW_COUNTS_MATCH = PASS
CRITICAL_TABLE_CHECKSUMS_MATCH = PASS
FOREIGN_KEYS_VALID = PASS
UNIQUE_CONSTRAINTS_VALID = PASS
PRIMARY_KEYS_PRESERVED = PASS
POSTGRES_SEQUENCES_RESET = PASS
UUID_FIDELITY = PASS
DECIMAL_FIDELITY = PASS
EXPIRY_DATE_FIDELITY = PASS
TIMESTAMP_FIDELITY = PASS
JSON_FIDELITY = PASS
OE1_POSTGRES_VALIDATION = PASS
OE2_POSTGRES_VALIDATION = PASS
OE3_POSTGRES_VALIDATION = PASS
OE2_PREVIEW_POSTGRES_RACES = PASS
OE3_QUEUE_POSTGRES_RACES = PASS
OE3_HOLD_RELEASE_POSTGRES_CONCURRENCY = PASS
POSTGRES_TRANSACTION_ISOLATION = PASS
POSTGRES_CAS_SEMANTICS = PASS
POSTGRES_DEADLOCK_SAFE = PASS
SQLITE_FALLBACK_STARTUP = PASS
SQLITE_FALLBACK_CORE_COMPATIBILITY = PASS
POSTGRES_DOWN_NO_SQLITE_AUTO_WRITE = PASS
DB_BACKEND_DIAGNOSTIC = PASS
DB_HEALTH_CHECK = PASS
POSTGRES_BACKUP_DOCUMENTED = PASS
SQLITE_FALLBACK_DOCUMENTED = PASS
CUTOVER_RUNBOOK = PASS
ROLLBACK_RUNBOOK = PASS
POSTGRES_PRIMARY_BROWSER_SMOKE = PASS
OE1_FROZEN_SEMANTICS_INTACT = PASS
OE2_FROZEN_SEMANTICS_INTACT = PASS
OE3_REGRESSION_FREE = PASS
FULL_BACKEND_POSTGRES = PASS
FULL_BACKEND_SQLITE_COMPATIBILITY = PASS
FRONTEND_REGRESSION = PASS
BUILD = PASS
CHANGED_FILE_MYPY = PASS
REPOSITORY_MYPY_GATE = PRE_EXISTING_UNRELATED
RUFF = PASS
RUFF_FORMAT = PASS
COMPILE = PASS
PIP_CHECK = PASS
TYPESCRIPT = PASS
ESLINT = PASS
PRETTIER = PASS
GIT_DIFF_CHECK = PASS
DB1_STATUS = READY_FOR_INDEPENDENT_REVIEW
```

`OE3_REGRESSION_FREE` means current behavior/gates are preserved on PostgreSQL; it does not close the separate pending OE-3 findings. Full-suite skip details and the known mypy debt are recorded in section V.

## Y. Known limitations / carry-forward

- Local single PostgreSQL server and manual dumps are not HA/PITR/off-host backup or production TLS validation.
- SQLite is a stale pre-cutover recovery snapshot; no reverse export, automatic failover or dual-write.
- Source precision already lost in SQLite cannot be reconstructed; migration refuses new representational loss detectable by exact normalized comparison.
- Live provider/Broker execution is not used for tests. Browser fixtures use synthetic provider data with real PostgreSQL persistence.
- OE-3 coherence/history immutability/pagination findings remain pending; no Queue worker/scheduling/risk/Broker execution is added.
- Distinct-Preview global idempotency and future reconciliation remain outside DB-1.
- Existing unrelated mypy errors remain recorded above.

## Z. Final status

**DB1_STATUS = READY_FOR_INDEPENDENT_REVIEW.** PostgreSQL is the active authoritative runtime, migration and restore are verified, live primary/fallback gates pass, and OE-1/OE-2 semantics remain frozen. Independent review should target data fidelity, transaction races, failure/restart behavior, backup/recovery and no-auto-failover. DB-1 is not frozen here. No commit, tag or push; no OE-4 worker or Broker handoff.

# DB-1 Independent Adversarial Review

Date: 2026-10-15. Scope: PostgreSQL authority, migration fidelity, transactions, concurrency, recovery, and explicit SQLite fallback. **Review only; no production remediation.**

## A. Executive verdict

**DB1_REVIEW_STATUS = FAIL**  
**DB1_FREEZE_RECOMMENDATION = REMEDIATION_REQUIRED**

Two independently reproduced findings prevent acceptance:

1. **DB1-R1 — HIGH:** SQLite NUMERIC extraction can change a value and still report `IMPORTED_AND_VERIFIED`. The content verifier hashes the already-rounded extraction, so it cannot detect that loss.
2. **DB1-R2 — MEDIUM:** Queue admission can return a false `QUEUE_INVARIANT_FAILURE` under PostgreSQL READ COMMITTED. Separate reads observe the Order before another admission commits and its Queue Entry afterward. Durable admission remains atomic, but valid concurrent replay incorrectly fails.

The current migrated dataset independently matches: **45 application tables, 4,052 rows**, plus Alembic metadata. No current-data corruption, split-brain write, consumed-Preview orphan, duplicate Order, or duplicate Queue Entry was observed. These positive results do not excuse R1 or R2.

## B. Preflight and worktree preservation

Branch `main`; HEAD `603131d07cf0d704d2dcd681fcab4456c4595b82`. Existing DB-1 and OE-3/Trade modifications were present before review. Initial tracked and visible untracked files were individually SHA-256 fingerprinted. Review checks found no change to those files. No reset, stash, clean, checkout, commit, tag, or push was performed.

This report is the only new source-tree deliverable. Reproduction scripts, logs, inventories and dumps are private under ignored `var/db1/review/`. Disposable test files reside in `/tmp/twf-db1-review-tests`; a copy is retained with the evidence. Frontend checks used `/tmp/twf-db1-review-work` to avoid overwriting the running development server's build.

## C. Runtime authority verification

The real API's `/ready` returned HTTP 200 with `database_backend=PostgreSQL`, `database_status=ready`, and `database_checked=true`. Code inspection confirmed the label comes from the actual engine dialect. Independent SQL connections inspected the actual `twf` database, `twf_app` role, backend PID, session timezone, server version, tables and application-role sessions.

The authoritative container remains `twf-db1-postgres-1`, loopback port 55432, persistent volume `twf-db1_twf_postgres`, PostgreSQL 16.13. Independent backend gates used private socket-only PostgreSQL 16.15 clusters. Recovery attacks used a separate PostgreSQL 16.13 container/volume, subsequently removed. The actual runtime was never stopped for an outage test.

## D. Configuration and fail-closed review

Missing URL fails Settings validation. Environment overrides dotenv; explicit trusted Settings arguments override environment. Unsupported/malformed URLs are rejected by the existing validator. PostgreSQL authentication rejection, closed port, invalid hostname, and stopped disposable PostgreSQL all failed closed. A stale `twf.db` placed beside the failing app was unchanged; no substitute SQLite file appeared.

Explicit SQLite remains supported and identified as `SQLite fallback`. Startup checks the configured backend and head before setting `initialized`; it does not migrate or switch databases. In the outage rehearsal, `/health` stayed 200, `/ready` became 503 with PostgreSQL/unavailable, and `/ready` recovered to 200 after PostgreSQL restarted.

## E. PostgreSQL schema and migrations

Fresh isolated Alembic upgrades and upgrade/downgrade/re-upgrade gates passed through the published history and `0025_twf_queue`. Independently setting behind, future, and unknown revision identifiers caused startup refusal. Actual schema inventory includes 46 tables, all validated constraints, and the intended owner/history/FIFO indexes.

No historical migration file was rewritten by DB-1. The pre-existing OE-3 `0025_twf_queue.py` and metadata registration remain separate pending work. Startup's compatibility check is a revision check, not a general schema-tampering detector; it must not be advertised as full database attestation.

## F. SQLite backup review

Original `apps/api/twf.db` was retained. Its review-start SHA-256 was:

`1c63f76686fd845a0c5368218c94f47909ed2a96db05aec62eeeb0e5cd47b4bc`

The immutable snapshot is `var/backups/db1/20261015T065401Z/twf-pre-postgres.sqlite`, 100,544,512 bytes, SHA-256:

`26d95bead54fba479e982965335d12ecc8a2d68f0b06ed6eefa96b26c1950f4f`

Independent checks matched the manifest, mode 0400, filesystem immutable flag, integrity result `ok`, no FK violations and revision 0025. Opening the immutable snapshot for writing was denied without modifying it. Different original/backup binary hashes are expected for a newly generated SQLite backup image; logical content was compared separately.

Disposable attacks covered missing/unreadable source, corrupt database, FK corruption, unwritable destination and manifest-write failure. Each failed without deleting the source or creating a successful verification manifest. Partial failure artifacts are not accepted backups. The helper creates read-only files; filesystem immutability/WORM remains an explicit operator step as documented.

## G. Migration-tool adversarial review

A fresh import of the actual immutable backup into an isolated migrated PostgreSQL schema reproduced 45 tables/4,052 rows. Reimport/non-empty targets were refused. A constraint failure in a table ordered after populated tables rolled back earlier inserts. A fractional SQLite INTEGER was rejected rather than truncated. A source-file mutation after initial hashing caused rollback. Complete table/column inventory, FK dependency order, locking and transactional sequence restart were inspected.

The import transaction and restart behavior held in these probes. The **value-verification guarantee did not hold for high-precision NUMERIC**: R1 is a false-positive verification defect, not a partial-commit defect. Ordinary tagged JSON canonicalization distinguishes numbers, strings, arrays, objects, SQL NULL and JSON null; its correct tagging does not repair lossy input extraction.

## H. Independent data fidelity verification

The review did not reuse the migration utility's `_inventory`, `_value`, `_canonical` or `_serialize` to establish current-data fidelity. A separate positional-row serializer normalized schema types, read SQLite numeric values directly, applied declared numeric scale, preserved JSON arbitrary-precision numbers, and compared sorted row fingerprints.

All 46 tables matched, including all 45 application tables and 4,052 rows. IDs, owner references, secret ciphertext, Watchlists, scanner history, discovery data, metadata, MCP data and auth sessions were covered. Actual Order/Preview/Queue tables were verified empty, not populated artificially. Separate mock-provider fixtures exercised their populated lifecycle states.

A fresh PostgreSQL dump was restored into a new database. Independently comparing sorted `row_to_json(... )::text` results matched every table between PostgreSQL source and restore. No importer hash helper was used for that comparison either.

## I. Dates, timezones, Decimal and JSON

Exchange-calendar dates survived unchanged, including `2026-10-15` and leap day `2028-02-29`. Timestamp fixtures covered naive UTC, IST crossing the previous UTC date, DST-offset instants and microseconds. Explicit connection options requesting Asia/Kolkata, America/New_York and UTC all yielded UTC application sessions. The disposable container used a different timezone environment; restored application sessions still used UTC.

JSON fixtures preserved large integers, long fractional numbers, booleans, nested objects/arrays, empty objects, nulls, Unicode and escaped controls. Integer maximum 2,147,483,647 survived; fractional integer input failed atomically.

Numeric grid values `0.1`, `0.01`, `123456789.123456`, `1.230000`, `0.000001`, zero and a negative value survived their tested scales. The larger precision fixture failed fidelity while being reported verified. Details and scope are in R1 below. Current application NUMERIC columns and actual rows passed independent comparison; the failing `NUMERIC(20,5)`/`NUMERIC(20,6)` examples are isolated supported-type fixtures.

## J. Privileges and security

Actual application role flags are `rolsuper=false`, `rolcreatedb=false`, `rolcreaterole=false`. Equivalent restored application-role attempts to create a database or role failed with SQLSTATE `42501`. Normal restored application startup succeeded without administrator credentials. The application role owns its schema; this is not a separate restricted-runtime/migration-role deployment.

Master-key settings matched the retained pre-cutover configuration. Broker secret (1), Dhan secret (1), and MCP secrets (12) decrypted without exposing plaintext. A wrong key rejected them. Two expired, consumed MCP OAuth verifier records could not decrypt with the retained key, but the same records already failed in the immutable SQLite source with the old configuration; ciphertext and configuration were unchanged. This is a historical observation, not migration corruption.

Scanning tracked/visible source files for actual runtime password/master-key substrings found no matches. Private environment, dump, manifest and review-report paths are ignored. Evidence directories restrict access. No broker order was submitted to a real provider. The mock-provider browser Broker flow is explicitly synthetic.

## K. OE-1 transaction review

Frozen runtime/domain files remained unchanged. Existing focused/full PostgreSQL tests exercised trusted identities, source/owner boundaries, READY immutability, CAS and state/event atomicity. Additional independent SQL-level failures at Order insertion and audit-event insertion left no partial Order/history through the OE-2 transaction. The same preview remained reusable after rollback. No authority/state-model change was introduced for review.

## L. OE-2 concurrency review

**100 rounds**, cycling **2, 5 and 10 concurrent callers**, used a fresh Preview per round. Every Create response returned the same Order identity for that round. Raw persisted-table queries after every round required exactly one additional Order and one consumed Preview linked to an Order. All 100 rounds passed those assertions; no consumed Preview with zero Order and no duplicate Order occurred.

Independent failures before Order insertion, before event insertion and at final Preview linkage rolled back all related writes. A subsequent retry succeeded. Existing focused gates additionally cover TTL, ownership, catalog changes and exact contract/terms binding. Distinct-preview global idempotency remains deferred.

## M. OE-3 concurrency review

The same **100 rounds** independently admitted each READY Order using separate QueueService instances/sessions. Every round persisted exactly one Queue Entry, one Queue admission event and one Order → QUEUED event; the Order finished QUEUED. No durable atomicity violation occurred.

However, in the first series, rounds **15, 63, 66 and 69**, each with ten callers, produced one false `QUEUE_INVARIANT_FAILURE` each. A second independent 100-round series reproduced **six** such errors across rounds **9, 18, 54, 60 and 66**, again only in ten-way contention; all 200 durable outcomes and Preview responses remained correct. A controlled interleaving reproduced the cause deterministically. The API maps this error to HTTP 409. Thus the durable one-entry invariant passes, while the complete concurrent-replay interaction fails (R2).

Ten rounds each of ten-way Hold/Hold, mixed Hold/Release and Release/Release contention produced one successful state transition, one version increment and a coherent event sequence. Stale contenders did not create duplicate transitions. Independent failures after Queue insert, after Order transition and after Queue event insertion rolled everything back.

## N. Connection loss and deadlocks

A real PostgreSQL backend was terminated after an uncommitted test update; it rolled back. More directly, the Queue connection was terminated after its Order update. Queue Entry, Order transition and Queue event all rolled back; the Order remained READY, and subsequent admission succeeded.

Opposite-order concurrent row updates forced SQLSTATE `40P01`: one transaction committed, one failed, and the final two rows reflected exactly one complete update. Pool size two/zero overflow exhausted at the configured approximately ten-second timeout and recovered after connections were released. Pre-ping/outage recovery worked. These bounded probes do not establish global deadlock freedom or a generalized PostgreSQL retry policy.

## O. No failover, dual-write or split-brain path

Structural inspection traced one active engine/session factory through application initialization and Order/Queue writes. SQLite-specific retry logic does not create another backend. No backup write-on-commit, reverse synchronization, mirrored persistence or automatic fallback path was found.

Both absent/unavailable PostgreSQL scenarios with stale SQLite and recovery after a stopped disposable PostgreSQL were exercised. The actual retained SQLite file's content hash, size, modification time and sidecar inventory are compared before and after the PostgreSQL write probes. No real trading records were added to the authoritative user database for these checks.

## P. Dump, restore and recovery

A **new** private custom-format dump of the live PostgreSQL database was restored to an empty disposable database owned by `twf_app`. All table content matched independently; the restored app started and was ready. A truncated copy failed restore. Restoring into the non-empty restored database failed under `--exit-on-error`, rather than overwriting its data.

The runbook correctly separates pre-cutover failure from post-write recovery, prohibits returning to stale SQLite after new PostgreSQL writes, retains master-key custody and requires working copies for explicit fallback. The commands require the operator's actual project/env-file and destination context; isolated rehearsals substituted only review-specific names/credentials. No destructive command targeted the authoritative Compose project.

## Q. Container persistence and restart

A separate container used a named review-only volume. Stop/start and container removal/recreation without deleting that volume preserved a committed marker. Abrupt container termination with another transaction open retained the committed row and discarded the uncommitted row after restart. Restored application readiness recovered after an outage.

The review container and its volume were removed after evidence capture. The authoritative container/volume were left running. `docker compose down -v` remains a destructive operator command and was never run on the authoritative stack.

## R. Test-backend honesty and isolation

The independent race probe queried actual `version()`, `pg_backend_pid()` and `transaction_isolation` from its application's session factory. These were PostgreSQL, not a label. The launcher creates a new cluster/socket directory, no TCP listener, and a `twf_test_*` database; fixtures create/drop unique schemas. The full SQLite gate explicitly selected SQLite. Parallel isolated launchers completed without cross-schema teardown or runtime-data changes.

Some inherited test IDs still contain `sqlite` as a historical parameter label; selected Settings/session factories, not those labels, determine the actual backend. SQLite-specific locking tests remain explicit and are skipped on PostgreSQL. The fixture name is not used as evidence of backend selection.

## S. Regression gates

| Gate                                                                     | Independently observed result                                                       |
| ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------- |
| Full PostgreSQL, sequential rerun                                        | **1,458 passed, 1 skipped**, 657.39s                                                |
| Full SQLite, sequential rerun                                            | **1,455 passed, 4 skipped**, 478.69s                                                |
| Frontend unit tests                                                      | **294 passed**                                                                      |
| Frontend production build                                                | Passed in isolated source copy                                                      |
| PostgreSQL browser smoke                                                 | **12 passed**, widths 390 and 1440, 2.0 minutes                                     |
| Independent contention                                                   | 100 Preview rounds passed; 100 Queue durable outcomes passed; 4 false replay errors |
| Ten-way Hold/Release                                                     | 30 rounds passed                                                                    |
| Independent SQL/connection transaction faults                            | 4 passed                                                                            |
| Independent actual constraints, timezone overrides and fresh real import | 5 passed                                                                            |

The final consolidated adversarial suite completed with **24 passed and 4 deliberately failing assertions**, all four reproducing R1/R2 (numeric single-value/grid and Queue natural/controlled interleaving); no additional production defect appeared. Runtime: 101.03s.

The first full PostgreSQL and SQLite runs overlapped and each hit one MCP timeout failure. Both exact failures passed isolated reruns. Both complete suites were then rerun sequentially and passed; their results above are recorded separately. Failed exploratory runs are retained and are not counted as passing gates.

Browser journeys cover login, Watchlists, Scanner selection, Trade Orders/Positions, Equity/Futures/Option Preview → READY, Queue admission/Hold/Release, and the retained synthetic Broker flow. Neither browser nor backend probes called live broker execution.

## T. Static quality gates

Ruff, Ruff format check, compileall, pip check, changed-file mypy, TypeScript, ESLint, Prettier, frontend build and `git diff --check` passed. Repository mypy reports 15 errors in three unchanged test files. Those files are byte-identical to HEAD; an isolated committed-HEAD mypy run independently reproduced the same 15 errors in the same three files. The errors concern existing method assignments, missing annotations and typing in option-chain/derivative tests, not DB-1 changes.

## U. Attack matrix

Evidence paths below are relative to private `var/db1/review/`. PASS applies to the bounded attack described, not every possible future workload.

| Attack                           | Method                                                             | Expected                         | Observed                               | Result   | Severity   | Evidence                                            |
| -------------------------------- | ------------------------------------------------------------------ | -------------------------------- | -------------------------------------- | -------- | ---------- | --------------------------------------------------- |
| PostgreSQL unavailable           | Closed port, invalid host, stopped container                       | Fail closed                      | Startup refused; ready 503             | PASS     | —          | `fault-probes.log`, `recovery-result.json`          |
| Missing DB URL                   | Clear env/dotenv                                                   | Configuration error              | Validation failure                     | PASS     | —          | `fault-probes.log`                                  |
| Explicit SQLite fallback         | Full explicit-backend gate                                         | SQLite identified and supported  | Explicit SQLite path exercised         | PASS     | —          | `sqlite-full-serial.log`                            |
| Stale SQLite present             | Hash stale file beside failed PG app                               | No fallback write                | File unchanged                         | PASS     | —          | `fault-probes.log`                                  |
| Rejected credentials             | Deliberately wrong PG password                                     | No initialization/fallback       | Safe unavailable error                 | PASS     | —          | `security-results.json`                             |
| No dual-write                    | Trace active engine and compare retained SQLite                    | One authority                    | No second write path                   | PASS     | —          | `initial-sqlite.json`, `final-preservation.json`    |
| Fresh Alembic upgrade            | Empty disposable schema                                            | Head 0025                        | Full history works                     | PASS     | —          | `postgres-full-serial.log`                          |
| Behind/ahead/unknown head        | Change isolated revision                                           | Startup refused                  | All refused                            | PASS     | —          | `fault-probes.log`                                  |
| Downgrade/re-upgrade             | Full migration gate                                                | Coherent rebuild                 | Passed                                 | PASS     | —          | `postgres-full-serial.log`                          |
| Source backup verification       | Hash, mode, flag, integrity, FKs                                   | Verified immutable snapshot      | Matches; write-open denied             | PASS     | —          | `independent-runtime.json`, `security-results.json` |
| Backup failure paths             | Corrupt/unreadable/FK/unwritable/manifest fault                    | No verified success              | Exceptions; source retained            | PASS     | —          | `fault-probes.log`                                  |
| Partial import failure           | Later-table CHECK violation                                        | Entire import rolls back         | Earlier table empty                    | PASS     | —          | `fidelity-probes.log`                               |
| Non-empty destination            | Existing successful import                                         | Refuse                           | Refused                                | PASS     | —          | `schema-import-probes.log`                          |
| Migration replay                 | Repeat import                                                      | No overwrite/duplicates          | Refused                                | PASS     | —          | `fidelity-probes.log`                               |
| Source mutation                  | Append after initial source hashing                                | Roll back                        | Source-change rejection                | PASS     | —          | `fidelity-probes.log`                               |
| Row counts                       | Independent SELECT COUNT/inventory                                 | 45 tables, 4,052 rows            | Match                                  | PASS     | —          | `independent-runtime.json`                          |
| Independent content              | Separate serializer across all rows                                | Semantic match                   | All 46 tables match                    | PASS     | —          | `inspect_runtime.py`, `independent-runtime.json`    |
| Decimal fidelity                 | NUMERIC(20,5)/(20,6) fixtures                                      | Exact value or refusal           | Changed value accepted as verified     | **FAIL** | **HIGH**   | `numeric-adversary.json`, `numeric-grid.json`       |
| Integer fidelity                 | Max signed int, fractional source                                  | Preserve/reject respectively     | Preserved/rejected                     | PASS     | —          | `fidelity-probes.log`                               |
| Expiry date fidelity             | IST boundary and leap date                                         | Same calendar date               | Preserved                              | PASS     | —          | `fidelity-probes.log`                               |
| Timestamp/timezone               | UTC, IST, DST, microseconds; session overrides                     | Same instant, UTC session        | Preserved                              | PASS     | —          | `fidelity-probes.log`, `schema-import-probes.log`   |
| JSON fidelity                    | Nested/type/null/large-number fixtures                             | Preserve semantics               | Preserved                              | PASS     | —          | `fidelity-probes.log`                               |
| Encrypted secret fidelity        | Exact comparison and decrypt; wrong key                            | No rewrite; wrong key fails      | Matches; rejects wrong key             | PASS     | —          | `security-results.json`, `independent-runtime.json` |
| FK/unique/CHECK enforcement      | Orphan owner, duplicate linkage, bad state/version, broken Preview | Reject                           | All rejected                           | PASS     | —          | `schema-import-probes.log`                          |
| Role privileges                  | Flags; forbidden CREATE DATABASE/ROLE                              | Refuse privileged operations     | 42501                                  | PASS     | —          | `recovery-result.json`, `independent-runtime.json`  |
| OE-1 rollback                    | Fail Order/event SQL                                               | No partial aggregate/history     | Empty after failure                    | PASS     | —          | `transaction-faults.log`                            |
| OE-2 Preview races               | 100 rounds; 2/5/10 callers                                         | Exactly one linked Order         | 100/100 durable and response success   | PASS     | —          | `independent-100-races.json`                        |
| OE-3 Queue races                 | 100 rounds; separate services                                      | One Entry, coherent replay       | One durable Entry each; 4 false errors | **FAIL** | **MEDIUM** | `independent-races-complete.log`                    |
| Deterministic Queue interleaving | Commit competing admission between two reads                       | Replay existing Entry            | False invariant error                  | **FAIL** | **MEDIUM** | `fault-probes.log`                                  |
| Hold/Release races               | 30 ten-way rounds                                                  | One transition/version/event     | Passed                                 | PASS     | —          | `independent-probes.log`                            |
| Connection loss mid-transaction  | Terminate Queue backend after Order update                         | Complete rollback                | READY, zero Entry/events; retry works  | PASS     | —          | `transaction-faults.log`                            |
| Deadlock                         | Opposite lock order                                                | Bounded loser, no partial commit | 40P01; one full winner                 | PASS     | —          | `independent-probes.log`                            |
| Pool exhaustion                  | Hold all configured connections                                    | Bounded timeout/recovery         | About 10s, recovered                   | PASS     | —          | `independent-probes.log`                            |
| Fresh dump/restore               | New dump, empty isolated DB, independent row comparison            | Exact restore                    | 46/46 tables; app ready                | PASS     | —          | `recovery-result.json`                              |
| Corrupted dump                   | Truncated copy                                                     | Restore fails                    | Exit 1                                 | PASS     | —          | `recovery-result.json`                              |
| Non-empty restore                | Repeat --exit-on-error restore                                     | No silent overwrite              | Exit 1                                 | PASS     | —          | `recovery-result.json`                              |
| Container restart/recreation     | Named disposable volume                                            | Durable data survives            | Marker retained                        | PASS     | —          | `recovery-result.json`                              |
| Crash durability                 | Committed and open uncommitted transaction                         | Keep committed only              | Exactly committed row                  | PASS     | —          | `recovery-result.json`                              |
| SQLite unchanged after PG writes | Before/after hash/stat/sidecars                                    | Unchanged                        | Unchanged                              | PASS     | —          | `final-preservation.json`                           |
| /ready on DB outage              | Stop disposable PG under running app                               | 503, health 200                  | Observed; recovery 200                 | PASS     | —          | `recovery-result.json`                              |
| Backend honesty                  | Query engine sessions and PID; isolated launchers                  | Actual PG/explicit SQLite        | Verified                               | PASS     | —          | `independent-races-complete.log`, gate logs         |
| Secret exclusion                 | Exact secret substring scan, ignore checks                         | No tracked disclosure            | No matches                             | PASS     | —          | `security-results.json`                             |

## V. Findings by severity

### DB1-R1 — HIGH — Lossy numeric extraction is certified as an exact migration

Location: `apps/api/src/twf/infrastructure/sqlite_migration.py:127`, particularly the `CAST(... AS TEXT)` at line 130; the same extraction feeds source inventory and insertion.

Reproduction: create a read-only SQLite snapshot at the required revision with `amount NUMERIC(20,5)` containing `12345678901.12345`; create the matching empty PostgreSQL table; read SQLite through its original SQLAlchemy Numeric schema, import, then read PostgreSQL independently.

- Original stored SQLite value under `NUMERIC(20,5)` semantics: **12345678901.12345**.
- Migrated PostgreSQL value: **12345678901.12340**.
- Import result: **IMPORTED_AND_VERIFIED**.
- Independent equality: **false**.

SQLite's real-to-text CAST shortens the value before Decimal sees it. Hashing that shortened value on the source side and then importing it makes both inventories agree, masking a newly introduced loss. The six-decimal grid reproduces the same class of error. This is not merely unrecoverable precision already lost when SQLite first stored the value: the independently observed pre-migration schema value differs from the imported schema value.

Impact: the utility's exact-value verification can certify a corrupt transfer for a supported NUMERIC declaration. The actual 4,052-row migration independently matched; current mapped NUMERIC columns have smaller precision. No actual current monetary/Order corruption is claimed. Nevertheless the advertised general fidelity guarantee is false, so the migration foundation must not freeze until conversion/verification refuses or preserves such inputs. No repair was made.

### DB1-R2 — MEDIUM — READ COMMITTED admission replay mixes two snapshots

Location: `apps/api/src/twf/queue/service.py:143` through line 153. API error mapping: `apps/api/src/twf/api/twf_queue.py:60` (HTTP 409 mapping near that location).

Reproduction interleaving:

1. Caller A reads the Order while it is READY.
2. Caller B atomically commits its Queue Entry, Order → QUEUED and histories.
3. Caller A's next SELECT sees B's Queue Entry under READ COMMITTED.
4. A compares that Entry to its already-loaded READY Order and raises `QUEUE_INVARIANT_FAILURE`.

Natural contention reproduced four failures in the first 100 rounds and six in a second 100-round series, all in ten-way rounds. A review-only pause after `_owned_order` followed by a second service's admission reproduced the same error deterministically. Persisted state was coherent in every case. The error is neither the known OE-3 direct-SQL cross-table coherence gap nor an actual durable invariant violation.

Impact: a valid idempotent admission/replay is reported as inconsistent, confusing callers and operators. This is a PostgreSQL semantic interaction that two-caller passing tests did not establish as safe. Severity is **MEDIUM**, because no durable atomicity, ownership or exactly-once violation was observed. It is not described as lost data or duplicate execution. No repair was made.

## W. Limitations and non-findings

- Known OE-3 F1 cross-table direct-SQL coherence, F2 Queue event immutability and F3 pagination remain separate pending findings. They were not reclassified or fixed. R2 is a distinct service-read interleaving.
- The first overlapping full gates had MCP timeout flakes; exact isolated reruns passed. Their failed logs remain available. The final full sequential gates are recorded separately, not substituted with a handful of passing tests.
- Review-harness setup mistakes (one wrong column name, one placeholder count, a subprocess wrapper keyword, and cross-filesystem dependency hard-linking) were corrected only in private review tooling. They are not production findings; their exploratory outputs are retained where relevant.
- The two old consumed/expired OAuth verifier decryption failures predate migration. Active secret ciphertext and retained keys matched.
- Public CONNECT defaults and schema-owner power are not a complete production least-privilege/TLS design. No unrelated database's data was accessed. Required role flags and privilege-denial operations were checked in bounded scope.
- Current real Order/Preview/Queue tables were empty. Populated transaction and recovery evidence therefore uses isolated synthetic providers; it is not represented as a real trading-history migration.
- Local dumps do not establish HA, PITR, off-host retention or every possible OS/filesystem failure. The review did not certify other PostgreSQL major versions.
- No Queue worker, SUBMITTING processor, scheduling, risk engine, Broker handoff or reverse-sync implementation was added. No production repair was performed.

## X. Required scorecard

```text
DB1_REVIEW_STATUS = FAIL
POSTGRES_PRIMARY_REAL = PASS
SQLITE_NOT_PRIMARY = PASS
NO_AUTO_FAILOVER = PASS
NO_DUAL_WRITE = PASS
NO_SPLIT_BRAIN_PATH_FOUND = PASS
CONFIG_PRECEDENCE_SAFE = PASS
MISSING_URL_FAILS_CLOSED = PASS
BACKEND_DIAGNOSTIC_TRUTHFUL = PASS
READYNESS_DB_AWARE = PASS
SCHEMA_HEAD_ENFORCED = PASS
FRESH_POSTGRES_MIGRATION = PASS
MIGRATION_HISTORY_SAFE = PASS
DOWNGRADE_REUPGRADE = PASS
SOURCE_SQLITE_PRESERVED = PASS
IMMUTABLE_BACKUP_VERIFIED = PASS
BACKUP_FAILURE_SAFE = PASS
MIGRATION_EMPTY_DEST_REQUIRED = PASS
MIGRATION_PARTIAL_FAILURE_ATOMIC = PASS
MIGRATION_REPLAY_SAFE = PASS
TABLE_INVENTORY_COMPLETE = PASS
ROW_COUNTS_INDEPENDENTLY_MATCH = PASS
CONTENT_INDEPENDENTLY_MATCHES = PASS
HASH_CANONICALIZATION_SAFE = FAIL
UUID_FIDELITY = PASS
INTEGER_FIDELITY = PASS
DECIMAL_FIDELITY = FAIL
EXPIRY_DATE_FIDELITY = PASS
TIMESTAMP_FIDELITY = PASS
SESSION_TIMEZONE_UTC = PASS
JSON_FIDELITY = PASS
ENCRYPTED_SECRET_FIDELITY = PASS
POSTGRES_ROLE_LEAST_PRIVILEGE = PASS
POSTGRES_SCHEMA_CONSTRAINTS = PASS
CONNECTION_POOL_RESILIENCE = PASS
OE1_ATOMICITY_POSTGRES = PASS
OE1_CAS_POSTGRES = PASS
OE2_PREVIEW_ATOMICITY_POSTGRES = PASS
OE2_PREVIEW_100_ROUND_RACE = PASS
OE3_QUEUE_ATOMICITY_POSTGRES = PASS
OE3_QUEUE_100_ROUND_RACE = FAIL
OE3_HOLD_RELEASE_CONTENTION = PASS
CONNECTION_LOSS_ROLLBACK = PASS
DEADLOCK_HANDLING = PASS
READ_COMMITTED_SEMANTICS_SAFE = FAIL
POSTGRES_TESTS_TRULY_POSTGRES = PASS
SQLITE_TESTS_TRULY_SQLITE = PASS
TEST_DB_ISOLATION = PASS
PG_DUMP_RESTORE = PASS
RESTORED_APP_STARTUP = PASS
CORRUPT_BACKUP_FAILS = PASS
POST_CUTOVER_ROLLBACK_GUIDANCE_SAFE = PASS
SQLITE_UNCHANGED_AFTER_PG_WRITES = PASS
NO_REVERSE_SYNC = PASS
POSTGRES_CONTAINER_PERSISTENCE = PASS
POSTGRES_RESTART_DURABILITY = PASS
HOST_TIMEZONE_INDEPENDENCE = PASS
OE1_FROZEN_SEMANTICS_INTACT = PASS
OE2_FROZEN_SEMANTICS_INTACT = PASS
OE3_NOT_ACCIDENTALLY_FROZEN = PASS
OE4_NOT_IMPLEMENTED = PASS
FULL_BACKEND_POSTGRES = PASS
FULL_BACKEND_SQLITE = PASS
FRONTEND = PASS
BROWSER_POSTGRES = PASS
CHANGED_FILE_MYPY = PASS
REPO_MYPY = PRE_EXISTING_UNRELATED
RUFF = PASS
FORMAT = PASS
COMPILE = PASS
PIP_CHECK = PASS
TYPESCRIPT = PASS
ESLINT = PASS
PRETTIER = PASS
GIT_DIFF_CHECK = PASS
DB1_FREEZE_RECOMMENDATION = REMEDIATION_REQUIRED
```

`HASH_CANONICALIZATION_SAFE=FAIL` includes the lossy pre-hash numeric extraction in R1; JSON type tagging itself passed. `OE3_QUEUE_ATOMICITY_POSTGRES=PASS` records durable outcomes, while `OE3_QUEUE_100_ROUND_RACE=FAIL` records the four erroneous replay responses. `READ_COMMITTED_SEMANTICS_SAFE=FAIL` is limited to that demonstrated read interleaving, not a claim that CAS/transactions generally fail.

## Y. Freeze recommendation

**REMEDIATION_REQUIRED.** Consolidate R1 and R2 for a deliberate hardening pass. R1 alone is an unresolved data-fidelity/verifier defect and therefore blocks acceptance under the requested decision rule. The passing current-data comparison, live concurrency durability, restore rehearsal and regression gates do not override it. OE-1/OE-2 remain frozen; OE-3 remains pending its separate hardening; OE-4 is not started.

## Z. Commands and evidence

Commands ran from repository root unless stated. Private connection URLs were loaded from private configuration or generated by the disposable launcher; passwords were not placed in argv or this report.

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git diff --check
tools/test-postgres.sh -q
# From apps/api:
.venv/bin/python -m pytest --db-backend=sqlite -q
# Independent probes, restored from private evidence if /tmp is gone:
PYTHONPATH="$PWD/apps/api/tests" tools/test-postgres.sh \
  /tmp/twf-db1-review-tests/test_review.py -q -s
apps/api/.venv/bin/python var/db1/review/inspect_runtime.py
apps/api/.venv/bin/python var/db1/review/security_inspect.py
apps/api/.venv/bin/python var/db1/review/recovery_probe.py
apps/api/.venv/bin/python var/db1/review/static_gates.py
apps/api/.venv/bin/python var/db1/review/frontend_gates.py
/tmp/twf-db1-review-work/tools/test-postgres.sh --browser \
  tests/browser/twf-orders.spec.ts tests/browser/twf-queue.spec.ts \
  tests/browser/trade-workspace.spec.ts tests/browser/broker-orders.spec.ts \
  tests/browser/watchlists.spec.ts tests/browser/scanner-watchlist-unification.spec.ts \
  --project=chromium-390 --project=chromium-1440
```

The adversarial probe suite intentionally fails the numeric-loss and Queue-interleaving assertions until remediation; a red result there is reproduced evidence, not permission to alter production code. Both 100-round runs are retained: the first run has its log and explicit summary; the repeated run has the complete per-round JSON inventory. Assertions inspected durable state after every round despite the recorded Queue replay errors.

Primary private artifacts: `initial-files.json`, `initial-sqlite.json`, `independent-runtime.json`, `security-results.json`, `numeric-adversary.json`, `numeric-grid.json`, `first-series-summary.json`, `independent-100-races.json` (repeat series), `repeat-100-races.json`, `recovery-result.json`, `fresh-runtime.dump`, `fresh-import-review.json`, `final-preservation.json`; corresponding `*-probes.log`, `transaction-faults.log`, full/serial backend logs, frontend/static logs and `browser-postgres.log`. `review-tests/` contains the exact independent probes and isolation fixture.


## Subsequent R1/R2 remediation addendum — 2026-10-15

The original A–Z review above, its FAIL verdict, reproductions and scorecard are
preserved unchanged. A subsequent bounded remediation addresses DB1-R1 and DB1-R2
only; see [TWF_DB1_REMEDIATION_REPORT.md](TWF_DB1_REMEDIATION_REPORT.md) for the full
A–U corrective report, exact evidence, current-data qualifications and gates.

Both original failures were preserved as permanent tests and failed before the
fix. NUMERIC values are now certified against SQLite storage independently of
formatting, or explicitly refused. Queue replay now reads Entry and Order in one
statement and refreshes stale ORM state; real corruption still fails. Two
100-round PostgreSQL series each passed 563 Queue callers without false invariant
errors. Frozen OE-1/OE-2 and the separate OE-3 F1/F2/F3 findings remain unchanged.

Remediation validation: the full PostgreSQL gate passes (1,535 passed / 1 skipped),
but two full SQLite runs fail the existing MCP timeout durability case
`test_negative_after_commit_retains_marker_until_reconciled[sqlite-1-TIMEOUT]`
(1,463 passed / 1 failed / 72 skipped). Consequently the required overall status
is FAIL and readiness for focused re-review is NO. No MCP repair was made in this
bounded pass. This addendum does not retroactively turn the original review into
PASS, does not replace a focused independent re-review, and does not freeze DB-1
or OE-3.

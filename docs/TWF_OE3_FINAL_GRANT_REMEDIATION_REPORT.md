# OE-3 final grant remediation report

**Date:** 16 October 2026. **Decision:** `OE3_FINAL_GRANT_REMEDIATION_STATUS = PASS`; `OE3_READY_FOR_FINAL_REREVIEW = YES`. **Scope:** runtime DELETE/UPDATE grants, Order-event audit immutability, final gates. OE-1, OE-2 and DB-1 remain frozen. OE-3 is **not** frozen by this implementation.

## A. Executive verdict

The broad PostgreSQL runtime DELETE policy was replaced by an explicit 11-table allowlist. `twf_order_events` and `twf_queue_events` receive SELECT/INSERT only; the new 0027 migration also rejects Order-event UPDATE/DELETE at the database boundary on PostgreSQL and SQLite-managed connections. Live PostgreSQL was upgraded and hardened after a stopped-writer backup and successful disposable restore. All required backend, static, frontend and browser gates below passed; the implementation is ready for an independent final re-review.

## B. Preflight

Branch `main`, HEAD `fd7c391dd4f711b7a3dfaae31b8a6755c0ee3094`, `origin/main` `33ae038fc00a8db313c4ac033dc9f52442888d32`. Existing uncommitted OE-3 work was retained; no reset, stash, clean, commit, tag or push occurred. `git diff --check` passed. Live PostgreSQL was at 0026, owned by `twf_migrator`, with 44 runtime DELETE grants. The API was stopped and runtime login gated for the cutover.

The normative table classification is the 46-row matrix in [the focused independent review](TWF_OE3_FINAL_FOCUSED_REVIEW.md). Current code still contains each of the 11 identified delete paths. The earlier FAIL review and cutover evidence were preserved; their historical verdicts were not rewritten.

## C. Original grant-policy defect

The role tool previously granted SELECT/INSERT/UPDATE/DELETE to every table except `alembic_version` and `twf_queue_events`. This gave `twf_app` DELETE on 33 tables with no runtime delete path, including durable Order intent, Order audit, broker intents and Queue Entries. The review had reproduced commit-capable Order/event erasure and broker-intent deletion under the runtime role.

## D. DELETE allowlist design

`tools/postgres_roles.py` now declares `REQUIRED_DELETE_TABLES` with exactly the 11 current cleanup tables. `harden` revokes all table rights first, then grants DELETE only if the table is in that set. New tables inherit no runtime DELETE. `verify` enumerates the actual table catalog and rejects any DELETE set different from the allowlist; the real-role regression creates an unknown table and proves it still receives no DELETE. The 33 formerly granted NOT_REQUIRED tables now deny DELETE; `alembic_version` and `twf_queue_events` remain denied.

The 11 retained paths are broker attempt expiry; Dhan secret replacement; discovery active-slot release; expired manual Preview retention; MCP OAuth attempt and revoked secret cleanup; user derivative-template delete; archived watchlist permanent delete; and watchlist item, note and activity removal/purge.

## E. UPDATE policy hardening

Order and Queue events are append-only audit rows, so runtime receives SELECT/INSERT and neither UPDATE nor DELETE. `preference_changes` and `scanner_v2_runs` are also append-only evidence in current service code and now lack UPDATE. The UPDATE audit retained it for `twf_orders` lifecycle CAS, `twf_queue_entries` Hold/Release, `broker_order_intents` status, `mcp_operations` operation state, and mutable scanner/discovery records. This is a bounded current-path decision, not a claim that all evidence tables are immutable.

## F. Role-tool implementation

The CLI now enforces exact head 0027, applies the explicit DELETE policy, denies UPDATE on the four audited append-only tables, verifies the Order audit trigger/function, and checks migrator rights. During the live upgrade, the prior ownership cutover's inherited ACL was found to withhold database CONNECT from `twf_migrator` despite its ownership. The tool now explicitly grants the migrator database and schema rights after ownership transfer, while keeping `twf_app` limited. The one-time live migrator grant was applied before migration. The CLI's shebang/file-mode mismatch was fixed by removing the shebang, consistent with documented `python tools/postgres_roles.py` invocation. Ruff and format pass.

## G. Live privilege cutover

The API was stopped; `twf_app` login was disabled and its active session count verified as zero. A fresh mode-0400, custom-format PostgreSQL dump was created, listed, and restored into a disposable database. The restored copy retained all 46 original table row-content fingerprints, upgraded to 0027 as `twf_migrator`, and passed `harden`/`verify`; business rows remained identical. The same migration and grant policy were then applied live. Runtime login was restored, the API restarted, and `/ready` returned HTTP 200 with PostgreSQL ready. The only expected data fingerprint difference is `alembic_version` moving from 0026 to 0027. The first rehearsal stopped before live migration when this marker difference was not excluded from the business-row comparison; the second found the prior migrator CONNECT ACL defect, fixed it at the owner grant, and the final complete rehearsal/cutover passed. No broker order was submitted.

Cutover evidence is private under `var/backups/oe3-final-grant/`; successful stamp `20261016T033738Z`. Pre-grant dump: 12,063,922 bytes, SHA-256 `f91072cb69784773fcc4eb7df577979f2cb2cdf1b6040fa4130f692caf6f86e0`. Post-grant dump: 12,064,748 bytes, SHA-256 `ab69ced56f47c1388119d0facdf20a6ba894725c7f7b70820ac4823739694523`. Both are mode 0400. Private logs and before/after per-table hashes are mode 0600.

## H. Order/audit direct attacks

A real live `twf_app` login attempted rollback-only DELETE on `twf_order_events` and `twf_orders`, and UPDATE on `twf_order_events`. All returned SQLSTATE `42501`. The isolated test also exercises the 0027 trigger as the database owner, so the trigger independently rejects actual-row UPDATE/DELETE even when table privileges exist. The same owner-level test runs on SQLite-managed connections.

## I. Broker-intent direct attack

A real live `twf_app` rollback-only DELETE on `broker_order_intents` returned `42501`. Existing SELECT/INSERT/UPDATE Broker V2 status paths remain granted. Broker business behavior was unchanged.

## J. Required cleanup-path regressions

The 11 required tables retain DELETE grants. Source path inspection reconfirmed the runtime operations recorded in the focused review. Full backend suites exercise broker/Dhan/MCP/Preview/template/watchlist/discovery services; the real-role suite exercises Preview/Create, Queue admission/replay/Hold/Release. No synthetic or live broker execution was invoked. The real-role test's positive 11-table grant matrix is paired with service-level regression tests; it does not claim a standalone end-to-end fixture for every cleanup path under the restricted role.

## K. Negative DELETE matrix

The disposable `twf_app` test enumerated all 46 tables and attempted direct DELETE against each of the 33 formerly granted NOT_REQUIRED tables. Each returned a permission error. Both already-denied tables remained denied. The live catalog likewise reports exactly 11 DELETE grants, matching the allowlist.

## L. F1/F2/F3 regressions

The direct Order/Queue binding and event-tampering tests, 125/500-entry keyset traversals, owner/tie/mutation/cursor attacks, and DB1-R2 replay tests are included in the backend gates. The 0026 reciprocal constraints and Queue trigger were not modified. Operator presentation remains newest-first; Queue execution FIFO is unchanged.

```text
ORDER_EVENT_DELETE_DENIED = PASS
ORDER_EVENT_UPDATE_DENIED = PASS
ORDER_DELETE_DENIED = PASS
BROKER_INTENT_DELETE_DENIED = PASS
QUEUE_ENTRY_DELETE_DENIED = PASS
F1_STILL_ENFORCED = PASS
F2_STILL_ENFORCED = PASS
F3_STILL_ENFORCED = PASS
```

## M. SQLite gate closure

Three sequential full SQLite runs passed without modifying MCP production code or increasing timeouts. The first completed with 1,473 passed, 75 PostgreSQL-only skips in 506.51 seconds; it began before the new Order-event test was added. The **two full runs over the final collected test set** each had **1,474 passed, 75 skips, 4 existing SQLAlchemy cyclic-FK warnings** (453.10 and 418.46 seconds). The previously observed MCP durability timing failure did not recur.

## N. PostgreSQL full gate

The complete isolated live-PostgreSQL backend suite passed: **1,548 passed, 1 SQLite-specific skip, 4 existing SQLAlchemy cyclic-FK warnings in 564.91 seconds**. This includes the real-role privilege test, 0027 migration, Order-event mutation rejection, F1/F2/F3, DB1-R2 concurrency, OE-1 and OE-2 paths. No production broker connection was used by the test cluster.

## O. OE-1/OE-2/DB-1 regressions

Both backend suites covered frozen Order creation/lifecycle, bound Preview/Create, and DB1 fallback/concurrency behavior; the PostgreSQL suite included live-dialect DB1-R2 replay. Real-role Preview/Create through READY and explicit Queue admission/replay/Hold/Release passed inside the privilege test. PostgreSQL remains primary, SQLite remains explicit fallback, and no dual-write or auto-failover code changed. Existing service code, trust boundaries and OE-1/OE-2 lifecycle contracts were not modified.

## P. Frontend/browser results

Web Vitest passed **296/296**. Next route type generation, TypeScript, ESLint (`--max-warnings=0`), Prettier and production build passed. PostgreSQL-backed Chromium passed **10/10** existing Trade, OE-2 Orders, Queue admission/Hold/Release/pagination, Positions and Broker fixture flows at 390px and 1440px in 1.3 minutes. Broker tests used the synthetic test server, not a live broker. The generated `apps/web/next-env.d.ts` was restored to its pre-checkout content after the build. The live API was relaunched as active transient user service `twf-api-oe3.service`; `/ready` returned PostgreSQL ready.

## Q. Static gates

Ruff and Ruff format passed on all changed Python files, including `tools/postgres_roles.py`; the full API source/test/Alembic scope also passed (237 files formatted). `compileall`, `pip check`, and `git diff --check` passed. Changed-file mypy found no issues in six source files. Repository-wide mypy still reports the same 15 errors in three untouched tests (`test_derivative_templates.py`, `test_option_chain.py`, `test_derivative_relative_volume.py`); these are recorded as `PRE_EXISTING_UNRELATED`, not hidden or treated as a clean repo gate. Frontend static gates appear in section P.

## R. Backup/restore

The stopped-writer dump passed `pg_restore --list` and a full disposable restore. All original table fingerprints matched, and `harden`/`verify` on the restored copy reproduced the 11-table DELETE policy and Order audit restrictions at head 0027. A fresh post-remediation custom dump was also listed and hashed. No stale SQLite restore was used.

## S. Live data preservation

Before and after cutover, all 46 table row counts and sorted row-content SHA-256 fingerprints matched except the expected single Alembic revision marker. Normal API use after restart may advance operational timestamps; those are separate post-cutover writes, not grant-cutover mutations. SQLite data was not touched.

## T. Exact files changed

New: `apps/api/alembic/versions/0027_oe3_order_event_audit.py`, this report. Updated for this remediation: `tools/postgres_roles.py`, `apps/api/src/twf/infrastructure/database.py`, `apps/api/tests/test_database_foundation.py`, `apps/api/tests/test_postgres_privilege_boundary.py`, `apps/api/tests/test_twf_queue_oe3_hardening.py`, `README.md`, `docs/TWF_DATABASE_ARCHITECTURE.md`, `docs/TWF_SQLITE_TO_POSTGRES_MIGRATION_RUNBOOK.md`, `docs/TWF_QUEUE_OE3_ARCHITECTURE.md`, `docs/TWF_OE3_PRIVILEGE_CURSOR_REMEDIATION_REPORT.md`. Pre-existing OE-3 worktree modifications were preserved. No 0025/0026 rewrite or OE-4 worker was added.

## U. Final DELETE matrix

The two previously denied tables remain denied. Thus 11 REQUIRED rows are granted; 33 formerly granted NOT_REQUIRED rows were revoked, for 35 denied rows total.

| Table | DELETE before | DELETE after | Runtime path | Required? | Final status |
|---|---|---|---|---|---|
| `alembic_version` | No | No | Alembic-only | NOT_REQUIRED | DENIED ALREADY |
| `auth_sessions` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `broker_accounts` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `broker_attempts` | Yes | Yes | Expired connection-attempt cleanup (`brokers/service.py:206`) | REQUIRED | RETAINED |
| `broker_order_intents` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `broker_secrets` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `dhan_market_data_connections` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `dhan_market_data_secrets` | Yes | Yes | Old/revoked secret replacement (`discovery/dhan_credentials.py:211,404`) | REQUIRED | RETAINED |
| `discovery_active_slots` | Yes | Yes | Release active slot (`discovery/temporal.py:336`) | REQUIRED | RETAINED |
| `discovery_comparison_scopes` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `discovery_episodes` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `discovery_llm_explanations` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `discovery_market_context` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `discovery_observations` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `discovery_projection_checkpoints` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `discovery_scan_admissions` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `discovery_scan_evidence_series` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `discovery_scan_matches` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `discovery_scan_runs` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `discovery_settings` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `discovery_snapshots` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `discovery_temporal_lanes` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `discovery_transitions` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `fno_liquidity_cache` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `instrument_metadata` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `instrument_metadata_refreshes` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `manual_order_previews` | Yes | Yes | Expired Preview retention (`twf_orders/manual.py:252`) | REQUIRED | RETAINED |
| `mcp_connections` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `mcp_oauth_attempts` | Yes | Yes | Disconnect attempt cleanup (`integrations/mcp/connection.py:353`) | REQUIRED | RETAINED |
| `mcp_operations` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `mcp_secrets` | Yes | Yes | Revoked secret cleanup (`integrations/mcp/connection.py:1062`) | REQUIRED | RETAINED |
| `preference_changes` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `preference_profiles` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `scanner_v2_derivative_templates` | Yes | Yes | User template deletion (`scanner_v2/derivative_templates.py:412`) | REQUIRED | RETAINED |
| `scanner_v2_runs` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `scanner_v2_saved` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `twf_order_events` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `twf_orders` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `twf_queue_entries` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `twf_queue_events` | No | No | None in runtime | NOT_REQUIRED | DENIED ALREADY |
| `user_preferences` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `users` | Yes | No | None in `apps/api/src/twf` | NOT_REQUIRED | REVOKED |
| `watchlist_activity` | Yes | Yes | Archived-list purge (`watchlists/service.py:183`) | REQUIRED | RETAINED |
| `watchlist_items` | Yes | Yes | Remove/move/purge (`watchlists/service.py:183,368,404`) | REQUIRED | RETAINED |
| `watchlist_notes` | Yes | Yes | Archived-list purge (`watchlists/service.py:183`) | REQUIRED | RETAINED |
| `watchlists` | Yes | Yes | Archived-list permanent deletion (`watchlists/service.py:185`) | REQUIRED | RETAINED |

## V. Final UPDATE matrix

The role audit also checked active mutation paths before narrowing UPDATE. PostgreSQL runtime grants are:

| Table | SELECT | INSERT | UPDATE | DELETE | Reason |
|---|---|---|---|---|---|
| `twf_order_events` | Yes | Yes | No | No | Durable append-only Order audit; 0027 trigger also rejects owner-level mutation. |
| `twf_orders` | Yes | Yes | Yes | No | Lifecycle/version CAS remains necessary; physical deletion is not. |
| `broker_order_intents` | Yes | Yes | Yes | No | Broker intent status can change; deletion has no runtime path. |
| `twf_queue_entries` | Yes | Yes | Yes | No | Admission and Hold/Release update Queue state; no runtime deletion. |
| `twf_queue_events` | Yes | Yes | No | No | Existing immutable Queue audit and 0026 trigger. |
| `mcp_operations` | Yes | Yes | Yes | No | Operation/finalization state is mutable, with no runtime delete path. |
| `scanner_v2_runs` | Yes | Yes | No | No | Completed run evidence is inserted/read, not updated or deleted. |
| `preference_changes` | Yes | Yes | No | No | Append-only change history. |

## W. Required scorecard

```text
OE3_FINAL_GRANT_REMEDIATION_STATUS = PASS

DELETE_POLICY_DEFAULT_DENY = PASS
DELETE_REQUIRED_TABLES = 11
DELETE_REQUIRED_TABLES_GRANTED = PASS
DELETE_NOT_REQUIRED_TABLES = 33
DELETE_NOT_REQUIRED_TABLES_DENIED = PASS

ORDER_EVENT_DELETE_DENIED = PASS
ORDER_EVENT_UPDATE_DENIED = PASS
ORDER_DELETE_DENIED = PASS
BROKER_INTENT_DELETE_DENIED = PASS
QUEUE_ENTRY_DELETE_DENIED = PASS

ORDER_EVENT_AUDIT_IMMUTABLE = PASS
QUEUE_EVENT_AUDIT_IMMUTABLE = PASS

ROLE_TOOL_RUFF = PASS
ROLE_TOOL_FORMAT = PASS

RESTORE_GRANT_POLICY = PASS
LIVE_DATA_PRESERVED = PASS

F1_REGRESSION = PASS
F2_REGRESSION = PASS
F3_REGRESSION = PASS

DB1_FROZEN_INTACT = PASS
OE1_FROZEN_INTACT = PASS
OE2_FROZEN_INTACT = PASS
OE4_NOT_IMPLEMENTED = PASS

FULL_BACKEND_POSTGRES = PASS
FULL_BACKEND_SQLITE_RUN_1 = PASS
FULL_BACKEND_SQLITE_RUN_2 = PASS
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

OE3_READY_FOR_FINAL_REREVIEW = YES
```

## X. Final status

`PASS / YES`. The previously failing DELETE/UPDATE grant boundary is corrected, the PostgreSQL and two final SQLite suites are green, and restored/live role verification passed. This is **ready for final independent re-review**, not OE-3 acceptance or freeze. No OE-4 worker, Broker submission consumer, scheduling, risk engine or execution retry loop was added; no commit, tag or push was made.

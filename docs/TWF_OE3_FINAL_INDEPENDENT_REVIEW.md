# OE-3 final independent review and freeze recommendation

**Review date:** 16 October 2026. **Mode:** independent, adversarial, review-only. **Decision:** `OE3_FINAL_INDEPENDENT_REVIEW_STATUS = PASS`; `OE3_FREEZE_RECOMMENDATION = ACCEPT_AND_FREEZE`. This is a recommendation, not an OE-3 freeze operation. No production code, grants, live business rows, migration history, commit, tag, or remote branch was changed for this review.

## A. Executive verdict

The live PostgreSQL boundary now matches the declared policy, independently of the implementation's green suites. An actual `twf_app` connection had DELETE on **exactly** the 11 approved cleanup tables. Direct no-op DELETE against every other ordinary table failed (35/35, including all 33 formerly over-granted tables). `twf_order_events` and `twf_queue_events` denied UPDATE and DELETE; `twf_orders`, `broker_order_intents`, and `twf_queue_entries` denied DELETE. The runtime role cannot own or dismantle the protected constraints or audit triggers. Direct F1 attacks failed, owner-level actual-row audit mutations failed on an isolated restore, and 125/500-row independent traversals had no duplicate or omission. All required PostgreSQL, two SQLite, MCP, browser, and relevant static gates passed. The full frontend suite passed with one Vitest worker; its default parallel run twice timed out in an unchanged Watchlists test, recorded below as a low-severity gate-reliability observation.

No CRITICAL or HIGH finding remains. OE-4 remains unimplemented.

## B. Preflight

`main` was clean at `da764be130fe8e36a455ac13f804b49b31c89ee2`; `origin/main` was `33ae038fc00a8db313c4ac033dc9f52442888d32`. The checkpoint branch `safety/oe3-final-grant-hardening` exists at HEAD. `git diff --check` was clean before review. No reset, stash, clean, checkout, commit, tag, or push occurred. The local checkpoint is intentionally ahead of `origin/main`; this is understood existing state, not an unreviewed worktree modification. The review read the OE-3 hardening, independent, privilege/cursor, live-cutover, focused-review, final-remediation, Queue architecture, and DB architecture documents, then inspected current code, migrations, grants, and both databases.

## C. Migration history verification

`0025_twf_queue.py` is byte-for-byte unchanged relative to `origin/main`; `0026_oe3_queue_hardening.py` is unchanged relative to the earlier `fd7c391` OE-3 checkpoint. New `0027_oe3_order_event_audit.py` follows 0026 and installs an Order-event UPDATE/DELETE trigger on PostgreSQL and equivalent two triggers on managed SQLite. Its downgrade removes only those 0027 guards. The live Alembic head is `0027_oe3_order_event_audit`. The full backend suites include migration upgrade/downgrade/re-upgrade tests, data preservation, and malformed-0025 refusal. No prior migration was rewritten for this remediation.

## D. Live role and ownership

The runtime URL connected as `current_user=twf_app`; PostgreSQL sessions also showed a live idle `twf_app` API connection, and `/ready` returned HTTP 200 with `database_backend=PostgreSQL` and `database_status=ready`. The role is not superuser, CREATEROLE, CREATEDB, replication, or BYPASSRLS and is not a member of `twf_migrator`. Database `twf`, schema `public`, all 46 tables, all 149 indexes, both immutable trigger functions, and the protected Order, Preview, Broker intent, and Queue tables are owned by `twf_migrator`; none is owned by `twf_app`. There are no current application sequences. Both reciprocal F1 foreign keys are validated, deferrable and initially deferred; both audit triggers are enabled (`O`). The role tool's independent `verify` also passed on the restored copy.

## E. DDL bypass review

Using the actual live runtime login, ALTER TABLE, DROP F1 constraint, DISABLE/DROP audit trigger, ALTER/DROP audit function, ALTER OWNER, CREATE in `public`, CREATE TEMP TABLE, SET ROLE migrator, GRANT migrator, and changing `session_replication_role` were rejected with SQLSTATE `42501`. CREATE ROLE and an autocommit CREATE DATABASE were also rejected with `42501`. These probes were rollback-safe; no schema object persisted. The owner/runtime separation therefore protects the 0026/0027 guards from ordinary runtime-role DDL removal.

## F. DELETE/UPDATE grant matrix

The following matrix was regenerated from live `pg_class` and `has_table_privilege` results, not copied from the remediation scorecard. “UPDATE expected” describes the current role policy for mutable rows; it is not a claim that every UPDATE column is needed by every endpoint. The two audit tables plus `preference_changes` and `scanner_v2_runs` have no runtime UPDATE. `broker_order_intents` retains UPDATE for status/reconciliation, `mcp_operations` for operation state, and mutable discovery/scan settings and projections retain it. The runtime-path column records DELETE paths, which were independently checked against source; “None” means no current runtime DELETE path.

| Table | DELETE expected | DELETE actual | UPDATE expected | UPDATE actual | Runtime DELETE path | Result |
|---|---|---|---|---|---|---|
| `alembic_version` | No | No | No | No | Migration only | PASS |
| `auth_sessions` | No | No | Yes | Yes | None | PASS |
| `broker_accounts` | No | No | Yes | Yes | None | PASS |
| `broker_attempts` | Yes | Yes | Yes | Yes | expired broker attempts | PASS |
| `broker_order_intents` | No | No | Yes | Yes | None | PASS |
| `broker_secrets` | No | No | Yes | Yes | None | PASS |
| `dhan_market_data_connections` | No | No | Yes | Yes | None | PASS |
| `dhan_market_data_secrets` | Yes | Yes | Yes | Yes | secret replacement | PASS |
| `discovery_active_slots` | Yes | Yes | Yes | Yes | slot release | PASS |
| `discovery_comparison_scopes` | No | No | Yes | Yes | None | PASS |
| `discovery_episodes` | No | No | Yes | Yes | None | PASS |
| `discovery_llm_explanations` | No | No | Yes | Yes | None | PASS |
| `discovery_market_context` | No | No | Yes | Yes | None | PASS |
| `discovery_observations` | No | No | Yes | Yes | None | PASS |
| `discovery_projection_checkpoints` | No | No | Yes | Yes | None | PASS |
| `discovery_scan_admissions` | No | No | Yes | Yes | None | PASS |
| `discovery_scan_evidence_series` | No | No | Yes | Yes | None | PASS |
| `discovery_scan_matches` | No | No | Yes | Yes | None | PASS |
| `discovery_scan_runs` | No | No | Yes | Yes | None | PASS |
| `discovery_settings` | No | No | Yes | Yes | None | PASS |
| `discovery_snapshots` | No | No | Yes | Yes | None | PASS |
| `discovery_temporal_lanes` | No | No | Yes | Yes | None | PASS |
| `discovery_transitions` | No | No | Yes | Yes | None | PASS |
| `fno_liquidity_cache` | No | No | Yes | Yes | None | PASS |
| `instrument_metadata` | No | No | Yes | Yes | None | PASS |
| `instrument_metadata_refreshes` | No | No | Yes | Yes | None | PASS |
| `manual_order_previews` | Yes | Yes | Yes | Yes | expired preview cleanup | PASS |
| `mcp_connections` | No | No | Yes | Yes | None | PASS |
| `mcp_oauth_attempts` | Yes | Yes | Yes | Yes | disconnect cleanup | PASS |
| `mcp_operations` | No | No | Yes | Yes | None | PASS |
| `mcp_secrets` | Yes | Yes | Yes | Yes | revoked secret cleanup | PASS |
| `preference_changes` | No | No | No | No | None | PASS |
| `preference_profiles` | No | No | Yes | Yes | None | PASS |
| `scanner_v2_derivative_templates` | Yes | Yes | Yes | Yes | user template deletion | PASS |
| `scanner_v2_runs` | No | No | No | No | None | PASS |
| `scanner_v2_saved` | No | No | Yes | Yes | None | PASS |
| `twf_order_events` | No | No | No | No | None | PASS |
| `twf_orders` | No | No | Yes | Yes | None | PASS |
| `twf_queue_entries` | No | No | Yes | Yes | None | PASS |
| `twf_queue_events` | No | No | No | No | None | PASS |
| `user_preferences` | No | No | Yes | Yes | None | PASS |
| `users` | No | No | Yes | Yes | None | PASS |
| `watchlist_activity` | Yes | Yes | Yes | Yes | archived watchlist purge | PASS |
| `watchlist_items` | Yes | Yes | Yes | Yes | item removal/purge | PASS |
| `watchlist_notes` | Yes | Yes | Yes | Yes | archived watchlist purge | PASS |
| `watchlists` | Yes | Yes | Yes | Yes | archived watchlist deletion | PASS |

The live set was 46 tables, 11 DELETE grants and 35 denials. Each of the 33 previously granted NOT_REQUIRED tables rejected an actual `DELETE ... WHERE false` under `twf_app` with SQLSTATE `42501`; `alembic_version` and `twf_queue_events` were the other two denied tables. The five named critical DELETE/UPDATE attacks likewise returned `42501`. The 11 positive grants match existing cleanup paths. A disposable future table had no app DELETE immediately after creation and still had none after re-running role `harden` and `verify`; no broad default DELETE ACL exists.

## G. Order-event immutability

On the isolated restored database, a real synthetic Order event was inserted and the **owner** attempted actual-row UPDATE and DELETE. Both failed with SQLSTATE `23514` from the 0027 trigger, proving a DB guard independent of runtime grants. The matching Queue-event tests failed identically under its 0026 trigger. Each transaction rolled back. On live `twf_app`, Order and Queue event UPDATE/DELETE were independently denied by privilege (`42501`). SQLite's 0027 trigger is covered by the managed-connection test in both complete SQLite runs; the test inserts an event, attempts UPDATE/DELETE, and verifies unchanged history.

## H. F1 verification

Rollback-only, actual live-role synthetic transactions attempted READY Order plus Entry, QUEUED Order without Entry, a cross-Order binding, and a cross-owner Entry. Each failed at statement or forced deferred-constraint check with `23503`. Deleting a bound Entry under `twf_app` was denied by privilege (`42501`); the disposable owner-level persistence test additionally confirms the reciprocal FK rejects it. Final live fingerprints matched before/after these probes, demonstrating no residue. The normal service tests passed explicit READY → QUEUED admission, one Entry, both histories and replay. The PostgreSQL full gate included **two 100-round** Preview/Create and Queue admission contention series, cycling 2, 5 and 10 callers; every round converged to one durable Entry and coherent histories, with no false replay error. DB1-R2 stale-read replay remains a separate passing regression.

## I. F2 verification

Live `twf_app` Queue-event UPDATE/DELETE and bulk/no-op variants were denied with `42501`. The owner-level isolated-restore probes used actual rows and failed `23514` for both verbs. The managed SQLite F2 tests exercise single and bulk mutations, verify prior rows remain unchanged, roll back insert-then-mutate transactions, and confirm normal Hold/Release appends sequences 1–3. The same actual-row owner test on Order events confirms the 0027 audit guard rather than relying solely on role ACLs.

## J. F3 verification

An independent disposable PostgreSQL traversal inserted 125 entries for one owner and 500 for another, with three-way `admitted_at` ties. At limit 37 it returned exactly 125 in four pages and 500 in 14 pages, in descending `(admitted_at, queue_entry_id)` order: **zero duplicates and zero omissions**. A new newest entry inserted after page one appeared on refreshed page one while the original older page remained identical. Owner A queries never returned owner B's rows. The full backend suites also reran equivalent API/service tests on PostgreSQL and SQLite, including state-filter changes and cross-owner cursor rejection. Operator order remains newest-first; the separate execution FIFO index/order remains admission-ascending. No worker consumes it in OE-3.

## K. Cursor review

The decoder checks HMAC, exact keys and types, version, owner, state filter, aware timestamp, UUID and bounded token length before querying. The PostgreSQL and SQLite full suites reran the former signed-numeric-ID 500 reproduction, signed invalid timestamps/IDs, wrong version and shape, wrong owner/filter, altered signature, oversized token, and a deterministic corpus of 180 malformed signed payloads. Each returned typed `INVALID_CURSOR` HTTP 400, with zero 500 responses. No cross-owner rows were observed.

## L. SQLite trust boundary

The DB and Queue architecture documents correctly distinguish PostgreSQL's adversarial runtime-role boundary from SQLite's trusted-process/file-access boundary. Managed SQLite connections enable FKs and use the 0026 reciprocal binding and Queue-event guards plus the 0027 Order-event guards; both complete SQLite suites reran F1/F2/F3. A hostile process with arbitrary write access to the SQLite file can change schema or connection PRAGMAs, and the documentation does not claim equivalent protection. SQLite remains explicit fallback, with no automatic failover or dual-write.

## M. Required cleanup-path regressions

The 11 allowlisted DELETE paths remain present: expired broker attempts, Dhan secret replacement, active-slot release, expired Preview retention, MCP OAuth/revoked-secret cleanup, derivative-template deletion, and watchlist item/note/activity/permanent-list removal. The full backend suites cover these service families; focused real-role tests cover Preview/Create, Queue admission/replay, Hold/Release and history. On the isolated restored database, I additionally ran the actual Watchlist API under the restricted runtime role: login, create, add an item, add a note, archive, and permanent-delete returned 200/201/200/201/200/200, with `deleted: 1`. This exercised representative required cleanup across watchlists, items, notes and activity after the grant cutover. Direct grants on all 11 were confirmed. No destructive action was performed on live user rows. The retained broker read and fixture flow performed no live Broker order.

## N. Restore/backup grant verification

Both retained stopped-writer/post-remediation custom-format dumps were mode 0400 and their SHA-256 digests matched the remediation record: pre `f91072cb69784773fcc4eb7df577979f2cb2cdf1b6040fa4130f692caf6f86e0`, post `ab69ced56f47c1388119d0facdf20a6ba894725c7f7b70820ac4823739694523`. `pg_restore --list` could read the post dump. I restored that post dump into a **new socket-only disposable PostgreSQL cluster**, provisioned independent migrator/runtime roles, ran `harden` and `verify`, and started the API against the restored `oe3_review_app` role; `/ready` returned 200/PostgreSQL. The restored head was 0027. All 46 restored counts and sorted row-content SHA-256 fingerprints matched `live-after-20261016T033738Z.json` exactly after setting the restore session to UTC. (The local cluster initially defaulted to Asia/Kolkata, producing only timestamp-rendering hash differences; normalizing to UTC eliminated all differences.) The restored runtime again had exactly 11 DELETE grants and denied both audit UPDATEs. A new table remained DELETE-denied before and after re-hardening. This procedure is reproducible from the documented role tool, not a live-only ACL state. The disposable cluster was removed; recovery points were retained.

## O. Live data preservation

The independent read-only snapshot covered all 46 live tables and 4,058 rows. Its counts and content hashes matched the post-remediation baseline **46/46** before attacks, after attacks, and at final review. No unexplained row mutation occurred. All live DML/DDL attack transactions rolled back or were denied; all seeded traversal/guard data lived only in disposable databases. No sensitive row contents or credentials are in this report.

## P. OE-1/OE-2/DB-1 regression

The complete PostgreSQL and SQLite suites reran the frozen OE-1 lifecycle/authority and exact-identity tests, OE-2 bound Preview/Create and single-use tests, and DB-1 numeric/fail-closed and replay tests. A separate PostgreSQL focused Order/OE-2/Queue/cursor run passed **122/122**. PostgreSQL remains primary; SQLite is explicit fallback, with no auto failover or dual-write. No frozen OE-1 or OE-2 domain contract changed in this review.

## Q. PostgreSQL full gate

`tools/test-postgres.sh -q`: **1,548 passed, 1 SQLite-specific skip, 4 known SQLAlchemy deferred-FK sorting warnings, 0 failed** in 699.18 seconds. This used an isolated, real PostgreSQL cluster and included live-dialect role tests and two 100-round contention series.

## R. SQLite full gates and MCP timing

Full SQLite run 1: **1,474 passed, 75 backend-specific skips, 4 known warnings, 0 failed** in 474.19 seconds. Run 2: **1,474 passed, 75 skips, 4 warnings, 0 failed** in 427.87 seconds. Both were sequential and used the final test set. The separately rerun MCP remediation/durability modules passed **40/40** in 14.19 seconds, including the former broader-suite timeout family. No timeout was increased.

## S. Frontend, browser and static gates

PostgreSQL-backed Chromium: **10/10 passed** at 390px and 1440px, covering shared Trade context, OE-2 ticket, Queue admission/Hold/Release/pagination, Positions navigation, and a synthetic Broker read/mock flow. No live broker execution was attempted. TypeScript/Next type generation, ESLint, Prettier and production build passed. The complete 296-test Vitest suite passed with `--maxWorkers=1` using the original test timeouts. Two default parallel `npm run test` attempts each had 295 passed and one unchanged Watchlists test timeout; the same test passed alone in 2.12 seconds. This is a low-severity parallel-run reliability observation, not a hidden clean default gate. The generated `next-env.d.ts` was returned to its pre-build bytes.

Ruff and Ruff format passed on API source/tests/Alembic and `tools/postgres_roles.py` (238 formatted files); role-tool checks passed separately. Compileall, pip check, changed-file mypy (nine source files), and `git diff --check` passed. Repository mypy reports 11 existing errors in three untouched tests: `test_derivative_templates.py`, `test_option_chain.py`, and `test_derivative_relative_volume.py`; they are unrelated to OE-3 changes. An exploratory lint/format run over **all** `tools/` found pre-existing findings in the unchanged `tools/market_metadata` utility; this is outside the required changed-file/role-tool scope and is disclosed rather than represented as a repository-wide clean lint result.

## T. OE-4 leakage check

Queue runtime code contains no worker, claim/lease loop, SUBMITTING transition, scheduler, risk execution, automatic retry, or Queue-to-Broker submission consumer. The existing staged Broker New Order fixture remains operational and separate. The schema permits bound future Order states but OE-3 services expose only explicit admission and READY/HELD Queue operations.

## U. Findings by severity

- **CRITICAL:** none.
- **HIGH:** none. The previously demonstrated runtime Order/audit/broker-intent deletion and guard-removal paths are closed.
- **MEDIUM:** none within the OE-3 acceptance boundary.
- **LOW / carry-forward:** the unchanged Watchlists unit test times out under default parallel Vitest execution but the complete serial suite and isolated test pass without a timeout change; repository mypy and broad legacy `tools/market_metadata` lint/format debt remain outside changed files. Architecture documents still describe OE-3 as pending review; documentation status can be updated in a separate freeze/closure step. These observations do not weaken the execution/audit boundary.

## V. Required scorecard

```text
OE3_FINAL_INDEPENDENT_REVIEW_STATUS = PASS

LIVE_RUNTIME_ROLE_TWF_APP = PASS
TWF_APP_NOT_OWNER = PASS
TWF_MIGRATOR_OWNERSHIP = PASS
DDL_BYPASS_BLOCKED = PASS
ROLE_ESCALATION_BLOCKED = PASS

DELETE_POLICY_DEFAULT_DENY = PASS
DELETE_REQUIRED_COUNT = 11
DELETE_REQUIRED_EXACT = PASS
DELETE_NOT_REQUIRED_COUNT = 33
DELETE_NOT_REQUIRED_ALL_DENIED = PASS

ORDER_EVENT_UPDATE_DENIED = PASS
ORDER_EVENT_DELETE_DENIED = PASS
ORDER_DELETE_DENIED = PASS
BROKER_INTENT_DELETE_DENIED = PASS
QUEUE_ENTRY_DELETE_DENIED = PASS

ORDER_EVENT_DB_IMMUTABLE = PASS
QUEUE_EVENT_DB_IMMUTABLE = PASS

F1_POSTGRES = PASS
F1_SQLITE_MANAGED = PASS
F2_QUEUE_EVENT_IMMUTABILITY = PASS
F2_ORDER_EVENT_IMMUTABILITY = PASS
F1_DIRECT_ATTACKS = PASS
F3_125 = PASS
F3_500 = PASS
F3_DUPLICATES = 0
F3_OMISSIONS = 0
F3_TIES = PASS
F3_INSERT_BETWEEN_PAGES = PASS
F3_OWNER_ISOLATION = PASS

CURSOR_INVALID_4XX = PASS
CURSOR_FUZZ_NO_500 = PASS
CURSOR_NO_500 = PASS

SQLITE_BOUNDARY_TRUTHFUL = PASS
SQLITE_MANAGED_F2 = PASS
SQLITE_MANAGED_F3 = PASS

ROLE_TOOL_RUFF = PASS
ROLE_TOOL_FORMAT = PASS

RESTORE_GRANT_POLICY = PASS
LIVE_DATA_PRESERVED = PASS

DB1_FROZEN_INTACT = PASS
OE1_FROZEN_INTACT = PASS
OE2_FROZEN_INTACT = PASS
OE4_NOT_IMPLEMENTED = PASS

FULL_BACKEND_POSTGRES = PASS
FULL_BACKEND_SQLITE_RUN_1 = PASS
FULL_BACKEND_SQLITE_RUN_2 = PASS
MCP_TIMING_REGRESSION = PASS

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

OE3_FREEZE_RECOMMENDATION = ACCEPT_AND_FREEZE
```

## W. Freeze recommendation

**`ACCEPT_AND_FREEZE`** is recommended. The exact 11/33 privilege policy, critical denials, F1/F2/F3, typed cursor handling, reproducible restore model, complete database gates, relevant static checks and no-OE-4 boundary all passed, with zero CRITICAL/HIGH finding. This review itself does not freeze OE-3 or start OE-4. The low-severity frontend-parallel and pre-existing static-debt observations should remain visible in any subsequent documentation closure.

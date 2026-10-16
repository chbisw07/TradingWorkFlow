# OE-3 final focused re-review — independent decision

**Review date:** 16 October 2026. **Scope:** F1/F2/F3, live PostgreSQL privilege separation, SQLite managed boundary, cursor handling, DELETE grants, and direct regressions. **Decision:** `OE3_FINAL_REVIEW_STATUS = FAIL`; `OE3_FREEZE_RECOMMENDATION = REMEDIATION_REQUIRED`. This is a review only; no production code, migration, role grant, or live business row was changed.

## A. Executive verdict

The live role split is real: `twf_app` does not own the protected schema and cannot remove the 0026 Queue constraints or Queue audit trigger. Direct F1/F2 attacks were rejected, and the stopped-writer backup restored with matching data and role restrictions. The DELETE-grant audit found a separate **CRITICAL** authority gap. No TWF runtime code deletes `twf_order_events` or `twf_orders`, yet `twf_app` has DELETE on both. In a live-role, rollback-only transaction, it deleted a synthetic Order event and then the READY Order; all constraints passed. The same role could UPDATE the Order event. This can erase or rewrite the durable trading intent and its audit trail without touching F1/F2 guards. A direct DELETE of a real `broker_order_intents` row also succeeded within a rolled-back transaction. OE-3 must not freeze with these unneeded execution/audit privileges.

This finding is about direct SQL available to a compromised or misused **runtime database role**; it is not a claim that an HTTP user can call an Order-delete endpoint. Broad DELETE alone is not the failure criterion: 11 grants support identified product cleanup paths. The blocker is the unneeded, unguarded DELETE on execution and audit records.

## B. Preflight

`main` at `fd7c391dd4f711b7a3dfaae31b8a6755c0ee3094`, one commit ahead of `origin/main` (`33ae038fc00a8db313c4ac033dc9f52442888d32`). Safety branches `safety/db1-final-accepted`, `safety/db1-remediation-pre-mcp`, and `safety/oe3-hardening-pre-review` exist. The worktree already contained uncommitted OE-3 remediation/docs and untracked review/test files; they were preserved. `git diff --check` passed. Live `/ready` returned PostgreSQL ready with a database check; the API process was running normally. No git history operation was performed.

## C. Live role and ownership

Catalog inspection: database `twf`, schema `public`, all 46 ordinary tables, 149 indexes, and `twf_queue_event_immutable()` are owned by `twf_migrator`; protected Orders, Previews, Queue Entries and Queue Events are included. `twf_app` is LOGIN but neither superuser, role creator, database creator, replication role, nor BYPASSRLS; it is not a member of `twf_migrator`. It has no database/schema CREATE. Direct runtime connection reported `current_user=twf_app`; five idle application sessions and `/ready` corroborated live use. Queue audit trigger `trg_twf_queue_events_immutable` was enabled (`O`). Migration head was `0026_oe3_queue_hardening`; no 0027 exists.

## D. DDL bypass re-attack

Using the actual `twf_app` login, rollback-only ALTER TABLE, DROP F1 constraint, DISABLE/DROP Queue audit trigger, ALTER/DROP audit function, ALTER OWNER, CREATE ROLE and SET ROLE migrator all returned SQLSTATE `42501`. CREATE DATABASE under autocommit also returned `42501`. No DDL persisted. The runtime role cannot dismantle F1/F2 by ownership or role escalation.

## E. F1 direct-DML revalidation

Rollback-only synthetic live-role transactions rejected READY + Entry, QUEUED without Entry, an owner mismatch using **two existing users**, and a cross-Order binding using **two otherwise coherent pairs**, with `23503` at statement or forced deferred-constraint check. Deleting a bound Entry with a Queue event was rejected with `23503`. Migration 0026's reciprocal deferred composite FKs and admitted-state checks are installed and enabled. The synthetic transactions left zero Orders/Entries behind. Existing disposable regression coverage also tests mismatched bindings and post-QUEUED compatible states.

## F. F2 Queue-event revalidation

A synthetic bound Order/Entry/Event was inserted within a forced-rollback transaction. Single UPDATE, DELETE, bulk UPDATE and bulk DELETE of `twf_queue_events` each returned `42501`; the event remained present before rollback. `twf_app` has SELECT/INSERT, not UPDATE/DELETE, on this table, and cannot disable its trigger. This F2 result does **not** extend to `twf_order_events`, which is the separate critical finding.

## G. F3 pagination revalidation

An independent rollback-only live-role SQL traversal seeded 125 and 500 coherent pairs plus another owner, with three-way admission-time ties. At limit 37 it returned 125/125 in four pages and 500/500 in 14 pages, with zero duplicates, zero omissions and exact descending `(admitted_at, queue_entry_id)` order; no synthetic row persisted. The disposable API tests additionally exercise signed cursors, terminal cursors, insertion between pages, owner/filter scoping, and state changes between filtered pages. The operator query uses owner restriction, strict keyset comparison, `limit+1`, and a unique UUID tie-break; execution FIFO remains the separate ascending order. Final gate outcomes appear below.

## H. Cursor invalidity

The current decoder validates the exact payload keys and types, version, owner, filter, aware timestamp, UUID, signature and token length before SQL. The API maps `INVALID_CURSOR` to HTTP 400. The regression set includes the formerly 500-producing signed numeric ID, signed semantic-invalid timestamps/IDs, cross-owner and cross-filter tokens, altered/oversized tokens and 180 deterministic malformed signed payloads. Final gate outcomes appear below.

## I. SQLite boundary

The DB and Queue architecture documents explicitly limit SQLite to trusted process/file access. TWF-managed connections enable FKs; 0026 installs the reciprocal FKs and UPDATE/DELETE Queue-event triggers; pagination and cursor checks are shared application code. Arbitrary write access to the SQLite file/schema can disable those mechanisms, and the documents do not claim PostgreSQL-equivalent hostile-SQL protection. SQLite is explicit fallback/recovery, not automatic failover.

## J. Complete live DELETE-grant matrix

The matrix below covers **all 46** ordinary tables, including the 44 with DELETE and two denied exceptions. “Path found” means a current runtime `apps/api/src/twf` ORM/SQL DELETE path, not an Alembic migration, an HTTP client DELETE, or a theoretical future cleanup. Search covered ORM `delete(...)`, `db.delete(...)`, raw `DELETE FROM`, TRUNCATE, and model cascades. A grant classified REQUIRED may still be narrowed or guarded later, but is not a freeze blocker merely because it exists. The current broad grant is emitted by `tools/postgres_roles.py:320` for every table except the two special cases.

| Table | DELETE granted? | Runtime DELETE path found? | Required? | Protection if deleted | Risk | Recommendation |
|---|---|---|---|---|---|---|
| `alembic_version` | No | Alembic-only | NOT_REQUIRED | Grant absent; migration owner controls revision | None from runtime DELETE | Keep denied |
| `auth_sessions` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | No FK child; session rows can be erased | Medium: session/revocation trace | Revoke runtime DELETE |
| `broker_accounts` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | Referenced by attempts/intents; otherwise no delete guard | Medium: account/config availability | Revoke runtime DELETE |
| `broker_attempts` | Yes | Expired connection-attempt cleanup (`brokers/service.py:206`) | REQUIRED | No DB age guard; service limits cleanup to expired attempts | Low–medium: overbroad DML can still erase owner data | Retain for current path; constrain service calls |
| `broker_order_intents` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | No child FK or immutable trigger; live row deletion succeeded | High: broker intent/preview evidence erasure | Revoke runtime DELETE |
| `broker_secrets` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | Active-account FK may restrict; unreferenced rows deletable | Medium: credential loss | Revoke runtime DELETE |
| `dhan_market_data_connections` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | User FK only | Medium: provider/config loss | Revoke runtime DELETE |
| `dhan_market_data_secrets` | Yes | Old/revoked secret replacement (`discovery/dhan_credentials.py:211,404`) | REQUIRED | Connection FK restricts currently referenced secret; service retires old secret | Low–medium: overbroad DML can still erase owner data | Retain for current path; constrain service calls |
| `discovery_active_slots` | Yes | Release active slot (`discovery/temporal.py:336`) | REQUIRED | Operational slot release is intended; no immutable-history claim | Low–medium: overbroad DML can still erase owner data | Retain for current path; constrain service calls |
| `discovery_comparison_scopes` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | FK/CASCADE only; no immutable trigger | Medium: historical evidence loss | Revoke runtime DELETE |
| `discovery_episodes` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | FK/CASCADE only; no immutable trigger | Medium: historical evidence loss | Revoke runtime DELETE |
| `discovery_llm_explanations` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | FK/CASCADE only; no immutable trigger | Medium: historical evidence loss | Revoke runtime DELETE |
| `discovery_market_context` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | FK/CASCADE only; no immutable trigger | Medium: historical evidence loss | Revoke runtime DELETE |
| `discovery_observations` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | FK/CASCADE only; no immutable trigger | Medium: historical evidence loss | Revoke runtime DELETE |
| `discovery_projection_checkpoints` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | FK/CASCADE only; no immutable trigger | Medium: historical evidence loss | Revoke runtime DELETE |
| `discovery_scan_admissions` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | FK/CASCADE only; no immutable trigger | Medium: historical evidence loss | Revoke runtime DELETE |
| `discovery_scan_evidence_series` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | FK/CASCADE only; no immutable trigger | Medium: historical evidence loss | Revoke runtime DELETE |
| `discovery_scan_matches` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | FK/CASCADE only; no immutable trigger | Medium: historical evidence loss | Revoke runtime DELETE |
| `discovery_scan_runs` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | Several child CASCADE FKs | Medium: scan evidence cascade erasure | Revoke runtime DELETE |
| `discovery_settings` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | No dedicated DELETE guard | Low–medium: data/configuration loss | Revoke runtime DELETE |
| `discovery_snapshots` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | FK/CASCADE only; no immutable trigger | Medium: historical evidence loss | Revoke runtime DELETE |
| `discovery_temporal_lanes` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | FK/CASCADE only; no immutable trigger | Medium: historical evidence loss | Revoke runtime DELETE |
| `discovery_transitions` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | FK/CASCADE only; no immutable trigger | Medium: historical evidence loss | Revoke runtime DELETE |
| `fno_liquidity_cache` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | No dedicated DELETE guard | Low–medium: data/configuration loss | Revoke runtime DELETE |
| `instrument_metadata` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | No audit guard | Medium: canonical reference loss | Revoke runtime DELETE |
| `instrument_metadata_refreshes` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | FK/CASCADE only; no immutable trigger | Medium: historical evidence loss | Revoke runtime DELETE |
| `manual_order_previews` | Yes | Expired Preview retention (`twf_orders/manual.py:252`) | REQUIRED | Service purges over-day-expired previews; no DB age guard | Low–medium: overbroad DML can still erase owner data | Retain for current path; constrain service calls |
| `mcp_connections` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | Dependent rows/operation FKs may restrict | Medium: provider state loss | Revoke runtime DELETE |
| `mcp_oauth_attempts` | Yes | Disconnect attempt cleanup (`integrations/mcp/connection.py:353`) | REQUIRED | Temporary OAuth attempt; service clears attempts on disconnect | Low–medium: overbroad DML can still erase owner data | Retain for current path; constrain service calls |
| `mcp_operations` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | No child FK/audit guard; live row deletion succeeded | Medium: operation evidence erasure | Revoke runtime DELETE |
| `mcp_secrets` | Yes | Revoked secret cleanup (`integrations/mcp/connection.py:1062`) | REQUIRED | Connection FK restricts active reference; service deletes only revoked secret | Low–medium: overbroad DML can still erase owner data | Retain for current path; constrain service calls |
| `preference_changes` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | No immutable audit guard | Medium: preference history erasure | Revoke runtime DELETE |
| `preference_profiles` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | No dedicated DELETE guard | Low–medium: data/configuration loss | Revoke runtime DELETE |
| `scanner_v2_derivative_templates` | Yes | User template deletion (`scanner_v2/derivative_templates.py:412`) | REQUIRED | Owner-scoped user template delete endpoint; no DB delete guard | Low–medium: overbroad DML can still erase owner data | Retain for current path; constrain service calls |
| `scanner_v2_runs` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | No immutable guard; live row deletion succeeded | Medium: scan history/evidence erasure | Revoke runtime DELETE |
| `scanner_v2_saved` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | No dedicated DELETE guard | Low–medium: data/configuration loss | Revoke runtime DELETE |
| `twf_order_events` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | No immutable trigger; synthetic DELETE and UPDATE succeeded | Critical: Order audit erasure/alteration | Revoke runtime DELETE and unnecessary UPDATE; enforce audit immutability |
| `twf_orders` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | FKs restrict referenced rows; event-first READY Order erasure succeeded | Critical: durable trading intent erasure | Revoke runtime DELETE |
| `twf_queue_entries` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | Bound Order FK; Queue event FK protects admitted rows with events | Medium: unused grant; valid event-backed entries are FK-protected | Revoke runtime DELETE |
| `twf_queue_events` | No | None in runtime | NOT_REQUIRED | Grant absent; F2 trigger also blocks UPDATE/DELETE | None from runtime DELETE | Keep denied |
| `user_preferences` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | No dedicated DELETE guard | Low–medium: data/configuration loss | Revoke runtime DELETE |
| `users` | Yes | None in `apps/api/src/twf` | NOT_REQUIRED | FKs restrict referenced users, not unreferenced users | Medium: identity deletion | Revoke runtime DELETE |
| `watchlist_activity` | Yes | Archived-list purge (`watchlists/service.py:183`) | REQUIRED | Parent FK; service purges only with archived-list deletion | Low–medium: overbroad DML can still erase owner data | Retain for current path; constrain service calls |
| `watchlist_items` | Yes | Remove/move/purge (`watchlists/service.py:183,368,404`) | REQUIRED | Parent FK; service authorizes remove/move and archived-list purge | Low–medium: overbroad DML can still erase owner data | Retain for current path; constrain service calls |
| `watchlist_notes` | Yes | Archived-list purge (`watchlists/service.py:183`) | REQUIRED | Parent FK; service purges only with archived-list deletion | Low–medium: overbroad DML can still erase owner data | Retain for current path; constrain service calls |
| `watchlists` | Yes | Archived-list permanent deletion (`watchlists/service.py:185`) | REQUIRED | Child FKs require explicit child cleanup; archive check is in service | Low–medium: overbroad DML can still erase owner data | Retain for current path; constrain service calls |


There are **11 REQUIRED** grants and **33 NOT_REQUIRED** grants among the 44 granted tables. No table is classified UNCERTAIN after code-path inspection. FK references often block parent deletion, but do not make an unrelated audit/history row immutable. The cited `watchlists/service.py` paths include permanent deletion of archived watchlists and their dependent items, notes and activity; those four grants therefore have a current supported path.

## K. DELETE-grant impact and decisive probes

The actual ACL is `twf_app=arwd` on Orders, Order events, Queue Entries and broker intents, versus `twf_app=ar` on Queue events (`r`=SELECT, `a`=INSERT, `w`=UPDATE, `d`=DELETE). The live-role synthetic sequence was: INSERT user → INSERT READY Order → INSERT Order event → `DELETE twf_order_events` (returned one row) → `DELETE twf_orders` (returned one row) → force all constraints IMMEDIATE (accepted) → ROLLBACK. A separate UPDATE changed the synthetic Order event actor and was rolled back. This proves a commit-capable audit/intent erasure path, not merely a catalog grant. The persisted synthetic Order count was zero afterward. `twf_queue_events` DELETE was denied, and a bound Queue Entry could not be removed while its event remained, showing the protected Queue half works.

A real existing row in each of `broker_order_intents`, `mcp_operations`, `scanner_v2_runs`, and `watchlist_activity` could also be DELETEd by `twf_app` inside a rolled-back transaction. `broker_order_intents` has no runtime DELETE path and carries broker intent/preview evidence, so its deletion is a second HIGH finding. `mcp_operations` and scan histories have lesser but real evidence-loss exposure. `watchlist_activity` is distinct: its DELETE is needed for user-requested permanent archived-watchlist removal. No real row was committed deleted.

## L. Normal runtime DML and Queue replay

The live role inserted a synthetic coherent bound Order/Queue/Event, then performed Hold/Release state updates and appended three Queue events with final state READY inside a forced-rollback transaction. A separate rollback-only live-role probe created, archived and deleted a Watchlist, inserted/read a Scanner run, and read the existing Broker account; all worked and left no synthetic rows. Disposable real-role tests exercise Preview/Create, Queue admission/replay, Hold/Release, history and reads; the complete suites also cover Watchlists, Scanner persistence, Broker reads and DB1-R2 concurrent replay. No live broker submission was used. Final results appear below.

## M. Independent backup/restore role check

The 12,061,858-byte stopped-writer custom dump (`de5678ce…22f7edf`, mode 0400) restored into a **new private socket-only PostgreSQL cluster**. A fresh `twf_migrator`/`twf_app` split was provisioned and `harden`/`verify` succeeded. All 46 UTC/C-collation canonical count/content fingerprints matched the cutover snapshot, head remained 0026, restored runtime connected as `twf_app`, and protected DDL was denied. The restore also retained the unsafe Order-event DELETE grant, demonstrating the grant policy itself needs correction. The disposable cluster was removed; no live restore was performed.

## N. Live data preservation

A fresh read-only canonical fingerprint comparison against `live-after-restart-fingerprint-canonical.txt` found **45 of 46 tables byte-content equivalent at the row-hash level, with all 46 row counts unchanged**. The sole changed row is `broker_accounts`, whose `updated_at`/`last_read_at` are after the cutover and consistent with ordinary broker read/refresh activity. All Order, Queue, audit and Preview tables remain empty and unchanged; the review probes rolled back. This is no evidence of data mutation by the role transfer. The comparison initially used an incorrect empty string separator; after matching the recorded newline aggregation format, the result above is exact.

## O. DB-1/OE-1/OE-2 regressions

PostgreSQL remains primary, SQLite explicit fallback, with no dual-write or automatic failover. The source changes in this worktree do not alter frozen OE-1 lifecycle/identity or OE-2 Preview binding; their focused suites run in both full gates. DB-1 exact-or-refuse numeric migration and concurrent Queue replay remain covered. The finding is a **database privilege-policy exposure**, not a newly introduced Order lifecycle or OE-2 API transition.

## P. Frontend, browser and static gates

- Full PostgreSQL backend: **1,547 passed, 1 skipped, 0 failed, 4 known SQLAlchemy FK-cycle warnings in 796.45 s** (`/tmp/oe3-final-pg-suite.log`). This includes OE-1/OE-2, DB1-R2, F1/F2/F3, real-role and cursor security tests.
- Full explicit SQLite backend: **1,472 passed, 75 skipped, 1 failed, 4 warnings in 534.00 s** (`/tmp/oe3-final-sqlite-suite.log`). The sole failure was `test_terminal_decision_survives_delayed_completion[sqlite-commit_delivery-TIMEOUT-0]`: MCP elapsed about 0.731 s against a 0.520 s assertion. The exact isolated rerun passed 1/1 in 2.35 s without code or timeout change (`/tmp/oe3-final-sqlite-isolated.log`). The full-suite failure remains a failed gate; it does not implicate the passing OE-3 cases.
- Frontend Vitest: **296/296 across 33 files** with two workers. TypeScript, ESLint, Prettier and production Next build passed. PostgreSQL-backed Chromium passed **10/10** Trade/Orders/Queue/Positions/Broker flows at 390 and 1440 px in 1.5 min (`/tmp/oe3-final-browser.log`). The build-generated change to `apps/web/next-env.d.ts` was restored byte-for-byte from pre-review HEAD.
- Changed-file mypy: passed 4 files, including `tools/postgres_roles.py`. Repository mypy reported 11 existing errors in three untouched tests (`test_derivative_templates.py`, `test_option_chain.py`, `test_derivative_relative_volume.py`). Ruff and format over backend source/tests passed; wider scope including the changed role tool failed: `tools/postgres_roles.py` has EXE001 shebang/file-mode error and would be reformatted. An all-tools Ruff run additionally reports 21 pre-existing root-logger warnings in untouched market-metadata tooling. Compileall, pip check and `git diff --check` passed.

## Q. OE-4 leakage check

The Queue API exposes admission, owner-scoped list/history, Hold and Release only. Queue states reachable in OE-3 remain READY/HELD. `SUBMITTING` appears only in protected Order schema/future compatibility, with no Queue worker, broker submit consumer, scheduler, risk execution loop or execution retry pipeline. Existing retained Broker New Order behavior is a separate staged migration path.

## R. Findings by severity

- **CRITICAL — unnecessary, unguarded runtime DELETE/UPDATE on `twf_order_events` and DELETE on `twf_orders`.** Direct live-role synthetic DML proved an Order and its history can be erased, and event actor rewritten, without violating Queue coherence. There is no supported runtime deletion path. This materially weakens durable execution intent/audit and blocks freeze.
- **HIGH — unnecessary runtime DELETE on `broker_order_intents`.** A real row was deletable under rollback. Broker intent/preview evidence can be erased; no runtime DELETE path was found.
- **MEDIUM — unnecessary runtime DELETE on `twf_queue_entries`.** Normal admitted rows with Queue events are FK-protected, as independently tested. The grant has no OE-3 product path and should be removed for least privilege, but this grant alone is not a demonstrated ability to erase valid admissions and is not the freeze blocker.
- **MEDIUM — unnecessary DELETE on other history/configuration tables.** MCP operations, scanner/discovery evidence and preference changes have no current deletion path or database immutability guard. The matrix identifies each table, while legitimate temporary/archived-object deletion remains classified REQUIRED.
- **LOW — SQLite full-suite timing gate.** The broad run missed the unrelated MCP timeout wall-clock bound; the exact test passed in isolation. The full SQLite gate still fails, with no OE-3 test failure observed.
- **LOW — changed role-tool static hygiene.** Ruff flags `tools/postgres_roles.py` as non-executable with a shebang, and Ruff format would change it. Backend source/tests remain clean; the changed-tool gate is not clean.

## S. Required scorecard

```text
OE3_FINAL_REVIEW_STATUS = FAIL

LIVE_RUNTIME_ROLE_TWF_APP = PASS
TWF_APP_NOT_OWNER = PASS
TWF_MIGRATOR_OWNS_PROTECTED_OBJECTS = PASS

DDL_BYPASS_BLOCKED = PASS
ROLE_ESCALATION_BLOCKED = PASS

F1_DIRECT_DML_BLOCKED = PASS
F2_EVENT_TAMPER_BLOCKED = PASS

F3_125_TRAVERSAL = PASS
F3_500_TRAVERSAL = PASS
F3_DUPLICATES = 0
F3_OMISSIONS = 0

CURSOR_INVALID_INPUT_4XX = PASS
CURSOR_FUZZ_NO_500 = PASS

SQLITE_BOUNDARY_TRUTHFUL = PASS
SQLITE_MANAGED_F1 = PASS
SQLITE_MANAGED_F2 = PASS
SQLITE_MANAGED_F3 = PASS

DELETE_GRANTS_REVIEWED_ALL_TABLES = PASS
DELETE_GRANTS_REQUIRED_OR_JUSTIFIED = FAIL
DELETE_ON_AUDIT_EXECUTION_DATA_SAFE = FAIL

NORMAL_RUNTIME_DML = PASS

RESTORE_ROLE_MODEL = PASS
LIVE_DATA_PRESERVED = PASS

DB1_FROZEN_INTACT = PASS
OE1_FROZEN_INTACT = PASS
OE2_FROZEN_INTACT = PASS
OE4_NOT_IMPLEMENTED = PASS

FULL_BACKEND_POSTGRES = PASS
FULL_BACKEND_SQLITE = FAIL
FRONTEND = PASS
BROWSER_POSTGRES = PASS

CHANGED_FILE_MYPY = PASS
REPO_MYPY = PRE_EXISTING_UNRELATED
RUFF = FAIL
FORMAT = FAIL
COMPILE = PASS
PIP_CHECK = PASS
TYPESCRIPT = PASS
ESLINT = PASS
PRETTIER = PASS
GIT_DIFF_CHECK = PASS

OE3_FREEZE_RECOMMENDATION = REMEDIATION_REQUIRED
```

## T. Freeze recommendation

`REMEDIATION_REQUIRED`. Preserve the passing F1/F2/F3 and split-role design. A bounded grant-policy correction must remove unnecessary runtime DELETE on execution/audit records (and address unneeded Order-event UPDATE), with direct probes proving the new privilege boundary and normal cleanup paths still work. Re-run the focused review afterward. This review does not implement that correction, freeze OE-3, modify OE-1 contracts, or start OE-4.

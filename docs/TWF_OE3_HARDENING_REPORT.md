# OE-3 hardening report

## A. Executive verdict

OE-3 hardening implements commit-time Order/Queue binding, database-enforced append-only Queue history, and owner-scoped newest-first operator pagination. This is an implementation report pending independent adversarial review; OE-3 is **not frozen**. No Queue worker, Broker V2 handoff, or OE-4 behavior was added.

## B. Preflight

Work began on clean `main` at `33ae038fc00a8db313c4ac033dc9f52442888d32`, equal to `origin/main`. Migration `0025_twf_queue.py` was not edited. The PostgreSQL and SQLite tests use disposable databases; the live runtime database was not migrated or modified by this work.

## C. Prior findings and reproductions

The independent OE-3 review found that direct DML could persist an Entry for a `READY` Order, a `QUEUED` Order without an Entry, and mutable Queue events. The old operator list returned only the earliest 50–100 rows, with no cursor, so new admissions could be invisible behind old or HELD rows. The new direct-DML and 125/500-row tests preserve these as regressions.

## D. F1 invariant design

`twf_orders.queue_entry_id` is an explicit binding. `DRAFT` and `READY` Orders must have a null binding. `QUEUED`, `SUBMITTING`, `BROKER_ACCEPTED`, `PARTIALLY_FILLED`, and `FILLED` must have a binding. Other post-admission terminal states can retain it without prescribing OE-4 transitions. A deferred composite FK from Order binding to `(queue_entry_id, twf_order_id, owner_id)` on Queue Entry, and a deferred composite FK back from Entry to `(twf_order_id, owner_id, queue_entry_id)` on Order, require reciprocal identity at COMMIT. The original immediate Entry-to-Order owner FK and one-entry-per-Order uniqueness remain. This allows the existing single transaction to insert the Entry and then compare-and-swap the Order to `QUEUED` while preventing either half from committing alone.

## E. F1 migration and service implementation

New migration `0026_oe3_queue_hardening.py` first rejects incoherent 0025 data. PostgreSQL adds and backfills the binding, then installs checks, uniqueness, and deferred FKs. SQLite transactionally rebuilds the two tables because it cannot add the composite FKs in place; it checks all FKs before completion. The migration has downgrade/re-upgrade tests on both dialects with Queue data. Queue admission now writes the binding in its existing Order CAS. Replay checks it. Unexpected DB invariant failures become a typed `QUEUE_INVARIANT_FAILURE`, logged without exposing SQL or credentials.

The new deferred cycle also changes how DB-1's cross-database importer must order its inserts. Its insertion sort now excludes only commit-deferred edges; all constraints remain enabled and all FKs are verified after copy. This is a compatibility fix to preserve DB-1 data fidelity, not a change to authority or failover policy.

## F. F1 direct-database attacks

The focused tests use ordinary test-application database connections on disposable PostgreSQL and SQLite. The test catches either statement-time or COMMIT-time rejection, then reopens a transaction to inspect durable state.

| Direct-DML attack | PostgreSQL | SQLite | Durable state after failure |
| --- | --- | --- | --- |
| Entry for a `READY` Order | `IntegrityError` | `IntegrityError` | Order remains READY; no Entry added |
| Order changed to `QUEUED` without an Entry | `IntegrityError` | `IntegrityError` | Order remains READY; no binding |
| Order A bound to Order B's Entry | `IntegrityError` | `IntegrityError` | A remains bound to its own Entry |
| Entry owner changed away from Order owner | `IntegrityError` | `IntegrityError` | Owner remains unchanged |
| Delete a bound Entry | `IntegrityError` | `IntegrityError` | Entry and Order binding remain |

The same test directly changes an already bound Order to `SUBMITTING` and back, proving schema compatibility for a future post-QUEUED lifecycle without adding that transition to the OE-3 service.

## G. F1 concurrency and service regression

The original admission/Hold/Release suites pass on both dialects. The frozen DB-1 R2 regression includes two independent 100-round PostgreSQL series with 2/5/10 concurrent callers. The full PostgreSQL run completed **1,542 passed, 1 skipped, 0 failed in 847.84 seconds**. The full SQLite fallback run completed **1,471 passed, 73 skipped, 0 failed in 516.20 seconds**. Focused post-gate assertions passed 7/7 on PostgreSQL and 6/6 with one expected skip on SQLite. Queue admission still creates one Entry, one Order transition, and one event in each history, with no Broker call.

## H. F2 immutable audit

Migration 0026 installs PostgreSQL `BEFORE UPDATE OR DELETE` and SQLite `BEFORE UPDATE`/`BEFORE DELETE` triggers on `twf_queue_events`. Neither application ORM code nor API authorization is the sole guard. Normal `INSERT` remains allowed. Queue history continues to sort by per-entry sequence.

## I. F2 mutation attacks

Focused tests attempt single-row and bulk UPDATE/DELETE against Queue events on both dialects. PostgreSQL raises `IntegrityError` from the event trigger; SQLite raises `IntegrityError` from its triggers. Reopening the session shows the original event rows and actor unchanged. An INSERT followed by a forbidden UPDATE in one transaction rolls the new row back as well. Admission, Hold, and Release still append events with sequences 1, 2, and 3.

## J. F3 API pagination contract

`GET /api/v1/twf-queue` now returns `{items, next_cursor, has_more}` with default limit 50 and maximum 100, plus optional `cursor` and `state=READY|HELD`. The operator sort is `admitted_at DESC, queue_entry_id DESC`. The cursor carries the last key, owner, filter, and version under a session-keyed HMAC; malformed, tampered, cross-owner, and cross-filter cursors return typed `INVALID_CURSOR` (HTTP 400). The owner/FIFO btree index supports reverse traversal; no speculative index was added. Future execution FIFO remains `admitted_at ASC, queue_entry_id ASC` and is not driven by this operator list.

## K. F3 UI behavior

Trade → Execution Queue opens on the newest page. All/Ready/Held filters, Load older, and Back to newest expose the full list without page numbers. Older pages append with ID deduplication; a request epoch prevents stale refreshes from mixing pages after filter changes. A new admission refreshes the newest view. Status-card counts label loaded rows rather than claiming global totals. The compact Trade visual design remains unchanged.

## L. F3 traversal and adversarial results

Parameterized tests created 125 and 500 bound Orders/Entries, including many identical admission timestamps. With page size 37, traversal reached **125/125 rows in 4 pages** and **500/500 rows in 14 pages** on each dialect: **0 duplicates, 0 omissions**. They also verify malformed, tampered, and filter-mismatched cursors; strict tie ordering; and insertion between pages. The new Entry appears on refreshed page one without altering older cursor results. A READY→HELD change between filtered pages leaves the next page READY-only with no repeated entry; this is live-list behavior, not a multi-page snapshot. An API test verifies that a cursor cannot cross owners. A component test and PostgreSQL-backed browser tests cover Load older, Back to newest, state filter, and narrow/desktop layout. On the 500-row dataset, PostgreSQL `EXPLAIN` used an `Index Only Scan Backward` on `ix_twf_queue_entries_owner_fifo` for the first page. Focused PostgreSQL timings (ms) were admission 12.58, replay 3.13, Hold 6.27, Release 4.96, first page 4.26, next page 4.71; SQLite timings were 7.31, 1.90, 4.92, 3.17, 2.79, 3.05 respectively. These are bounded sanity observations, not service-level targets.

## M. Migration validation

Disposable PostgreSQL and SQLite tests cover fresh upgrade to 0026, existing Queue data downgrade to 0025 and re-upgrade to 0026, preservation of Entries and audit rows, and refusal of incoherent 0025 data without silent repair. The live disposable PostgreSQL check reported server 16.15, backend PID 2391330, database `twf_test_db1`, and `read committed` isolation. Offline PostgreSQL SQL generation passes. `0025_twf_queue.py` remains byte-for-byte unchanged.

## N. PostgreSQL / SQLite parity

The same binding and history invariants were verified on both dialects. PostgreSQL is the primary database. SQLite remains explicit fallback only; there is no automatic failover or dual-write. SQLite's table rebuild requires an operator-controlled schema migration window with API writers stopped.

## O. DB-1 regression status

DB-1's exact snapshot importer still requires a verified immutable SQLite backup and an empty PostgreSQL destination. The deferred-FK insertion-order compatibility fix retains all constraints and post-copy FK checks. The former test that wrote an incoherent Order now expects the stronger database rejection and confirms idempotent replay still returns the original Entry.

## P. OE-1/OE-2 regression status

The only OE-1 persistence touch is the nullable Queue binding and model-registration import needed by its database schema; no OE-1 lifecycle, canonical identity, or source-trust logic changed. OE-2 Preview/Create code was unchanged. Both full backend gates include their focused tests.

## Q. Frontend and browser results

The frontend unit suite passed **295/295** across 33 files. PostgreSQL-backed Chromium tests passed **8/8** at 390 px and 1440 px: shared Trade Orders/Positions navigation, admission, Hold/Release, Queue pagination, the retained synthetic Broker New Order path, and responsive width. TypeScript, ESLint, Prettier, and production build passed. No live broker submission was made.

## R. Static gates

Changed-file mypy passed on 10 source files. Repository mypy (`mypy apps/api/src apps/api/tests`) reports **11 errors in three untouched tests**: `test_derivative_templates.py`, `test_option_chain.py`, and `test_derivative_relative_volume.py`. The earlier DB-1 report recorded 15 errors in the same files; the current command still finds no error in changed files, and all three debt files match HEAD. Ruff, Ruff format (234 files), compileall, pip check, TypeScript, ESLint, Prettier, production build, and `git diff --check` passed.

## S. Files changed

- Migration: `apps/api/alembic/versions/0026_oe3_queue_hardening.py` (new); migration 0025 unchanged.
- Backend: `apps/api/src/twf/api/twf_queue.py`, `apps/api/src/twf/infrastructure/database.py`, `apps/api/src/twf/infrastructure/sqlite_migration.py`, `apps/api/src/twf/infrastructure/twf_order.py`, `apps/api/src/twf/infrastructure/twf_queue.py`, `apps/api/src/twf/queue/contracts.py`, `apps/api/src/twf/queue/errors.py`, `apps/api/src/twf/queue/service.py`.
- Backend tests: `apps/api/tests/test_database_db1_remediation.py`, `apps/api/tests/test_database_foundation.py`, `apps/api/tests/test_twf_queue_oe3.py`, `apps/api/tests/test_twf_queue_oe3_hardening.py` (new).
- Frontend: `apps/web/src/components/orders/queue-workspace.tsx`, `apps/web/src/lib/twf-queue.ts`, `apps/web/src/styles/orders.css`.
- Frontend tests: `apps/web/tests/browser/twf-queue.spec.ts`, `apps/web/tests/queue-pagination.test.tsx` (new).
- Documentation: `README.md`, `docs/TWF_QUEUE_OE3_ARCHITECTURE.md`, `docs/TWF_OE3_HARDENING_REPORT.md` (new).

## T. Known limitations

Operator pagination is not a cross-page snapshot; a Hold/Release can move a row into or out of a state-filtered page between requests. A session refresh invalidates older cursors. No worker exists, so execution FIFO is documented and indexed but cannot yet be exercised by an OE-4 consumer. Live authoritative runtime migration is an operator action outside this disposable-test implementation.

## U. Scorecard

```text
OE3_HARDENING_STATUS = PASS

F1_DB_COHERENCE_POSTGRES = PASS
F1_DB_COHERENCE_SQLITE = PASS
F1_READY_WITH_ENTRY_REJECTED = PASS
F1_QUEUED_WITHOUT_ENTRY_REJECTED = PASS
F1_MISMATCHED_PAIR_REJECTED = PASS
F1_OWNER_MISMATCH_REJECTED = PASS
F1_ENTRY_DELETE_REJECTED = PASS
F1_SERVICE_ADMISSION_STILL_ATOMIC = PASS
F1_CONCURRENT_REPLAY = PASS
F1_FUTURE_STATE_COMPATIBILITY = PASS

F2_EVENT_UPDATE_REJECTED_POSTGRES = PASS
F2_EVENT_DELETE_REJECTED_POSTGRES = PASS
F2_EVENT_UPDATE_REJECTED_SQLITE = PASS
F2_EVENT_DELETE_REJECTED_SQLITE = PASS
F2_BULK_MUTATION_REJECTED = PASS
F2_NORMAL_EVENT_INSERT = PASS
F2_HISTORY_ORDER_PRESERVED = PASS

F3_KEYSET_PAGINATION = PASS
F3_DEFAULT_NEWEST_VISIBILITY = PASS
F3_STABLE_TIE_BREAK = PASS
F3_125_ENTRY_TRAVERSAL = PASS
F3_500_ENTRY_TRAVERSAL = PASS
F3_DUPLICATES = 0
F3_OMISSIONS = 0
F3_INSERT_BETWEEN_PAGES = PASS
F3_OWNER_ISOLATION = PASS
F3_CURSOR_VALIDATION = PASS
F3_UI_NAVIGATION = PASS
F3_FIFO_SEMANTICS_UNCHANGED = PASS

MIGRATION_0026_CREATED = PASS
MIGRATION_0025_UNCHANGED = PASS
MIGRATION_EXISTING_DATA_PRESERVED = PASS
MIGRATION_CORRUPT_DATA_REFUSED = PASS
MIGRATION_POSTGRES_UP_DOWN_REUP = PASS
MIGRATION_SQLITE_COMPATIBILITY = PASS

DB1_FROZEN_INTACT = PASS
OE1_FROZEN_INTACT = PASS
OE2_FROZEN_INTACT = PASS
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

OE3_READY_FOR_INDEPENDENT_REVIEW = YES
```

## V. Final status

**READY_FOR_INDEPENDENT_REVIEW.** OE-3 is not accepted or frozen; OE-4 remains blocked pending the separate adversarial review. No commit, tag, or push was made.

# DB-1 final focused acceptance review

Date: 2026-10-15. Scope: DB1-R1, DB1-R2, SQLite MCP timeout ordering, primary/fallback gates, authority, and bounded recovery. **Decision: PASS; recommend `ACCEPT_AND_FREEZE`.** This is a review recommendation, not a commit, tag, deployment change, or closure of OE-3 findings.

## A. Executive verdict

R1 exact-value preservation/refusal, R2 caller-visible replay, and both MCP commit orders passed independent probes. Two sequential complete SQLite suites and the complete disposable PostgreSQL suite passed. The authoritative PostgreSQL data, immutable SQLite recovery point, and fresh dump/restore passed bounded verification. No new HIGH or CRITICAL DB-1 finding was found. The earlier independent review's FAIL and the subsequent remediation report's SQLite-gate FAIL remain historical facts; this review follows the later timing correction.

## B. Preflight

Branch `main`; HEAD `5d45a4c14e8b6c2e092e5573dce2e14599319e86`; safety checkpoint `safety/db1-remediation-pre-mcp` points to that commit. Before this review, the worktree already had modified MCP durability/permit tests and the remediation report, plus untracked MCP timing test and investigation report. They were preserved. `git diff --check` passed. No reset, stash, checkout, commit, tag, or push was performed.

## C. R1 numeric verification

The permanent 77-test DB1 suite passed. It includes the original `NUMERIC(20,5)` adversary, 60 precision/scale grid cases, ambiguous REAL refusal, excess-scale refusal, exact INTEGER/TEXT storage, Python-float rejection, verification against the former rounded value, and rollback after an earlier table insert. A separate direct probe against a fresh disposable PostgreSQL schema confirmed `12345678901.12345` reached a `NUMERIC(20,5)` destination **exactly** with `IMPORTED_AND_VERIFIED`; the `NUMERIC(20,6)` ambiguity raised `NumericMigrationFailure` and left zero destination rows (2/2 probes passed).

A fresh 4,000-case raw-SQLite-driver oracle accepted 2,085, explicitly refused 1,915, and found **zero accepted-value mismatches**. The oracle may inspect raw floats; the production converter rejects Python floats and independently checks REAL round-trip uniqueness at declared scale. Conservative refusal remains intentional. Evidence: `var/db1/final_review/numeric_exact.log`, `numeric_stress.json`, and `db1_focused.log`.

## D. R2 Queue replay verification

The permanent controlled interleaving forces caller A's READY read, caller B's committed admission, then A's replay. Its assertions require A to return B's exact entry, one QUEUED Order, one Queue Entry, one Queue event, one Order transition event, and actual PostgreSQL READ COMMITTED. The two 100-round series passed with 2/5/10 callers per round, exactly one durable entry and coherent histories per Order, and **zero caller-visible false `QUEUE_INVARIANT_FAILURE` errors**. The genuine direct-SQL READY/Entry corruption test still raises that invariant error. Thirty ten-way Hold/Hold, Hold/Release, and Release/Release rounds retained single-transition/version/event semantics. Backend-termination rollback and existing identity constraints passed. This validates the bounded service replay fix; it does not close OE-3 F1.

## E. MCP timeout-ordering verification

The prior 400 ms test deadline could expire before settlement commit even though the test asserted the post-commit-success marker. The current event-controlled regressions force both orders: timeout first yields durable `COMPLETE/TIMEOUT` without recovery debt; success commit first yields durable `COMPLETE/SUCCESS` with recovery debt visible to a fresh manager. Both direct tests passed. The corrected durability and permit tests use receipt, handler-entry, commit, and close events/explicit operation expiry; no sleep-only ordering or production deadline change was introduced. The post-commit test still asserts the persisted marker and reconciliation barrier. No production MCP file changed for the timing correction. Fresh repetitions passed: exact target **50/50** independent processes; full six-parameter family **20/20** cycles; entire durability module **10/10** runs. Evidence: `mcp_commit_orders.log`, `mcp_repeat_summary.json`, and the earlier deterministic red probe in the investigation report. No lost committed marker or production durability defect was reproduced.

## F. Full SQLite fallback gate

Two **sequential** explicit SQLite runs passed without overlapping heavy gates: **1,466 passed / 72 skipped** in 480.75 s and **1,466 passed / 72 skipped** in 539.19 s. Skips are PostgreSQL-only importer, row-lock, forced READ COMMITTED, and backend-termination probes; the applicable SQLite durability and Queue paths passed. Evidence: `sqlite_full_1.log`, `sqlite_full_2.log`.

## G. Full PostgreSQL primary gate

`tools/test-postgres.sh -q` passed **1,537 / 1 skipped** in 632.06 s on a fresh socket-only PostgreSQL cluster. The sole skip is SQLite's explicit `BEGIN IMMEDIATE` contention test. Focused PostgreSQL R1/R2 passed **77/77** in 58.50 s. Focused frozen OE-1/OE-2 passed **102/102** in 52.06 s. The launcher sets the actual PostgreSQL URL and isolates each test in a disposable schema; no authoritative runtime database was used by these suites. Evidence: `postgres_full.log`, `db1_focused.log`, `oe1_oe2_focused.log`.

## H. Authority and fail-closed behavior

The authoritative container remained healthy. The normal local API/web processes were not listening at preflight, so a bounded real API process was started with the existing runtime configuration: `/ready` returned HTTP 200, `database_backend=PostgreSQL`, `database_status=ready`, `database_checked=true`; it was then stopped. A separate application session confirmed actual dialect `postgresql`, database `twf`, UTC timezone, and `0025_twf_queue`. Missing URL, deliberately wrong PostgreSQL credentials, and a closed PostgreSQL port all failed startup without initialization; a stale SQLite marker remained unchanged. An outage of the **disposable restore server**, not the authoritative server, gave `/health` 200 and `/ready` 503, then `/ready` 200 on recovery. Code/config review found one chosen engine and no automatic fallback, reverse sync, or dual-write path. Explicit SQLite mode remains available only via an operator-supplied URL. Evidence: `authority.json`, `recovery-result.json`.

## I. Backup and restore sanity

A fresh 12,058,868-byte custom PostgreSQL dump restored into a separately named disposable container/database. Independent sorted PostgreSQL `row_to_json` content matched **all 46 tables** between authoritative source and restore. The restored app reached ready 200, used UTC, and ran under a non-superuser/non-role-creating/non-database-creating application role. A truncated dump and restore into the populated destination both failed. Disposable stop/recreate retained a committed marker and discarded an uncommitted crash-time row. The old SQLite snapshot correctly **refused** full verify-only equivalence to newer PostgreSQL because broker read timestamps changed after cutover. The disposable container and volume were removed; the authoritative container/volume were not stopped. Evidence: `fresh-runtime.dump`, `recovery.log`, `recovery-result.json` under ignored `var/db1/final_review/`.

## J. Original data fidelity and SQLite preservation

An independent positional, type-aware, read-only comparison found **45 application tables / 4,052 original rows**, zero missing original rows and no changed original business values. Current PostgreSQL has four additional `scanner_v2_runs` (135 original, 139 current); the single original `broker_accounts` row differs only in `updated_at` and `last_read_at`. The user previously confirmed precisely those post-cutover activities. The current 4,056 rows are **not** claimed equal to the historical 4,052-row snapshot. Original SQLite remains 100,544,512 bytes with SHA-256 `1c63f76686fd845a0c5368218c94f47909ed2a96db05aec62eeeb0e5cd47b4bc`; immutable backup remains 100,544,512 bytes with SHA-256 `26d95bead54fba479e982965335d12ecc8a2d68f0b06ed6eefa96b26c1950f4f`, mode 0400 and immutable flag. Source/backup hashes and source mtime match the pre-review record after all gates. Evidence: `original_data_comparison.json` and final hashes.

## K. OE-1/OE-2 regression status

The focused 102-test live PostgreSQL gate passed, covering trusted identity/ownership, exchange-calendar expiry, READY immutability, CAS/state-event rollback, Preview terms/catalog binding, TTL, single-use, and atomic Preview-to-Order linkage. Frozen OE-1/OE-2 domain/runtime files were unchanged by the timing correction or this review. Distinct-preview global idempotency remains deferred.

## L. OE-3 and OE-4 scope separation

OE-3 F1 cross-table direct-SQL coherence, F2 Queue-event DB immutability, and F3 pagination are **pending**, neither fixed nor frozen here. R2's service-read repair is distinct. No Queue worker, SUBMITTING consumer, scheduling, risk execution loop, or Broker V2 handoff was implemented. Synthetic Broker browser coverage does not authorize live execution.

## M. Frontend and browser

In an isolated web copy, TypeScript, ESLint, Prettier, and production build passed. The initial unit run had **293 passed / 1 failed**, an intermittent Discovery evidence-dialog focus assertion. That test passed in isolation (25/25), then the complete unchanged suite passed **294/294**. The failed output is retained; this is a LOW test-stability observation, not a DB-1 authority/fidelity failure. PostgreSQL-backed Chromium smoke passed **12/12** at 390 and 1440 pixels: login, Watchlists, Scanner selection, Trade Orders/Positions, Equity/Futures/Option Preview → READY, Queue admission/Hold/Release, and the retained synthetic Broker flow. No live broker order was sent. Evidence: frontend and browser logs in `var/db1/final_review/`.

## N. Static gates

Ruff check passed; Ruff format check reports 232 files formatted; Python compileall and pip check passed. Changed MCP-test mypy passed (3 files). Repository mypy still reports exactly **15 pre-existing errors in three unchanged tests**: `test_option_chain.py`, `test_derivative_relative_volume.py`, and `test_derivative_templates.py`. Those files have no diff against HEAD. TypeScript, ESLint, Prettier, production build, and `git diff --check` passed. The repository-wide typing debt is classified `PRE_EXISTING_UNRELATED`, not silently marked green.

## O. Exact files changed by this review

Only `docs/TWF_DB1_FINAL_ACCEPTANCE_REVIEW.md` was added to the source tree in this review. Review-only scripts, logs, private dump and results are ignored under `var/db1/final_review/`; the frontend copy is under `/tmp/twf-db1-review-work`. The pre-existing uncommitted MCP test/documentation files listed in B were not modified by this review. No OE-1/OE-2 runtime, Scanner/Trade UI, Broker execution, OE-3 F1/F2/F3, or OE-4 file was changed.

## P. New findings

No new HIGH or CRITICAL DB-1 finding. One LOW intermittent frontend focus-test failure appeared in an initial full run; the unchanged isolated test and full rerun passed. It remains recorded for later test-stability work. The expected historical snapshot/live timestamp and scanner-run differences are documented data evolution, not corruption.

## Q. Required scorecard

```text
DB1_FINAL_REVIEW_STATUS = PASS

R1_NUMERIC_REPRO = PASS
R1_NUMERIC_STRESS = PASS
R1_FALSE_VERIFICATION_ELIMINATED = PASS
R1_REAL_ORIGINAL_DATA_PRESERVED = PASS

R2_CONTROLLED_INTERLEAVING = PASS
R2_200_CONTENTION_ROUNDS = PASS
R2_FALSE_INVARIANT_ERRORS = 0
R2_TRUE_CORRUPTION_STILL_DETECTED = PASS
R2_HOLD_RELEASE = PASS

MCP_ROOT_CAUSE_CONFIRMED_TEST_ORDERING = PASS
MCP_NO_PRODUCTION_DURABILITY_DEFECT_FOUND = PASS
MCP_BOTH_COMMIT_ORDERS_REGRESSED = PASS
MCP_EVENT_SYNCHRONIZATION = PASS
MCP_EXACT_CASE_REPEATED = PASS
MCP_FAMILY_REPEATED = PASS
MCP_DURABILITY_MODULE_REPEATED = PASS

FULL_SQLITE_RUN_1 = PASS
FULL_SQLITE_RUN_2 = PASS
FULL_POSTGRES = PASS
DB1_R1_R2_FOCUSED = PASS
OE1_OE2_FOCUSED = PASS

POSTGRES_PRIMARY_REAL = PASS
SQLITE_EXPLICIT_FALLBACK_ONLY = PASS
NO_AUTO_FAILOVER = PASS
NO_DUAL_WRITE = PASS
SQLITE_RETAINED_UNCHANGED = PASS

PG_DUMP_RESTORE = PASS
RESTORED_APP_READY = PASS
SESSION_TIMEZONE_UTC = PASS
ALEMBIC_HEAD = PASS

OE1_FROZEN_INTACT = PASS
OE2_FROZEN_INTACT = PASS
OE3_F1_PENDING = PASS
OE3_F2_PENDING = PASS
OE3_F3_PENDING = PASS
OE4_NOT_IMPLEMENTED = PASS

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

DB1_FREEZE_RECOMMENDATION = ACCEPT_AND_FREEZE
```

## R. Freeze recommendation

**`ACCEPT_AND_FREEZE` for DB-1.** This recommendation covers PostgreSQL-primary authority, explicit SQLite fallback, R1/R2 remediation, and the final MCP gate correction. It does not freeze OE-3 F1/F2/F3 or initiate OE-4. Git finalization is a separate explicit step; this review made no commit, tag, or push.

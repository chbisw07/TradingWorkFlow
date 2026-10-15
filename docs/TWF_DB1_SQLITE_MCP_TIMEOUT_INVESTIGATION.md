# DB-1 SQLite MCP timeout investigation

## Decision and scope

**Primary root cause: invalid test assumption about event ordering (LOW severity).** The `negative_after_commit` test paused after a successful settlement commit, but its 400 ms real-time deadline began at invocation entry. Under a broader SQLite run, that deadline could fire **before** settlement committed. A timeout that commits first is durably recorded as `COMPLETE/TIMEOUT`; it has no success-candidate recovery marker to retain. Conversely, when `COMPLETE/SUCCESS` commits first and the caller times out before receiving success, `reconciliation_required` remains true until negative reconciliation. Those are distinct, valid orderings. The previous test asserted the latter without ensuring it.

No MCP production code, DB-1-R1/R2 code, Queue/OE code, schema or provider deadline was changed. The repair synchronizes timeout at the exact post-commit barrier and adds a deterministic pre-commit ordering regression. Two neighboring MCP permit tests had related wall-clock assumptions. In the late-provider test, the 80 ms deadline could expire before the shielded handler entered; it now expires the operation after handler entry. In the real-pool shield test, a strict `elapsed < 0.15 s` assertion failed under suite scheduling even though the caller returned TIMEOUT; it now proves that the actual deadline expires and the public call returns while the real HTTPcore close remains blocked by an event. The explicit-expiry tests use a longer watchdog only to reach their intended event barriers. The shield test still waits for its real deadline, so its persisted deadline and status projection remain coherent.

The production effect observed in these probes is **none**: SQLite preserved the appropriate terminal state in both orderings, and a separate manager read the committed state correctly. The test effect was a false durability failure in the original case, plus pre-dispatch and elapsed-time failures in neighboring permit tests. This is not a waiver of the durability contract: the post-commit success-candidate test still asserts both the persisted marker and a fresh manager's `recovery_required` before permitting reconciliation.

## Preflight and original failure

At preflight, `main` was clean at `5d45a4c14e8b6c2e092e5573dce2e14599319e86`. The safety checkpoint is the local branch `safety/db1-remediation-pre-mcp` at the same commit. `git diff --check` passed. The existing DB-1 implementation and remediation reports were read; no DB-1 production files were edited.

The exact `sqlite-1-TIMEOUT` parameter passed its initial isolated run and 20 more independent processes (21/21), with per-process durations recorded in `isolated-summary.json`. Two prior full SQLite runs recorded in `TWF_DB1_REMEDIATION_REPORT.md` failed that exact parameter, and the earlier independent review saw the same family at `sqlite-0-TIMEOUT`. The independent pre-fix full SQLite run here had **1 failed, 1,463 passed, 72 skipped in 559.28 s**. It passed the original target at collection index 930, but failed `test_late_provider_result_is_quarantined` at index 990 because the handler-entry event did not arrive before the 1 s assertion. Its separate SQLite permit was already `COMPLETE/TIMEOUT`, with no provider outcome and no reconciliation debt; the 80 ms budget had expired before the handler could start. This moved failure is evidence of timing-sensitive test setup, not proof that the original failure disappeared. The first full SQLite run after the initial correction then found `test_real_pool_shield_does_not_extend_public_deadline[True-False]`: public TIMEOUT returned in 0.4295 s, exceeding its 0.15 s wall-clock assertion, while 1,465 tests passed and 72 skipped. This failure was not called a clean gate. The failed logs and persisted DB inspection are preserved privately under `var/db1/mcp_timeout/`.

## Deterministic timeline and contract

A review-only probe used a SQLAlchemy `before_commit` event and thread/asyncio events to force expiry on either side of settlement. It used the real `Operation.expire()` path and a separate `ConnectionManager.status()` read. The old unconditional `recovery_required` assertion was made deliberately red in the pre-commit branch without any predecessor; the expected/actual failure is preserved in `deterministic-old-assertion.log`.

| Forced ordering (monotonic seconds) | Persisted permit before reconciliation | Fresh peer status |
| --- | --- | --- |
| Expire 1209139.708632 → commit 1209139.711026 → status 1209139.715535 | `COMPLETE/TIMEOUT`, provider outcome `SUCCESS`, `reconciliation_required=false`, cleanup `COMPLETE` | `recovery_required=false` |
| Commit 1209139.959102 → expire 1209139.959226 → status 1209139.965292 | `COMPLETE/SUCCESS`, provider outcome `SUCCESS`, `reconciliation_required=true`, cleanup `COMPLETE` | `recovery_required=true` |

Both public callers received `TIMEOUT`. `Operation` owns an absolute monotonic deadline beginning at invocation. `ConnectionManager.completed()` serializes settlement, and `ConnectionManager.pending()` includes incomplete permits or permits with `reconciliation_required=true`. `status()` opens a fresh session; `view()` derives recovery from these persisted fields, not a process cache. The integrated S2-3 durability contract states that a committed **SUCCESS candidate** retains reconciliation obligation until post-return delivery receipt and that the callback cannot clear it before the timeout/cancellation boundary. It also states known negative outcomes stay negative. The old test conflated that committed success candidate with a negative outcome that had already won the commit race.

This evidence disproves the hypothesis that a post-commit marker was invisibly lost because of SQLite snapshot isolation. In the after-commit branch, a new connection sees the marker. In the before-commit branch, there is no marker to see because the committed terminal outcome is negative. Reconciliation does not need to race the status read to explain the failure.

## Predecessors and state inventory

The immediate predecessor plus target passed; previous ten plus target passed; all six family parameters passed; the durability module passed; the relevant durability/finalization/permit modules passed. Three shuffled reductions, seeds 1729, 2026 and 5170, also passed. There is **no required predecessor**: one case with expiry forced before `settle` commit reproduces the old assertion. The minimal reproducible sequence is `test_timeout_commit_ordering[sqlite-before_commit]` in isolation with the old unconditional marker assertion inserted; the permanent test instead asserts the actual durable negative state. The reduction details are in `predecessor-reduction.json`.

`tests/conftest.py` gives every SQLite case a distinct `tmp_path/isolated.db`, removes inherited `TWF_*` variables, and restores environment/chdir through `monkeypatch`. The MCP fixture creates a manager per test and disposes its engine. File-backed SQLite uses SQLAlchemy's normal pool (not `StaticPool`), with `check_same_thread=False`, Python sqlite `autocommit=False`, explicit commit/rollback and foreign keys enabled. The observed connection PRAGMAs were `journal_mode=delete`, `synchronous=2`, `foreign_keys=1`, `busy_timeout=200`, `locking_mode=normal`, `read_uncommitted=0`; WAL/SHM checkpoint behavior is inapplicable. Test-owned operations are drained, their deadline callbacks are canceled on completion, the operation ContextVar is reset, and manager/DB objects are fixture-local. Relevant test monkeypatches target instance attributes or use pytest's reversible `monkeypatch`; no cross-test singleton, fake-clock, leaked SQLite file handle or shared transaction was needed to reproduce the failure. A prior `BEGIN IMMEDIATE` case cannot leave a lock on this case's distinct DB file.

## Bounded correction and permanent regressions

- `apps/api/tests/test_mcp_durability.py`: waits for the connection receipt, pauses after the settlement transaction returns, invokes `scope.expire()` for TIMEOUT or cancels for CANCELLED, and checks the committed `COMPLETE/SUCCESS` marker before asking a fresh peer for `recovery_required`. It still checks admission is blocked until negative reconciliation and the final persisted negative result.
- `apps/api/tests/test_mcp_timing.py`: new event-controlled before-commit and after-commit regressions. Before commit, `COMPLETE/TIMEOUT` and no recovery debt are required; after commit, `COMPLETE/SUCCESS` and recovery debt are required. Both paths assert public TIMEOUT and operation drain.
- `apps/api/tests/test_mcp_permits.py`: the late-provider test now waits for actual handler entry, then explicitly expires the running operation. It retains its assertions that the late result is quarantined, no extra provider send occurs, no success tools are published, and status remains TIMEOUT. The real-pool shield test now waits for transport to reach the intended body/close phase, lets the real deadline expire, and asserts that the public TIMEOUT returns while HTTPcore close is still blocked. A bounded test watchdog detects a public path that incorrectly awaits teardown. Its existing permit, drain, disconnect and cleanup-error assertions remain.

No sleep was added. No production deadline or recovery behavior was relaxed. The review-only red probe was removed from the test tree after being converted to the permanent regressions.

## Validation

The exact target passed 100/100 independent SQLite processes (mean 2.378 s; range 2.071–3.787 s), the six-case family passed 50/50 cycles, the durability module passed 20/20 independent runs, and the minimal controlled sequence passed 50/50 cycles. All timing distribution samples are in `repeat-summary.json`. Both corrected full SQLite suites passed: run 1 **1,466 passed / 72 skipped / 0 failed in 458.72 s**; run 2 **1,466 passed / 72 skipped / 0 failed in 425.38 s**. The 72 skips are the existing PostgreSQL-only importer/locking/recovery probes; they are exercised by the PostgreSQL gate.

The full disposable PostgreSQL suite passed **1,537 passed / 1 SQLite-only skip / 0 failed in 511.71 s**. Focused PostgreSQL DB1-R1/R2 passed **77 tests in 47.83 s**, including exact numeric preservation/refusal and two 100-round Queue replay contention series with no false invariant errors. Focused OE-1/OE-2 passed **102 tests in 40.32 s**. `tools/test-postgres.sh` used a temporary Unix-socket cluster, not the authoritative runtime database.

Ruff check, Ruff format (232 files), Python compileall, `pip check`, and `git diff --check` passed. Changed-file mypy passed with `MYPYPATH=src`. Repository-wide mypy reports exactly the previously documented 15 errors in the same three untouched test files (`test_option_chain.py`, `test_derivative_relative_volume.py`, `test_derivative_templates.py`); no new typing error was introduced. Logs and gate summaries are under the ignored private `var/db1/mcp_timeout/` directory. A direct check of the final diff confirms no changes to OE-3 F1/F2/F3 or OE-4 implementation. Frontend/browser checks are not required for a tests-and-documentation-only correction.

## Boundaries and remaining risk

This is a test synchronization repair only. It does not close OE-3 F1/F2/F3, does not add OE-4, and does not freeze DB-1. The existing limitations in the DB-1 reports remain. Validation uses synthetic MCP providers and disposable PostgreSQL; no broker order is submitted. Frontend unit/build/browser work is not required because no production code or frontend code changed.

## Root-cause report

```text
ROOT_CAUSE_CLASS = INVALID_TEST_ASSUMPTION
ROOT_CAUSE_SUMMARY = The short test deadline could expire before SQLite settlement committed; the test asserted post-commit success-marker semantics without proving timeout happened after that commit. Two adjacent permit tests also depended on short wall-clock scheduling to reach their intended phase.
MINIMAL_REPRO_SEQUENCE = No predecessor; force Operation.expire() at the SQLite settle before_commit hook in the single timing test and apply the old unconditional recovery_required assertion.
DETERMINISTIC_REPRO = YES
SEVERITY = LOW
```

## Required scorecard

```text
MCP_TIMEOUT_INVESTIGATION_STATUS = PASS

ORIGINAL_FAILURE_REPRODUCED = PASS
ISOLATED_20_RUNS = PASS
FULL_SUITE_FAILURE_REPRODUCED = PASS
MINIMAL_PREDECESSOR_FOUND = PASS
ROOT_CAUSE_IDENTIFIED = PASS
DETERMINISTIC_REPRO_CREATED = PASS

SQLITE_DB_ISOLATION_VERIFIED = PASS
FIXTURE_ISOLATION_VERIFIED = PASS
GLOBAL_STATE_CLEANUP_VERIFIED = PASS
BACKGROUND_TASK_CLEANUP_VERIFIED = PASS
TIMEOUT_CONTRACT_VERIFIED = PASS
COMMIT_VISIBILITY_VERIFIED = PASS
RECOVERY_REQUIRED_SEMANTICS_VERIFIED = PASS

PRODUCTION_FIX_REQUIRED = NO
PRODUCTION_FIX_BOUNDED = NOT_REQUIRED
TEST_FIX_REQUIRED = YES
TEST_FIX_BOUNDED = PASS

EXACT_CASE_100_RUNS = PASS
TEST_FAMILY_50_CYCLES = PASS
MCP_MODULE_20_RUNS = PASS
PREDECESSOR_SEQUENCE_50_RUNS = PASS

FULL_SQLITE_RUN_1 = PASS
FULL_SQLITE_RUN_2 = PASS
FULL_POSTGRES = PASS

DB1_R1_REGRESSION = PASS
DB1_R2_REGRESSION = PASS

OE1_REGRESSION = PASS
OE2_REGRESSION = PASS
OE3_F1_F2_F3_UNCHANGED = PASS
OE4_NOT_IMPLEMENTED = PASS

CHANGED_FILE_MYPY = PASS
REPO_MYPY = PRE_EXISTING_UNRELATED
RUFF = PASS
FORMAT = PASS
COMPILE = PASS
PIP_CHECK = PASS
GIT_DIFF_CHECK = PASS

DB1_FINAL_GATE_READY = YES
```

`FULL_SUITE_FAILURE_REPRODUCED=PASS` covers the two historical full-suite failures of the exact parameter and this investigation's pre-fix full-suite failure in the adjacent timer setup; the independent full run here did **not** fail the original parameter. The original assertion itself was reproduced deterministically by the single-test pre-commit interleaving. `MINIMAL_PREDECESSOR_FOUND=PASS` means the minimal predecessor set was established as empty, not that one earlier test was identified. The repo-wide mypy debt is unchanged and does not satisfy a new-code failure condition.


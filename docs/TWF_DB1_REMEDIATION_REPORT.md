# DB-1 R1/R2 remediation report

Date: 2026-10-15. Scope: numeric fidelity and PostgreSQL Queue replay consistency only. **R1/R2 fixes and focused regressions pass; overall acceptance is FAIL because the full SQLite gate remains red. DB-1 is not frozen.**

## A. Executive remediation verdict

Both original failures were reproduced before changing production code. The permanent R1/R2 regressions, 211-test focused PostgreSQL gate, both 100-round contention series, and full PostgreSQL gate pass. The complete SQLite gate failed twice at the existing MCP timeout-sensitive durability assertion, including a serial retry. Under the requested acceptance rule, **DB1_REMEDIATION_STATUS = FAIL** and **DB1_READY_FOR_FOCUSED_REREVIEW = NO**. The exact remaining gate blocker is recorded in P/S; no unrelated MCP repair was made. This is a subsequent corrective pass; the independent review's original FAIL verdict is preserved.

## B. Preflight and worktree preservation

Branch `main`; HEAD `603131d07cf0d704d2dcd681fcab4456c4595b82`. Pre-existing DB-1 and OE-3/Trade work was recorded in `var/db1/remediation/preflight-status.txt`; 65 existing modified/untracked files were fingerprinted in `preflight.json`. No reset, stash, clean, checkout, commit, tag or push. Final per-file comparison found exactly six authorized edits among those files plus the two new files in R; no unrelated change. The original independent review remains an exact byte prefix of the append-only document. Existing runtime configuration, migrations, frozen OE-1/OE-2 code and unrelated UI work are preserved. Evidence: `final-preservation.json`.

## C. R1 root-cause confirmation

The original test failed with source `NUMERIC(20,5)` semantics `12345678901.12345`, destination `12345678901.12340`, and status `IMPORTED_AND_VERIFIED`. SQLite stored the value as REAL. Its ordinary `CAST(... AS TEXT)` returned `12345678901.1234`, while the original SQLAlchemy Numeric read returned `.12345`. The source hash, insert and verifier all consumed the shortened representation.

Storage inspection also demonstrated why INTEGER and REAL must be treated separately: integer `9007199254740993` is exact in SQLite, but formatting it through REAL or the ORM's float conversion can lose the last unit. Evidence: `before-fix.log`, `sqlite-type-inspection.json`.

## D. R1 implementation

`sqlite_migration.py` now checks SQLite storage class and matching explicit precision/scale declarations. INTEGER is read as exact integer text, TEXT as its stored string, and NULL unchanged. Numeric conversion accepts only text, integer or Decimal; Python float is explicitly rejected. Values must be finite and fit precision/scale exactly.

For REAL, high-detail SQLite formatting proposes a declared-scale Decimal candidate. Three independent SQL comparisons against the stored value certify that the candidate round-trips while both adjacent scale values do not. If there is no candidate or more than one possible candidate at that scale, the importer refuses. Formatting is never sufficient proof. This is a conservative reconstruction of uniquely representable declared-scale semantics, not a promise to recover decimal intent lost before SQLite storage.

`NumericMigrationFailure` carries table, column, primary key, declared type and sanitized reason. No offending numeric value is printed. No lossy override exists. Source inventory uses certified values; PostgreSQL destination values are read independently as Decimal and checked for exact representability. The existing transaction, locks, FK validation and sequence handling remain intact.

## E. R1 adversarial evidence

| Case | Original behavior | Remediated behavior |
| --- | --- | --- |
| `NUMERIC(20,5)`, `12345678901.12345` | `.12340`, falsely verified | Exact `.12345`, verified; independent equality passes |
| Same stored REAL, `NUMERIC(20,6)` | Shortened decimal falsely verified | Explicit ambiguity refusal; no import |
| `NUMERIC(10,2)`, `1.234` | Potential destination rounding | Explicit refusal before certification |
| Exact INTEGER `9007199254740993`, `NUMERIC(20,0)` | At risk through float normalization | Exact stored integer preserved |
| Already-imported old `.12340` versus original `.12345` | Same lossy source hash could pass | Verify-only rejects mismatch; destination remains unchanged |

Permanent tests include the original R1 reproduction, 60 grid cases across `(10,2)`, `(15,4)`, `(20,5)`, `(20,6)`, exact/unsupported storage classes, NULL, trailing zeros, positive/negative micro-values, near/max bounds, excess precision/scale, explicit Python-float refusal and whole-import rollback after an earlier table has already been inserted. A manufactured decimal-TEXT affinity mismatch is correctly refused by SQLite integrity checking; its exact extraction is tested separately without certifying an invalid source database.

A separate independent 4,012-value cross-check accepted 2,082 and explicitly refused 1,930; **zero accepted values differed from the independent raw-driver/declared-scale oracle**. That oracle may use raw floats to attack the implementation; the production migration path does not. Evidence: `numeric-independent-stress.json`. All safe test values are synthetic.

## F. R1 current-data verification

The immutable source still contains **45 application tables / 4,052 rows**. A fresh import into disposable PostgreSQL passed independent per-table comparison of every value, using the review's separate serializer rather than importer hash helpers (`fresh-import-independent.json`). All 46 tables including Alembic match exactly. A final isolated rerun also passed after tightening the independent JSON-number normalizer to exact coefficient/exponent tuples; it performs no Decimal-context rounding (`fresh-import-final.log`).

The live database now has **4,056 application rows**, because four scanner runs were added after cutover. All 135 original scanner runs are unchanged. All 4,052 original rows remain present; the only changed original columns are broker-account `last_read_at` and `updated_at`. Every other original business value matches. The user explicitly confirmed these four scans and broker read timestamps are expected post-cutover usage. These are documented differences, not silently excluded corruption or an exact full-snapshot match. The importer correctly refuses to certify the newer live database against the older snapshot.

Evidence: `independent-runtime.json`, `runtime-deltas.json`, user confirmation in this session. No production data was changed for verification. The scorecard's retained-data PASS means all original business data is preserved with these explicitly confirmed operational changes; it does not claim that 4,056 current rows equal a 4,052-row historical snapshot.

## G. R2 root-cause confirmation

The controlled original reproduction loaded READY into caller A's ORM identity map, committed caller B's atomic Queue admission, then let A observe the new Entry. A falsely raised `QUEUE_INVARIANT_FAILURE` by comparing that Entry to stale READY. `before-fix.log` records the failure. Durable admission itself was not broken.

## H. R2 implementation

Authentication and ownership checks remain first. Existing-admission replay now selects Queue Entry and linked Order together in one statement under unchanged READ COMMITTED. `populate_existing=True` replaces stale ORM state with that statement's snapshot. An outer join plus owner/state validation detects broken linkage or inconsistent state instead of treating it as success. The bounded-contention fallback uses the same read.

The admission write transaction, uniqueness/CAS checks, event creation, expected-version policy, Hold/Release and SQLite contention policy are unchanged. No global isolation change, additional sleep, broad exception suppression or new worker path was added.

## I. R2 deterministic interleaving result

The preserved reproduction forces A's READY read → B's committed admission → A's replay read. After remediation A returns B's exact Entry and QUEUED Order. Two callers, one durable Entry, one Queue admission event and one Order → QUEUED event; zero false invariant errors. Actual session isolation is asserted READ COMMITTED. This test intentionally skips only in SQLite mode, where the forced two-snapshot pattern is not the PostgreSQL behavior under review.

## J. R2 contention results

Two independently initialized 100-round series cycle 2/5/10 callers. Each series has **563 concurrent Preview/Create calls and 563 Queue calls**. All Create calls return the one linked Order; all Queue calls return the one Entry. Every round checks raw persisted Order, Preview linkage, Entry and both event counts.

| Series | Rounds | Preview calls | Queue calls | Durable Entries | QUEUED Orders | Queue events | Order → QUEUED events | False invariant errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 100 | 563 | 563 | 100 | 100 | 100 | 100 | 0 |
| 2 | 100 | 563 | 563 | 100 | 100 | 100 | 100 | 0 |

The permanent test runs both series on PostgreSQL and shorter ten-round series on explicit SQLite. Thirty ten-way Hold/Hold, mixed Hold/Release and Release/Release rounds retain exactly one successful transition/version increment per round and coherent history. Genuine direct-SQL READY/Entry corruption still raises the invariant error; wrong-owner/link writes remain rejected by existing constraints. No live Broker writes occur.

## K. R2 rollback and deadlock results

Termination of the Queue PostgreSQL backend after its uncommitted Order update rolls back everything: Order READY, zero Entry, zero Queue event and zero QUEUED event. Retry succeeds. Independent faults after Queue insert, Order transition and event creation also roll back. Opposite-order row-lock contention produces one `40P01` loser and one complete winner without partial updates; pool exhaustion is bounded and recovers. Both 100-round admission series finish without deadlock. This is bounded evidence, not a claim of global deadlock freedom.

## L. PostgreSQL/SQLite authority verification

Runtime `/ready` and actual SQL sessions report PostgreSQL; application sessions use UTC. Missing configuration and closed-port failures are covered by backend gates, deliberately incorrect real PostgreSQL authentication fails closed, and stopping only the disposable recovery container returns ready=503 while health=200. Restart restores readiness. No automatic fallback, dual-write, reverse-sync or changed authority configuration was added. The final retained SQLite fingerprint equals preflight: SHA-256 `1c63f76686fd845a0c5368218c94f47909ed2a96db05aec62eeeb0e5cd47b4bc`, size 100,544,512 bytes, mtime_ns `1792045580078891452`, and no sidecars. The immutable backup and manifest retain their original verified hash, 0400 permissions and immutable flag. Final read-only runtime comparison still finds only the expected two-table differences described in F. Evidence: `final-preservation.json`, `independent-runtime-final.log`, `runtime-deltas-final.log`, `security-results.json`.

## M. OE-1/OE-2 regression status

Focused PostgreSQL gate: **211 passed**, 160.93s. It includes frozen Order/Preview behavior, Queue, DB-1 and the permanent remediation cases. The two 100-round Preview series, SQL fault rollback, exact binding, TTL/single-use, provenance, owner and CAS tests pass. Changed-file mypy passes. Frozen runtime code remains unchanged; global idempotency across distinct previews stays deferred.

## N. OE-3 scope separation

F1 direct-DB cross-table coherence, F2 Queue event immutability and F3 Queue pagination remain explicitly pending. No trigger, constraint, migration or pagination implementation was added. The corruption regression deliberately retains F1's reproducible direct-write gap while proving replay does not hide it. No OE-4 worker, SUBMITTING, scheduling, risk checks or Broker handoff is implemented.

## O. Backup/restore verification

A new private PostgreSQL custom dump was restored to a separately named disposable container/database. Independent sorted `row_to_json` comparison matches all 46 current PostgreSQL tables, including the four expected new scanner runs. Restored startup succeeds with UTC sessions. Comparing it against the older SQLite snapshot correctly refuses the broker timestamp mismatch. A truncated dump and nonempty restore fail. Restart/recreation retains committed data; crash rolls back an uncommitted row. Only the specifically named disposable container and volume were removed; the authoritative instance was never stopped.

The first rehearsal encountered a disposable-container initialization/readiness race. The harness was corrected to wait for the final TCP listener rather than the temporary initialization socket and the full rehearsal passed. No production repair was involved. Evidence: `recovery.log`, `recovery-rerun.log`, `recovery-result.json`, `fresh-runtime.dump`.

## P. Full backend/frontend/browser gates

Full backend gates ran sequentially; the second complete SQLite run also ran without concurrent browser/build work:

| Gate | Result |
| --- | --- |
| Full PostgreSQL | **1,535 passed, 1 skipped**, 626.33s |
| Full explicit SQLite | **FAIL: 1,463 passed, 1 failed, 72 skipped**, 452.79s; independent serial retry: same counts, 448.56s |
| Frontend units / build / static | 294 tests passed; build, TypeScript, ESLint and Prettier passed |
| PostgreSQL browser, 390/1440 | 12 passed, 1.7 minutes |

The PostgreSQL skip is solely the explicit SQLite `BEGIN IMMEDIATE` contention
probe. No PostgreSQL-critical remediation case is skipped on PostgreSQL. SQLite skips consist of four existing PostgreSQL-only probes, 66 importer cases requiring a PostgreSQL destination, the forced READ COMMITTED interleaving, and backend termination. Its applicable Queue remediation and corruption/concurrency cases pass.
Frontend/browser use an isolated working copy, synthetic providers and disposable
PostgreSQL; no live broker order.

## Q. Static gates

Ruff, format, compileall, pip check and changed-file mypy pass. Full mypy still reports exactly 15 existing errors in `test_option_chain.py`, `test_derivative_relative_volume.py`, and `test_derivative_templates.py`; all three remain byte-identical to HEAD. TypeScript, ESLint and Prettier also pass. Final preservation and `git diff --check` pass. The MCP durability test and connection implementation are byte-identical to HEAD. No static check was relaxed.

## R. Exact files changed in this pass

- `apps/api/src/twf/infrastructure/sqlite_migration.py`
- `apps/api/src/twf/queue/service.py`
- `apps/api/tests/test_database_db1_remediation.py`
- `docs/TWF_DATABASE_ARCHITECTURE.md`
- `docs/TWF_SQLITE_TO_POSTGRES_MIGRATION_RUNBOOK.md`
- `docs/TWF_DB1_IMPLEMENTATION_REPORT.md`
- `docs/TWF_DB1_INDEPENDENT_REVIEW.md` (append-only remediation addendum)
- `docs/TWF_DB1_REMEDIATION_REPORT.md`

Ignored private artifacts: `var/db1/remediation/`; temporary isolated validation workspaces under `/tmp`. No credentials are included in source/report text.

## S. Known limitations

Conservative REAL refusal is intentional: exact decimal intent lost before storage cannot be recovered, and ambiguous scale is not guessed. No force-lossy option exists. The immutable snapshot is historical and newer application writes are separately accounted for. Current real Order/Queue tables remain empty; populated execution-domain validation uses synthetic providers. Existing mypy debt, OE-3 F1/F2/F3, distinct-preview global idempotency and local deployment HA/PITR/off-host backup limitations remain separate.

The initial extended test run had one invalid manufactured TEXT-affinity fixture expectation; SQLite correctly refused its failed integrity check. The test was corrected to retain that refusal and independently test exact extraction. The subsequent focused gate passed all 211 tests. Earlier failed logs remain available and are not counted as passing gates.

The first full SQLite run also hit the existing timeout-sensitive MCP durability
case `test_negative_after_commit_retains_marker_until_reconciled[sqlite-1-TIMEOUT]`.
The same test family failed during the prior independent review. This exact case
passed in isolation (2.81s), but the complete serial retry again failed that exact
case at `tests/test_mcp_durability.py:158`: after the forced timeout,
`peer.status(...).recovery_required` was false. The earlier independent review also
recorded this family failing at `[sqlite-0-TIMEOUT]`. An isolated pass is not a
substitute for a clean full gate, and the repeated full-suite failure is not
waived as a flake. MCP production/test code and deadlines were not changed.
This is the exact blocker to the required overall PASS; its separate investigation
is outside DB1-R1/R2. Evidence: `sqlite_full.log`, `sqlite_full_serial_retry.log`,
`sqlite-timeout-isolated.log`, and the original `var/db1/review/sqlite-full.log`.

## T. Required scorecard

```text
DB1_REMEDIATION_STATUS = FAIL

R1_REPRODUCED_BEFORE_FIX = PASS
R1_NUMERIC_EXTRACTION_FIXED = PASS
R1_NO_BINARY_FLOAT_PATH = PASS
R1_LOSSY_VALUE_PRESERVED_OR_REFUSED = PASS
R1_FALSE_IMPORTED_AND_VERIFIED_ELIMINATED = PASS
R1_NUMERIC_GRID = PASS
R1_FAILURE_ATOMICITY = PASS
R1_REAL_4052_ROWS_STILL_MATCH = PASS
R1_RESTORE_STILL_MATCHES = PASS

R2_REPRODUCED_BEFORE_FIX = PASS
R2_DETERMINISTIC_INTERLEAVING_FIXED = PASS
R2_FIRST_100_ROUNDS = PASS
R2_SECOND_100_ROUNDS = PASS
R2_FALSE_INVARIANT_ERRORS = 0
R2_EXACTLY_ONE_QUEUE_ENTRY = PASS
R2_ORDER_QUEUED = PASS
R2_EVENTS_COHERENT = PASS
R2_TRUE_INVARIANT_FAILURE_STILL_DETECTED = PASS
R2_HOLD_RELEASE_REGRESSION = PASS
R2_CONNECTION_LOSS_ROLLBACK = PASS
R2_SQLITE_COMPATIBILITY = PASS

POSTGRES_PRIMARY_UNCHANGED = PASS
SQLITE_RETAINED_UNCHANGED = PASS
NO_AUTO_FAILOVER = PASS
NO_DUAL_WRITE = PASS
SESSION_TIMEZONE_UTC = PASS

OE1_FROZEN_SEMANTICS_INTACT = PASS
OE2_FROZEN_SEMANTICS_INTACT = PASS
OE3_F1_STILL_SEPARATE = PASS
OE3_F2_STILL_SEPARATE = PASS
OE3_F3_STILL_SEPARATE = PASS
OE4_NOT_IMPLEMENTED = PASS

FULL_BACKEND_POSTGRES = PASS
FULL_BACKEND_SQLITE = FAIL
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

DB1_READY_FOR_FOCUSED_REREVIEW = NO
```

R1 retained-data PASS is qualified by the explicit, user-confirmed post-cutover changes in F. Overall FAIL follows the full-SQLite-gate rule; it does not recategorize passing R1/R2 probes as failures.

## U. Final status

**DB1_REMEDIATION_STATUS = FAIL**

**DB1_READY_FOR_FOCUSED_REREVIEW = NO**

Both requested remediations are implemented with permanent regressions. The sole remaining required-gate blocker is the repeated full SQLite failure of `test_negative_after_commit_retains_marker_until_reconciled[sqlite-1-TIMEOUT]`. No DB-1 freeze, commit, tag or push. OE-3 F1/F2/F3 remain separate and pending; OE-4 was not started.

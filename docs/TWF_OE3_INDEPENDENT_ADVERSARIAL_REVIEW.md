# OE-3 independent adversarial review

**Review date:** 15 October 2026
**Baseline:** `fd7c391dd4f711b7a3dfaae31b8a6755c0ee3094` (`main`, with `safety/oe3-hardening-pre-review` at the same commit)
**Decision:** `OE3_REVIEW_STATUS = FAIL`; `OE3_FREEZE_RECOMMENDATION = REMEDIATION_REQUIRED`

## A. Executive verdict

OE-3 cannot be frozen. Direct SQL on normally configured PostgreSQL and SQLite connections rejected the tested incoherent Order/Queue writes and Queue-event updates/deletes. The independent attacks also found three boundary defects:

1. **CRITICAL — PostgreSQL Order/Queue coherence and Queue audit can be defeated by the actual application role.** The live `twf_app` role is a non-superuser and owns `twf_orders`, `twf_queue_entries`, and `twf_queue_events`. On a disposable PostgreSQL database, a matching non-superuser table owner dropped the reciprocal binding FKs and committed both `READY + Entry` and `QUEUED + missing Entry`. The same role disabled the Queue-event immutability trigger, changed a committed event, and re-enabled it. Ordinary DML was rejected while the constraints/trigger remained installed. No live row or schema was changed.
2. **HIGH — SQLite fallback coherence and audit depend on mutable connection/schema settings.** A normal app engine connection rejected incoherence while `PRAGMA foreign_keys=ON`. The same connection, after switching foreign keys off in DBAPI autocommit mode, committed both `READY + Entry` and `QUEUED + missing Entry`. Re-enabling foreign keys did not undo either write; `PRAGMA foreign_key_check` found the damage. The app connection could also drop the Queue-event update trigger, rewrite a committed event, and restore the trigger. SQLite has no separate database roles, so this is a direct-SQL/operator boundary rather than a demonstrated HTTP caller exploit.
3. **MEDIUM — a signed malformed Queue cursor returns HTTP 500.** An authenticated user can derive the cursor HMAC key from their own session cookie (`SHA-256(cookie)`), sign a structurally scoped cursor with `id: 0`, and receive HTTP 500 on both dialects. `UUID(0)` raises `AttributeError`, which `_parse_cursor` does not translate to `INVALID_CURSOR`. Ordinary truncated, altered-signature, oversized, cross-filter, and cross-owner cursors returned HTTP 400. No cross-owner rows were exposed.

The review changed no production code, migration, or permanent test. The report and ignored private probes are the only additions. OE-4 remains unimplemented.

## B. Preflight and repository preservation

The branch was `main`, the worktree was clean, `git diff --check` passed, and the safety branch existed. `HEAD` was the local OE-3 checkpoint `fd7c391`, one commit ahead of `origin/main` (`33ae038`); this differs from the attachment's expected equality but provided a stable, committed review baseline. `HEAD^{tree}` was `fe2db818a22195ac1530e84a2e92958c27a23b2d`. No reset, stash, clean, checkout, commit, tag, or push was performed. The Next build rewrote generated `apps/web/next-env.d.ts`; it was restored byte-for-byte from `HEAD` after the build. Before this report was created, `git status --short` was empty.

Baseline and final SHA-256 values matched for migration 0026 (`e42745f0d699fb3a7641a44a1a1f6e6ae9f4b291e1e88ec055d482a3d96261a0`), Queue persistence (`1d29c62c4fecf8ebdf92af063eed390769eaa6bc6dd7b9a63445b3d869ce1015`), Queue service (`a1487e2da7385166b1a8b19a797b337744340180f3eb12dd66ff18472db09516`), Queue API (`25819eb021cdc2c17db6f9472202701ead587b1a26372baa6588cade137c7c13`), Queue UI (`c0d45a891700792324c4e5d350b69caab134b2d71dc69d6b7ee84b5114b65be0`), hardening test (`7cdd988e01ac016d31848f3561ee05f7ccadc6b1caea2b4ce758a56525f04d6e`), and implementation report (`be5cfd47e3240e15ac8242443d88360b288fc1af2aa10757f8e4477b7b4e6fad`).

## C. Migration 0025/0026 review

`0025_twf_queue.py` is byte-for-byte identical to `origin/main`. The only new OE-3 schema migration is `0026_oe3_queue_hardening.py`. Disposable PostgreSQL and explicit SQLite fixtures upgraded from empty to head. The independent 0025 fixture contained an unadmitted READY Order, a QUEUED Order with a HELD Entry, and both histories. Upgrade, downgrade, and re-upgrade preserved IDs, owners, states, versions, timestamps, and history snapshots. Four separately corrupted 0025 fixtures were refused without a partial 0026 revision: READY with Entry, QUEUED without Entry, owner mismatch, and orphaned Entry. The latter two required elevated *fixture setup* to create data already prohibited by 0025's existing FKs. Since 0025 had no explicit Queue binding, an alleged association to a different valid Order has no independent identity field from which a migration could infer human intent; this is a representational limit, not silent repair.

## D. F1 actual schema invariant

`DRAFT` and `READY` Orders must have a null `queue_entry_id`; `QUEUED`, `SUBMITTING`, `BROKER_ACCEPTED`, `PARTIALLY_FILLED`, and `FILLED` must have a binding. Composite, initially deferred FKs enforce reciprocal `(queue_entry_id, twf_order_id, owner_id)` identity at COMMIT. The original immediate owner FK, one-Entry-per-Order uniqueness, and RESTRICT delete behavior remain. An Entry therefore cannot be committed for an unbound READY Order with foreign keys active; a bound Order cannot survive without its matching Entry. Post-QUEUED states can retain the binding without invoking any OE-4 runtime transition. `twf_queue_events` has a separate composite FK to its Entry. This schema does not assert that unknown state strings are valid lifecycle transitions; frozen OE-1 authority remains the application boundary for that question.

## E. F1 PostgreSQL direct attacks

A disposable non-superuser **DML-only** role performed the direct attacks, not QueueService. COMMIT rejected READY+Entry, QUEUED with no Entry, a random binding, Order A bound to Entry B, owner mismatch, deletion of a bound Entry, and deletion of its Order. Durable state was reopened and checked after rejected transactions. Both `Entry → Order update` and `Order update → Entry` succeeded in one transaction, demonstrating actual deferred-FK timing; the temporary incomplete states did not survive COMMIT. A bound Order temporarily accepted the reserved `SUBMITTING` state at the schema level and returned to QUEUED without implementing broker submission.

This is only a **DML-only** guarantee. The actual runtime role is a table owner. A separate disposable non-superuser table-owner probe dropped `fk_twf_orders_queue_binding` and `fk_twf_queue_entries_order_binding` and then committed `QUEUED + missing Entry` and `READY + Entry`. Thus the unqualified claim that incoherence cannot survive COMMIT under the ordinary *deployed application role* is false. The attack needs permitted DDL; no HTTP path to issue this DDL was found.

## F. F1 SQLite direct attacks

With the application's normal `foreign_keys=ON` connection setting, the same attacks rejected and both valid transaction orders committed. On a separate disposable app engine connection, explicitly switching `PRAGMA foreign_keys=OFF` allowed both halves of the split-state attack to commit. Switching it back ON did not retroactively validate them. This fails the attachment's **unqualified** database-boundary claim for SQLite fallback, while normal configured connections retain the intended protection. The private probe made this setting change directly; no HTTP path to make the change was found.

## G. F1 migration upgrade/corruption review

The independent upgrade/down/re-upgrade and four corruption-refusal cases passed on both dialects. SQLite's copy/swap temporarily disables foreign keys on its migration connection and runs `foreign_key_check` before completion; the documented migration window requires API writers stopped. The ordinary application engine turns FKs on when it creates a SQLite connection, but a process with connection control can later change that setting as shown above.

## H. F1 concurrency/replay review

The full PostgreSQL suite ran the permanent DB1-R2 interleaving (`A reads READY; B commits; A replays`) and two 100-round series with caller counts cycling 2/5/10. Each round checks raw counts for one Preview-linked Order, one Queue Entry, one QUEUED Order, one Queue admission event, and one Order transition event; all callers converged without false invariant errors. The suite also terminated a PostgreSQL backend after partial admission work: the transaction rolled back to READY with no Entry or history, then retry succeeded. Ten-round-per-series SQLite contention, 10-way Hold/Release CAS tests, and related lock-order regressions passed. No new deadlock appeared in these runs. They do not prove absence of every possible scheduling interleaving.

## I. F2 immutability mechanism

0026 installs a PostgreSQL row-level `BEFORE UPDATE OR DELETE` trigger invoking `twf_queue_event_immutable()` and SQLite `BEFORE UPDATE`/`BEFORE DELETE` abort triggers. The protected table is `twf_queue_events`; 0026 downgrade drops only those named guards and its own binding objects. The event schema has `actor`, type, sequence, reason, and timestamp; it has no separate `source` column. The triggers allow normal INSERT.

## J. F2 mutation attacks

On normal configured connections, direct single-row actor/sequence UPDATE and DELETE, bulk UPDATE and DELETE, and an INSERT followed by a forbidden UPDATE in one transaction were rejected on both dialects. Reopened reads showed original events unchanged and the mixed transaction's new event absent. Normal admission, Hold, and Release inserted events with sequences 1, 2, and 3. History remained ordered by per-entry sequence. These passing DML checks do not negate the trigger-bypass finding.

## K. F2 privilege/bypass review

The same PostgreSQL role-ownership condition breaks F1: read-only live inspection showed `twf_app` owns all three protected tables, and the disposable non-superuser table-owner probe dropped each reciprocal binding FK before committing both incoherent states. Separately, a disposable non-superuser table owner first received a trigger rejection for direct UPDATE, then ran `ALTER TABLE twf_queue_events DISABLE TRIGGER trg_twf_queue_events_immutable`, changed one committed actor to `TAMPERED`, and re-enabled the trigger. The tampered row remained, and the trigger again reported enabled. Read-only inspection of the live runtime confirmed `current_user=twf_app`, `rolsuper=false`, and owner `twf_app` for `twf_orders`, `twf_queue_entries`, and `twf_queue_events`, matching the decisive privilege condition. No live row or schema was changed. A SQLite app connection could similarly drop/recreate its update trigger around a committed audit mutation. PostgreSQL system FK triggers were not disabled; the demonstrated bypass concerns the user-defined Queue audit trigger.

## L. F3 API/cursor contract

The owner-scoped endpoint defaults to limit 50, accepts 1–100, and returns `items`, `next_cursor`, `has_more`. It sorts `admitted_at DESC, queue_entry_id DESC` and optionally filters READY/HELD. The cursor encodes version, owner, filter, timestamp, and Entry UUID with HMAC keyed by `session_hash`. That hash is derived from the authenticated user's cookie and is not an independent server secret; server-side owner and filter equality checks remain effective. The query joins the exact owner-matched Order and applies a strict older-than keyset predicate. This is a live list, not a multi-page snapshot.

## M. F3 traversal attacks

Independent HTTP traversal of 125 and 500 paired records took 4 and 14 pages at limit 37 on **each dialect**, with zero duplicates and zero omissions. Five rows per timestamp forced ties; the UUID tie-breaker gave deterministic order and distinct cursors. Terminal `has_more=false` had `next_cursor=null`. Limits 0, negative, 101, and huge values returned validation errors; 1, 50, and 100 worked. Encoded garbage, truncation, altered signatures, oversize input, and filter mismatch returned 400. A two-owner fixture proved each owner saw only their own rows and rejected the other owner's cursor. A *correctly signed*, scoped cursor with numeric ID returned 500 on both dialects, violating the typed malformed-cursor contract. No SQL injection or cross-owner exposure was observed.

The representative PostgreSQL `EXPLAIN` used `Index Only Scan Backward` on `ix_twf_queue_entries_owner_fifo` for the newest page. The index supports the operator sort in reverse and the future ascending FIFO key; small-set planner estimates are not treated as a performance guarantee.

## N. F3 concurrent-change behavior

After page one, a newer Entry appeared on refreshed page one but did not enter the old cursor's page two. A READY row changed to HELD between READY-filtered pages; the continued page omitted that row, preserved older relative ordering, and did not loop. This matches the documented live-list semantics. Deletion of a bound Entry was blocked by F1, so Hold/Release-style state change was the relevant mutation. Future execution FIFO remains admission ascending by `(admitted_at, queue_entry_id)`; OE-3 contains no consumer.

## O. F3 UI/browser verification

PostgreSQL-backed Chromium passed eight Trade/Queue/Broker cases at 390 px and 1440 px. The tests exercised newest/older/back-to-newest controls, state filter, Queue detail/history, explicit admission, Hold/Release, shared Trade tabs/New Order, retained Broker flow, and no document-width overflow. The pagination browser test uses a mocked Queue API page envelope; the independent 125/500-row probes above supply the real API traversal evidence. No visual redesign was made and no broker execution was triggered by Queue admission.

## P. PostgreSQL/SQLite parity

Normal configured DML behavior, migration roundtrip, and keyset traversal matched across dialects. PostgreSQL has a role privilege problem because the actual app role owns the Order, Entry, and audit tables. SQLite has no independent role boundary and can be made to ignore FK/trigger protection by a process with direct connection/schema control. These differences must be treated explicitly; a passing SQLite application test alone does not establish an unconditional commit-time invariant.

## Q. DB-1 regression

Read-only `/ready` returned 200 and `database_backend=PostgreSQL`; the live connection reported PostgreSQL 16.13, backend PID, non-superuser `twf_app`, and UTC session timezone. Configuration requires an explicit `TWF_DATABASE_URL`, including for SQLite fallback; no automatic PostgreSQL-to-SQLite write failover or dual-write was introduced. The full suites included DB1-R1 exact-or-refuse numeric regressions and DB1-R2 replay/contention regressions; all passed.

## R. OE-1/OE-2 regression

Full PostgreSQL and SQLite suites passed frozen OE-1 lifecycle, provenance, ownership, CAS, identity, and event tests and OE-2 Preview/Create binding, single-use replay, rollback, and concurrency tests. The checkpoint's OE-3 change list does not modify OE-2 Preview/Create code or OE-1 lifecycle authority. This is regression evidence, not a renewed acceptance review of those phases.

## S. OE-4 leakage review

The OE-3 checkpoint diff contains no Queue worker, dequeue consumer, scheduler, risk pipeline, `SUBMITTING` execution, Queue-to-Broker submission, or Broker V2 write. `SUBMITTING` appears only as a reserved bound Order state in schema/tests. The retained Broker New Order path remains separate.

## T. Full and static gates

| Gate | Result |
| --- | --- |
| Full PostgreSQL backend | **1,544 passed, 1 SQLite-specific skipped**, 4 warnings; 748.99 s |
| Full explicit SQLite backend | **1,472 passed, 73 PostgreSQL-specific skipped**, 4 warnings; 552.57 s |
| Independent PostgreSQL probes | 7 passed, 1 skipped, 2 expected failures exposing HTTP 500; owner bypass was a *passing reproduction* |
| Independent SQLite probes | 7 passed, 1 skipped, 2 expected failures exposing HTTP 500; FK/trigger bypass was a *passing reproduction* |
| Frontend unit suite, default workers | 292/295 then 294/295 twice; 5-second timeouts in unrelated Discovery/Scanner/Watchlists initially, then only Watchlists; no timeout was increased |
| Frontend unit suite, one worker | **295/295 passed**, 33 files; same test and timeout settings |
| TypeScript, ESLint, Prettier, production build | Passed |
| PostgreSQL-backed Chromium | **8/8 passed** across 390 px and 1440 px |
| Ruff, Ruff format, compileall, pip check | Passed; Ruff format checked 234 files |
| Focused changed-file mypy | Passed, 10 files |
| Repository mypy | **11 errors in three unchanged tests**, matching the implementation report's known unrelated baseline; no changed-file error |
| `git diff --check` | Passed |

The default-worker frontend command is not a clean gate despite the full one-worker pass. This timing issue is separate from OE-3 hardening, and this review made no test or timeout change.

## U. Findings by severity

| ID | Severity | Finding | Boundary and impact |
| --- | --- | --- | --- |
| OE3-RV-1 | **CRITICAL** | PostgreSQL app role owns Order, Entry, and audit tables; it can drop F1 binding constraints or disable F2 immutability trigger, then commit incoherence/audit tampering | Actual production role privilege; disposable non-superuser reproductions; no live mutation |
| OE3-RV-2 | **HIGH** | SQLite app connection can disable FKs and commit incoherent Order/Entry states, or drop/restore an event trigger around a committed audit UPDATE | Explicit fallback, requires direct connection/schema control; normal configured DML still rejected |
| OE3-RV-3 | **MEDIUM** | Authenticated, correctly signed malformed cursor returns HTTP 500 rather than `INVALID_CURSOR` | Same-owner request; no cross-owner leak observed |
| OE3-RV-4 | **LOW** | Default-worker frontend suite repeatedly times out on an unchanged Watchlists test; full single-worker run passes | Gate reproducibility; not tied to Queue implementation |

There was no demonstrated ordinary HTTP path to toggle SQLite enforcement, no cross-owner exposure, no duplicate Queue admission, and no broker submission from OE-3. No production repair was attempted.

## V. Attack matrices

**F1.** “Normal” means FKs active through the configured app connection and PG constraints installed. P/S/PO/SB evidence paths are listed in Y.

| Attack | PostgreSQL | SQLite | Expected | Observed / result | Severity | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| READY + Entry | DML-only rejected; table owner dropped FK and committed | Normal rejected; FK-off committed | Reject | **FAIL** under deployed PG role and SQLite connection control | CRITICAL/HIGH | P, PO, S, SB |
| QUEUED without Entry | DML-only rejected; table owner dropped FK and committed | Normal rejected; FK-off committed with random binding | Reject | **FAIL** under deployed PG role and SQLite connection control | CRITICAL/HIGH | P, PO, S, SB |
| Mismatched pair | Rejected | Normal rejected | Reject | PASS under configured connections | — | P, S |
| Owner mismatch | Rejected | Normal rejected | Reject | PASS under configured connections | — | P, S |
| Delete bound Entry / Order | Rejected | Normal rejected | Reject | PASS under configured connections | — | P, S |
| Entry-first / Order-first transaction | Both committed when final pair coherent | Both committed when FKs on | Permit valid final state | PASS | — | P, S |
| Corrupt 0025 input | Four fixtures refused | Four fixtures refused | Refuse without partial 0026 | PASS for representable corruption | — | P, S |
| DB1-R2 replay | One Entry/event | One Entry/event in supported races | Idempotent convergence | PASS | — | PG, SQ |
| 200-round contention | 2 × 100 all converged | 2 × 10 fallback rounds | One durable admission/transition/event | PASS | — | PG, SQ |
| Connection loss | Backend killed; rollback, retry succeeds | PostgreSQL-specific test skipped | No orphan or consumed intent | PASS on PostgreSQL | — | PG |

**F2.** The separate bypass row does not discount the configured DML rejections.

| Attack | PostgreSQL | SQLite | Expected | Observed / result | Severity | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| Single UPDATE | Trigger rejects | Trigger rejects | Reject | PASS normal DML | — | P, S |
| Single DELETE | Trigger rejects | Trigger rejects | Reject | PASS normal DML | — | P, S |
| Bulk UPDATE | Entire statement rejected | Entire statement rejected | Reject all | PASS normal DML | — | P, S |
| Bulk DELETE | Entire statement rejected | Entire statement rejected | Reject all | PASS normal DML | — | P, S |
| Insert then tamper | Transaction rolled back | Transaction rolled back | No partial insert/mutation | PASS | — | P, S |
| Admission INSERT | Sequence 1 | Sequence 1 | Allow | PASS | — | P, S |
| Hold INSERT | Sequence 2 | Sequence 2 | Allow | PASS | — | P, S |
| Release INSERT | Sequence 3 | Sequence 3 | Allow | PASS | — | P, S |
| App privilege bypass | Non-superuser owner disabled trigger and rewrote event | App connection dropped trigger and rewrote event | No bypass | **FAIL** | CRITICAL/HIGH | P, SB, Q |

**F3.** The two independent traversals ran against both dialects.

| Attack | PostgreSQL | SQLite | Expected | Observed / result | Severity | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| Default newest-first | Correct | Correct | Newest first | PASS | — | P, S |
| 125-row traversal | 4 pages, 125 IDs | 4 pages, 125 IDs | 0 duplicates/omissions | PASS | — | P, S |
| 500-row traversal | 14 pages, 500 IDs | 14 pages, 500 IDs | 0 duplicates/omissions | PASS | — | P, S |
| Timestamp ties | UUID order stable | UUID order stable | Unique advance | PASS | — | P, S |
| Insert between pages | Old continuation stable | Old continuation stable | No old-row loss/duplication | PASS | — | P, S |
| State/filter change | Current READY membership | Current READY membership | Live-list semantics | PASS | — | P, S |
| Malformed cursor | Signed numeric ID → 500 | Signed numeric ID → 500 | Typed 4xx | **FAIL** | MEDIUM | P, S |
| Cursor tamper | Bad signature → 400; signed numeric ID → 500 | Same | Safe refusal/bounded use | **FAIL** | MEDIUM | P, S |
| Cross-owner cursor/list | 400 / owner-only rows | 400 / owner-only rows | No leak | PASS | — | P, S |
| Limits | 1–100 accepted; 0/negative/>100 rejected | Same | Bounded | PASS | — | P, S |
| Terminal cursor/loop | Distinct cursors, null terminal | Same | Terminate | PASS | — | P, S |
| 390 px Queue UI | Browser passed | API backed by disposable PG | Usable | PASS | — | B |
| 1440 px Queue UI | Browser passed | API backed by disposable PG | Usable | PASS | — | B |

## W. Required scorecard

```text
OE3_REVIEW_STATUS = FAIL

F1_POSTGRES_COMMIT_COHERENCE = FAIL
F1_SQLITE_COMMIT_COHERENCE = FAIL

F1_READY_WITH_ENTRY_BLOCKED_PG = FAIL
F1_READY_WITH_ENTRY_BLOCKED_SQLITE = FAIL

F1_QUEUED_WITHOUT_ENTRY_BLOCKED_PG = FAIL
F1_QUEUED_WITHOUT_ENTRY_BLOCKED_SQLITE = FAIL

F1_MISMATCHED_PAIR_BLOCKED = PASS
F1_OWNER_MISMATCH_BLOCKED = PASS
F1_BOUND_ENTRY_DELETE_BLOCKED = PASS

F1_TRANSACTION_ORDER_INDEPENDENT = PASS
F1_0025_VALID_DATA_UPGRADE = PASS
F1_0025_CORRUPT_DATA_REFUSED = PASS
F1_FUTURE_STATE_COMPATIBLE = PASS

F1_DB1_R2_REPLAY = PASS
F1_200_ROUND_POSTGRES_CONTENTION = PASS
F1_SQLITE_CONTENTION = PASS
F1_CONNECTION_LOSS_ROLLBACK = PASS

F2_UPDATE_BLOCKED_POSTGRES = PASS
F2_DELETE_BLOCKED_POSTGRES = PASS
F2_UPDATE_BLOCKED_SQLITE = PASS
F2_DELETE_BLOCKED_SQLITE = PASS
F2_BULK_UPDATE_BLOCKED = PASS
F2_BULK_DELETE_BLOCKED = PASS
F2_MIXED_TRANSACTION_SAFE = PASS
F2_NORMAL_INSERTS_WORK = PASS
F2_APP_ROLE_CANNOT_BYPASS = FAIL

F3_DEFAULT_NEWEST_FIRST = PASS
F3_FIFO_SEMANTICS_UNCHANGED = PASS
F3_125_TRAVERSAL = PASS
F3_500_TRAVERSAL = PASS
F3_DUPLICATES = 0
F3_OMISSIONS = 0
F3_TIE_BREAK_STABLE = PASS
F3_INSERT_BETWEEN_PAGES = PASS
F3_OWNER_ISOLATION = PASS
F3_CURSOR_FILTER_BINDING = PASS
F3_MALFORMED_CURSOR_SAFE = FAIL
F3_CURSOR_TAMPER_SAFE = FAIL
F3_CURSOR_TERMINATION = PASS
F3_UI_390 = PASS
F3_UI_1440 = PASS

MIGRATION_0025_UNCHANGED = PASS
MIGRATION_0026_POSTGRES_FRESH = PASS
MIGRATION_0026_SQLITE_FRESH = PASS
MIGRATION_0026_UP_DOWN_REUP = PASS

DB1_FROZEN_INTACT = PASS
OE1_FROZEN_INTACT = PASS
OE2_FROZEN_INTACT = PASS
OE4_NOT_IMPLEMENTED = PASS

FULL_BACKEND_POSTGRES = PASS
FULL_BACKEND_SQLITE = PASS
FRONTEND = FAIL
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

OE3_FREEZE_RECOMMENDATION = REMEDIATION_REQUIRED
```

`FRONTEND = FAIL` records the repeatable standard full-suite timeout. All 295 tests passed with one worker, which narrows the issue but does not erase the default-command failure.

## X. Freeze recommendation

**REMEDIATION_REQUIRED.** The PostgreSQL app-role ownership bypass defeats both F1 and F2, including committed incoherent Order/Queue states. The SQLite connection-level F1/F2 bypasses and signed-cursor 500 provide separate failures. The freeze rule requires zero CRITICAL/HIGH findings and passing full gates; it is not met. This is a finding set for a later deliberate remediation, not authorization to change OE-3 here.

## Y. Exact review evidence paths

- `var/db1/oe3_review_fd7c391/test_probe.py` — ignored private adversarial probe source; no production import.
- `/tmp/twf_oe3_review_pg_probe_final.log` (**P**) — independent PostgreSQL direct SQL, migration, pagination, and Queue-event table-owner attack.
- `/tmp/twf_oe3_review_pg_f1_owner.log` (**PO**) — non-superuser Order/Entry table-owner constraint-removal attack.
- `/tmp/twf_oe3_review_sqlite_probe_final.log` (**S**) — independent normal SQLite direct SQL, migration, pagination.
- `/tmp/twf_oe3_review_sqlite_bypass_final.log` (**SB**) — SQLite FK-off and trigger-drop committed bypasses.
- `/tmp/twf_oe3_review_pg_full.log` (**PG**) — complete PostgreSQL backend and DB1-R2 regressions.
- `/tmp/twf_oe3_review_sqlite_full.log` (**SQ**) — complete explicit SQLite backend.
- `/tmp/twf_oe3_review_browser.log` (**B**) — PostgreSQL-backed Chromium at both widths.
- `/tmp/twf_oe3_review_web_test.log`, `/tmp/twf_oe3_review_web_test_serial.log`, `/tmp/twf_oe3_review_web_test_serial2.log`, `/tmp/twf_oe3_review_web_watchlist_target.log`, `/tmp/twf_oe3_review_web_test_single_worker.log` — frontend test outcomes.
- `/tmp/twf_oe3_review_web_typescript.log`, `/tmp/twf_oe3_review_web_lint.log`, `/tmp/twf_oe3_review_web_prettier.log`, `/tmp/twf_oe3_review_web_build.log` — frontend static/build gates.
- `/tmp/twf_oe3_review_ruff.log`, `/tmp/twf_oe3_review_ruff_format.log`, `/tmp/twf_oe3_review_compile.log`, `/tmp/twf_oe3_review_pip.log`, `/tmp/twf_oe3_review_mypy_changed.log`, `/tmp/twf_oe3_review_mypy_repo_root.log` — backend static gates.
- Read-only runtime observations: `GET http://localhost:8000/ready` returned PostgreSQL ready; SQL `SELECT current_user, rolsuper, pg_get_userbyid(relowner), current_setting('TimeZone'), pg_backend_pid(), version()` returned `twf_app`, false, `twf_app`, `Etc/UTC`, a backend PID, PostgreSQL 16.13. A separate read-only ownership query returned `twf_app` for all three protected tables. No credentials or live row contents were printed.

The `/tmp` logs and ignored private probe are local review evidence, not committed artifacts. The permanent findings and decision are in this report.

## Z. Final status

```text
OE3_REVIEW_STATUS = FAIL
OE3_FREEZE_RECOMMENDATION = REMEDIATION_REQUIRED
```

OE-3 was not accepted or frozen. OE-4 was not started. No production code, 0025/0026 migration, or permanent test was repaired during this review.

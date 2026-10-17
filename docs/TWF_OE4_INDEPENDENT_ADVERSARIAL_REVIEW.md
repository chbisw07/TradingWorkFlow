# OE-4 Independent Adversarial Review

**Review date:** 16 October 2026  
**Branch:** `main`  
**Reviewed commit:** `209c6b1ef558ce8c6d04818b63818c3df479e532`  
**Review mode:** independent, adversarial, review-only

## A. Executive verdict

`OE4_REVIEW_STATUS = FAIL`

The execution boundary itself withstood the adversarial review. The operator interlock is checked before any database claim, adapter catalog call, or Broker V2 submission; AUTO selection uses each Queue Entry's immutable admission-time `effective_dispatch_mode`; MANUAL and AUTO converge on one `DispatchService` and the existing Broker V2 `_submit_claimed` path; uncertain outcomes are never automatically resent; and the tested crash/race windows converged to one logical attempt. No real broker adapter was invoked and the live database remained at zero dispatch attempts.

OE-4 cannot be frozen because the specification requires every full gate to pass and the complete PostgreSQL-backed Playwright matrix is red: 151 passed, 19 skipped, and 274 failed. The OE-4 Queue browser scenario passed all six Chromium widths, but WebKit failed on an internal navigation error and multiple unrelated Chromium tests contain stale or failing expectations. There are zero CRITICAL and zero HIGH OE-4 safety findings; the browser gate failure is a MEDIUM acceptance blocker.

`OE4_FREEZE_RECOMMENDATION = REMEDIATION_REQUIRED`

## B. Preflight

| Item                   | Observed                                   |
| ---------------------- | ------------------------------------------ |
| Worktree before review | Clean                                      |
| Branch                 | `main`                                     |
| HEAD                   | `209c6b1ef558ce8c6d04818b63818c3df479e532` |
| `origin/main`          | `f8b61d269be1a6416f9b83cf1a1aa7870e7969db` |
| Safety branch          | `safety/oe4-pre-review` at reviewed HEAD   |
| Alembic current/head   | `0028_oe4_dispatch` / `0028_oe4_dispatch`  |
| Runtime DB             | PostgreSQL                                 |
| Runtime role           | `twf_app`                                  |
| Queue policy           | `MANUAL`, version 7                        |
| Execution capability   | OFF                                        |
| Live dispatch attempts | 0 before and after review                  |
| Live broker intents    | 10 before and after review                 |
| `git diff --check`     | PASS                                       |

All mock-enabled dispatch testing used the repository's synthetic broker and disposable databases. The live database was queried read-only and rolled back. No live execution capability was enabled.

## C. Execution interlock review

`Settings.queue_dispatch_enabled` defaults to `False`. `DispatchService.dispatch()` rejects immediately when it is false, before opening the validation transaction, resolving a broker adapter, fetching an execution catalog, or invoking the shared submit path. `DispatchService.cycle()` returns immediately when false. Application startup creates the coordinator only when the flag is true and the environment is not `test`.

A disposable probe created a READY AUTO entry, ran 25 coordinator cycles, and attempted manual dispatch with the flag off. The result was a typed 409 `INVALID_QUEUE_TRANSITION`; provider calls, dispatch attempts, Queue events, Queue version, Queue state, and `updated_at` all remained unchanged. Default-OFF process restart behavior follows from immutable settings composition and the startup guard.

## D. Queue policy semantics

The policy is keyed by owner and broker account. First access inserts MANUAL. Changes use expected-version CAS and append an immutable policy event containing the old/new mode, owner, account, actor, version, and timestamp. Policy changes update only the policy row and event ledger.

The runtime UI correctly labels the control “Dispatch mode for new admissions” and says “Existing Queue entries are unchanged.” It separately reports when Queue execution is disabled.

## E. Admission-time mode snapshot

Queue admission locks and reads the owner/account policy inside the admission transaction, then copies `current_dispatch_mode` and policy version into the new Queue Entry. Migration 0028 backfills/prepares pre-OE4 entries as MANUAL/version 0. A database trigger rejects later changes to the entry's effective mode, account, policy version, source, and public ID.

The permanent mode-snapshot test and independent probes demonstrated MANUAL→AUTO and AUTO→MANUAL transitions without rewriting historical entries.

## F. Mode-switch races

The permanent race test was independently repeated five times for 100 total concurrent admission/policy changes on each backend. Every admitted row matched one coherent serialized pair: either the prior mode/version or the committed new mode/version. No null/ambiguous modes, lost admissions, or duplicate Queue Entries were observed.

## G. Manual dispatch review

A MANUAL entry remains READY until explicit Dispatch. Concurrent Dispatch calls converged to one claim, one `DispatchAttempt`, one Broker V2 intent, and one synthetic provider call. Replays returned current state/conflict without another send. With execution disabled, manual Dispatch was blocked before adapter invocation and left Queue state unchanged.

## H. Auto coordinator review

The coordinator query filters `queue_state = READY` and `effective_dispatch_mode = AUTO`, ordered FIFO by admission time and Queue UUID. It never reads current policy for selection. A historical MANUAL entry was ignored after policy switched to AUTO, while a historical AUTO entry remained eligible after policy switched to MANUAL. A newly constructed coordinator discovered and dispatched a persisted AUTO entry exactly once in the disposable enabled environment.

The loop sleeps two seconds after every cycle; an interlock-off cycle returns before reads or writes, preventing event/attempt storms.

## I. Hold/Cancel races

HELD entries are excluded from AUTO selection. Hold/Release preserves the immutable entry mode. MANUAL remains waiting after cross-mode release; AUTO becomes eligible after release. Cancel/Hold versus AUTO-claim races had one winner: when the operator transition won there was no broker call; when dispatch won the operator received a conflict and no false reversal was recorded.

## J. Dispatch transaction boundaries

The dispatch transaction atomically creates the Broker V2 `OrderIntent`, creates one unique `DispatchAttempt`, and transitions Queue/Order to DISPATCHING/SUBMITTING. That transaction commits before the only provider write. The permanent lock probe proved a separate writer could acquire/write during the synthetic `place_order` call, demonstrating no database transaction spans broker I/O.

Completion occurs in a later transaction and maps Broker V2 outcomes to DISPATCHED, FAILED, or RECONCILIATION_REQUIRED.

## K. Broker V2 reuse/bypass review

Static search found one production invocation of `adapter.place_order`: `twf.brokers.order_service.OrderService._submit_claimed`. Queue calls that shared method after its durable claim. Scanner, Watchlist, webhook, Trade, and other application modules have no parallel submission invocation.

The retained Broker workspace manual order path is the documented migration exception and uses the same existing Broker V2 service; it was not introduced by OE-4.

## L. Idempotency

There is one unique dispatch-attempt linkage per Queue Entry and one durable Broker V2 intent/tag for the logical attempt. Entries already DISPATCHING, DISPATCHED, RECONCILIATION_REQUIRED, or FAILED do not create another attempt. Retries and worker recovery inspect the existing linkage rather than minting a replacement intent.

## M. Failure/reconciliation

| Outcome                      | Observed behavior                                          |
| ---------------------------- | ---------------------------------------------------------- |
| Definitive broker rejection  | FAILED/REJECTED; one call; no retry                        |
| Pre-send/fresh-check failure | FAILED with typed reason; zero broker calls                |
| Timeout/lost response        | RECONCILIATION_REQUIRED/SUBMITTING; one call; no resend    |
| Server/unknown exception     | RECONCILIATION_REQUIRED; one call; no resend               |
| Repeated coordinator cycles  | Existing terminal/ambiguous state observed; no new attempt |

OE-4 persists attempt ID, Broker intent ID, optional broker order ID, claimed/finished timestamps, outcome, source, actor, and Queue/Order audit links for OE-5 reconciliation without implementing OE-5.

## N. Crash/restart recovery

A crash after the durable claim but before provider acceptance leaves a stable SUBMITTING intent; after the recovery cutoff the Queue becomes RECONCILIATION_REQUIRED with zero provider calls. A crash after synthetic provider acceptance and local Broker V2 persistence recovers to DISPATCHED with the same single provider call. A crash after provider receipt but before definitive local truth remains ambiguous and is not resent. Restart discovery of a READY AUTO entry dispatched it once only when the disposable interlock was explicitly enabled. With the interlock off, restart creates no worker and no dispatch.

## O. Source provenance

MANUAL provenance is copied from the frozen Order. WATCHLIST and SCANNER use trusted preview/source bindings; client spoof attempts are rejected. Post-admission source mutation is denied by the database trigger. Webhook intake is not implemented and no contract claims that it is.

## P. Public IDs

Order aliases use `ORD-YYYYMMDDHHMMSS-NNN`; Queue aliases use `QID-YYYYMMDD-HHMM-NNN`. Canonical UUIDs remain primary and unchanged. Permanent concurrency tests created 100 Orders in one second and 100 Queue Entries in one minute without collision.

The independent overflow probe allocated 1,005 QIDs in one minute, producing unique suffixes through `1005` without wrap. India-time probes mapped `2026-10-16T18:29:59Z` to `ORD-20261016235959-*` and `2026-10-16T18:30:00Z` to `ORD-20261017000000-*`; canonical timestamps remained UTC.

## Q. Privilege/security review

A read-only live-role audit observed:

- role `twf_app`, Alembic head `0028_oe4_dispatch`;
- exactly 51 registered runtime tables with exact per-table grants;
- DELETE on exactly the accepted 11 cleanup tables;
- zero public-schema objects owned by runtime;
- no runtime execute privilege on protected trigger functions;
- OE-4 tables owned by `twf_migrator` with no DELETE grant;
- append-only event/alias tables limited to SELECT/INSERT.

The full PostgreSQL suite re-ran OE-3 coherence, event immutability, DDL denial, cursor security, pagination, and privilege-boundary probes successfully.

## R. UI/browser verification

Static/UI/unit evidence passed for:

- current policy applies only to future admissions;
- execution-disabled text is distinct from MANUAL/AUTO;
- MANUAL shows READY FOR DISPATCH and a Dispatch action;
- AUTO shows AWAITING AUTO DISPATCH and no manual Dispatch action;
- Source, public ORD/QID aliases, effective mode, and long UUID details are exposed;
- typed endpoint errors render as an operational notice rather than a raw 500.

The PostgreSQL-backed OE-4 Queue Playwright scenario passed at all six Chromium widths: 390, 768, 1024, 1440, 1920, and 2560. It failed at all six WebKit widths before application interaction because `page.goto('/login')` returned `WebKit encountered an internal error`.

The complete browser matrix was not clean: 151 passed, 19 skipped, 274 failed. Chromium failures also exposed stale expectations outside the Queue bridge, including an added broker positions column, removed/changed headings/navigation, and scanner/options preview expectations. No browser production code was changed during review.

## S. Frozen-system regressions

The complete PostgreSQL backend suite passed 1,578 tests with one expected SQLite-specific skip. The final complete SQLite fallback run passed 1,504 tests with 75 expected PostgreSQL-only skips. OE-1 lifecycle/trust authority, OE-2 Preview/Create binding and concurrency, OE-3 Queue coherence/audit/pagination/replay, DB-1 PostgreSQL-primary/fail-closed/numeric rules, and existing Broker V2 tests all remained green.

The first SQLite full run had one unrelated MCP delayed-finalization timing failure. The complete 18-case timing matrix then passed in isolation, and the entire SQLite suite passed on immediate full rerun. It is recorded as a non-reproduced observation, not an OE-4 finding.

## T. Full/static gates

| Gate                            | Result                                                  |
| ------------------------------- | ------------------------------------------------------- |
| Focused OE-4 SQLite             | PASS — 21 passed                                        |
| Focused OE-4 PostgreSQL         | PASS — 21 passed                                        |
| Independent probes SQLite       | PASS — 4 passed                                         |
| Independent probes PostgreSQL   | PASS — 4 passed                                         |
| Full PostgreSQL backend         | PASS — 1,578 passed, 1 skipped, 4 warnings              |
| Full SQLite fallback, final run | PASS — 1,504 passed, 75 skipped, 4 warnings             |
| Frontend unit                   | PASS — 296 passed in 33 files                           |
| TypeScript                      | PASS                                                    |
| ESLint                          | PASS                                                    |
| Prettier                        | PASS                                                    |
| Production build                | PASS                                                    |
| Full PostgreSQL browser matrix  | **FAIL — 151 passed, 19 skipped, 274 failed**           |
| Ruff                            | PASS                                                    |
| Ruff format                     | PASS — 245 files                                        |
| compileall                      | PASS                                                    |
| pip check                       | PASS                                                    |
| Changed-file mypy               | PASS — 30 files                                         |
| Repository mypy                 | PRE_EXISTING_UNRELATED — 15 errors in 3 unchanged tests |
| `git diff --check`              | PASS                                                    |

## U. Findings by severity

### CRITICAL

None.

### HIGH

None.

### MEDIUM

**OE4-R1 — Required full PostgreSQL browser gate is not clean.** The full configured matrix completed with 274 failures. The OE-4 Queue scenario passed every Chromium width but failed every WebKit width on an internal WebKit navigation error. Repeated Chromium failures in unrelated pages show current browser assertions also lag the accepted product surface. The freeze rule requires the full browser gate to pass, so this is an acceptance blocker even though no Queue dispatch safety defect was reproduced.

### LOW

None.

### Observations

The first full SQLite run had one non-reproduced MCP finalization timing failure; its 18-case matrix and the subsequent full SQLite run passed. Repository mypy debt remains exactly 15 errors in three unchanged test files.

## V. Attack matrices

### Mode matrix

| Scenario                                | Expected mode  | Observed mode  | Broker call?                      | Result |
| --------------------------------------- | -------------- | -------------- | --------------------------------- | ------ |
| MANUAL admitted before AUTO switch      | MANUAL         | MANUAL         | No until click                    | PASS   |
| AUTO admitted after switch              | AUTO           | AUTO           | One mock worker call when enabled | PASS   |
| AUTO admitted before MANUAL switch      | AUTO           | AUTO           | One mock worker call when enabled | PASS   |
| MANUAL admitted after switch            | MANUAL         | MANUAL         | No until click                    | PASS   |
| HELD MANUAL, policy AUTO, release       | MANUAL         | MANUAL         | No                                | PASS   |
| HELD AUTO, policy MANUAL, release       | AUTO           | AUTO           | One when enabled                  | PASS   |
| Restart with interlock OFF              | Persisted mode | Persisted mode | No                                | PASS   |
| Restart with AUTO and mock interlock ON | AUTO           | AUTO           | Exactly one                       | PASS   |

### Concurrency matrix

| Attack                                      | Observed                                              |
| ------------------------------------------- | ----------------------------------------------------- |
| 100 mode switches vs admissions per backend | Coherent old/new mode+version only; no loss/duplicate |
| Double manual Dispatch                      | One attempt and one provider call                     |
| Two AUTO workers                            | One attempt and one provider call                     |
| Cancel vs claim                             | One winner; no false cancellation                     |
| Hold vs claim                               | One winner; no in-flight reversal                     |
| Crash after claim                           | Reconciliation required; no send/retry                |
| Crash after broker acceptance               | Durable link recovered; one send                      |

### Broker safety matrix

| Scenario                       |                                            Calls | Durable result                                | Result |
| ------------------------------ | -----------------------------------------------: | --------------------------------------------- | ------ |
| Interlock OFF, MANUAL          |                                                0 | READY unchanged, typed 409                    | PASS   |
| Interlock OFF, AUTO, 25 cycles |                                                0 | READY unchanged; no rows/events/version churn | PASS   |
| Mock success                   |                                                1 | DISPATCHED/BROKER_ACCEPTED                    | PASS   |
| Definitive reject              |                                                1 | FAILED/REJECTED                               | PASS   |
| Pre-send failure               |                                                0 | FAILED with typed reason                      | PASS   |
| Ambiguous timeout              |                                                1 | RECONCILIATION_REQUIRED                       | PASS   |
| Delayed/lost response replay   |                                                1 | No blind resend                               | PASS   |
| Crash recovery                 | 0 or 1 according to whether provider was reached | Stable existing attempt reused                | PASS   |

### ID matrix

| Probe                             | Result                              |
| --------------------------------- | ----------------------------------- |
| 100 Orders in same second         | 100 unique aliases; UUIDs unchanged |
| 100 Queue Entries in same minute  | 100 unique aliases; UUIDs unchanged |
| 1,005 aliases in one bucket       | Unique through suffix `1005`        |
| UTC/IST midnight and day rollover | Correct Asia/Kolkata buckets        |
| Canonical identity                | UUID remains authoritative          |

### Source matrix

| Source    | Trusted path            | Spoof blocked | Immutable | Result          |
| --------- | ----------------------- | ------------- | --------- | --------------- |
| MANUAL    | Authenticated context   | Yes           | Yes       | PASS            |
| WATCHLIST | Trusted preview binding | Yes           | Yes       | PASS            |
| SCANNER   | Trusted run binding     | Yes           | Yes       | PASS            |
| WEBHOOK   | Not implemented         | n/a           | n/a       | NOT_IMPLEMENTED |

## W. Scorecard

```text
OE4_REVIEW_STATUS = FAIL

EXECUTION_INTERLOCK_OFF_BLOCKS_MANUAL = PASS
EXECUTION_INTERLOCK_OFF_BLOCKS_AUTO = PASS
EXECUTION_INTERLOCK_PRE_BROKER = PASS
NO_LIVE_BROKER_ORDER = PASS

QUEUE_POLICY_DEFAULT_MANUAL = PASS
QUEUE_POLICY_OWNER_ACCOUNT_SCOPED = PASS
QUEUE_POLICY_AUDITED = PASS

ENTRY_MODE_SNAPSHOTTED_AT_ADMISSION = PASS
ENTRY_MODE_IMMUTABLE = PASS
MANUAL_TO_AUTO_EXISTING_UNCHANGED = PASS
AUTO_TO_MANUAL_EXISTING_UNCHANGED = PASS
MODE_SWITCH_NO_ROW_REWRITE = PASS

AUTO_WORKER_USES_ENTRY_MODE = PASS
HISTORICAL_MANUAL_NOT_AUTODISPATCHED = PASS
HISTORICAL_AUTO_STILL_AUTODISPATCHED = PASS

MANUAL_RELEASE_WAITS = PASS
AUTO_RELEASE_AUTODISPATCHES = PASS
HELD_NEVER_DISPATCHES = PASS

MANUAL_DOUBLE_CLICK_SAFE = PASS
MULTI_AUTO_WORKER_SAFE = PASS
MODE_ADMISSION_RACE_SAFE = PASS
CANCEL_CLAIM_RACE_SAFE = PASS
HOLD_CLAIM_RACE_SAFE = PASS

COMMON_DISPATCH_SERVICE = PASS
AUTO_MANUAL_CHECK_PARITY = PASS
ATOMIC_DISPATCH_CLAIM = PASS
NO_DB_TX_ACROSS_BROKER_IO = PASS

BROKER_V2_REUSED = PASS
BROKER_BYPASS_ABSENT = PASS
BROKER_INTENT_LINKAGE = PASS
STABLE_IDEMPOTENCY = PASS

AMBIGUOUS_TIMEOUT_NO_BLIND_RETRY = PASS
RECONCILIATION_REQUIRED = PASS
CRASH_AFTER_CLAIM_SAFE = PASS
CRASH_AFTER_BROKER_ACCEPT_SAFE = PASS
RESTART_AUTO_RECOVERY = PASS

SOURCE_MANUAL = PASS
SOURCE_WATCHLIST = PASS
SOURCE_SCANNER = PASS
SOURCE_WEBHOOK = NOT_IMPLEMENTED
SOURCE_SPOOF_BLOCKED = PASS
SOURCE_IMMUTABLE = PASS

PUBLIC_ORDER_ID_UNIQUE = PASS
PUBLIC_QUEUE_ID_UNIQUE = PASS
PUBLIC_ID_OVERFLOW_SAFE = PASS
PUBLIC_ID_TIMEZONE_SAFE = PASS
CANONICAL_UUIDS_PRESERVED = PASS

OE4_RUNTIME_GRANTS_CORRECT = PASS
OE3_SECURITY_INTACT = PASS
OE2_FROZEN_INTACT = PASS
OE1_FROZEN_INTACT = PASS
DB1_FROZEN_INTACT = PASS

FULL_BACKEND_POSTGRES = PASS
FULL_BACKEND_SQLITE = PASS
FRONTEND = PASS
BROWSER_POSTGRES = FAIL

CHANGED_FILE_MYPY = PASS
REPO_MYPY = PRE_EXISTING_UNRELATED
RUFF = PASS
FORMAT = PASS
COMPILE = PASS
PIP_CHECK = PASS
TYPESCRIPT = PASS
ESLINT = PASS
PRETTIER = PASS
BUILD = PASS
GIT_DIFF_CHECK = PASS

OE4_FREEZE_RECOMMENDATION = REMEDIATION_REQUIRED
```

## X. Freeze recommendation

`REMEDIATION_REQUIRED` solely because a required full gate is red. The dispatch safety model itself produced no CRITICAL or HIGH finding. A bounded browser-gate remediation/revalidation should restore a clean PostgreSQL-backed matrix, including a functioning WebKit environment or an explicitly approved browser policy, and reconcile stale Chromium assertions with current accepted UI behavior. OE-4 production dispatch code should not be changed unless that focused investigation demonstrates a real defect.

## Y. Evidence paths

- `docs/TWF_OE4_QUEUE_BROKER_BRIDGE_ARCHITECTURE.md`
- `docs/TWF_OE4_IMPLEMENTATION_REPORT.md`
- `docs/TWF_OE4_RUNTIME_PRIVILEGE_REMEDIATION_REPORT.md`
- `apps/api/src/twf/queue/dispatch.py`
- `apps/api/src/twf/queue/policy.py`
- `apps/api/src/twf/queue/service.py`
- `apps/api/src/twf/brokers/order_service.py`
- `apps/api/alembic/versions/0028_oe4_dispatch.py`
- `tools/postgres_roles.py`
- `apps/api/tests/test_queue_dispatch_oe4.py`
- `apps/api/tests/test_postgres_privilege_boundary.py`
- `apps/web/src/components/orders/queue-policy-control.tsx`
- `apps/web/src/components/orders/queue-workspace.tsx`
- `apps/web/tests/browser/queue-dispatch.spec.ts`
- representative WebKit artifact: `apps/web/test-results/queue-dispatch-OE-4-policy-f5cc1-O-executes-and-MANUAL-waits-webkit-2560/error-context.md`

## Z. Final status

```text
OE4_REVIEW_STATUS = FAIL
OE4_FREEZE_RECOMMENDATION = REMEDIATION_REQUIRED
```

---

## AA. Browser-gate remediation status — 17 October 2026

The original independent verdict above remains an accurate record of the reviewed tree and is intentionally preserved: `OE4_REVIEW_STATUS = FAIL` and `OE4_FREEZE_RECOMMENDATION = REMEDIATION_REQUIRED` were caused solely by the required browser gate.

A later bounded browser remediation identified the WebKit pre-navigation failure as Snap `GIO_MODULE_DIR` contamination, reconciled stale Chromium assertions with the accepted current UI, isolated parallel browser fixture identities, and fixed two narrowly proven frontend defects. No OE-4 backend production or Queue workspace file changed.

Post-remediation evidence:

- exact PostgreSQL-backed browser gate: **427 passed, 17 applicability skips, 0 failed**;
- Chromium: **214 passed, 8 skipped, 0 failed**;
- WebKit: **213 passed, 9 skipped, 0 failed**;
- OE-4 Queue scenario: passed both engines at all six widths;
- focused OE-4 backend: **21 PostgreSQL + 21 SQLite passed**;
- frontend: **296 unit tests**, TypeScript, ESLint, Prettier, and production build passed;
- read-only live verification: execution disabled, zero dispatch attempts, 10 pre-existing broker intents, MANUAL policy version 7;
- no live broker call and no live database contamination.

The complete evidence and matrices are in `docs/TWF_OE4_BROWSER_GATE_REMEDIATION_REPORT.md`.

This addendum does not rewrite the original review verdict and does not freeze OE-4. It records that the bounded remediation is ready for the required final independent focused re-review.

```text
OE4_BROWSER_REMEDIATION_STATUS = PASS
OE4_READY_FOR_FINAL_REREVIEW = YES
```

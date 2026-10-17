# OE-4 Final Focused Re-review and Freeze Decision

## A. Executive verdict

**OE4_FINAL_REVIEW_STATUS = PASS.** The final bounded review found no CRITICAL,
HIGH, MEDIUM, or LOW OE-4 defect. The execution interlock, immutable admission-time
dispatch mode, common dispatch path, concurrency controls, ambiguous-outcome
handling, recovery behavior, source authority, public IDs, and PostgreSQL privilege
boundary all held under independent inspection and test execution.

The repaired browser gate passed in full: **427 passed, 17 justified skips, 0
failed** across Chromium and WebKit at all six required widths. The full PostgreSQL
and SQLite backend suites, frontend unit/static/build gates, focused OE-4 suites,
and backend static gates are clean. Live execution remained disabled throughout;
the live dispatch-attempt count remained zero and no real broker order was sent.

**Recommendation: `ACCEPT_AND_FREEZE`.** This report records the recommendation;
it does not itself freeze, tag, commit, push, or begin OE-5.

## B. Preflight

| Check                        | Observed                                                                  | Result |
| ---------------------------- | ------------------------------------------------------------------------- | ------ |
| Branch                       | `main`                                                                    | PASS   |
| HEAD                         | `fab94957f8026ef0b8efe2e3731442bbaa391bcd`                                | PASS   |
| `origin/main`                | `f8b61d269be1a6416f9b83cf1a1aa7870e7969db`                                | PASS   |
| Local checkpoint             | `fab9495` is the intentional unpushed OE-4 browser-remediation checkpoint | PASS   |
| Safety branches              | `safety/oe4-pre-review` and `safety/oe4-final-rereview` exist             | PASS   |
| Initial worktree             | Clean before this required report was created                             | PASS   |
| Unexpected unrelated changes | None                                                                      | PASS   |
| Git mutation                 | No reset, rewrite, commit, tag, or push performed                         | PASS   |
| `git diff --check`           | Clean                                                                     | PASS   |

The five normative OE-4 documents were read as claims to verify. Production code,
migration `0028_oe4_dispatch`, tests, Playwright configuration, fixture isolation,
and the live runtime grant model were inspected independently.

## C. Live safety baseline

The live/dev runtime was queried read-only before the review gates:

| Property                   | Baseline                         |
| -------------------------- | -------------------------------- |
| Database                   | PostgreSQL, ready                |
| Runtime role               | `twf_app`                        |
| Alembic revision           | `0028_oe4_dispatch`              |
| Queue execution capability | `False`                          |
| Queue policy               | one `MANUAL` policy at version 7 |
| Dispatch attempts          | 0                                |
| Broker order intents       | 10                               |

The browser and backend tests used disposable databases and synthetic providers.
No review step enabled the live execution capability.

## D. Execution interlock

The interlock is the first operation in `DispatchService.dispatch` and in the AUTO
coordinator cycle. With `queue_dispatch_enabled=False`, manual dispatch returns a
typed Queue transition error and AUTO returns without selecting work. In both
cases the focused tests prove zero provider calls, zero attempt rows, unchanged
Queue state, and no event/version churn.

The check occurs before broker account capture, execution catalog access, durable
dispatch claim, Broker V2 submission, and provider network I/O. There is no
post-send interlock path. The live setting remained false before and after every
gate.

## E. Queue policy/mode snapshot

Queue policy is owner/account scoped, defaults to `MANUAL`, uses versioned updates,
and appends policy audit events. Admission copies the current policy into the Queue
Entry's `effective_dispatch_mode`; absent policy produces `MANUAL`. The database
immutability boundary rejects later edits to that snapshot.

| Scenario                          | Expected                     | Observed                                                          | Result |
| --------------------------------- | ---------------------------- | ----------------------------------------------------------------- | ------ |
| MANUAL -> AUTO, historical MANUAL | existing entry stays MANUAL  | existing entry remained MANUAL; new admission was AUTO            | PASS   |
| AUTO -> MANUAL, historical AUTO   | existing entry stays AUTO    | existing entry remained AUTO; new admission was MANUAL            | PASS   |
| Repeated policy changes           | no existing-row rewrite      | entry mode, source, public ID, and Queue snapshot remained stable | PASS   |
| MANUAL HELD -> release            | READY and waits for user     | released entry remained manual-dispatch only                      | PASS   |
| AUTO HELD -> release              | READY and worker-eligible    | released entry was selected by AUTO coordinator                   | PASS   |
| Restart with historical AUTO      | selection follows entry mode | AUTO entry rediscovered independently of current policy           | PASS   |
| Restart with execution OFF        | no submission                | state preserved; zero broker calls                                | PASS   |

## F. Admission/mode races

Bounded concurrent policy-change/admission probes passed on both PostgreSQL and
SQLite. Every admission captured one coherent policy/version outcome; no entry had
a null mode, no historical row was rewritten, and the unique Order-to-Queue
admission invariant prevented duplicates. The focused test suite also attempts
direct database mutation of the mode snapshot and policy audit evidence; both are
rejected.

## G. Manual dispatch

Manual dispatch requires an authenticated owner principal, matching owner/account,
a `MANUAL` Queue Entry in `READY`, a matching expected version, and the execution
interlock to be enabled. Concurrent manual dispatches converge on one durable
claim, one DispatchAttempt, one Broker V2 intent, and one synthetic provider call.
Replay observes the existing attempt and cannot mint a second logical order.

## H. AUTO coordinator

The coordinator query explicitly selects
`TWFQueueEntryRecord.effective_dispatch_mode == "AUTO"`; current Queue policy is
absent from both ready-selection and recovery queries. Historical MANUAL entries
are ignored after policy changes, while historical AUTO entries remain eligible
after the current policy becomes MANUAL. Multiple workers racing the same entry
converge on the same dispatch claim and one provider call. With execution disabled,
the coordinator exits before querying work and does not busy-spin or churn state.

## I. Hold/Cancel races

Hold and pre-dispatch Cancel require the expected Queue version and operate only on
eligible pre-claim states. In dispatch-versus-Cancel and dispatch-versus-Hold
races, the row/version transition admits one coherent winner. If the operator
action wins, the provider is not called. If the dispatch claim wins, the operator
action receives a typed conflict/current-state result and cannot reverse an
in-flight dispatch.

## J. Dispatch transaction boundaries

Both authorities converge on `DispatchService`. The transaction structure remains:

1. validate current broker/catalog truth outside a write transaction;
2. TX1 atomically revalidates and persists Queue/Order claim, DispatchAttempt, and
   Broker V2 intent, then commits;
3. Broker V2 performs provider I/O with no database transaction or row lock held;
4. TX2 records the definitive or ambiguous completion.

The rollback probe proves a failed claim leaves no attempt/intent and sends
nothing. The no-lock probe proves provider I/O is outside the database transaction.

## K. Broker V2 reuse/bypass

Static production search found one invocation of `adapter.place_order`:
`twf.brokers.order_service.OrderService._submit_claimed`. Queue dispatch calls that
shared Broker V2 method only after the durable claim. Scanner, Watchlist, Trade,
webhook, and Queue code contain no parallel adapter submission path. Adapter
protocol and Zerodha implementation declarations are definitions, not extra
callers.

## L. Idempotency

Unique Queue Entry linkage on DispatchAttempt and Broker intent, durable claim
state, stable correlation/tag identity, and repeat-state handling enforce one
logical submission per Queue Entry. Manual replay, multiple AUTO workers, repeated
coordinator cycles, and crash recovery all reuse or finalize the existing attempt.
No test produced a second Broker V2 intent or synthetic provider call.

## M. Failure/reconciliation

| Scenario                    | Expected                           | Observed                                        | Result |
| --------------------------- | ---------------------------------- | ----------------------------------------------- | ------ |
| Definitive broker rejection | FAILED/rejected, no retry          | one call; terminal rejection retained           | PASS   |
| Proven pre-send failure     | typed failure, zero sends          | zero provider calls; no attempt churn           | PASS   |
| Lost response/timeout       | RECONCILIATION_REQUIRED, no resend | one call; stable attempt/intent; no blind retry | PASS   |
| Ambiguous server outcome    | RECONCILIATION_REQUIRED, no resend | one call; stable ambiguous state                | PASS   |
| Later coordinator cycles    | retain existing outcome            | no new attempt and no resend                    | PASS   |

The reconciliation-required state and recovery hook are present. A full broker
reconciliation engine is deliberately absent and remains future OE-5 scope.

## N. Crash/restart recovery

The focused recovery probes cover both crash windows. A crash after durable claim
but before provider send is recovered without a blind send and is surfaced as
reconciliation-required when broker truth is not definitive. A synthetic provider
accept followed by local-completion interruption is finalized through the same
logical attempt and one provider call. Restart discovers persisted AUTO READY work
when execution is enabled in the disposable synthetic environment; restart with
the interlock off submits nothing.

## O. Source provenance

MANUAL, WATCHLIST, and SCANNER sources are issued from trusted application
contexts and snapshotted immutably at Queue admission. Focused WATCHLIST and
SCANNER probes bind trusted preview provenance and reject ordinary caller attempts
to spoof the source or reference. Owner and broker account checks are applied at
each operation. WEBHOOK intake is `NOT_IMPLEMENTED`, as allowed by the OE-4
boundary.

## P. Public IDs

Public IDs are transactional aliases; canonical UUIDs remain authoritative.
Concurrent creation of 100 Orders in one second and 100 Queue Entries in one minute
produced unique aliases on both PostgreSQL and SQLite. Allocation uses an atomic
upsert counter. Decimal formatting has minimum width rather than a three-digit
cap, so values above 999 grow without wrap or collision. Buckets are derived by
converting aware UTC timestamps to `Asia/Kolkata`, including UTC/IST day rollover;
stored canonical timestamps remain UTC.

## Q. Runtime privileges

The canonical live verifier and inventory passed independently:

- schema registry contains exactly 51 runtime tables and zero runtime sequences;
- all 51 relations and all four protected functions are owned by `twf_migrator`;
- `twf_app` owns zero protected objects and cannot execute protected functions;
- table grants match the explicit registry and DELETE remains the exact accepted
  11-table allowlist;
- `twf_order_events`, `twf_queue_events`, public aliases, and policy events retain
  append-only grants and enabled immutability triggers;
- runtime cannot DELETE `twf_orders`, `twf_queue_entries`, or
  `broker_order_intents`, cannot UPDATE/DELETE Order or Queue audit events, cannot
  edit Alembic head, and cannot perform protected DDL;
- OE-4 tables have only their required SELECT/INSERT/UPDATE grants and no DELETE;
- database/schema ownership and OE-3 reciprocal Queue coherence constraints remain
  intact.

The full PostgreSQL suite also recreated and exercised the policy on disposable
databases; this review did not apply live grants or change business rows.

## R. Browser remediation verification

The WebKit failure was independently traced to the inherited Snap
`GIO_MODULE_DIR`, which pointed Playwright WebKit at incompatible core20 modules.
`playwright.config.ts` clones the browser environment and removes exactly that
variable from browser launch. It does not suppress console failures, alter app
responses, retry tests, or mask assertions.

The fresh canonical gate passed every applicable WebKit `/login`, authentication,
OE-4 Queue, and workspace case. Chromium assertion changes were inspected against
the accepted current UI rather than obsolete page-title/layout expectations.

The two production frontend fixes are bounded and legitimate:

- planned navigation links disable speculative prefetch so unimplemented routes do
  not race current-workspace assertions;
- quote polling waits two seconds after completion, preventing an immediate
  follow-up request after a slow success from tripping admission and erasing fresh
  data.

Neither changes OE-4 backend semantics or accepted Queue UX.

Protected fingerprints remained exactly:

| File                       | SHA-256                                                            |
| -------------------------- | ------------------------------------------------------------------ |
| `queue/dispatch.py`        | `b0becef1d5f04dfdc85299bc525cf92f191a3d3d87c4215d76bd053cefbfe273` |
| `queue/policy.py`          | `2288a5fa25edbfb84eddf4f64963a8296e866553b3daab27d6e13d5914a27bb0` |
| `brokers/order_service.py` | `a1be4c9695d451c7b904c6279f9a5f189ee401a5b4453ca50a1e75a618a582f5` |
| `api/twf_queue.py`         | `10b24159d83ca95ce45c49f9499ea66afd6d8e066f949670e402e293267555f3` |
| `config/settings.py`       | `7ff290c87cd7d8930e45bdcaacddb1b419e1a0d7cd5e1bfabcb081d6a3e6bd8e` |
| `queue-workspace.tsx`      | `c9a64a85d2d7fd4f3a806213d9732959fc65a9cdc223e0e4ea4310da0f1e70b7` |
| `queue-policy-control.tsx` | `cc2ec6ec4ef191594ce775374f491523f6d4bbcf51fe9fe4961b7037b8de5116` |

## S. Browser skip audit

| Reason                                                                           | Chromium | WebKit |                                                                                                        Total | Justification                                                                                           | Result    |
| -------------------------------------------------------------------------------- | -------: | -----: | -----------------------------------------------------------------------------------------------------------: | ------------------------------------------------------------------------------------------------------- | --------- |
| Discovery desktop two-panel assertion skipped below 1200 px                      |        3 |      3 |                                                                                                            6 | compact ledger is covered by the primary journey at 390/768/1024; this assertion runs at 1440/1920/2560 | JUSTIFIED |
| Futures auxiliary-catalog failure injection runs at representative Chromium 1440 |        5 |      6 | failure logic is browser/viewport independent; the full Futures parity journey still runs in all 12 projects | JUSTIFIED                                                                                               |
| **Total**                                                                        |    **8** |  **9** |                                                                                                       **17** | no spec/browser-wide disablement                                                                        | **PASS**  |

There are only two `test.skip` predicates in the browser suite. Both are local,
explicit, and reasoned; retries remain zero and no mass skip was introduced.

## T. Frozen-system regressions

The full backend gates include OE-1 lifecycle/authority, OE-2 Preview/Create
binding and atomicity, DB-1 PostgreSQL-primary/fail-closed/numeric behavior, and
OE-3 coherence/audit/pagination/privilege/concurrent replay coverage. All passed on
their applicable backends. Browser coverage for OE-2 Orders and OE-3 Queue also
passed in all 12 projects. Protected OE-4 backend and Queue workspace fingerprints
were unchanged by browser remediation.

OE-5 remains unimplemented: production code contains only the OE-4
`RECONCILIATION_REQUIRED` state and completion/recovery hook, not a broker
reconciliation subsystem.

## U. Backend/frontend/static gates

| Gate                         | Result                                                               |
| ---------------------------- | -------------------------------------------------------------------- |
| Full PostgreSQL backend      | PASS — 1,578 passed, 1 intentional SQLite-only skip, 4 warnings      |
| Full SQLite fallback backend | PASS — 1,504 passed, 75 explicit PostgreSQL-only skips, 4 warnings   |
| Focused OE-4 PostgreSQL      | PASS — 21 passed                                                     |
| Focused OE-4 SQLite          | PASS — 21 passed                                                     |
| Frontend unit                | PASS — 296 tests in 33 files                                         |
| TypeScript                   | PASS                                                                 |
| ESLint                       | PASS, zero warnings                                                  |
| Prettier                     | PASS                                                                 |
| Production build             | PASS                                                                 |
| Changed backend-file mypy    | PASS — 40 source files                                               |
| Repository mypy              | PRE_EXISTING_UNRELATED — the same 15 errors in three unchanged tests |
| Ruff                         | PASS                                                                 |
| Ruff format                  | PASS — 246 files already formatted                                   |
| Python compileall            | PASS                                                                 |
| `pip check`                  | PASS — no broken requirements                                        |
| `git diff --check`           | PASS                                                                 |

The three repository-mypy debt files are byte-identical to the OE-3 accepted
baseline. An extra diagnostic that applied the backend's strict mypy configuration
to the standalone Playwright Python fixture reproduced seven existing fixture
annotation/monkeypatch findings; that fixture is outside the configured backend
mypy scope and was unchanged by the browser-remediation delta. It did not affect
the required changed backend-file or repository gates.

### Full browser matrix

| Browser   |  Passed | Skipped | Failed |
| --------- | ------: | ------: | -----: |
| Chromium  |     214 |       8 |      0 |
| WebKit    |     213 |       9 |      0 |
| **Total** | **427** |  **17** |  **0** |

### OE-4 Queue scenario by width

| Width | Chromium | WebKit |
| ----: | -------- | ------ |
|   390 | PASS     | PASS   |
|   768 | PASS     | PASS   |
|  1024 | PASS     | PASS   |
|  1440 | PASS     | PASS   |
|  1920 | PASS     | PASS   |
|  2560 | PASS     | PASS   |

### Execution safety matrix

| Scenario                        | Expected                | Observed                                             | Result |
| ------------------------------- | ----------------------- | ---------------------------------------------------- | ------ |
| Execution OFF, manual           | no claim/send/mutation  | typed block; zero calls/attempts                     | PASS   |
| Execution OFF, AUTO             | no selection/send/churn | early return; zero calls/attempts                    | PASS   |
| Manual success, synthetic       | one logical submission  | one claim, attempt, intent, call                     | PASS   |
| AUTO success, synthetic         | one logical submission  | one claim, attempt, intent, call                     | PASS   |
| Double manual                   | one winner              | one provider call                                    | PASS   |
| Two AUTO workers                | one winner              | one provider call                                    | PASS   |
| Cancel vs claim                 | coherent single winner  | cancel prevents send or typed conflict follows claim | PASS   |
| Hold vs claim                   | coherent single winner  | no in-flight reversal                                | PASS   |
| Definitive reject               | terminal, no retry      | FAILED/rejected after one call                       | PASS   |
| Pre-send failure                | zero calls              | FAILED with zero calls                               | PASS   |
| Ambiguous timeout               | reconcile, no resend    | RECONCILIATION_REQUIRED after one call               | PASS   |
| Crash after claim               | no duplicate send       | recovered without send; reconcile state              | PASS   |
| Crash after provider acceptance | same attempt, one call  | broker truth finalized through existing attempt      | PASS   |
| Restart AUTO recovery           | discover once           | persisted eligible entry handled exactly once        | PASS   |
| Restart with execution OFF      | preserve without send   | zero calls and unchanged state                       | PASS   |

## V. Live post-review safety

The final live read-only check matched the baseline exactly:

| Property                   | Final                            |
| -------------------------- | -------------------------------- |
| Database / role            | PostgreSQL / `twf_app`           |
| Alembic revision           | `0028_oe4_dispatch`              |
| Queue execution capability | `False`                          |
| Queue policy               | one `MANUAL` policy at version 7 |
| Dispatch attempts          | 0                                |
| Broker order intents       | 10                               |

All provider interactions in tests were synthetic/disposable. No real broker order
was submitted.

## W. Findings by severity

| Severity | Count | Findings |
| -------- | ----: | -------- |
| CRITICAL |     0 | None     |
| HIGH     |     0 | None     |
| MEDIUM   |     0 | None     |
| LOW      |     0 | None     |

Non-finding observations retained for transparency: repository mypy has the same
15 unrelated errors in three unchanged test files; SQLAlchemy emits four known
relationship-cycle warnings; and the 17 browser skips are the two narrow,
explicitly justified groups in section S.

## X. Scorecard

```text
OE4_FINAL_REVIEW_STATUS = PASS

EXECUTION_INTERLOCK_OFF_BLOCKS_MANUAL = PASS
EXECUTION_INTERLOCK_OFF_BLOCKS_AUTO = PASS
INTERLOCK_PRE_BROKER = PASS
NO_LIVE_BROKER_ORDER = PASS

QUEUE_POLICY_DEFAULT_MANUAL = PASS
QUEUE_POLICY_OWNER_ACCOUNT_SCOPED = PASS
QUEUE_POLICY_AUDITED = PASS

ENTRY_MODE_SNAPSHOT = PASS
ENTRY_MODE_IMMUTABLE = PASS
MANUAL_TO_AUTO_EXISTING_UNCHANGED = PASS
AUTO_TO_MANUAL_EXISTING_UNCHANGED = PASS
MODE_SWITCH_NO_ROW_REWRITE = PASS
MODE_ADMISSION_RACE_SAFE = PASS

AUTO_WORKER_USES_ENTRY_MODE = PASS
HISTORICAL_MANUAL_NOT_AUTODISPATCHED = PASS
HISTORICAL_AUTO_STILL_AUTODISPATCHED = PASS

MANUAL_RELEASE_WAITS = PASS
AUTO_RELEASE_AUTODISPATCHES = PASS
HELD_NEVER_DISPATCHES = PASS

DOUBLE_MANUAL_SAFE = PASS
MULTI_AUTO_WORKER_SAFE = PASS
CANCEL_CLAIM_SAFE = PASS
HOLD_CLAIM_SAFE = PASS

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
CRASH_AFTER_PROVIDER_ACCEPT_SAFE = PASS
RESTART_AUTO_RECOVERY = PASS

SOURCE_MANUAL = PASS
SOURCE_WATCHLIST = PASS
SOURCE_SCANNER = PASS
SOURCE_WEBHOOK = NOT_IMPLEMENTED
SOURCE_IMMUTABLE = PASS
SOURCE_SPOOF_BLOCKED = PASS

PUBLIC_ORDER_ID_UNIQUE = PASS
PUBLIC_QUEUE_ID_UNIQUE = PASS
PUBLIC_ID_OVERFLOW_SAFE = PASS
PUBLIC_ID_TIMEZONE_SAFE = PASS
CANONICAL_UUIDS_PRESERVED = PASS

OE4_RUNTIME_GRANTS_CORRECT = PASS
OE3_FROZEN_INTACT = PASS
OE2_FROZEN_INTACT = PASS
OE1_FROZEN_INTACT = PASS
DB1_FROZEN_INTACT = PASS

WEBKIT_ROOT_CAUSE_CONFIRMED = PASS
WEBKIT_REMEDIATION_REPRODUCIBLE = PASS
CHROMIUM_STALE_ASSERTIONS_CORRECTED = PASS
NO_TEST_WEAKENING = PASS
NO_MASS_SKIPS = PASS

FULL_BROWSER_GATE = PASS
BROWSER_FAILED_COUNT = 0

FULL_BACKEND_POSTGRES = PASS
FULL_BACKEND_SQLITE = PASS
FRONTEND = PASS
TYPESCRIPT = PASS
ESLINT = PASS
PRETTIER = PASS
BUILD = PASS

CHANGED_FILE_MYPY = PASS
REPO_MYPY = PRE_EXISTING_UNRELATED
RUFF = PASS
FORMAT = PASS
COMPILE = PASS
PIP_CHECK = PASS
GIT_DIFF_CHECK = PASS

OE5_NOT_IMPLEMENTED = PASS

OE4_FREEZE_RECOMMENDATION =
    ACCEPT_AND_FREEZE
```

## Y. Freeze recommendation

All binary acceptance conditions are satisfied: zero CRITICAL/HIGH findings,
execution-off guarantees, immutable mode snapshots, one dispatch path, safe
concurrency and recovery, no blind ambiguous retry, intact authority and privilege
boundaries, collision-safe public IDs, a reproducible zero-failure browser gate,
clean backend/frontend/static gates, intact frozen systems, no OE-5 leakage, and no
real broker activity.

**OE4_FREEZE_RECOMMENDATION = `ACCEPT_AND_FREEZE`.**

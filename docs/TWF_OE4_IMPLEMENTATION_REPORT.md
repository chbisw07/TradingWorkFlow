# OE-4 Implementation Report

> **Runtime privilege remediation (16 October 2026): PASS.** The live OE-4 grant omission was corrected in the canonical role policy and applied to the authoritative database. Fresh, upgrade, and restore paths reproduce the same policy. See [OE-4 Runtime Privilege Remediation Report](TWF_OE4_RUNTIME_PRIVILEGE_REMEDIATION_REPORT.md). This supersedes older statements below that no live grants were changed.

## A. Executive verdict

**OE4_STATUS = PASS. READY_FOR_INDEPENDENT_REVIEW. Not accepted/frozen.** Required implementation and validation gates are complete, with unchanged repository typing debt explicitly carried forward. No commit, tag, push, live migration, live execution enablement, real broker order or OE-5 work.

The implementation preserves the user's central rule: current owner/account policy controls only future admissions. Immutable entry mode controls existing work, including after policy switches and restarts.

## B. Preflight

Preflight passed before edits: branch `main`, clean worktree, `HEAD == origin/main == f8b61d269be1a6416f9b83cf1a1aa7870e7969db`, clean `git diff --check`. Current uncommitted changes are this implementation. No history operation was performed.

## C. OE-4 architecture

See [Queue/Broker bridge architecture](TWF_OE4_QUEUE_BROKER_BRIDGE_ARCHITECTURE.md). One DispatchService bridges durable Queue intent to the existing Broker V2 claim/submission outcome machinery. No new broker adapter or parallel execution pipeline.

## D. Queue current policy

Persisted owner/account key; default MANUAL; CAS version; immutable previous/new-mode audit with owner/account/actor/time/version. Policy endpoints reject foreign accounts and stale versions using existing authenticated owner checks. Changing policy never updates Queue rows.

## E. Admission-time mode snapshot

Entry, mode/account/policy-version/source/public-ID snapshot, Order READY→QUEUED and histories share a transaction. PostgreSQL locks the policy row; SQLite reserves the writer before reading. Frozen idempotent admission recovery is retained.

## F. Mode-switch concurrency semantics

Twenty alternating admission/policy races per backend (ten each direction) require one exact old/new `(mode, policy_version)` pair. No partial snapshot. Mode-switch tests compare the complete entry response before/after switching, including versions and timestamps.

Exact disposable PostgreSQL trace:

```json
{
  "calls_after_manual_dispatch": 2,
  "calls_after_worker": 1,
  "entries": [
    {
      "admission_sha256": "a236dfca5cb8ac32b2e2d0e780e181715ee60d94ff90ed628a78c1c183ba4234",
      "admission_version": 1,
      "effective_mode": "MANUAL",
      "order": "ORD-20261016173922-001",
      "policy_version": 1,
      "queue": "QID-20261016-1739-001",
      "source": "MANUAL"
    },
    {
      "admission_sha256": "e3e9b94a0dc58f271408d2d448d3217c5c00ef67b059cda9b944f8bfaf3e7700",
      "admission_version": 1,
      "effective_mode": "AUTO",
      "order": "ORD-20261016173922-002",
      "policy_version": 2,
      "queue": "QID-20261016-1739-002",
      "source": "MANUAL"
    },
    {
      "admission_sha256": "5584b37a87a140c7f66bc08fbfc4fdb302f561bfcd9cd0c500f8758ac2978c95",
      "admission_version": 1,
      "effective_mode": "MANUAL",
      "order": "ORD-20261016173922-003",
      "policy_version": 3,
      "queue": "QID-20261016-1739-003",
      "source": "MANUAL"
    }
  ],
  "final_states": ["DISPATCHED", "DISPATCHED", "READY"],
  "unchanged_across_policy_switches": true
}
```

The entry hashes above were unchanged across the corresponding policy switch (full response equality asserted). Q1 remains MANUAL at version 1 after MANUAL→AUTO. Q2 remains AUTO at version 1 after AUTO→MANUAL. Q3 snapshots MANUAL. One worker cycle makes exactly one synthetic broker call for Q2. Q1 and Q3 still wait READY. User Dispatch of Q1 adds exactly one call; final states are DISPATCHED, DISPATCHED, READY. No user Dispatch is issued for Q2.

## G. Existing-row MANUAL backfill

0028 defaults every existing entry to MANUAL and policy version 0; preserves UUIDs and reconstructs source from durable Order provenance. Timestamp/UUID ordering produces deterministic aliases. Existing account-less entries are never assigned a guessed execution account or auto-dispatched. The strengthened migration preservation/downgrade/corruption probe explicitly asserts MANUAL, policy version 0, no guessed account, source, both aliases and unchanged UUIDs after upgrade; it passes on PostgreSQL and SQLite.

## H. Queue/Order lifecycle

READY/HELD remain the accepted pre-dispatch states. Claim adds Queue DISPATCHING / Order SUBMITTING; confirmed acknowledgement adds DISPATCHED / BROKER_ACCEPTED; rejection gives FAILED / REJECTED; ambiguity gives RECONCILIATION_REQUIRED / SUBMITTING; pre-claim cancellation gives CANCELLED / CANCELLED. No fabricated fill state. OE-1 public lifecycle and authority contracts are unchanged.

## I. Source provenance

MANUAL uses the frozen manual path. WATCHLIST/SCANNER use additive trusted adapters, validate source ownership/visibility and exact instrument membership, and bind source/reference to the same Preview/Create record. Ordinary payloads cannot set provenance/state/actor/authority. A sourced preview cannot be consumed by the manual endpoint. Queue copies trusted Order provenance and cannot rewrite it. WEBHOOK generation is NOT_IMPLEMENTED; no future generator was added. Options Analytics now opens a manual TWF Order; Broker workspace direct flow is explicitly retained.

## J. Public IDs

UTC timestamps and UUID PK/FK/API identities remain unchanged. IST aliases use transactional counters, unique constraints and immutable storage: ORD-second / QID-minute formats with a minimum three-digit suffix that expands past 999. One hundred same-second Orders and one hundred same-minute admissions using eight concurrent clients pass on both backends in the focused suite.

## K. DispatchService

Manual and automatic calls share exact-contract resolution, broker account ownership/connectivity/credentials/generation checks, Broker V2 executable-contract/quantity/price/product validation, immutable Order comparison, atomic claim and outcome transitions. A fault after claim writes rolls back entry/Order/attempt/intent/events; retry then sends once. A broker-I/O probe acquires the persisted entry lock and a separate writer during placement, proving the claim transaction is closed.

## L. AUTO coordinator

Bounded FIFO scan of persisted READY + AUTO entries, independent of current policy. Restart rediscovers work. HELD never dispatches. MANUAL Release waits; AUTO Release becomes eligible. The explicit operator execution switch defaults OFF for both modes. Synthetic fixtures alone enable it during validation.

## M. Broker V2 bridge

The shared `_submit_claimed` implementation owns the single adapter `place_order` call. Queue persists a Broker V2 intent and unique attempt before I/O, retains its correlation tag and records returned broker order reference. Existing Broker manual confirm path still uses its original preview/claim checks and the same extracted post-claim implementation.

## N. Idempotency

One attempt per Queue entry; one unique Broker intent per attempt. Double manual clicks and competing AUTO workers cannot create a second logical dispatch. Broker tags are correlation aids, not asserted provider idempotency. No retry of an uncertain write. Distinct Order intents retain the existing explicitly deferred global-idempotency boundary.

## O. Failure/reconciliation

Synthetic success, definitive rejection, transport loss and server failure have explicit outcomes. Repeated worker cycles never resend. Pre-dispatch errors record temporary/permanent classification and zero broker calls. Process interruption before send becomes reconciliation-required; interruption after a persisted acceptance recovers that acceptance without another send. OE-5 fill reconciliation is not implemented.

## P. Cancel/Hold behavior

READY/HELD cancellation and READY Hold serialize with claim. A winning local action means zero broker calls. A winning claim returns a typed conflict to the losing action; it cannot be presented as a local cancellation. Historical MANUAL/AUTO release retains its admission mode.

## Q. Concurrency/crash evidence

`tests/test_queue_dispatch_oe4.py`: 21 focused cases, including four simultaneous manual dispatches; ten two-worker races; five Cancel and five Hold races; twenty policy/admission races; 100+100 public-ID allocation; claim-transaction rollback; pre-/post-acceptance interruptions; direct mode/source/account/alias/policy-audit tampering; exact futures/CE/PE dispatch; source Preview binding/spoof rejection; default-off execution; and no DB lock across broker I/O. Focused result: **21 passed SQLite; 21 passed live disposable PostgreSQL**.

## R. UX

Compact owner/account policy control describes new admissions and confirms existing entries are unchanged. Table source/mode/readable IDs and lifecycle states are visible. Browser evidence covers synthetic success, rejection and reconciliation-required outcomes, plus Hold/Release/Cancel. MANUAL READY offers Dispatch/Hold/Cancel/Details; AUTO offers no Dispatch. The action strip stays visible when the table scrolls. History exposes entry snapshot/authority/attempt/intent/result. Account selector/New Order remain available across Trade tabs. Existing blue/white structure and semantic status colors remain.

## S. Migration/privileges

Only new migration 0028; no edits to 0025/0026/0027. PostgreSQL runtime grants retain exactly the same 11 DELETE cleanup tables; all other 40 schema tables are denied (38 generic probes plus separately tested Queue audit and Alembic metadata); audit/alias tables are SELECT/INSERT only. Enforcing objects remain migrator-owned and their functions are not executable by runtime directly. No live grants were changed. SQLite retains managed-connection protections and its accepted trusted-process/file-access boundary.

Initial checks caught and corrected a migration/model unique-constraint name mismatch and missing offline-data SQL generation. Offline SQL now includes deterministic PostgreSQL backfill; online live PostgreSQL migration/testing is still mandatory. Clean pre-execution downgrade is supported; downgrade refuses to erase bridge execution/policy/source audit.

## T. Frozen-system regressions

No changes to OE-1 contracts, lifecycle, trusted-context or resolver boundaries. OE-2's MANUAL path retains its single-use TTL/owner/exact-terms Preview binding and atomic create transaction; sourced adapters extend the private implementation using existing sealed subsystem context. OE-3 relational coherence, append-only events, owner cursors, newest-first pagination and DB1-R2 concurrent replay are retained. PostgreSQL remains primary; no fallback failover/dual-write.

## U. Backend/frontend/browser gates

Final backend gates passed. Initial failures in schema inventory, migration metadata/offline generation and stale fixture expectations were corrected without suppressing assertions.

The first final PostgreSQL run, while SQLite/build/browser work overlapped, recorded **1 failed, 1,576 passed, 1 skipped**: the unchanged MCP delayed-completion deadline test returned in 0.847s against its 0.52s bound. No MCP implementation, test or timeout was changed. Its complete file then passed **33/33 in 17.04s** in isolation; the entire PostgreSQL gate rerun without competing validation passed below. This records the observed timing sensitivity; it does not claim a proven root cause. A frontend run similarly hit one unchanged Watchlist timeout during overlapping validation; its final bounded-parallelism rerun is reported below, with no timeout increase.

| Gate                                   | Result / evidence                                                                                                                                               |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Complete PostgreSQL                    | **1,577 passed, 1 skipped**, 643.90s — `/tmp/oe4-full-pg-serial.log`; SQLite-only contention skip                                                               |
| Complete SQLite                        | **1,503 passed, 75 skipped**, 571.79s — `/tmp/oe4-full-sqlite-final.log`; backend-specific skips                                                                |
| Final focused OE-4 + legacy backfill   | **22 PostgreSQL / 22 SQLite passed**, 31.87s / 26.73s; final typing-only changes included                                                                       |
| PostgreSQL restart + explicit backfill | **2 passed**, 5.58s — `/tmp/oe4-restart-backfill.log`                                                                                                           |
| Frontend unit suite                    | **296 passed, 33 files**, 29.94s (`--maxWorkers=2`) — `/tmp/oe4-web-serial.log`                                                                                 |
| PostgreSQL browser                     | **15 passed**, 2.2m, across Chromium 390/1024/1440 — `/tmp/oe4-browser-last.log`; final header/outcome flow **3 passed**, 25.4s — `/tmp/oe4-browser-header.log` |
| Changed backend/source mypy            | **152 files clean**; source, changed migration and backend tests checked directly                                                                               |
| Repository-configured mypy             | **PRE_EXISTING_UNRELATED**: 15 errors in 3 unchanged test files; 243 files checked                                                                              |
| Ruff / format / compile / pip          | Passed; 244 Python files formatted, no broken requirements                                                                                                      |
| TypeScript / ESLint / Prettier / build | All passed; final build `/tmp/oe4-build-header.log`, TypeScript `/tmp/oe4-typecheck-last.log`                                                                   |
| git diff --check                       | Passed                                                                                                                                                          |

The unchanged mypy debt is in `tests/test_derivative_templates.py`, `tests/test_option_chain.py`, and `tests/test_derivative_relative_volume.py`; all three are byte-identical to HEAD. The earlier 145-file clean result covered application source only and is not presented as a clean repository-wide gate.

Restart evidence used a temporary pytest wrapper around the permanent mode-snapshot test: after Q1/Q2/Q3 were committed and current policy returned to MANUAL, it disposed connection pools and restarted only the `tools/test-postgres.sh` private `/tmp/twf-pg-test.*` cluster with `pg_ctl -m fast restart`. It then resumed the unchanged worker/assertions: Q2 dispatched automatically, Q1/Q3 stayed READY, and explicit Q1 Dispatch produced one additional synthetic call. No deployment database or credentials were loaded.

## V. Exact files changed

- `README.md`
- `apps/api/alembic/versions/0028_oe4_dispatch.py`
- `apps/api/src/twf/api/twf_orders.py`
- `apps/api/src/twf/api/twf_queue.py`
- `apps/api/src/twf/brokers/order_contracts.py`
- `apps/api/src/twf/brokers/order_service.py`
- `apps/api/src/twf/brokers/queue_authority.py`
- `apps/api/src/twf/brokers/service.py`
- `apps/api/src/twf/config/settings.py`
- `apps/api/src/twf/infrastructure/database.py`
- `apps/api/src/twf/infrastructure/dispatch.py`
- `apps/api/src/twf/infrastructure/order_preview.py`
- `apps/api/src/twf/infrastructure/twf_order.py`
- `apps/api/src/twf/infrastructure/twf_queue.py`
- `apps/api/src/twf/main.py`
- `apps/api/src/twf/queue/contracts.py`
- `apps/api/src/twf/queue/dispatch.py`
- `apps/api/src/twf/queue/policy.py`
- `apps/api/src/twf/queue/public_ids.py`
- `apps/api/src/twf/queue/service.py`
- `apps/api/src/twf/twf_orders/manual.py`
- `apps/api/tests/test_backend_shell.py`
- `apps/api/tests/test_database_foundation.py`
- `apps/api/tests/test_foundation.py`
- `apps/api/tests/test_postgres_privilege_boundary.py`
- `apps/api/tests/test_queue_dispatch_oe4.py`
- `apps/api/tests/test_twf_queue_oe3_hardening.py`
- `apps/web/src/app/api/v1/twf-orders/[[...path]]/route.ts`
- `apps/web/src/app/api/v1/twf-queue/[[...path]]/route.ts`
- `apps/web/src/components/brokers/order-ticket.tsx`
- `apps/web/src/components/options/options-workspace.tsx`
- `apps/web/src/components/orders/orders-workspace.tsx`
- `apps/web/src/components/orders/queue-admission-dialog.tsx`
- `apps/web/src/components/orders/queue-policy-control.tsx`
- `apps/web/src/components/orders/queue-workspace.tsx`
- `apps/web/src/components/scanner/derivatives-scanner.tsx`
- `apps/web/src/components/scanner/futures-scanner.tsx`
- `apps/web/src/components/scanner/scanner-workspace.tsx`
- `apps/web/src/components/watchlists/watchlists-workspace.tsx`
- `apps/web/src/lib/twf-queue.ts`
- `apps/web/src/styles/orders.css`
- `apps/web/tests/broker-orders.test.tsx`
- `apps/web/tests/browser/auth-test-server.mjs`
- `apps/web/tests/browser/derivatives-scanner.spec.ts`
- `apps/web/tests/browser/queue-dispatch.spec.ts`
- `apps/web/tests/browser/service_fixture_api.py`
- `apps/web/tests/browser/twf-queue.spec.ts`
- `apps/web/tests/options.test.tsx`
- `apps/web/tests/queue-pagination.test.tsx`
- `docs/TWF_OE4_IMPLEMENTATION_REPORT.md`
- `docs/TWF_OE4_QUEUE_BROKER_BRIDGE_ARCHITECTURE.md`
- `tools/postgres_roles.py`

## W. Known limitations and carry-forward

- Execution is deliberately disabled in deployment configuration; live migration/grant cutover and enabling dispatch require a separate accepted rollout. No real broker writes were used as proof.
- Legacy Queue entries without account binding cannot execute; cancel and create a new reviewed intent with an account. They are never retroactively reassigned or converted to AUTO.
- Ambiguous attempts are fenced for reconciliation. Automatic broker-fill reconciliation/Order synchronization is OE-5, not part of this implementation.
- A temporary pre-dispatch failure is terminal for this admission; no implicit resend/retry policy was introduced.
- WEBHOOK, future generator subsystems, advanced risk/SL/TP/scheduling and global idempotency across distinct intents remain deferred.
- SQLite security remains trusted-process/file-access; it is not a PostgreSQL-equivalent role boundary.
- Existing accepted bidirectional Order/Queue FKs produce four SQLAlchemy table-sort warnings during full metadata checks; do not weaken the relational invariant to silence them.
- Repository-wide mypy retains 15 pre-existing errors in three byte-identical test files. The isolated deadline failure under overlapping workloads and subsequent clean reruns are retained in section U; no frozen MCP code or timing contract was changed.
- Automatic approval review rejected an earlier attempt to start the AUTO worker in every non-test environment because it could enable live submissions. The accepted implementation instead requires an explicit default-off execution setting; only isolated synthetic fixtures enable it.

## X. Scorecard

Implementation readiness only; independent review and acceptance/freeze remain separate. Repository mypy preserves documented unrelated debt.

```text
OE4_STATUS = PASS
QUEUE_CURRENT_MODE_PERSISTED = PASS
QUEUE_DEFAULT_MODE_MANUAL = PASS
QUEUE_MODE_OWNER_ACCOUNT_SCOPED = PASS
QUEUE_MODE_CHANGE_AUDITED = PASS
ENTRY_EFFECTIVE_MODE_PERSISTED = PASS
ENTRY_EFFECTIVE_MODE_IMMUTABLE = PASS
MODE_SNAPSHOTTED_AT_ADMISSION = PASS
MANUAL_TO_AUTO_EXISTING_ENTRIES_UNCHANGED = PASS
AUTO_TO_MANUAL_EXISTING_ENTRIES_UNCHANGED = PASS
MODE_SWITCH_NO_EXISTING_ROW_REWRITE = PASS
PRE_OE4_ENTRIES_BACKFILLED_MANUAL = PASS
MANUAL_NO_AUTO_DISPATCH = PASS
MANUAL_DISPATCH_BUTTON = PASS
AUTO_NO_USER_CLICK_REQUIRED = PASS
AUTO_WORKER_USES_ENTRY_MODE_NOT_CURRENT_POLICY = PASS
AUTO_SAME_DISPATCH_SERVICE = PASS
HISTORICAL_MANUAL_REMAINS_MANUAL = PASS
HISTORICAL_AUTO_REMAINS_AUTO = PASS
HELD_NEVER_DISPATCHES = PASS
MANUAL_RELEASE_WAITS = PASS
AUTO_RELEASE_AUTODISPATCHES = PASS
PRE_DISPATCH_CANCEL = PASS
CANCEL_NO_BROKER_CALL = PASS
SOURCE_MANUAL = PASS
SOURCE_WATCHLIST = PASS
SOURCE_SCANNER = PASS
SOURCE_WEBHOOK = NOT_IMPLEMENTED
SOURCE_IMMUTABLE = PASS
SOURCE_SPOOF_BLOCKED = PASS
INTERNAL_UUIDS_PRESERVED = PASS
PUBLIC_ORDER_ID = PASS
PUBLIC_QUEUE_ID = PASS
PUBLIC_ID_CONCURRENCY = PASS
DISPATCH_COMMON_SERVICE = PASS
AUTO_MANUAL_CHECK_PARITY = PASS
DISPATCH_CLAIM_ATOMIC = PASS
NO_DB_TX_ACROSS_BROKER_IO = PASS
BROKER_V2_REUSED = PASS
BROKER_INTENT_LINKED = PASS
BROKER_IDEMPOTENCY = PASS
DOUBLE_MANUAL_DISPATCH_SAFE = PASS
MULTI_AUTO_WORKER_SAFE = PASS
ADMISSION_MODE_SWITCH_RACE_SAFE = PASS
CANCEL_AUTO_RACE_SAFE = PASS
AMBIGUOUS_TIMEOUT_NO_BLIND_RETRY = PASS
RECONCILIATION_REQUIRED_SUPPORTED = PASS
CRASH_RECOVERY = PASS
OE3_FROZEN_INTACT = PASS
DB1_FROZEN_INTACT = PASS
OE1_FROZEN_INTACT = PASS
OE2_FROZEN_INTACT = PASS
NO_LIVE_BROKER_ORDER = PASS
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
BUILD = PASS
GIT_DIFF_CHECK = PASS
OE4_READY_FOR_INDEPENDENT_REVIEW = YES
```

## Y. Final status

**READY_FOR_INDEPENDENT_REVIEW.** OE-4 is not accepted or frozen. Execution remains default-off; no live cutover, real broker order, commit/tag/push or OE-5.

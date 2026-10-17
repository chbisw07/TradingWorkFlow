# OE-4 — Queue → Broker V2 bridge

Status: READY_FOR_INDEPENDENT_REVIEW; not accepted or frozen. PostgreSQL remains authoritative. OE-1/OE-2/DB-1/OE-3 remain accepted foundations. No OE-5 reconciliation worker is introduced.

## Governing rule

**No TWF subsystem may initiate a broker order except through the governed TWF execution path.**

Application trading surfaces use **TWF Order → Execution Queue → DispatchService → Broker V2 → adapter**. The existing Broker workspace/manual Broker New Order remains operational as the explicitly retained migration path. Its adapter and outcome persistence are shared with Queue dispatch, not duplicated.

**Queue current dispatch mode affects only FUTURE admissions. Each Queue Entry snapshots `effective_dispatch_mode` at admission. Existing Queue Entry mode never changes retroactively.**

`MANUAL` waits for an explicit Dispatch action. `AUTO` is discoverable by the coordinator without that click. Both modes have identical account, exact-contract, terms, state/version, claim, broker and outcome checks. A later policy change neither starts a historical MANUAL backlog nor stops historical AUTO entries.

## Policy and admission

`twf_queue_dispatch_policies` is keyed by owner/account, defaults to MANUAL, and uses version CAS. Mode changes append immutable `twf_queue_policy_events` with previous/new mode, actor, timestamp and version. No policy update touches Queue entries.

Admission locks the same policy row used by mode changes. PostgreSQL uses row locks; SQLite reserves its single writer before reading. The policy snapshot, entry, public ID, Order READY→QUEUED transition and both histories commit together. Existing Queue replay and deferred Order↔Queue constraints remain in force. Concurrent admission observes one serialized old/new policy version, never a hybrid.

The Queue entry stores immutable mode, account, policy version, source kind/reference and public Queue alias. Database triggers enforce snapshot immutability. Account ownership is checked on admission and dispatch. No client may set source, state, actor or effective mode through admission payloads.

Pre-OE-4 rows receive MANUAL and policy version 0. No execution account is guessed for a legacy row. Such rows remain visible and holdable/cancellable, but cannot dispatch. Cancel and create a newly reviewed Order with an explicit account to execute. This is a deliberate migration limitation, not an automatic conversion or a silent failure.

## Claim and execution transactions

1. Authenticate the manual actor, or mint an internal, process-issued capability bound to a persisted AUTO READY entry and its account. The worker does not impersonate a browser session. Inactive users cannot dispatch.
2. Read current credentials/catalog outside a database transaction. Project exact structured contract identity using OE-2's resolver; compare every canonical Order field, then reuse Broker V2 resolution and quantity/product/price/expiry validation.
3. In a short transaction, lock/recheck Queue and Order, versions, account ownership, connection generation and broker identity. Persist one unique attempt and Broker V2 intent, transition Queue→DISPATCHING and Order→SUBMITTING, append audit, then commit.
4. Call the shared Broker V2 post-claim submission implementation. No database transaction or row lock spans broker I/O.
5. Persist Broker V2 response, then atomically finish Queue/Order and audit. Attempt linkage and claim identity cannot be rewritten by runtime DML.

The Queue entry has at most one dispatch attempt, which has one unique Broker intent. The intent's existing tag is a correlation aid, **not a claim that the broker provides idempotency**. The durable local claim prevents repeated sends. Double clicks, competing workers and retries observe the existing claim/outcome.

## Outcomes and recovery

| Observation | Queue | TWF Order | Send/retry policy |
| --- | --- | --- | --- |
| Confirmed broker order reference | DISPATCHED | BROKER_ACCEPTED | No resend; never invent a fill |
| Definitive broker rejection | FAILED | REJECTED | No resend |
| Timeout, lost/malformed response, uncertain acceptance | RECONCILIATION_REQUIRED | SUBMITTING | No blind resend |
| Pre-dispatch check fails | FAILED | FAILED | Zero broker writes; temporary/permanent classification recorded |
| Cancel wins before claim | CANCELLED | CANCELLED | Zero broker writes |

A temporary pre-dispatch failure is recorded, not automatically retried into a new logical attempt. An operator may investigate and create a newly reviewed intent. Claim interruptions are recovered from persisted attempts and Broker intent state. If a confirmed intent result exists, recovery records acceptance; otherwise it records RECONCILIATION_REQUIRED, including a crash before the network request where sending cannot safely be distinguished from an uncertain send. Broker V2 read reconciliation remains available; automatic fill reconciliation/propagation is OE-5 work.

The coordinator selects only persisted `queue_state=READY AND effective_dispatch_mode=AUTO`, FIFO by admission time/UUID, in bounded cycles. **It never consults current policy.** Process restart rediscovers persisted work. Unique attempts plus transactional state/version checks are the concurrency arbiter; workers may perform redundant read-only catalog checks, but only one claims a send.

HELD entries are not eligible. Release preserves mode: MANUAL waits; AUTO becomes discoverable. Hold/Cancel compete with claim atomically. After claim, Cancel returns a typed conflict and never pretends that broker execution was locally undone.

## Provenance and Order intake

The existing Select Instrument → Ticket → Preview experience remains. Trade and manual Options Analytics intake create MANUAL TWF Orders. Watchlist and Scanner adapters validate owner-visible persisted source references **and membership of the exact selected instrument** before issuing a sealed subsystem origin. They reuse the short-lived, single-use Preview/Create binding; source/reference are included in that binding. A manual endpoint cannot consume a sourced preview. Creation re-resolves current contract truth. Queue snapshots only trusted Order provenance.

Source reference is not sufficient by itself: unrelated/empty sources, foreign ownership, a changed contract or arbitrary source fields do not establish origin. No webhook Order generator exists in this phase; WEBHOOK intake is NOT_IMPLEMENTED, not simulated. Future Discovery/Strategy/Agent generators are deferred.

## Public aliases

Internal UUIDs remain all PK/FK, API and reconciliation identities. Operator aliases use Asia/Kolkata while canonical timestamps remain UTC:

- `ORD-YYYYMMDDHHMMSS-NNN`
- `QID-YYYYMMDD-HHMM-NNN`

An atomic upsert/increment of `twf_public_id_counters` allocates aliases in the same transaction as the Order/Queue row. Sequence width is a minimum of three; 1000 expands rather than wrapping. Unique constraints cover both aliases. Backfill orders by timestamp then UUID within each IST bucket. PostgreSQL offline SQL uses the equivalent partitioned row-number calculation. Public aliases are immutable. Failed transactions roll back allocation; aliases never replace canonical identity.

## Migration, privileges and rollout

Migration **0028_oe4_dispatch** is additive to accepted 0027; earlier migrations are unchanged. It adds policy/audit/attempt/alias storage, mode/source/account snapshots, bound-preview source reference and extended Queue states. SQLite migration-only FK suspension follows the existing trusted-process procedure and finishes with `foreign_key_check`. Normal managed connections retain FK and audit protections.

Run schema migration with the existing migrator role, then the existing PostgreSQL role hardening/verification procedure. There are 51 schema tables including `alembic_version`: DELETE is granted on exactly the same 11 approved cleanup tables and denied on all other 40. The existing generic denial matrix covers 38; `twf_queue_events` and `alembic_version` have separate boundary checks. Policy events and Order aliases join the SELECT/INSERT-only audit allowlist. Order/Queue audit remains append-only. The runtime role cannot own/alter/drop/disable enforcing objects. Future tables receive no DELETE by default.

A downgrade refuses to discard execution, policy-change or sourced-preview audit. A clean pre-execution downgrade can remove the additive schema. After execution use verified backup/recovery procedures, not an audit-destroying downgrade.

`TWF_QUEUE_DISPATCH_ENABLED` defaults to **false** and gates both manual and automatic execution. Policy can be configured while execution is off; the UI says so. No deployment setting, live database, live policy or live broker order was changed during implementation. Enabling execution is a distinct operator rollout after independent acceptance, migration, grants and readiness checks. Existing account trading capability checks still apply. The only enabled validation environments use the synthetic Broker adapter and disposable databases.

## UX

Execution Queue retains the Scanner's compact blue/white design, newest-first operator pagination, and FIFO execution ordering. The account-level mode control explicitly describes future admissions and confirms that existing entries are unchanged. Rows show source, stored mode, readable Order/Queue aliases and semantic lifecycle badges. MANUAL READY rows offer Dispatch/Hold/Cancel/Details; AUTO rows offer no manual dispatch. Histories retain mode/version/source, authority, attempt/intent linkage and outcomes. Canonical UUIDs remain available in details.

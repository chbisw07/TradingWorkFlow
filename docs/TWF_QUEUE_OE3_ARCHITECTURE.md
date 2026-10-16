# TWF Queue — OE-3 architecture

**Status:** OE-3 live privilege cutover passed on 16 October 2026; ready for focused independent re-review, not accepted/frozen. OE-1 and OE-2 are accepted/frozen. This document describes OE-3 only and does not authorize broker submission.

## Purpose and boundaries

A **TWF Order** is the durable trading intent. A **TWF Queue Entry** is the separate, durable admission of that Order to a governed future execution path. Creating an Order stops at `READY`; only an explicit Add to Queue action invokes OE-3. One Order has zero entries before admission and at most one afterward. A Queue Entry has its own immutable UUID, owner, state, version, admission timestamp, and append-only history. The Order remains the source of truth for instrument and trading terms; Queue reads project these fields through the linked Order rather than copying them.

**Governing rule:** No TWF subsystem may initiate a broker order except through the governed TWF execution path. OE-3 implements no broker order write, worker, or Queue-to-Broker bridge. Existing Broker New Order remains operational during migration. `READY` on a Queue Entry means admitted for future processing, not broker-approved or executable now.

## Authority and admission

`POST /api/v1/twf-queue/admit` accepts only a TWF Order UUID and optional expected Order version. The server derives the authenticated owner and USER actor from the persisted session, revalidates the session for each operation, and uses the separate trusted `TWF_QUEUE` lifecycle authority. The client cannot set owner, source, actor, authority, Queue state, or Order state. Queue admission does not change the Order's original MANUAL source. Direct ordinary OE-1 transitions to `QUEUED` remain denied by its frozen public service.

Admission requires an existing owner-bound `READY` Order, matching expected version if supplied, and no existing Queue Entry. The single transaction inserts a Queue Entry in `READY`, compare-and-swaps the Order from `READY` to `QUEUED`, and appends both the Order `STATE_TRANSITIONED` event and Queue `QUEUE_ADMITTED` event. Any failure rolls back all four writes. Migration `0026_oe3_queue_hardening` adds an explicit nullable `twf_orders.queue_entry_id` binding, state checks, and deferred composite foreign keys in both directions. At COMMIT, a Queue Entry can exist only for the matching bound Order/owner, and a `QUEUED` Order must point to its Queue Entry. The binding continues through future post-`QUEUED` states; `DRAFT` and `READY` must remain unbound. A composite Queue-event foreign key protects event linkage. Repeated admission returns the same entry. Competing admissions retry the entire atomic operation under SQLite contention; they cannot create a second entry or second transition. Typed concurrency errors are returned if contention cannot be resolved.

## Queue lifecycle and history

OE-3 activates only Queue `READY` and `HELD`. A versioned Hold changes `READY → HELD`; Release changes `HELD → READY`. Neither changes the Order's `QUEUED` state or submits anything. Version compare-and-swap rejects stale writes; transient SQLite contention retries the entire Hold/Release transaction before returning a typed retryable conflict. History appends `QUEUE_ADMITTED`, `QUEUE_HELD`, and `QUEUE_RELEASED` events with stable per-entry sequence and version, actor, reason where relevant, and UTC timestamp. Database triggers reject Queue event `UPDATE` and `DELETE` on both PostgreSQL and SQLite, including bulk statements. Following the [live PostgreSQL role cutover](TWF_OE3_LIVE_PRIVILEGE_CUTOVER_REPORT.md), the runtime role cannot own/disable/drop that trigger or its function; audit table runtime grants are SELECT/INSERT only. SQLite guarantees this on normal TWF-managed connections within a trusted-process/file-access boundary, not against a process with arbitrary writable database access. Normal append-only event insertion remains allowed. No ordinary event update/delete endpoint exists. Current Queue state and Order state are separate facts.

`BLOCKED`, `CANCELLED`, `EXPIRED`, `FAILED`, `SUBMITTING`, and `SENT` are not reachable OE-3 runtime states. Queue cancellation/removal and automatic expiry are deferred because frozen Order transitions and validity semantics do not authorize them. No invented risk, margin, funds, market-hours, or scheduling gate is represented by a Queue state.

## Owner isolation, ordering, and API

Every Queue query and mutation is scoped by the authenticated owner. A guessed ID for another owner is reported as not found. Operator list uses newest-first keyset pagination, 50 entries by default (maximum 100), and joins the linked Order in one query. The response has `items`, `next_cursor`, and `has_more`. Cursors bind owner, optional READY/HELD filter, admission timestamp, and Queue Entry UUID with a session-keyed signature; decoding, signature, shape, semantic types, timestamp, UUID, and scope are checked before querying. Invalid or mismatched cursors return `INVALID_CURSOR` (HTTP 400), including a correctly signed but semantically invalid cursor. The next page reads rows strictly older than the last visible key. New admissions appear on a refreshed first page, while state transitions can change membership between filtered pages; pagination is not a cross-page snapshot. Future execution FIFO remains ascending by `admitted_at`, then Queue Entry UUID, independent of this operator sort. Detail and history are separate owner-scoped lookups; history orders by sequence rather than timestamp alone.

Endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/twf-queue?limit=50&cursor=…&state=READY` | Owner-scoped newest-first keyset page; cursor and state are optional |
| GET | `/api/v1/twf-queue/{queue_entry_id}` | Entry and exact linked Order projection |
| GET | `/api/v1/twf-queue/by-order/{twf_order_id}` | Existing admission for an Order |
| GET | `/api/v1/twf-queue/{queue_entry_id}/history` | Append-only Queue history |
| POST | `/api/v1/twf-queue/admit` | Explicit atomic admission |
| POST | `/api/v1/twf-queue/{queue_entry_id}/hold` | Versioned manual Hold |
| POST | `/api/v1/twf-queue/{queue_entry_id}/release` | Versioned manual Release |

Mutation endpoints enforce the existing origin check. They expose no generic state PATCH or broker operation.

## Workspace and persistence

The top-level **Trade** workspace has deep-linked **Orders | Execution Queue | Positions** tabs at `/trade/orders`, `/trade/queue`, and `/trade/positions`; legacy `/orders` and `/positions` redirect there. One shared Instrument account selector and the existing OE-2 New Order ticket remain available from all three tabs. READY Order rows/details offer Add to Queue with a confirmation showing exact Order identity and terms. QUEUED Orders offer View in Queue. The Queue view shows compact status cards, a dense newest-first operator table, linked Order terms, state, age, Hold/Release, detail, and history. Admission does not submit to the broker. The Positions tab displays the existing selected-account **read-only Broker positions snapshot** and totals; it is not an OE-8 TWF-managed Position lifecycle. Service-health diagnostics remain available outside Trade; the Trade surface omits the engineering context and console panels.

Alembic `0025_twf_queue` adds `twf_queue_entries` and `twf_queue_events`, keys, owner-preserving foreign keys, one-entry-per-order uniqueness, positive versions, active-state check, and owner/FIFO/history indexes. Migration `0026_oe3_queue_hardening` adds the bidirectional binding and immutable event guards without changing 0025. Migration `0027_oe3_order_event_audit` makes TWF Order events append-only with UPDATE/DELETE triggers on PostgreSQL and SQLite-managed connections; PostgreSQL runtime receives SELECT/INSERT only. The migrator owns the PostgreSQL guards, while SQLite remains within the documented trusted-process/file-access boundary. SQLite uses a transaction-scoped table rebuild on a migration connection with foreign keys temporarily disabled and checked before completion; perform schema migration with the API stopped. Both 0026 upgrade and downgrade are tested on disposable PostgreSQL and SQLite. UTC timestamps are localized only at display time.

## Deferred and version history

OE-4 will design the Queue-to-Broker V2 bridge, worker claim/lease, submission idempotency, exact broker handoff and response semantics. Risk/margin checks, scheduling, automatic expiry, Queue cancellation/removal, external intake, and global idempotency across distinct OE-2 previews are not part of OE-3. Queue admission idempotency is per TWF Order only. Any later additions must preserve frozen OE-1/OE-2 boundaries and the atomic admission invariant.

- **V1 — OE-3 (15 October 2026):** explicit durable admission, owner-scoped READY/HELD lifecycle, FIFO/history/API and Queue visibility. Pending independent review; not frozen.
- **V1.1 — Trade UX amendment (15 October 2026):** consolidated Orders, Execution Queue and read-only account Positions under Trade, with persistent account/New Order controls and compatible legacy redirects. Queue and Order domain semantics unchanged.

- **V1.2 — OE-3 hardening (15 October 2026):** commit-time Order/Queue coherence, database-immutable Queue history, and owner-scoped newest-first keyset operator pagination. Pending independent review; not frozen.

- **V1.3 — privilege/cursor remediation (15 October 2026):** PostgreSQL migrator/runtime privilege split, truthful SQLite trusted-process boundary, and typed malformed-cursor rejection. Pending focused re-review; not frozen.

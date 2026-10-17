# TradingWorkFlow (TWF)

TradingWorkFlow is a trader-facing web application for market scanning,
discovery, watchlists, market intelligence, and governed broker workflows. It
keeps discovery separate from trading authority: a scan can identify and explain
an opportunity, but it cannot silently turn that result into a trade.

> **Execution rule:** No TWF subsystem may initiate a broker order except through
> the governed TWF execution path.

**Current active program: OE — TWF Order & Execution Foundation.** The planned
Opportunity/Discovery work O6–O13 is deferred, not cancelled, while TWF builds the
Order → Queue → Broker foundation. Existing Broker V2 preview and execution
controls remain operational during that transition.

## Where We Are Now

TWF has moved beyond foundation-only development. The operational product now
includes the application shell, the accepted Broker workspace, persistent
Watchlists, Equity/Index and Options/Futures Scanners, real Dhan market data,
system-global NSE instrument metadata, deterministic Market Context ranking,
and Dynamic Sector Context V1. Options O1/O2/O3, the O4 Options Scanner, and the
O5 Futures Scanner have implemented foundations; the live validation gates noted
below remain open.

**OE is the current implementation priority.** It will establish a canonical
TWF Order, durable TWF Queue, governed Broker V2 submission, reconciliation,
and first-class Trade workspace. The manual Orders entry/list/detail path is
accepted and frozen in OE-2. OE-3 implements explicit, durable Queue admission
and operator visibility; Queue-to-Broker handoff remains future work. O6–O13
and further Scanner/Market Context expansion remain planned but are not the next
implementation sequence. Broader
user validation remains open for recent Scanner, Watchlist, metadata, and
Market Context work; Sprint 2 as a whole is not accepted or frozen.

## Current Product Status

| Area                          | Current status                            | Product truth                                                                                                                                  |
| ----------------------------- | ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| TWF-0 / TWF-1 foundations     | **ACCEPTED / FROZEN**                     | Architecture, repository, API, database, authentication, settings, and service-client foundations                                              |
| Broker V1 / V2                | **ACCEPTED / FROZEN**                     | Read-only broker data plus governed manual order preview, intent, submission, and reconciliation                                               |
| Options O1                    | **IMPLEMENTED / USER VALIDATION**         | Provider-neutral option identity plus Zerodha single-leg Broker V2 preview and execution foundation                                            |
| Options O2                    | **IMPLEMENTED**                           | Shared bounded canonical chain service, Dhan adapter, and exact Broker V2 preview handoff                                                      |
| Options O3                    | **IMPLEMENTED / USER VALIDATION PENDING** | Responsive option-chain workspace, canonical contract selection and existing Broker V2 preview                                                 |
| Application shell             | **IMPLEMENTED**                           | Shared responsive header, grouped navigation, theme support, and preserved product routes                                                      |
| Watchlists                    | **IMPLEMENTED / USER VALIDATION**         | Persistent custom lists, read-only built-ins, Dhan enrichment, metadata, charts, and broker handoff                                            |
| Scanner V2                    | **IMPLEMENTED / USER VALIDATION**         | Typed daily technical scanning, saved/history workflows, evidence, ranking, metadata, and Watchlist handoff                                    |
| Discovery                     | **IMPLEMENTED / USER VALIDATION**         | Downstream candidate interpretation and temporal tracking, separate from Scanner execution                                                     |
| Dhan market data              | **IMPLEMENTED / LIVE PATH VALIDATED**     | Authoritative real quotes and bounded completed-bar OHLCV; no silent synthetic fallback                                                        |
| Instrument Metadata harvester | **IMPLEMENTED**                           | Project-owned offline NSE metadata maintenance workflow                                                                                        |
| Runtime Instrument Metadata   | **IMPLEMENTED**                           | System-global database, importer, service, API, and bounded Scanner/Watchlist lookup                                                           |
| Deterministic Market Context  | **IMPLEMENTED / FURTHER WORK DEFERRED**   | Explainable ranking that preserves technical match truth                                                                                       |
| Dynamic Sector Context V1     | **IMPLEMENTED / USER VALIDATION**         | Metadata-led sector identity with live Dhan benchmark analysis                                                                                 |
| Broad-market regime           | **PLANNED / DEFERRED**                    | Planned Market Context dimension, deferred during OE                                                                                           |
| Market breadth                | **PLANNED / DEFERRED**                    | Planned Market Context dimension, deferred during OE                                                                                           |
| Institutional flows / events  | **PARTIAL**                               | Available evidence is normalized without inventing unavailable history or sentiment                                                            |
| Scanner LLM narrative         | **PLANNED / DEFERRED / OPTIONAL**         | Future natural-language synthesis only; deterministic scores remain authoritative                                                              |
| Derivatives Scanner O4        | **IMPLEMENTED / USER VALIDATION PENDING** | Bounded single-leg NSE options scanning, transparent Intraday/Positional templates, and exact O1/O3 handoffs                                   |
| Derivatives Scanner O5        | **IMPLEMENTED / LIVE VALIDATION PENDING** | Exact NSE FUTSTK/FUTIDX Dhan quote scanning, explicit Futures filters/templates, archived evidence, and guarded Broker V2 preview              |
| OE — TWF Order / Queue        | **OE-1/2 ACCEPTED / FROZEN; OE-3 HARDENED / REVIEW** | Manual Orders intake stops at READY; explicit OE-3 Queue admission atomically creates one entry and moves the Order to QUEUED. Broker bridge is absent |
| Opportunity O6–O13            | **PLANNED / DEFERRED**                    | Analytics, Discovery, context, monitoring, and execution handoff follow the OE foundation                                                      |

The accepted Broker capability is TWF's execution substrate. It is not intended
to recreate a complete broker terminal.

## Product Surfaces

### Brokers

The Broker workspace currently provides accepted Zerodha-backed account views
and Broker V2 manual trading under explicit preview and confirmation. Its existing
New Order flow remains available until the OE migration is implemented. Durable intent,
idempotency, reconciliation, ownership, and audit controls remain the authority
for order submission. Options O1 extends this same path with provider-neutral
contract identity, exact Zerodha mapping, lot validation, MARKET/LIMIT option
preview, risk information, and explicit confirmation. It does not implement a
multi-leg strategy engine. The target Broker workspace is the faithful broker-truth
and reconciliation surface: connection/authentication, funds, holdings, actual
broker orders and positions, broker errors, instruments/metadata, and
refresh/connect/disconnect. Normal TWF trade initiation will move to TWF Orders;
Broker is not yet fully read-only. See the
[Broker V2 manual-order foundation](docs/TWF_BROKER_V2_MANUAL_ORDER_ENTRY.md) and
[Options architecture](docs/TWF_OPTIONS_ARCHITECTURE.md).

### Watchlists

Watchlists are a substantial, persistent workspace:

- owner-scoped custom lists and centrally managed read-only system lists;
- `EQ`, `IDX`, `FUT`, and `OPT` instrument support where exact canonical
  metadata is available;
- Dhan quote, daily technical, change, volume, and chart enrichment;
- system-global Sector and instrument metadata;
- selected-instrument analysis and governed Broker V2 preview;
- CSV import/export, notes, activity, trash, restore, and permanent-delete
  workflows.

Built-in lists cover the enabled official Nifty universes and TWF-defined dynamic F&O
Liquidity 50/100/200 universes, which show explicit collection/readiness status
and become available after three trustworthy completed sessions. Details and validation boundaries are in the
[Watchlists architecture](docs/TWF_WATCHLIST_ARCHITECTURE.md).

### Scanner V2

Scanner V2 is operational for Equity/Index daily technical scans. It provides:

- Custom and Watchlist universes; Index, Sector, and Market universe contracts
  are present, while their feeds are not yet configured;
- typed filters, comparison-aware value fields, active filter chips, templates,
  saved scans, and immutable recent-scan history;
- compact match reasons with detailed, archived evidence;
- deterministic Market Context ranking and explicit context coverage;
- system-global metadata, including Sector in results and richer details;
- selected-result handoff to Watchlists; and
- a current validation limit of 20 instruments per scan.

The Equity/Index scanner, bounded O4 single-leg Options Scanner, and O5 Futures
Scanner are implemented. O4/O5 live acceptance remains pending; current result
handoffs use Broker V2 controls while OE prepares the common TWF Order entry.
See the
[Scanner V2 architecture and validation record](docs/TWF_SCANNER_V2_ARCHITECTURE.md).

### Discovery

Scanner and Discovery have different responsibilities:

```text
Scanner    = deterministic universe evaluation, technical match, and ranking
Discovery  = downstream candidate interpretation, evidence, and temporal tracking
```

Discovery keeps immutable observations and candidate history without gaining
trading authority. Optional explanation boundaries exist, but unimplemented LLM
synthesis is not presented as an operational feature.

## Market Data and Instrument Metadata

### Dhan

Dhan is the authoritative real market-data provider for Scanner and Watchlist
market evidence. The runtime resolves canonical instruments, reads bounded quotes
or completed-bar OHLCV, normalizes provider responses, and preserves provenance.
A real-data request that fails remains a typed failure or unavailable result; it
does not fall back silently to deterministic fixtures.

### Instrument Metadata

The project-owned metadata harvester maintains an approximately 2,600-instrument
NSE universe with sector, industry, market cap, relative cap category, TWF
analytical tier, context benchmark, provenance, and observation time. The normal
maintenance cadence is monthly:

```text
offline NSE/Yahoo-assisted harvest
  → review generated artifacts
  → import accepted artifact
  → system-global runtime metadata
  → Scanner and Watchlist bounded lookup
```

Yahoo/NSE harvesting is an offline maintenance activity, not a Scanner or
Watchlist runtime dependency. Runtime consumers use the imported database through
the metadata service and API. See the
[Data Architecture](docs/TWF_DATA_ARCHITECTURE.md) and the
[metadata utility guide](tools/market_metadata/README.md).

## Current Scanner Analysis Pipeline

```text
Universe
  ↓
Typed technical filters
  ↓
Deterministic technical MATCH
  ↓
System-global Instrument Metadata
  ↓
Market Context
  ├─ Sector Context .............. IMPLEMENTED
  ├─ India VIX ................... IMPLEMENTED when evidence is available
  ├─ Institutional flows ......... PARTIAL
  ├─ Broad-market regime ......... PLANNED / DEFERRED
  ├─ Market breadth .............. PLANNED / DEFERRED
  └─ Events / news ............... PARTIAL
  ↓
Explainable relevance ranking
  ↓
Reason + detailed Evidence
  ↓
Watchlist handoff / Discovery tracking
```

**Technical match and ranking are separate.** In Ranking mode, Market Context
cannot rewrite technical match truth. A candidate can match its technical rules
and rank lower when the available context is adverse. Context used as a hard
filter must be selected explicitly.

### Market Context maturity

| Dimension           | Status                 | Current behavior                                                                            |
| ------------------- | ---------------------- | ------------------------------------------------------------------------------------------- |
| Sector Context      | **IMPLEMENTED**        | Dynamic benchmark evidence and deterministic, direction-aware contribution                  |
| India VIX           | **IMPLEMENTED**        | Normalized volatility context when provider evidence is available                           |
| Institutional flows | **PARTIAL**            | Current flow evidence may contribute; unsupported rolling velocity/streak stays unavailable |
| Broad-market regime | **PLANNED / DEFERRED** | Deterministic regime model remains planned after the OE foundation                          |
| Market breadth      | **PLANNED / DEFERRED** | Breadth model and evidence are not yet implemented                                          |
| Events / news       | **PARTIAL**            | Explicit provider evidence is retained; missing sentiment or scope is not inferred          |

TapTide is the optional provider-neutral market-intelligence adapter. Its
owner-scoped MCP connection, bounded allowlisted tools, normalization, and failure
isolation are implemented, and selected live technical/reference paths have been
exercised. TapTide context can enrich ranking but cannot own Dhan OHLCV, change
technical matches, block Dhan scanning, or authorize a trade.

### Dynamic Sector Context V1

Dynamic Sector Context derives the candidate's sector and provider-neutral context
benchmark from Instrument Metadata, then resolves that benchmark through the Dhan
alias layer and reads Dhan OHLCV. It produces:

- benchmark trend and 1-day, 5-day, and 20-day returns;
- sector relative strength versus NIFTY;
- candidate relative strength versus its sector benchmark;
- a deterministic rotation state;
- direction-aware ranking contribution; and
- explainable evidence with provenance and freshness.

All 11 currently configured benchmark families resolve through the Dhan alias
layer. Provider security identifiers remain adapter details and are not part of
the product contract.

### Optional LLM role

Deterministic scanning, evidence, and relevance ranking work without an LLM. A
future optional LLM may synthesize stored evidence into natural language, but it
may not change the deterministic match or score. Any configured LLM remains
subject to TWF's one-active-LLM policy.

## Current Priorities

1. **Validate OE-3 — TWF Queue** through user and independent adversarial review
   of explicit READY → QUEUED admission, Hold/Release, owner boundaries and
   durable audit. OE-1 and OE-2 are accepted and frozen.
2. Preserve existing Broker V2, Watchlist, and Scanner functionality while their
   normal trade initiation moves toward TWF Orders. Queue admission is implemented;
   Queue-to-Broker submission, workers, and reconciliation are not.
3. Complete outstanding authenticated O3/O4/O5 live validation and broader
   Watchlist/Scanner/metadata acceptance without automated test orders. These
   are validation gates, not a competing implementation priority.
4. Resume planned O6–O13 Opportunity/Discovery work after the OE foundation is
   stable. Broad-market regime, breadth, richer flow/event context, and optional
   LLM explanation are included in that later context program.

Final Sprint-2 acceptance and freeze still require documented validation,
adversarial review, and hardening gates.

## Active Program — TWF Order & Execution Foundation (OE)

TWF is building a governed trading workflow above the broker. **No TWF
subsystem may initiate a broker order except through the governed TWF execution
path.** Manual entry, Watchlists, Scanner, Discovery, Strategy, future agents,
and external integrations must create or request a TWF Order rather than submit
a broker order directly:

```text
Manual / Watchlist / Scanner / Discovery / Strategy / Agent / external intake
  → TWF Order
  → TWF Queue
  → governed execution
  → Broker V2
  → actual broker
  → broker truth and reconciliation
```

Today, Broker, Watchlist, and Scanner order entry already converges on the
Broker V2 preview, intent, submission, and reconciliation machinery. OE moves
the shared governed entry point one level upward; the diagram is the **target
architecture**. OE-1 provides the non-executional TWF Order domain, OE-2 the
manual READY intake, and OE-3 the non-executing TWF Queue. The Queue-to-Broker
runtime bridge does not yet exist. Broker V2 remains the broker-facing
submission boundary. Broker truth, including
rejections and fills, remains authoritative; TWF must not claim a fill before
broker confirmation.

### Broker boundary and existing New Order reuse

The target Broker workspace is primarily a faithful reflection of the external
broker: connections and authentication, funds, holdings, actual broker orders
and positions, rejections/errors, reconciliation, instruments/metadata, and
refresh/connect/disconnect. Normal TWF trade initiation moves to the TWF Orders
workspace. The current Broker New Order flow is still operational; Broker is
**not** already read-only.

The proven `Select Instrument → Ticket → Preview → Result` experience is the
starting point, not a flow to discard or redesign wholesale. OE-2 reuses
it for `TWF New Order → TWF Order → TWF Queue → Broker V2 → broker
result/reconciliation`. Foundational routing and state integrity come
before a richer ticket.

A TWF Order is intended to grow beyond a broker-native order. Later capabilities
may include Equity/Futures/Options, exact identity and provenance, entry intent,
SL/TP, max profit/loss, trailing SL, conditional or timed execution, scale-in/out,
hedges, parent/child relationships, and authority mode. These are **future
increments**, not prerequisites to stabilizing the basic Order → Queue → Broker
path.

### Durable audit and external intake

TWF-generated and TWF-managed trades require durable operational and audit
records. As OE develops, capture origin, owner and actor/subsystem, TWF Order ID,
Queue transitions and authority decisions, Broker V2 submission/response IDs,
fills, amendments/cancellations, reconciliation, errors, timestamps, and
referenced evidence where applicable. This supports debugging, governance,
restart/recovery, and later performance analysis.

Future TradingView webhooks, strategy services, external applications, and
agents may submit **TWF Order requests** to the governed intake. They must never
submit directly to Broker V2; the same TWF Order → Queue → governed execution
boundary applies. Historical TradingView market-data integration remains
decommissioned as described below.

### OE implementation sequence

**OE-1 — TWF Order Domain & Lifecycle Foundation: ACCEPTED / FROZEN (14 October
2026).** Independent review, F1–F8 hardening, and final acceptance are complete.
The freeze covers canonical broker-neutral Order contracts, exact instrument
identity and owner/source trust boundaries, lifecycle and Queue/Broker authority
guards, optimistic concurrency, migration, persistence, and audit/history
semantics. OE-2, OE-3 and DB-1 are also **ACCEPTED / FROZEN**. OE-4 is now
implemented for independent review, with live execution disabled by default.
Queue policy affects only future admissions; every entry keeps its immutable
admission-time MANUAL/AUTO mode. See the [OE-4 bridge architecture](docs/TWF_OE4_QUEUE_BROKER_BRIDGE_ARCHITECTURE.md)
and [implementation evidence](docs/TWF_OE4_IMPLEMENTATION_REPORT.md).

1. **OE-1 — TWF Order Domain & Lifecycle Foundation (ACCEPTED / FROZEN).**
   Owner-scoped, broker-neutral Equity/Futures/Options orders have exact canonical
   UUID identity, typed MARKET/LIMIT requests, durable provenance, optimistic
   version checks and atomic lifecycle/audit history. New orders begin as DRAFT;
   ordinary callers cannot assert Queue or broker-truth states. No API, UI, Queue,
   broker submission or advanced SL/TP execution was added. See the
   [normative Order architecture](docs/TWF_Order_Domain_and_Lifecycle_Architecture.md).
2. **OE-2 — Existing New Order → TWF Order (ACCEPTED / FROZEN).** Trade →
   Orders reuses Select Instrument/Ticket/Preview, resolves canonical identity
   server-side, creates MANUAL TWF Orders, validates and stops at READY.
   Owner-scoped list/detail/history use OE-1 persistence. No Queue or broker
   submission occurs. See the [OE-2 architecture](docs/TWF_ORDERS_OE2_ARCHITECTURE.md).
3. **OE-3 — TWF Queue Foundation (ACCEPTED / FROZEN).** Explicit Add to Queue
   atomically creates one owner-bound entry and transitions a READY Order to
   QUEUED, with Order and Queue audit events. Queue entries support READY and
   HELD, newest-first operator pagination with preserved FIFO semantics,
   Hold/Release, and Trade → Execution Queue operator views.
   Trade also groups Orders and read-only account Positions with one persistent
   Instrument account selector and New Order action. This does not implement the
   future TWF-managed Position lifecycle. It makes no broker write calls. See the [OE-3 Queue architecture](docs/TWF_QUEUE_OE3_ARCHITECTURE.md) and [OE-3 hardening report](docs/TWF_OE3_HARDENING_REPORT.md).
4. **OE-4 — Queue → Broker V2 Bridge (READY FOR INDEPENDENT REVIEW).** Owner/account
   policy is snapshotted immutably at admission. MANUAL and AUTO share one
   dispatch service, exact-contract checks and a durable pre-I/O claim. AUTO
   selects persisted entry mode, never current policy. Ambiguity requires
   reconciliation without resending. Operator IDs supplement UUIDs.
   Live execution remains off until an explicit, separately accepted rollout.
5. **OE-5 — Broker Reconciliation.** Reconcile broker order IDs and accepted,
   rejected, open, partially filled, filled, cancelled, and broker-side changes.
   Broker confirmation remains final execution truth.
6. **OE-6 — TWF Orders Workspace expansion.** Expand the OE-2 manual Orders
   list/detail/history with active/queued/submitted and completed outcomes once
   Queue and Broker handoff are implemented.
7. **OE-7 — TWF Trading Audit / Logging Foundation.** Persist exact transitions
   and evidence across TWF Order, Queue, Broker submission and response, and
   reconciliation.
8. **OE-8 — TWF Positions Linkage.** Derive TWF Positions from executed TWF
   Orders or explicitly adopted broker positions. Add entry basis, remaining
   quantity, risk/SL/target/trailing state, thesis, authority, and broker
   reconciliation incrementally.
9. **OE-9 — TWF Alerts Linkage.** Attach Alerts to Orders, Queue, and Positions
   for waits, disconnects, rejection, partial/complete fill, expiry, conditions,
   thresholds, and broker/TWF mismatches.
10. **OE-10 — Advanced TWF Order Model.** After the basic path is stable, add
    SL/TP, max loss/profit, trailing SL, entry/time conditions, scale-in/out,
    hedges, parent/child or OCO-like relationships, authority mode, and
    Scanner/Discovery/Strategy provenance.
11. **OE-11 — External Order Intake.** Admit TradingView webhook, strategy,
    application, and agent requests only as governed TWF Orders/Queue entries;
    never as direct Broker V2 submissions.
12. **OE-12 — Acceptance / Hardening / Freeze.** Adversarially validate state
    transitions, durability, idempotency, disconnects, retries, reconciliation,
    authorization, logging, crash/restart recovery, and the external boundary
    before freezing the end-to-end path.

The OE-1 freeze itself does not implement TWF Queue. OE-3 adds Queue admission
and Hold/Release without workers or Queue → Broker V2 handoff. TWF
Positions/Alerts lifecycles, SL/TP automation, max profit/loss execution, webhook
execution, and a finalized create/intake idempotency policy remain future work.
The current Broker New Order flow remains operational. Carry forward these observations:

- Historical pre-DB-1 result (superseded by the DB-1 platform gate): live PostgreSQL validation was **NOT_RUN** because a test environment was
  unavailable; SQLite validation and offline PostgreSQL migration SQL are not
  substitutes for a live run.
- Repository-wide mypy retains pre-existing, unrelated errors in unchanged test
  files. OE-1 changed-source type checking passed.
- OE-2 binds Create to a short-lived server Preview and consumes each preview
  once, including concurrent replay. Broader create/intake idempotency across
  distinct previews and automated sources remains deferred. Define stable
  source-event keys and uniqueness scope before later automated intake (OE-11).
- OE-2 wires the existing New Order flow to the trusted server-side canonical
  instrument authority introduced by OE-1; final acceptance is complete.
- Future Watchlist, Scanner, Discovery, Strategy, Agent, and Webhook adapters
  must issue trusted owner-bound source/origin contexts with event validators.

## Pending Opportunity / Discovery Program — O6–O13 (deferred)

These phases remain valid planned work. They are intentionally **deferred, not
cancelled**, while OE establishes the governed Order → Queue → Broker path.
Their ordering and scope should be revalidated when resumed.

### O6 — Futures Analytics + Chart Handoff

Complete post-scan Futures analysis with richer exact-contract detail,
spot-versus-futures basis, OI/ΔOI history, trend and interpretation evidence, and
an exact Futures chart where supported. If only an underlying-spot chart is
available, label that fallback clearly. This does not add Scanner logic.

### O7 — Derivatives Analytics Convergence

Unify deeper Options/Futures analysis through a shared instrument-detail shell,
consistent evidence/history, contract metadata, and risk context, with navigation
from Scanner to Analytics to the governed TWF Order flow.

### O8 — Scanner → Discovery Integration

Promote qualified Equity, Options, and Futures Scanner outputs into
`DiscoveryCandidate` with the originating scan, exact predicates, resolved
instrument identity, evidence, timestamp, horizon, and provenance intact.

### O9 — Discovery / Live Opportunity Book V1

Maintain a candidate book across `QUALIFIED`, `STALE`, `DEFUNCT`, `EXPIRED`, and
`REJECTED` (or approved equivalents). Invalid opportunities may disappear and
reappear later only with fresh qualifying evidence.

### O10 — Market Intelligence + Context Fusion

Combine deterministic Scanner/Discovery facts with market regime, sector,
India VIX, macro/events, news/catalysts, commodities, rates/bonds, and policy
context. Preserve the boundary between measured facts and interpretation.

### O11 — LLM Level-0 Interpretation

An optional LLM may explain, summarize, surface conflicts/risks, and describe
conditions using grounded evidence. It must not invent market evidence,
initiate broker execution, or bypass the governed TWF path.

### O12 — Candidate Lifecycle + Monitoring

Track entry zone, invalidation, target progression, freshness, stale/expired
state, refresh triggers, and continued actionability.

### O13 — Execution Handoff / TradeMonitor Integration

Connect a qualified candidate to `TWF Order → authority/risk checks → TWF Queue
→ Broker V2 → broker reconciliation → TWF Position → ongoing supervision`.
Discovery never gains independent broker-submission authority.

## Current Runtime Architecture

```text
Dhan
  → canonical instruments + normalized quotes/OHLCV
  → Watchlists and Scanner V2

Offline metadata harvester
  → reviewed import artifact
  → system-global Instrument Metadata
  → Watchlists + Scanner + Dynamic Sector benchmark identity

TapTide / future MI providers
  → bounded optional MarketIntelligenceProvider claims
  → deterministic Market Context

Scanner match + context ranking
  → explainable evidence
  → Watchlist handoff / Discovery candidate tracking

Broker V2
  → equity/futures plus canonical single-leg option identity
  → explicit preview and confirmation
  → governed manual execution and reconciliation
```

Historical TradingView S2-3 work remains preserved in its acceptance and
hardening records, but TradingView is decommissioned from the active market-data
runtime. Existing provenance is immutable and is never relabelled as Dhan
evidence. The generic MCP foundation remains active for compatible
market-intelligence and future service providers.

## Accepted Foundations and Milestone History

Important accepted and frozen history remains unchanged:

```text
TWF-0 Product / Architecture Foundation             ACCEPTED / FROZEN
TWF-1 Application Foundation                        ACCEPTED / FROZEN
Broker Workspace Architecture v0.3                  ACCEPTED / TAGGED
Broker V1 real-broker read-only foundation          ACCEPTED / FROZEN
Broker V2 manual-trading foundation                 ACCEPTED / FROZEN
Options O1 extension                                 IMPLEMENTED / USER VALIDATION
Options O2 chain foundation                          IMPLEMENTED
Options O3 chain workspace                           IMPLEMENTED / USER VALIDATION PENDING
Scan & Discover architecture                        ACCEPTED
S2-1 domain contracts / synthetic foundation        ACCEPTED / FROZEN
S2-2 Internal Scanner V0                            ACCEPTED / FROZEN
S2-3 historical TradingView provider                ACCEPTED / FROZEN HISTORY
Sprint 2 current product                            USER VALIDATION / NOT FROZEN
```

Relevant repository tags include:

- `twf-0-architecture-baseline`
- `twf-1-application-foundation`
- `twf-broker-workspace-architecture-v0.3`
- `twf-broker-v1`
- `twf-broker-v2`
- `twf-scan-discover-architecture-v0.2`
- `twf-s2-1-discovery-foundation`
- `twf-s2-2-internal-scanner-v0`
- `twf-s2-3-tradingview-mcp-provider`
- `twf-s2-scan-discover-user-validation-ready`

The last tag is a validation-ready checkpoint, not final Sprint-2 acceptance.
Historical acceptance documents remain historical unless a later authority
explicitly supersedes them.

## Database authority (DB-1)

**PostgreSQL is now the primary/default authoritative runtime database. SQLite is
explicit fallback / recovery snapshot / lightweight mode only.** There is no
automatic PostgreSQL → SQLite failover and no dual-write. An unavailable primary
fails closed. `TWF_DATABASE_URL` is required; startup checks connectivity and the
Alembic head before serving requests. `/ready` reports the active backend safely.

DB-1 runs before OE-4. OE-1/OE-2 domain semantics remain frozen; the pending OE-3
coherence, history immutability, and pagination findings remain a separate task.
No Queue worker or Broker handoff is added by this database migration.

- [Database architecture](docs/TWF_DATABASE_ARCHITECTURE.md)
- [SQLite → PostgreSQL migration and recovery runbook](docs/TWF_SQLITE_TO_POSTGRES_MIGRATION_RUNBOOK.md)
- [DB-1 implementation evidence and review status](docs/TWF_DB1_IMPLEMENTATION_REPORT.md)

## Local Development

Prerequisites: Python 3.12+, Node.js 20.19+, 22.13+, or 24+, and PostgreSQL 16
(server tools are also needed for the isolated primary test gate).

Start PostgreSQL using the [database runbook](docs/TWF_SQLITE_TO_POSTGRES_MIGRATION_RUNBOOK.md).
Configure a private `apps/api/.env` from `.env.example` with the PostgreSQL
application URL and existing credential master key before running the commands
below. Existing SQLite installations must follow the verified backup/import
procedure before switching their runtime URL.

```bash
# Terminal 1, from the repository root
cd apps/api
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps -e .
cd ../..
# First setup only, with operator-only URLs/passwords injected privately:
apps/api/.venv/bin/python tools/postgres_roles.py provision
apps/api/.venv/bin/python tools/postgres_roles.py prepare-fresh
tools/migrate-postgres.sh
apps/api/.venv/bin/python tools/postgres_roles.py harden
cd apps/api
TWF_ENVIRONMENT=development .venv/bin/python -m twf.bootstrap \
  --username trader --display-name "Development Trader"
# First setup only: enter your own password at the hidden prompt.
.venv/bin/uvicorn twf.main:create_app --factory --reload --no-access-log

# Terminal 2, from the repository root
cd apps/web
npm ci
npm run dev
```

Web: <http://localhost:3000>. API: <http://localhost:8000/health>,
<http://localhost:8000/ready>, <http://localhost:8000/api/v1/status>,
<http://localhost:8000/api/v1/meta>, and <http://localhost:8000/docs>.

`TWF_DATABASE_URL` is required and normally points to PostgreSQL. Run migrations
explicitly with `tools/migrate-postgres.sh` under separate `twf_migrator` credentials; API startup does
not run migrations. Compose provides a persistent PostgreSQL service and an opt-in `ops` migration
service. The API receives only `twf_app` credentials; provision and verify roles
with `tools/postgres_roles.py` before serving traffic. Its runtime DELETE policy
is default-deny with 11 explicitly allowlisted cleanup tables; TWF Order and Queue
events are append-only. Reapply and verify grants after each new migration. Keep
administrator and migrator secrets outside the API environment. Native URLs use loopback port 55432; container API URLs use
`postgres:5432`. Select SQLite only with an explicit fallback URL.

Primary backend gate: `tools/test-postgres.sh -q` (private disposable PostgreSQL,
per-test isolation, no developer data). SQLite compatibility: from `apps/api`, run
`.venv/bin/python -m pytest --db-backend=sqlite -q`. PostgreSQL-backed browser smoke
uses `tools/test-postgres.sh --browser ...`. Back up the authority with `pg_dump`
and rehearse `pg_restore`; the retained SQLite snapshot is not a current replica.

See the
[Ubuntu/Linux local development guide](docs/TWF_LOCAL_DEVELOPMENT_SETUP_LINUX.md)
for installation, validation, shutdown, and troubleshooting.

## Start Here

1. [Options Architecture](docs/TWF_OPTIONS_ARCHITECTURE.md)
2. [Scanner V2 Architecture](docs/TWF_SCANNER_V2_ARCHITECTURE.md)
3. [Watchlists Architecture](docs/TWF_WATCHLIST_ARCHITECTURE.md)
4. [Data Architecture](docs/TWF_DATA_ARCHITECTURE.md)
5. [Instrument Metadata Utility](tools/market_metadata/README.md)
6. [Scan & Discover Architecture](docs/TWF_SCAN_AND_DISCOVER_ARCHITECTURE.md)
7. [Integrated Sprint-2 Implementation](docs/TWF_SPRINT2_SCAN_DISCOVER_IMPLEMENTATION.md)
8. [Sprint-2 User Validation Plan](docs/TWF_SPRINT2_USER_VALIDATION_PLAN.md)
9. [Documentation Index](docs/TWF_DOCUMENTATION_INDEX.md)

Additional authority:

- [Product Vision and System Architecture](docs/TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md)
- [Broker Workspace Architecture](docs/TWF_BROKER_WORKSPACE_ARCHITECTURE.md)
- [Market Data Provider Architecture](docs/TWF_MARKET_DATA_PROVIDER_ARCHITECTURE.md)
- [Market Intelligence Provider Architecture](docs/TWF_MARKET_INTELLIGENCE_PROVIDER_ARCHITECTURE.md)
- [Generic MCP Connection and Authentication Foundation](docs/TWF_S2_3A_GENERIC_MCP_PROVIDER_CONNECTION_AUTH_FOUNDATION.md)
- [Security and Authentication Architecture](docs/TWF_SECURITY_AUTH_ARCHITECTURE.md)
- [Repository and Engineering Standards](docs/TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.md)
- [Sprint-2 Hardening Register](docs/TWF_SPRINT2_HARDENING_REGISTER.md)

Markdown files are the normative repository architecture, planning, and
acceptance records. DOCX files are polished reference companions unless a document
explicitly states otherwise. The
[Documentation Index](docs/TWF_DOCUMENTATION_INDEX.md) records authority and
companion relationships.

## Documentation Maintenance Rule

When a milestone or target changes state:

1. update its governing architecture, implementation, or acceptance record;
2. update the roadmap when sequencing or status changes;
3. update the documentation index when authority or inventory changes;
4. update this README's current-state map; and
5. preserve historical records and distinguish them from current runtime truth.

Documentation revision: **2026-10-14**.

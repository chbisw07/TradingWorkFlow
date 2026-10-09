# TradingWorkFlow (TWF)

TradingWorkFlow is a trader-facing web application for market scanning,
discovery, watchlists, market intelligence, and governed broker workflows. It
keeps discovery separate from trading authority: a scan can identify and explain
an opportunity, but it cannot silently turn that result into a trade.

## Where We Are Now

TWF has moved beyond foundation-only development. The operational product now
includes the application shell, the accepted Broker workspace, persistent
Watchlists, Scanner V2, real Dhan market data, system-global NSE instrument
metadata, deterministic Market Context ranking, and Dynamic Sector Context V1.
Options O1 is implemented on the accepted Broker V2 execution substrate. Options O2
canonical chain service is implemented. O3 adds the Options Analytics chain workspace
and exact Broker V2 ticket/preview handoff; user validation and authenticated live
chain acceptance remain pending.

The current focus is Scanner ranking quality. Broad-market regime and market
breadth are next, followed by richer flow and event context. Recent Scanner,
Watchlist, metadata, and Market Context work is implemented and awaiting broader
user validation; Sprint 2 as a whole is not accepted or frozen.

## Current Product Status

| Area                          | Current status                        | Product truth                                                                                               |
| ----------------------------- | ------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| TWF-0 / TWF-1 foundations     | **ACCEPTED / FROZEN**                 | Architecture, repository, API, database, authentication, settings, and service-client foundations           |
| Broker V1 / V2                | **ACCEPTED / FROZEN**                 | Read-only broker data plus governed manual order preview, intent, submission, and reconciliation            |
| Options O1                    | **IMPLEMENTED / USER VALIDATION**                | Provider-neutral option identity plus Zerodha single-leg Broker V2 preview and execution foundation         |
| Options O2                    | **IMPLEMENTED**                | Shared bounded canonical chain service, Dhan adapter, and exact Broker V2 preview handoff                  |
| Options O3                    | **IMPLEMENTED / USER VALIDATION PENDING** | Responsive option-chain workspace, canonical contract selection and existing Broker V2 preview |
| Application shell             | **IMPLEMENTED**                       | Shared responsive header, grouped navigation, theme support, and preserved product routes                   |
| Watchlists                    | **IMPLEMENTED / USER VALIDATION**     | Persistent custom lists, read-only built-ins, Dhan enrichment, metadata, charts, and broker handoff         |
| Scanner V2                    | **IMPLEMENTED / USER VALIDATION**     | Typed daily technical scanning, saved/history workflows, evidence, ranking, metadata, and Watchlist handoff |
| Discovery                     | **IMPLEMENTED / USER VALIDATION**     | Downstream candidate interpretation and temporal tracking, separate from Scanner execution                  |
| Dhan market data              | **IMPLEMENTED / LIVE PATH VALIDATED** | Authoritative real quotes and bounded completed-bar OHLCV; no silent synthetic fallback                     |
| Instrument Metadata harvester | **IMPLEMENTED**                       | Project-owned offline NSE metadata maintenance workflow                                                     |
| Runtime Instrument Metadata   | **IMPLEMENTED**                       | System-global database, importer, service, API, and bounded Scanner/Watchlist lookup                        |
| Deterministic Market Context  | **IMPLEMENTED / ACTIVE DEVELOPMENT**  | Explainable ranking that preserves technical match truth                                                    |
| Dynamic Sector Context V1     | **IMPLEMENTED / USER VALIDATION**     | Metadata-led sector identity with live Dhan benchmark analysis                                              |
| Broad-market regime           | **NEXT**                              | Planned deterministic Market Context dimension                                                              |
| Market breadth                | **NEXT**                              | Planned deterministic Market Context dimension                                                              |
| Institutional flows / events  | **PARTIAL**                           | Available evidence is normalized without inventing unavailable history or sentiment                         |
| Scanner LLM narrative         | **PLANNED / OPTIONAL**                | Future natural-language synthesis only; deterministic scores remain authoritative                           |
| Derivatives Scanner           | **PLANNED**                           | Product shell only; not an implemented scanner                                                              |

The accepted Broker capability is TWF's execution substrate. It is not intended
to recreate a complete broker terminal.

## Product Surfaces

### Brokers

The Broker workspace provides accepted Zerodha-backed account views and Broker V2
manual trading under explicit preview and confirmation. Durable intent,
idempotency, reconciliation, ownership, and audit controls remain the authority
for order submission. Options O1 extends this same path with provider-neutral
contract identity, exact Zerodha mapping, lot validation, MARKET/LIMIT option
preview, risk information, and explicit confirmation. It does not implement a
Derivatives Scanner or multi-leg strategies. See the
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

Built-in lists currently cover the enabled official Nifty universes. F&O 50 and
F&O 100 remain disabled while their eligibility definition is pending. Details
and validation boundaries are in the
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

The Equity/Index scanner is implemented. The Derivatives Scanner remains a
future-facing shell. See the
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
  ├─ Broad-market regime ......... NEXT
  ├─ Market breadth .............. NEXT
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

| Dimension           | Status          | Current behavior                                                                            |
| ------------------- | --------------- | ------------------------------------------------------------------------------------------- |
| Sector Context      | **IMPLEMENTED** | Dynamic benchmark evidence and deterministic, direction-aware contribution                  |
| India VIX           | **IMPLEMENTED** | Normalized volatility context when provider evidence is available                           |
| Institutional flows | **PARTIAL**     | Current flow evidence may contribute; unsupported rolling velocity/streak stays unavailable |
| Broad-market regime | **NEXT**        | Deterministic regime model is the next implementation priority                              |
| Market breadth      | **NEXT**        | Breadth model and evidence are not yet implemented                                          |
| Events / news       | **PARTIAL**     | Explicit provider evidence is retained; missing sentiment or scope is not inferred          |

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

1. Validate Options O3 authenticated live chains and exact Broker V2 preview through the running application, without automated live orders.
2. Implement deterministic broad-market regime.
3. Implement market breadth.
4. Continue Market Context quality, coverage, and validation improvements.
5. Deepen institutional-flow and event/news context where source contracts support
   it.
6. Add optional evidence-bound LLM narrative synthesis.
7. Implement the Derivatives Scanner after its contracts are approved.
8. Evolve Discovery without collapsing its boundary with Scanner.

Broader user validation remains open for recent Watchlist, Scanner V2, metadata,
and Dynamic Sector work. Final Sprint-2 acceptance and freeze require the
documented validation, adversarial review, and hardening gates.

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

## Local Development

Prerequisites: Python 3.12+ and Node.js 20.19+, 22.13+, or 24+.

```bash
# Terminal 1, from the repository root
cd apps/api
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/alembic upgrade head
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

`TWF_DATABASE_URL` defaults to local SQLite. PostgreSQL uses an externally
injected `postgresql+psycopg://` URL. Run migrations explicitly from `apps/api`
with `.venv/bin/alembic upgrade head`; API startup does not run production
migrations. For containers, run `docker compose up --build` from the repository
root.

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

Documentation revision: **2026-10-09**.

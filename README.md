# TradingWorkFlow (TWF)

TradingWorkFlow is a trader-facing web application that brings market scanning,
discovery, market intelligence, broker workflows, optional LLM explanations, and
future trade-management services into one coherent workspace.

The product keeps discovery separate from trading authority. Scan & Discover can
identify and explain a `DiscoveryCandidate`; it cannot place an order or silently
promote that candidate into an executable trade.

## Current Project Status

```text
TWF-0  Product / Architecture Foundation                ✅ ACCEPTED / FROZEN
TWF-1  Application Foundation                           ✅ ACCEPTED / FROZEN

Broker Workspace Architecture v0.3                      ✅ ACCEPTED / TAGGED
├── Broker V1 — real-broker read-only foundation        ✅ ACCEPTED / FROZEN
└── Broker V2 — manual-trading foundation               ✅ ACCEPTED / FROZEN

Scan & Discover architecture                            ✅ ACCEPTED
├── S2-0  Architecture / implementation readiness       ✅ ACCEPTED
├── S2-1  Domain contracts / synthetic providers        ✅ ACCEPTED / FROZEN
├── S2-2  Internal Scanner V0                           ✅ ACCEPTED / FROZEN
├── S2-3A Generic MCP connection/authentication         ✅ INTEGRATED
├── Historical TradingView S2-3                         ✅ ACCEPTED / FROZEN WITH
│                                                          DEFERRED HARDENING;
│                                                          DECOMMISSIONED AT RUNTIME
├── Current real market-data path — Dhan                ▶ IMPLEMENTED / LIVE PATH
│                                                          VALIDATED
├── S2-4 through S2-7                                   ✅ IMPLEMENTED
├── S2-8 internal implementation validation             ✅ COMPLETE
├── Scan-driven temporal-state implementation           ✅ IMPLEMENTED; ACCEPTANCE
│                                                          STILL PENDING
└── Sprint 2 overall                                    ▶ USER VALIDATION IN PROGRESS;
                                                           NOT ACCEPTED / FROZEN
```

The corresponding repository tags are `twf-0-architecture-baseline`,
`twf-1-application-foundation`, `twf-broker-workspace-architecture-v0.3`,
`twf-broker-v1`, `twf-broker-v2`,
`twf-scan-discover-architecture-v0.2`,
`twf-s2-1-discovery-foundation`, `twf-s2-2-internal-scanner-v0`, and the
historical `twf-s2-3-tradingview-mcp-provider`. The tag
`twf-s2-scan-discover-user-validation-ready` marks a validation-ready checkpoint;
it is not final Sprint-2 acceptance.

Historical milestone identities remain unchanged. In particular, the original
Broker Workspace BW gates remain planning history; the later Broker V1 and Broker
V2 acceptance records are the current implementation status.

## Scanner V2 — current workspace

`/scanners` now uses the fresh Scanner V2 product layout. Watchlist/Custom
universes, explicit daily technical filters, editable templates, saved scans,
immutable history, archived Dhan result analysis, and canonical Watchlist handoff
are implemented. TapTide provides optional technical screens, bounded movers and
reference metrics independently of internal Dhan scanning. Discovery remains a
separate downstream workspace with historical records intact.

Index-constituent, sector and broad-market universe feeds are not configured;
those controls explain the limitation. Derivatives is an explicit future shell.
Apply additive API migration `0018_scanner_v2` before using the new routes.
**Implemented / pending user validation; not accepted or frozen.** See the
[Scanner V2 architecture and validation record](docs/TWF_SCANNER_V2_ARCHITECTURE.md)
for exact scope, time bases, live evidence and limitations. The diagram below
continues to describe the preserved Discovery pipeline.

## Current Runtime Architecture

```text
Dhan
  ↓
MarketDataProvider
  ↓
canonical instrument resolution + normalized OHLCV
  ↓
Internal Scanner V0
  ↓
ScanMatch / relevance
  ↓
immutable temporal observation → DiscoveryCandidate
  ↓
Evidence Chart

TapTide / future MI providers
  ↓
MarketIntelligenceProvider
  ↓
bounded, optional market-context enrichment

DiscoveryCandidate
  ↓
future Opportunity → TradeOpportunity → LOB → Broker / TM
```

### Market data

**Dhan is the active authoritative market-data provider for real Scan & Discover.**
The real path resolves exact Dhan instrument identities, retrieves bounded OHLCV,
normalizes completed bars, runs the same Internal Scanner V0 profiles used by the
deterministic path, and persists matches, temporal outcomes, and evidence.

Owner-scoped Dhan credentials are configured under **Settings → Data providers →
Dhan market data**. Credentials are encrypted and never returned after saving. A
bounded connection test must reach `READY` before real scans are admitted; real
failures never fall back silently to synthetic data.

Bounded local validation has successfully exercised live Dhan data: a Dhan
connection reached `READY`, at least one real Dhan-backed scan produced valid
matches, and the Evidence Chart rendered real Dhan market data. This proves the
path, not broad symbol, interval, session, rate-limit, or market-condition coverage.
Broader real-data validation remains open.

The `MarketDataProvider` contract is provider-neutral. Zerodha is structurally
compatible and is the next intended adapter, but a production Zerodha S&D
market-data adapter is not implemented. Zerodha's current accepted role is the
Broker V1/V2 integration for account data and controlled manual trading.

### Evidence Chart

The Evidence Chart preserves a strict invariant: **the authoritative normalized
market series evaluated by a scan is the series archived to explain that scan.**
**As Scanned** reconstructs immutable historical evidence. **Current Chart** makes
a separate bounded provider read and cannot rewrite the historical result. The
provider-neutral renderer presents numerical and visual, profile-aware evidence,
including price/volume series, relevant indicators, thresholds, and the scan marker.

### Market intelligence

`MarketIntelligenceProvider` is separate from market data. Market Intelligence can
enrich context; it does not own OHLCV, scan predicates, execution prices, broker
state, or trading authority.

TapTide is the first optional provider-neutral MI adapter. Its bounded read-only
capabilities cover market pulse, India VIX, FII/DII activity, FPI sector activity,
index/sector context, market news, and corporate events. TapTide is registered in the
local API as a `MARKET_INTELLIGENCE` MCP provider and the generic Settings flow now
supports owner-scoped personal-token connect, readiness testing, reload, and
disconnect. **Live owner authorization and capability calls have not completed.**
TapTide failure cannot block Dhan technical scanning.

### TradingView and generic MCP

The TradingView MCP ScanProvider was successfully implemented and evaluated, reaching
its historical S2-3 acceptance decision with its limitations retained in
the acceptance and hardening records. It was then intentionally decommissioned from
the active market-data runtime. Existing run provenance remains immutable; the
product does not relabel old TradingView evidence as Dhan evidence.

The generic MCP foundation remains provider-neutral and active for TapTide, future
MI providers, and other compatible services. It retains OAuth/PKCE and API-key
modes, encrypted secret references, owner isolation, generation fencing, durable
operation permits, draining disconnect, hard caller deadlines, bounded responses,
and server-side tool allowlists. Focused deadline behavior is accepted in the MCP
record; strict cleanup/deadline timing under full-suite load remains a final
revalidation and hardening gate, together with remote cleanup/recovery obligations.

## What Works Today

- **Watchlists — implemented / ready for user validation, not accepted or frozen:**
  persistent owner-scoped editable equity/index/futures/options lists plus centrally
  resolved read-only built-ins for eight official Nifty universes. Built-ins use
  bounded, provenance-bearing NSE Indices constituent CSV caches, support inspect,
  export, Broker V2 preview, copy-selected/all into custom lists, and Scanner V2
  immutable universe snapshots. F&O 50/100 remain disabled as Definition pending.
  Custom archive/restore, search, CSV import/export, bulk move/copy, notes/activity,
  Dhan overlays and lazy charts remain intact. Optional TapTide news remains
  independent. Live built-in constituent and quote/chart validation requires current
  Dhan credentials; live preview needs broker reauthorization. See the
  [Watchlists architecture](docs/TWF_WATCHLIST_ARCHITECTURE.md) and
  [implementation evidence](docs/TWF_WATCHLIST_IMPLEMENTATION_REPORT.md).

- Authenticated TWF web application with a shared header, grouped navigation,
  responsive drawer, and theme switching. Existing Brokers and Scanners workspaces
  remain intact inside the new frame. Brokers is available from the workspace sidebar, user menu, or
  Settings → Integrations; Preferences, Integrations, and Advanced link into the
  same Settings page. Global symbol search and header market values are explicitly
  unavailable until their shared services are implemented. See the
  [shell implementation update](docs/TWF_TWF1_1_FRONTEND_SHELL.md#2026-10-06-application-shell-redesign).
- Personal Settings, validated profiles, service status, and owner-scoped provider
  configuration.
- Accepted Broker V1 read-only Zerodha workspace and Broker V2 opt-in manual order
  entry with preview, durable intent, submission, and reconciliation safeguards.
- Dhan authentication, readiness testing, canonical instrument resolution, quotes,
  and bounded normalized OHLCV.
- Real Dhan-backed and deterministic synthetic Scan & Discover paths through the
  same scanner contract.
- Internal Scanner V0 profiles, normalized matches, deterministic relevance,
  evidence, lifecycle, and immutable scan history.
- Scan-driven `PRESENT`, `ABSENT`, and `NOT_EVALUATED` observations with ordered
  finalization, late-result quarantine, and bounded logical HOT/COLD history.
- Evidence Chart with **As Scanned** and **Current Chart** modes.
- Candidate Review covering relevance, coverage, temporal state, tolerance, market
  context, observation history, and optional AI explanation. Evidence, technical
  details, and history use progressive disclosure.
- Optional provider-neutral MI architecture with a bounded TapTide adapter.

## Current Validation / Open Gates

- Complete broader product-owner validation with real Dhan data across representative
  profiles, instruments, intervals, partial failures, and market conditions.
- Enter an owner TapTide personal bearer token through Settings, test the seven
  required bounded capabilities, and validate the first VIX, FII/DII, sector/index,
  and news claims. Until then, TapTide is connection-ready but not live-validated.
- Revalidate generic MCP strict cleanup/deadline timing under full-suite load and
  carry forward the documented remote-cleanup, unresolved-work, diagnostic-fidelity,
  and dependency hardening items.
- Run the post-validation adversarial review, consolidate hardening evidence, and
  complete final Sprint-2 acceptance and freeze. Sprint 2 is not accepted/frozen now.
- Validate the temporal-state implementation independently; its architecture and
  implementation are complete, while user validation and acceptance remain pending.
- Complete Watchlists live user validation after refreshing Dhan credentials and reconnecting the trading broker, including official Nifty 500/Bank/Pharma/Metal constituent resolution and built-in-to-custom copy. System/custom persistence and automated validation are implemented; F&O 50/100 definitions remain pending an accepted eligibility source. Broader Universe Management remains separate.
- Keep Custom Typed Time Horizon as a separate TBD design.
- Defer richer scanner/profile parameterization, saved overrides/presets, and user
  tuning to a later refinement. Any future design must record the exact parameter
  set and version on each `ScanRun`.
- Confirm provider licensing and retention terms before production, sharing, or
  commercial use of retained market evidence.

The [Sprint-2 hardening register](docs/TWF_SPRINT2_HARDENING_REGISTER.md) owns detailed
findings; the [user validation plan](docs/TWF_SPRINT2_USER_VALIDATION_PLAN.md) owns
the validation workflows.

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

`TWF_DATABASE_URL` defaults to local SQLite. PostgreSQL uses an externally injected
`postgresql+psycopg://` URL. Run migrations explicitly from `apps/api` with
`.venv/bin/alembic upgrade head`; API startup does not run production migrations.
For containers, run `docker compose up --build` from the repository root.

See the [Ubuntu/Linux local development setup guide](docs/TWF_LOCAL_DEVELOPMENT_SETUP_LINUX.md)
for installation, validation, shutdown, and troubleshooting.

## Recommended Daily Startup

After one-time setup, start the native development servers in two terminals.

Terminal 1 — backend/API:

```bash
cd apps/api
source .venv/bin/activate
uvicorn twf.main:create_app --factory --reload --no-access-log
```

Terminal 2 — frontend/web:

```bash
cd apps/web
npm run dev
```

Open <http://localhost:3000>. Check the API at <http://localhost:8000/health> and
<http://localhost:8000/api/v1/status>. As a Docker alternative, run
`docker compose up --build` and stop it with `docker compose down`.

## Start Here

For a first reading:

1. [Product Vision and System Architecture](docs/TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md)
2. [Documentation Index](docs/TWF_DOCUMENTATION_INDEX.md)
3. [Detailed Roadmap](docs/TWF_DETAILED_ROADMAP.md)
4. [Scan & Discover Architecture](docs/TWF_SCAN_AND_DISCOVER_ARCHITECTURE.md)
5. [Integrated Sprint-2 implementation record](docs/TWF_SPRINT2_SCAN_DISCOVER_IMPLEMENTATION.md)
6. [Sprint-2 user validation plan](docs/TWF_SPRINT2_USER_VALIDATION_PLAN.md)

The [High-Level Discussion Record](docs/TWF_HIGH_LEVEL_DISCUSSION_RECORD.md) preserves
the original product discussion. The [TWF-0 Architecture Acceptance Review](docs/TWF_TWF0_ARCHITECTURE_ACCEPTANCE_REVIEW.md)
records the foundation acceptance decision.

## Architecture Overview

### Product

- [Product Vision and System Architecture](docs/TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md)
- [Detailed Roadmap](docs/TWF_DETAILED_ROADMAP.md)
- [Technology Decision Record](docs/TWF_TECHNOLOGY_DECISION_RECORD.md)
- `docs/TWF_MASTER_PRODUCT_ARCHITECTURE.docx` and
  `docs/TWF_COMPONENT_ARCHITECTURE.docx` — visual reference companions

### UX

- [UX Architecture](docs/TWF_UX_ARCHITECTURE.md)
- [Responsive Trading Application Architecture](docs/TWF_RESPONSIVE_TRADING_APPLICATION_ARCHITECTURE.md)
- [UX Bucket Roadmap](docs/TWF_UX_BUCKET_ROADMAP.md)

### Configuration

- [Configuration, Setup, Capability, Entitlement and Pluggability Architecture](docs/TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md)
- [Configuration Architecture Review](docs/TWF_CONFIGURATION_SETUP_ARCHITECTURE_REVIEW.md)

### Broker

- [Broker Workspace Architecture v0.3](docs/TWF_BROKER_WORKSPACE_ARCHITECTURE.md)
- [Broker Workspace Architecture Review](docs/TWF_BROKER_WORKSPACE_ARCHITECTURE_REVIEW.md)
- [Broker V1 read-only foundation](docs/TWF_BROKER_V1_VERTICAL_SLICE.md)
- [Broker V2 manual-trading foundation](docs/TWF_BROKER_V2_MANUAL_ORDER_ENTRY.md)

### Scan & Discover

- [Scan & Discover Architecture](docs/TWF_SCAN_AND_DISCOVER_ARCHITECTURE.md)
- [Opportunity Domain Architecture](docs/TWF_OPPORTUNITY_DOMAIN_ARCHITECTURE.md)
- [Sprint-2 Delivery Plan](docs/TWF_SPRINT2_SCAN_DISCOVER_DELIVERY_PLAN.md)
- [Scan-driven Temporal State Architecture](docs/TWF_SND_SCAN_DRIVEN_TEMPORAL_STATE_ARCHITECTURE.md)
- [Integrated Sprint-2 implementation record](docs/TWF_SPRINT2_SCAN_DISCOVER_IMPLEMENTATION.md)
- [Sprint-2 hardening register](docs/TWF_SPRINT2_HARDENING_REGISTER.md)
- [Sprint-2 user validation plan](docs/TWF_SPRINT2_USER_VALIDATION_PLAN.md)

Historical acceptance remains visible in the
[S2-1 initial HOLD review](docs/TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION_ACCEPTANCE_REVIEW.md),
the [S2-1 focused re-review](docs/TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION_REREVIEW.md),
the [S2-2 focused re-review](docs/TWF_S2_2_INTERNAL_SCANNER_V0_REREVIEW.md), and the
[historical S2-3 TradingView acceptance record](docs/TWF_S2_3_ACCEPTANCE_REVIEW.md).

### Market Data

- [Market Data Provider Architecture](docs/TWF_MARKET_DATA_PROVIDER_ARCHITECTURE.md)
- [Internal Scanner V0](docs/TWF_S2_2_INTERNAL_SCANNER_V0.md)

### Market Intelligence

- [Market Intelligence Provider Architecture](docs/TWF_MARKET_INTELLIGENCE_PROVIDER_ARCHITECTURE.md)
- [Generic MCP Connection and Authentication Foundation](docs/TWF_S2_3A_GENERIC_MCP_PROVIDER_CONNECTION_AUTH_FOUNDATION.md)
- [S2-3 deferred issues and hardening record](docs/TWF_S2_3_DEFERRED_ISSUES_AND_HARDENING_REGISTER.md)

### Data

- [Data Architecture](docs/TWF_DATA_ARCHITECTURE.md)

### Service Integration

- [Service Contract Architecture](docs/TWF_SERVICE_CONTRACT_ARCHITECTURE.md)
- [Service Integration Architecture](docs/TWF_SERVICE_INTEGRATION_ARCHITECTURE.md)
- [TI Integration Contract](docs/TWF_TI_INTEGRATION_CONTRACT.md)
- [TM Integration Contract](docs/TWF_TM_INTEGRATION_CONTRACT.md)

### Security

- [Security and Authentication Architecture](docs/TWF_SECURITY_AUTH_ARCHITECTURE.md)

### Deployment and Engineering

- [Deployment Architecture](docs/TWF_DEPLOYMENT_ARCHITECTURE.md)
- [Repository and Engineering Standards](docs/TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.md)
- [Local Development Setup](docs/TWF_LOCAL_DEVELOPMENT_SETUP_LINUX.md)

## Documentation Roles

```text
Markdown = normative repository architecture, planning, and acceptance record
DOCX     = polished visual/reference companion unless explicitly stated otherwise
```

Historical acceptance records remain historical unless a later authority explicitly
supersedes them. Some DOCX companions predate the accepted Scan & Discover and
configuration updates and are therefore reference snapshots rather than synchronized
current specifications. Use the [Documentation Index](docs/TWF_DOCUMENTATION_INDEX.md)
for the authority and companion inventory.

## Current Project Phase

The accepted TWF-0, TWF-1, Broker Workspace, Broker V1, and Broker V2 foundations
remain frozen. Scan & Discover architecture is accepted, and the current Sprint-2
product is substantially implemented. The Dhan migration, provider Settings flow,
temporal-state model, Evidence Chart, and Candidate Review refinement are committed
on `main`.

The current phase is **DHAN LIVE S&D VALIDATED / TAPTIDE LIVE VALIDATION PENDING /
SPRINT 2 USER VALIDATION IN PROGRESS**. Final Sprint-2 acceptance and freeze require
the open validation, adversarial review, and hardening gates above. No new acceptance
tag or freeze is claimed by this README reconciliation.

Documentation revision: **2026-10-02**.

## Documentation Maintenance Rule

Whenever a milestone or target changes state:

1. update its governing architecture, implementation, or acceptance record;
2. update the detailed roadmap when sequencing or status changes;
3. update the documentation index when authority or inventory changes;
4. update this README's high-level current-state map;
5. preserve historical records and keep them clearly distinguishable from current
   runtime truth.

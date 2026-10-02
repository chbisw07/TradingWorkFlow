# TradingWorkFlow (TWF) Documentation

This repository contains the application scaffold and authoritative architecture, planning, engineering, and acceptance documentation for **TradingWorkFlow (TWF)**.

TWF is the trader-facing web application that composes scanner, TradingIntelligence (TI), TradeMonitor (TM), LLMs, brokers, and other satellite services into one coherent workflow.

---

## Current Project Status

```text
TWF-0 — Product / Architecture Foundation                 ✅ ACCEPTED / FROZEN
│
├── Product vision / system architecture                  ✅ accepted
├── Master / component architecture                       ✅ accepted
├── Technology baseline                                   ✅ accepted for TWF-1
├── UX architecture                                       ✅ accepted
├── Data architecture                                     ✅ accepted
├── Security / authentication architecture                ✅ accepted
├── Service contract / integration architecture           ✅ accepted
├── Deployment architecture                               ✅ accepted
├── Repository / engineering standards                    ✅ accepted
└── Coding readiness                                      ✅ GO_TWF1

                         ↓

TWF-1 — Application Foundation                            ✅ ACCEPTED / FROZEN
│
├── TWF-1.0 Repository Scaffold                           ✅ accepted
├── TWF-1.1 Frontend Shell                                ✅ accepted
├── TWF-1.1A Theme Switching                              ✅ accepted
├── TWF-1.2 Backend Shell                                ✅ accepted
├── TWF-1.3 Database Foundation                          ✅ accepted
├── TWF-1.4 User / Login Foundation                      ✅ accepted (ba9bb8b)
├── Configuration architecture reconciliation             ✅ reviewed v0.6 / GO_TWF1_5
├── TWF-1.5 Settings Foundation                           ✅ accepted (664d4cf)
└── TWF-1.6 Service Client Foundation                     ✅ accepted (e3852d3)

UX maturity — parallel workstream
├── UX-B1 Foundational Complete UX                        PARTIAL (TWF-1.x / TWF-2)
├── UX-B2 Operationally Useful Trading UX                  PARTIAL (bounded Broker V1/V2 evidence)
└── UX-B3 Architecture-Complete UX                        PLANNED (progressive TWF-8–10)

Broker Workspace Architecture v0.3                        ✅ REVIEWED / ACCEPTED / TAGGED
Broker Workspace Workstream — mapped into TWF-2/TWF-6
├── Broker V1 coherent read-only rebuild                    ✅ ACCEPTED / FROZEN (main)
├── Broker V2 manual trading foundation                     ✅ ACCEPTED / FROZEN (twf-broker-v2)
├── BW-1 Synthetic Broker Read-Only Foundation             historical gate
├── BW-2 One real broker read-only                          PENDING
├── BW-3 Broker watchlists and draft/preview               PENDING
├── BW-4 Synthetic command and recovery foundation         PENDING
├── BW-5 Controlled live manual orders                     PENDING
├── BW-6 Second real broker proof                          PENDING
└── Later managed workflow                                 PENDING (separate TWF-5 gate)

Scan & Discover Workstream                              ✅ ARCHITECTURE ACCEPTED
│
├── S2-0  Architecture / implementation readiness       ✅ ACCEPTED
│
├── S2-1  Domain Contracts & Synthetic Provider
│         Foundation                                    ✅ ACCEPTED / FROZEN
│
├── S2-2  Internal Scanner V0                           ✅ ACCEPTED / FROZEN
│
├── S2-3A Generic MCP Connection & Authentication       ▶ DURABILITY REMEDIATED / INTEGRATED INTO S2-3
│
├── S2-3  Real Scan Provider Integration
│         Dhan market data + optional TapTide MI        ▶ MIGRATED / READY FOR USER VALIDATION
│
├── S2-4  Market Context / Market Intelligence          ✅ IMPLEMENTED
│
├── S2-5  Discovery Engine
│         Relevance / Evidence / Lifecycle              ✅ IMPLEMENTED
│
├── S2-6  Optional LLM Level-0 Intelligence             ✅ IMPLEMENTED
│
├── S2-7  Product UX / History / Settings /
│         Persistence                                   ✅ IMPLEMENTED
│
└── S2-8  End-to-End implementation validation          ✅ INTERNAL VALIDATION COMPLETE

Sprint 2                                                ▶ IMPLEMENTED / READY FOR USER VALIDATION

Later functional milestones — separately gated
├── TWF-2 Trader Workspace
├── TWF-3 Scanner Integration
├── TWF-4 TI + Active LLM Integration
├── TWF-5 TM Integration
├── TWF-6 Minimal Complete Trading Workflow
├── TWF-7 Realtime / Notifications
├── TWF-8 IFL / History / Learning Visibility
├── TWF-9 Multi-user / Subscription Readiness
└── TWF-10 Production Hardening
```

**Current state:** TWF-0 and TWF-1 are accepted/frozen. TWF-1 closure is recorded by
the existing annotated tag `twf-1-application-foundation` at `e3852d3`, whose message
is “TWF-1 Application Foundation accepted.” The
[Broker Workspace review](docs/TWF_BROKER_WORKSPACE_ARCHITECTURE_REVIEW.md) reconciles
the previously stale status pages against this repository evidence. Broker Workspace
Architecture v0.3 was independently reviewed and accepted at annotated tag
`twf-broker-workspace-architecture-v0.3` (`0b73492`); its [bounded gates](docs/TWF_BROKER_WORKSPACE_ARCHITECTURE.md#34-bounded-delivery-and-acceptance-gates)
are an implementation workstream, not replacement TWF milestone IDs. UX-B1 is still
partial. **Broker V1 is accepted/frozen and integrated into `main`**
(`aae52e9`; accepted implementation `4ffff9d`). Its Zerodha authentication,
encrypted credentials and six read-only views are the baseline.
**[Broker V2](docs/TWF_BROKER_V2_MANUAL_ORDER_ENTRY.md) is accepted/frozen:** manual
Equity/Futures/Options order entry, refined instrument search, live LTP, mandatory
Preview, durable OrderIntent and safe submission/reconciliation. A controlled real
Zerodha order smoke succeeded. Manual placement remains disabled by default until
explicitly enabled by the operator; broker acknowledgement does not guarantee execution.
See [Broker V1 setup](docs/TWF_BROKER_V1_VERTICAL_SLICE.md) and the V2 record for
scope, the additive migration, capability configuration and validation.
Earlier work is preserved on `archive/broker-work-before-simplification`; this
rebuild does not relabel historical BW gates as newly accepted.
The earlier Broker Workspace → Basic Execution Safety → TM → Scanner → TI
sequence remains dated planning history. The next workstream is
[Sprint-2 Scan & Discover](docs/TWF_SPRINT2_SCAN_DISCOVER_DELIVERY_PLAN.md), with
architecture accepted by the [independent review](docs/TWF_SCAN_DISCOVER_ARCHITECTURE_ACCEPTANCE_REVIEW.md).
Sprint 2 is **IMPLEMENTED / READY FOR USER VALIDATION**. [S2-1 domain contracts and synthetic providers](docs/TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION.md)
are ACCEPTED / FROZEN following focused independent re-review. S2-2 Internal Scanner V0
is ACCEPTED / FROZEN after [focused re-review](docs/TWF_S2_2_INTERNAL_SCANNER_V0_REREVIEW.md); S2-3A generic MCP connection/authentication is DURABILITY REMEDIATED / INTEGRATED INTO S2-3. The accepted TradingView S2-3 delivery is preserved as historical evidence; active runtime has migrated to Dhan market data with optional TapTide MI and is ready for user validation. S2-4 through S2-7 are IMPLEMENTED and S2-8 has completed internal implementation validation. User validation, adversarial review, consolidated hardening, verification, and final acceptance remain required. Provider/data/policy gates remain required
before dependent slices. It ends at
DiscoveryCandidate, works without LLM/TradingView dependencies in the core, and
preserves Broker V2 and TI/TM authority. Existing TWF milestone numbers retain their
meanings; real providers and live commands have separate gates.

### Current Implementation Status

```text
TWF-0 Architecture Foundation       ✅ accepted/frozen
TWF-1 Application Foundation        ✅ accepted/frozen (twf-1-application-foundation)
├── TWF-1.0 Repository Scaffold     ✅ accepted
├── TWF-1.1 Frontend Shell          ✅ accepted
├── TWF-1.1A Theme Switching        ✅ accepted
├── TWF-1.2 Backend Shell          ✅ accepted
├── TWF-1.3 Database Foundation    ✅ accepted
├── TWF-1.4 User / Login Foundation ✅ accepted after bounded fixes / committed ba9bb8b
├── TWF-1.5 Settings Foundation     ✅ accepted (664d4cf)
└── TWF-1.6 Service Client Foundation ✅ accepted (e3852d3)
```

The application contains a responsive Next.js trading shell, FastAPI health/status endpoints,
typed environment settings, a tested SQLite/PostgreSQL persistence foundation, and local
Docker configuration. See the [TWF-1.0 implementation record](docs/TWF_TWF1_0_REPOSITORY_PROJECT_SCAFFOLD.md)
for the accepted scaffold inventory and setup commands. See the
[TWF-1.1 Frontend Shell implementation record](docs/TWF_TWF1_1_FRONTEND_SHELL.md)
for the current shell architecture, exact changes, responsive/browser validation,
and historical implementation status. The accepted shell is tagged
`twf-1.1-frontend-shell`. The accepted theme enhancement is
[TWF-1.1A Theme Switching](docs/TWF_TWF1_1A_THEME_SWITCHING_FOUNDATION.md):
dark remains the default, with a locally persisted light-theme toggle.
Theme switching is accepted at `twf-1.1a-theme-switching`.
[TWF-1.2 Backend Shell](docs/TWF_TWF1_2_BACKEND_SHELL.md) is accepted at
`twf-1.2-backend-shell`, including typed readiness, metadata, request IDs, safe
errors, JSON logging, and configurable CORS. The accepted
[TWF-1.3 Database Foundation](docs/TWF_TWF1_3_DATABASE_FOUNDATION.md) provides synchronous
SQLAlchemy engine/session lifecycle, explicit transactions, empty Alembic baseline,
and verified SQLite/PostgreSQL migration paths. Readiness remains application-only.
[TWF-1.4 User / Login Foundation](docs/TWF_TWF1_4_USER_LOGIN_FOUNDATION.md) is accepted
after bounded fixes and committed at `ba9bb8b`: persistent users, protected shell,
login/logout and revocable sessions. Its implementation record retains its historical
pre-review status; this dashboard records the later accepted state. No new freeze tag
is asserted here.

The [configuration architecture reconciliation](docs/TWF_CONFIGURATION_SETUP_ARCHITECTURE_REVIEW.md)
concludes `GO_TWF1_5` under [configuration architecture v0.6](docs/TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md).
[TWF-1.5 Settings Foundation](docs/TWF_TWF1_5_SETTINGS_FOUNDATION.md) is accepted
and committed at `664d4cf`: personal Setup density, a safe future analysis default,
validated profiles, explicit apply/reset, revision checks and change metadata.
Theme remains device-local. APS/ACS administration, subscriptions and live integrations
remain deferred. Its implementation record preserves historical pre-review evidence.
[TWF-1.6 Service Client Foundation](docs/TWF_TWF1_6_SERVICE_CLIENT_FOUNDATION.md) is
accepted and committed at `e3852d3`: typed local/remote/synthetic adapters,
operator-configured service status, bounded transport, safe errors and a minimal
authenticated status panel. Defaults contain no services; no real integrations or
new persistence were introduced. Its implementation record preserves the historical
pre-review evidence; the existing TWF-1 tag records the later accepted foundation.
The [UX bucket roadmap](docs/TWF_UX_BUCKET_ROADMAP.md) tracks partial UX-B1/UX-B2 and planned UX-B3 alongside functional milestones; mature administration does not block core
trading integration.

Local development (Python 3.12+ and Node.js 20.19+ / 22.13+ / 24+):

```bash
# Terminal 1, from the repository root
cd apps/api
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/alembic upgrade head
TWF_ENVIRONMENT=development .venv/bin/python -m twf.bootstrap --username trader --display-name "Development Trader"
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
For containers, run `docker compose up --build` from the repository root.

Database setup, from `apps/api`: `.venv/bin/alembic upgrade head`.
`TWF_DATABASE_URL` defaults to local SQLite; deploy PostgreSQL using an externally
injected `postgresql+psycopg://` URL. Production migrations are explicit release
operations and never run at API startup. See the database foundation record for
transaction policy, test isolation, and container migration commands.

## Recommended Daily Startup

After completing the one-time setup, start the native development servers in two
terminals from the repository root.

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

Open the web app at <http://localhost:3000>. API checks are available at
<http://localhost:8000/health> and <http://localhost:8000/api/v1/status>.

As a Docker alternative, run `docker compose up --build` from the repository root
and stop it with `docker compose down`. See the
[Ubuntu/Linux local development setup guide](docs/TWF_LOCAL_DEVELOPMENT_SETUP_LINUX.md)
for initial installation, validation, shutdown, and troubleshooting.

---

## Start Here

For a first reading, follow this order:

1. [High-Level Discussion Record](docs/TWF_HIGH_LEVEL_DISCUSSION_RECORD.md)
2. [Product Vision and System Architecture](docs/TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md)
3. [Documentation Index](docs/TWF_DOCUMENTATION_INDEX.md)
4. [Detailed Roadmap](docs/TWF_DETAILED_ROADMAP.md)
5. [Technology Decision Record](docs/TWF_TECHNOLOGY_DECISION_RECORD.md)
6. [TWF-0 Architecture Acceptance Review](docs/TWF_TWF0_ARCHITECTURE_ACCEPTANCE_REVIEW.md)

Then review the specialist architecture documents as needed.

---

## Architecture Overview

### Product / System Architecture

- `docs/TWF_MASTER_PRODUCT_ARCHITECTURE.docx`
- `docs/TWF_COMPONENT_ARCHITECTURE.docx`
- [TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md](docs/TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md)

### UX

- [Responsive Trading Application Architecture](docs/TWF_RESPONSIVE_TRADING_APPLICATION_ARCHITECTURE.md) — normative responsive application clarification

- [TWF_UX_ARCHITECTURE.md](docs/TWF_UX_ARCHITECTURE.md)
- [UX Bucket Roadmap](docs/TWF_UX_BUCKET_ROADMAP.md) — cross-cutting maturity and acceptance criteria
- `docs/TWF_UX_ARCHITECTURE.docx`

### Configuration / Setup

- [Configuration, Setup, Capability, Entitlement and Pluggability Architecture](docs/TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md) — accepted design basis v0.6 with accepted v0.7 S&D extension
- [Configuration Architecture Review](docs/TWF_CONFIGURATION_SETUP_ARCHITECTURE_REVIEW.md) — decisions, SaaS gap review and TWF-1.5 readiness

### Scan & Discover — accepted architecture

- [Scan & Discover Architecture](docs/TWF_SCAN_AND_DISCOVER_ARCHITECTURE.md) — subsystem, providers, evidence, lifecycle, relevance, optional LLM and UX
- [Market Data Provider Architecture](docs/TWF_MARKET_DATA_PROVIDER_ARCHITECTURE.md) — Dhan-first authoritative market data, normalized contracts, evidence integrity, and Zerodha compatibility
- [Market Intelligence Provider Architecture](docs/TWF_MARKET_INTELLIGENCE_PROVIDER_ARCHITECTURE.md) — optional TapTide MCP claims, failure isolation, bounded calls, and multi-provider readiness
- [Scan-driven temporal state architecture](docs/TWF_SND_SCAN_DRIVEN_TEMPORAL_STATE_ARCHITECTURE.md) — 2026-10-01 design amendment: immutable observations, comparison/coverage, separate lifecycle and freshness, bounded HOT/COLD history; **GO_IMPLEMENTATION / NOT IMPLEMENTED**
- [Opportunity Domain Architecture](docs/TWF_OPPORTUNITY_DOMAIN_ARCHITECTURE.md) — shared identities and the future DiscoveryCandidate → Opportunity → TradeOpportunity → LOB progression
- [Sprint-2 Delivery Plan](docs/TWF_SPRINT2_SCAN_DISCOVER_DELIVERY_PLAN.md) — bounded scope, dependencies and acceptance gates
- [Architecture Reconciliation Record](docs/TWF_SCAN_DISCOVER_ARCHITECTURE_RECONCILIATION.md) — repository evidence, resolved contradictions, exact change inventory and stale DOCX companions
- [Independent Architecture Acceptance](docs/TWF_SCAN_DISCOVER_ARCHITECTURE_ACCEPTANCE_REVIEW.md) — decision, findings, authorization and next gate
- [S2-1 Domain Contracts & Synthetic Provider Foundation](docs/TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION.md) — implementation/remediation evidence, fixture policies and deferred scope; independently accepted
- [S2-1 Focused Re-review](docs/TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION_REREVIEW.md) — closes S21-01/02/03; GO_S2_2 for Internal Scanner V0 only
- [S2-2 Internal Scanner V0](docs/TWF_S2_2_INTERNAL_SCANNER_V0.md) — offline native scanning, indicator/condition proofs and S2-1 interoperability; independently accepted / frozen
- [S2-3A Generic MCP Connection & Authentication](docs/TWF_S2_3A_GENERIC_MCP_PROVIDER_CONNECTION_AUTH_FOUNDATION.md) — durability remediation incorporated into the integrated S2-3 review
- [S2-2 Focused Re-review](docs/TWF_S2_2_INTERNAL_SCANNER_V0_REREVIEW.md) — closes S22-01; historical GO_S2_3 decision for the original TradingView integration
- [Integrated Sprint-2 implementation](docs/TWF_SPRINT2_SCAN_DISCOVER_IMPLEMENTATION.md) — S2-4 through S2-8 implementation, persistence, API, UX, and internal validation evidence
- [Sprint-2 hardening register](docs/TWF_SPRINT2_HARDENING_REGISTER.md) — carried S2-3 obligations and new bounded post-validation hardening
- [Sprint-2 user validation plan](docs/TWF_SPRINT2_USER_VALIDATION_PLAN.md) — product-owner workflows required before adversarial acceptance

The normative architecture is **ACCEPTED / IMPLEMENTATION AUTHORIZED**; the
reconciliation record remains historical. Sprint 2 is **IMPLEMENTED / READY FOR USER VALIDATION**, with S2-1
**ACCEPTED / FROZEN** and S2-2 **ACCEPTED / FROZEN**; S2-3A is **DURABILITY REMEDIATED / INTEGRATED INTO S2-3**; the historical TradingView S2-3 delivery remains **ACCEPTED / FROZEN WITH DEFERRED HARDENING**, while the Dhan/TapTide runtime migration is **IMPLEMENTED / READY FOR USER VALIDATION**; S2-4 through S2-7 are **IMPLEMENTED** and S2-8 is **IMPLEMENTED / INTERNAL VALIDATION COMPLETE**. This is a persistent product implementation awaiting user validation and later adversarial acceptance; no new Git freeze is claimed. Sprint 2 stops at DiscoveryCandidate; later intelligence, construction,
LOB, managed execution and learning remain separate gates.

### Data

- [TWF_DATA_ARCHITECTURE.md](docs/TWF_DATA_ARCHITECTURE.md)
- `docs/TWF_DATA_ARCHITECTURE.docx`

### Security / Authentication

- [TWF_SECURITY_AUTH_ARCHITECTURE.md](docs/TWF_SECURITY_AUTH_ARCHITECTURE.md)
- `docs/TWF_SECURITY_AUTH_ARCHITECTURE.docx`

### Deployment

- [TWF_DEPLOYMENT_ARCHITECTURE.md](docs/TWF_DEPLOYMENT_ARCHITECTURE.md)
- `docs/TWF_DEPLOYMENT_ARCHITECTURE.docx`

### Broker Workspace

- [Broker Workspace Architecture v0.3](docs/TWF_BROKER_WORKSPACE_ARCHITECTURE.md) — sole normative broker design; independently reviewed and accepted at `twf-broker-workspace-architecture-v0.3`
- [Broker Workspace Architecture Review](docs/TWF_BROKER_WORKSPACE_ARCHITECTURE_REVIEW.md) — findings, status reconciliation, delivery gates and acceptance matrix
- `docs/TWF_BROKER_WORKSPACE_ARCHITECTURE.docx` — synchronized v0.3 presentation companion

### Service / Integration

- [TWF_SERVICE_CONTRACT_ARCHITECTURE.md](docs/TWF_SERVICE_CONTRACT_ARCHITECTURE.md)
- `docs/TWF_SERVICE_CONTRACT_ARCHITECTURE.docx`
- [TWF_SERVICE_INTEGRATION_ARCHITECTURE.md](docs/TWF_SERVICE_INTEGRATION_ARCHITECTURE.md)
- [TWF_TI_INTEGRATION_CONTRACT.md](docs/TWF_TI_INTEGRATION_CONTRACT.md)
- [TWF_TM_INTEGRATION_CONTRACT.md](docs/TWF_TM_INTEGRATION_CONTRACT.md)

---

## Planning / Engineering

- [TWF_DETAILED_ROADMAP.md](docs/TWF_DETAILED_ROADMAP.md)
- [TWF_TECHNOLOGY_DECISION_RECORD.md](docs/TWF_TECHNOLOGY_DECISION_RECORD.md)
- [TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.md](docs/TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.md)
- `docs/TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.docx`

---

## Acceptance / Readiness

- [TWF-0 Architecture Acceptance Review](docs/TWF_TWF0_ARCHITECTURE_ACCEPTANCE_REVIEW.md)
- [TWF-0 Coding Readiness Gate Template](docs/TWF_TWF0_ARCHITECTURE_ACCEPTANCE_AND_CODING_READINESS.md)
- `docs/TWF_TWF0_ARCHITECTURE_ACCEPTANCE_AND_CODING_READINESS.docx`

---

## Documentation Roles

```text
Markdown
    = authoritative repository-friendly architecture / planning record

DOCX
    = polished human-readable / diagram-oriented companion
```

Where both exist, Markdown is normative unless a later decision explicitly states
otherwise. DOCX files remain reference snapshots: the supplied configuration DOCX is
v0.5, while its Markdown has the accepted v0.6 basis and accepted v0.7 S&D extension.
Affected product/component/data/contract/UX/security/deployment DOCX companions are
stale for the accepted S&D architecture and await regeneration. Four additional
untracked S&D/product DOCX companions were present at review start; their
synchronization is unverified. No DOCX was created or edited by this review. The unchanged broker
Markdown/DOCX pair remains synchronized at v0.3. See the exact companion inventory
and authority rules in the [index](docs/TWF_DOCUMENTATION_INDEX.md).

---

## Current Project Phase

TWF-0 is tagged `twf-0-architecture-baseline`; TWF-1 is tagged
`twf-1-application-foundation`; Broker Workspace Architecture v0.3 is tagged
`twf-broker-workspace-architecture-v0.3`. [Broker V1](docs/TWF_BROKER_V1_VERTICAL_SLICE.md) is accepted/frozen on main.
[Broker V2](docs/TWF_BROKER_V2_MANUAL_ORDER_ENTRY.md), the manual trading foundation,
is accepted/frozen under `twf-broker-v2`, following independent review, user-driven
real Zerodha smoke and bounded correctness fixes. Automated validation uses fake
broker transports only. Historical BW gates remain an inventory of the original
plan; their pending labels do not override the accepted V1/V2 delivery records.
Scan & Discover and Opportunity-domain architecture are accepted. Sprint 2 is
**IMPLEMENTED / READY FOR USER VALIDATION**. S2-1 domain contracts and synthetic providers are **ACCEPTED / FROZEN**. The historical [S2-1 acceptance review](docs/TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION_ACCEPTANCE_REVIEW.md)
returned `HOLD_S2_1`; the [focused re-review](docs/TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION_REREVIEW.md)
closes its three blocking findings and records `GO_S2_2`. S2-2 Internal Scanner V0
is ACCEPTED / FROZEN following [focused re-review](docs/TWF_S2_2_INTERNAL_SCANNER_V0_REREVIEW.md), which closes S22-01 and records `GO_S2_3`. S2-3A is DURABILITY REMEDIATED / INTEGRATED INTO S2-3; the historical TradingView S2-3 delivery remains ACCEPTED / FROZEN WITH DEFERRED HARDENING; the active Dhan/TapTide migration is IMPLEMENTED / READY FOR USER VALIDATION. S2-4 through S2-7 are IMPLEMENTED; S2-8 is IMPLEMENTED / INTERNAL VALIDATION COMPLETE; Sprint 2 is IMPLEMENTED / READY FOR USER VALIDATION. Modify/cancel, additional brokers, Alerts-managed exits, full TI/TM,
Trade Construction, LOB and ML/IFL remain separately gated future work.

Documentation revision: **2026-10-02 / DHAN + TAPTIDE MIGRATION IMPLEMENTED / READY FOR USER VALIDATION**.
S2-1 is ACCEPTED / FROZEN under `twf-s2-1-discovery-foundation` at `caadc9d`.
S2-2 is ACCEPTED / FROZEN under `twf-s2-2-internal-scanner-v0` at `e22e17f`; its historical HOLD review is preserved. The historical TradingView S2-3 delivery is ACCEPTED / FROZEN WITH DEFERRED HARDENING. The active Dhan/TapTide migration is uncommitted and IMPLEMENTED / READY FOR USER VALIDATION; this task creates no checkpoint. MCP durability remediation remains integrated; historical TradingView proof and generic remote-cleanup obligations remain preserved in the [S2-3 review](docs/TWF_S2_3_ACCEPTANCE_REVIEW.md) and [hardening register](docs/TWF_S2_3_DEFERRED_ISSUES_AND_HARDENING_REGISTER.md). The integrated implementation and all carried obligations are consolidated in the [Sprint-2 implementation record](docs/TWF_SPRINT2_SCAN_DISCOVER_IMPLEMENTATION.md) and [Sprint-2 hardening register](docs/TWF_SPRINT2_HARDENING_REGISTER.md).
Prior accepted milestones and Git freezes remain unchanged.

---

## Documentation Maintenance Rule

Whenever a milestone or target changes state:

1. update the relevant architecture/implementation record;
2. update the detailed roadmap if sequencing changes;
3. update the documentation index if files/authority change;
4. preserve earlier accepted/historical records rather than rewriting them;
5. keep current status distinguishable from historical status.

---

## Notes

The documentation set is expected to grow as TWF moves through implementation.

Future document families may include:

- milestone/target implementation records;
- acceptance reports;
- API/service contract versions;
- UX component specifications;
- data-model records;
- security decision records;
- deployment runbooks;
- production hardening records.

## Scan-driven temporal architecture amendment — 2026-10-01

The [focused temporal-state architecture](docs/TWF_SND_SCAN_DRIVEN_TEMPORAL_STATE_ARCHITECTURE.md) is **IMPLEMENTED / PENDING USER VALIDATION AND INDEPENDENT ACCEPTANCE**. Candidate lifecycle changes through explicit comparable scan observations or audited owner decisions; clock passage affects separately labelled freshness/window validity. HOT is a bounded window over durable history, not an overwrite ring. Coverage must prove evaluated non-matches before recording absence. Sprint 2 remains **IMPLEMENTED / READY FOR USER VALIDATION**; existing acceptance/freeze history is unchanged.

## Active market-data and intelligence runtime — 2026-10-02

The original TradingView MCP implementation, acceptance record, and hardening evidence remain historical. TradingView was successfully implemented and evaluated, then intentionally decommissioned from active S&D because it is not the selected authoritative source for TWF's machine-driven technical data pipeline. Existing TradingView rows, observations, metrics, provenance, and generic MCP connection records are preserved.

Active Scan & Discover has two paths:

- **Synthetic** uses deterministic fixtures through the provider-neutral `MarketDataProvider` contract.
- **Real** resolves canonical Dhan instruments, retrieves normalized Dhan OHLCV, evaluates the exact same Internal Scanner V0 profiles, records temporal outcomes, and archives the exact evaluated series for As Scanned Evidence Chart reconstruction.

A successful evaluated non-match is `ABSENT`; Dhan authentication, rate-limit, timeout, missing-data, or malformed-response failures are `NOT_EVALUATED`. Current Chart obtains a new bounded Dhan series and cannot rewrite As Scanned truth. Dhan credentials are configured per owner through **Settings → Data providers → Dhan market data**, encrypted at rest, and never returned after saving. `TWF_DHAN_MARKET_DATA` remains an optional operator bootstrap fallback. Real scans require a successful connection test and never fall back to synthetic data.

TapTide is the first optional `MarketIntelligenceProvider`. It reuses generic MCP connection management and contributes bounded normalized market pulse, volatility, flow, sector/index, news, and event context. TapTide failure cannot block Dhan technical scanning. The product UI contains no active TradingView selector, evidence strip, chart fetch, or TradingView-specific connection action; the generic OAuth/PKCE callback and connection lifecycle remain available for TapTide and future providers.

See the [Market Data Provider Architecture](docs/TWF_MARKET_DATA_PROVIDER_ARCHITECTURE.md), [Market Intelligence Provider Architecture](docs/TWF_MARKET_INTELLIGENCE_PROVIDER_ARCHITECTURE.md), [Sprint-2 implementation record](docs/TWF_SPRINT2_SCAN_DISCOVER_IMPLEMENTATION.md), and [user validation plan](docs/TWF_SPRINT2_USER_VALIDATION_PLAN.md). This uncommitted migration is **IMPLEMENTED / READY FOR USER VALIDATION** and creates no acceptance tag or freeze.

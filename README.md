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
├── UX-B2 Operationally Useful Trading UX                  PLANNED (TWF-2–7)
└── UX-B3 Architecture-Complete UX                        PLANNED (progressive TWF-8–10)

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
the previously stale status pages against this repository evidence. This does not
close UX-B1 or accept any broker runtime. Next bounded target: BW-1 Synthetic Broker
Read-Only Foundation under [Broker Workspace v0.3](docs/TWF_BROKER_WORKSPACE_ARCHITECTURE.md#341-first-implementation-target-bw-1).
Broker Workspace → Basic Execution Safety → TM → Scanner → TI is the reviewed
delivery priority; existing TWF milestone numbers retain their original meanings.
Real providers and live commands have separate gates.

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
The [UX bucket roadmap](docs/TWF_UX_BUCKET_ROADMAP.md) tracks partial UX-B1 and planned
UX-B2/B3 alongside functional milestones; mature administration does not block core
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

- [Configuration, Setup, Capability, Entitlement and Pluggability Architecture](docs/TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md) — current normative v0.6
- [Configuration Architecture Review](docs/TWF_CONFIGURATION_SETUP_ARCHITECTURE_REVIEW.md) — decisions, SaaS gap review and TWF-1.5 readiness

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

- [Broker Workspace Architecture v0.3](docs/TWF_BROKER_WORKSPACE_ARCHITECTURE.md) — sole normative broker design; reviewed, not Git-frozen
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
v0.5, while its Markdown is now v0.6; other architecture DOCX companions retain their
TWF-0 content; the broker Markdown and DOCX are synchronized at v0.3. Broker
architecture updates must keep both formats in sync, with Markdown normative. See the [index](docs/TWF_DOCUMENTATION_INDEX.md) for current authority.

---

## Current Project Phase

TWF-0 is tagged `twf-0-architecture-baseline`; TWF-1 is tagged
`twf-1-application-foundation`. The next bounded target is BW-1 under TWF-2
workspace foundations. `GO_BROKER_WORKSPACE` accepts the reconciled design and
synthetic-first plan; no Broker Workspace runtime has been delivered or frozen.

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

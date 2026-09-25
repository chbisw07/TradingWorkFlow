# TradingWorkFlow (TWF) — Product Vision and System Architecture

## Status

**Accepted TWF-0 product baseline, extended by configuration reconciliation on 2026-09-25**

## 1. Purpose

TradingWorkFlow (TWF) is the trader-facing workflow application that unifies specialist trading systems into one coherent operating environment.

TWF integrates scanner/discovery systems, TradingIntelligence (TI), TradeMonitor (TM), LLM reasoning/synthesis, broker connectivity, alerts/notifications, future IFL feedback/learning, and other pluggable trading services.

TWF is a separate product and repository.

## 2. North Star

> Turn fragmented trading capabilities into a fast, explainable, governed, end-to-end trader workflow.

```text
discover → understand → decide → approve → execute/adopt → monitor → review
```

## 3. Product Goals

TWF should:

1. provide a fast, responsive web UX;
2. integrate scanner, TI, TM and other services;
3. support one active primary LLM while remaining provider-neutral;
4. support local and remote service deployment;
5. support SQLite initially and PostgreSQL later without domain redesign;
6. support multiple users/subscriptions in production;
7. preserve explicit authority boundaries;
8. support console-style operational visibility;
9. provide user-configurable settings and pluggable services;
10. establish a miniature but end-to-end complete system before advanced expansion.

## 4. Initial Non-Goals

The first miniature does not require autonomous trading, full multi-tenant billing, full IFL learning runtime, every scanner/broker/asset class, Kubernetes/service mesh, HFT, or complex distributed event infrastructure.

## 5. Core Responsibility Model

```text
Scanner  = discover / propose
TI       = assess / explain / forecast / advise
LLM      = reason / synthesize / interpret
TM       = govern / authorize / supervise / reconcile
Broker   = execution truth
TWF      = orchestrate / present / coordinate trader workflow
```

## 6. System Context

```text
                             ┌────────────────────┐
                             │       Trader       │
                             └─────────┬──────────┘
                                       │
                                       ▼
                             ┌────────────────────┐
                             │       TWF Web      │
                             │   Trader Cockpit   │
                             └─────────┬──────────┘
                                       │
                                       ▼
                             ┌────────────────────┐
                             │      TWF API /     │
                             │ Workflow Backend   │
                             └─────────┬──────────┘
                                       │
             ┌─────────────────────────┼──────────────────────────┐
             │                         │                          │
             ▼                         ▼                          ▼
       Scanner Service             TI Service                TM Service
             │                         │                          │
             └──────────────┬──────────┴──────────┬──────────────┘
                            │                     │
                            ▼                     ▼
                      LLM Service             Broker Service
                            │
                            ▼
                      Future IFL / History
```

## 7. Architectural Style

Use a service-oriented modular architecture.

```text
Logical service boundary = architectural requirement
Network/microservice boundary = deployment choice
```

A capability may run in-process or remotely through a stable contract.

## 8. Proposed Technology Direction

Subject to the Technology Decision Record:

- Frontend: Next.js + React + TypeScript
- Backend: FastAPI + Python
- Persistence: SQLAlchemy + Alembic
- Development DB: SQLite
- Production DB: PostgreSQL
- Realtime: WebSocket and/or SSE by use case
- Deployment: Docker-first, cloud-neutral
- Later optional infrastructure: Redis, task queue, object storage, centralized observability

## 9. Frontend Architecture Principles

- persistent application shell;
- responsive desktop-first layout;
- reusable panels;
- rapid instrument switching;
- minimal full-page reloads;
- explicit loading/stale/error states;
- keyboard-friendly actions where useful;
- service health visibility;
- authority/risk visibility;
- dense but readable trading UX.

## 10. Proposed UX Shell

```text
┌─────────────────────────────────────────────────────────────────┐
│ User | Workspace | Broker | Market | Active LLM | Alerts       │
├──────────────┬──────────────────────────────┬───────────────────┤
│ Watchlists   │ Instrument / Candidate       │ TI / LLM          │
│ Scanners     │ Chart / Thesis / Evidence    │ Intelligence      │
│ Alerts       │                              │                   │
├──────────────┴──────────────────────────────┼───────────────────┤
│ Positions / Orders / TM                    │ Risk / Actions    │
├─────────────────────────────────────────────┴───────────────────┤
│ Console / Events / Logs / Workflow History                    │
└─────────────────────────────────────────────────────────────────┘
```

Directional only; not frozen.

## 11. Major Functional Areas

### Authentication / User
Login/logout, profile, user/workspace ownership, sessions, future subscription hooks.

### Workspace
Persistent trader context, selected instrument, active watchlist, layout, active LLM and services.

### Watchlists
User-owned lists and instrument selection.

### Scanner
Scanner contract, candidate stream/results, filters/sort, candidate-to-workspace transition.

### TI
Analysis request, IntelligenceResponse, claims, horizon, evidence, provenance, optional trade expression.

### TM
Risk, authority, broker truth, adoption, execution supervision and monitoring.

### LLM
One active primary LLM configuration behind a provider-neutral service.

### Consoles
Reusable event/log/command surfaces.

### Settings / Plugins
User preferences, service endpoints, providers, layouts, feature toggles, separated from authority/security controls.

## 12. Workflow Model

```text
Candidate discovered
        ↓
Candidate opened in workspace
        ↓
TI analysis requested
        ↓
LLM/TI synthesis displayed
        ↓
Trader reviews
        ↓
Trade expression / intent proposed
        ↓
Send to TM
        ↓
TM risk + authority assessment
        ↓
Trader approves
        ↓
Execution/adoption
        ↓
TM monitors
        ↓
Workflow closes
```

Correlation IDs should connect stages.

## 13. TWF-Owned Domain Concepts

Potential TWF-owned concepts:

- User
- Workspace
- Watchlist
- Candidate
- Workflow
- WorkflowStep
- ServiceConfiguration
- UserPreference
- Notification
- AuditEvent

TWF should reference rather than unnecessarily duplicate TI IntelligenceResponse, TM authoritative position/authority state, broker execution truth, and scanner-owned metadata.

## 14. Database Architecture

```text
Application Services
       ↓
Repository Interfaces
       ↓
Persistence Adapters
       ↓
SQLAlchemy
      /       \
 SQLite     PostgreSQL
```

Initial repositories may include UserRepository, WorkspaceRepository, WatchlistRepository, WorkflowRepository, SettingsRepository, and AuditRepository.

## 15. Database Portability Rules

- schema migrations from day one;
- avoid SQLite-specific SQL semantics;
- use portable types;
- explicit indexes/constraints;
- consistent timestamps;
- production acceptance should exercise PostgreSQL;
- domain identity should not rely casually on DB auto-increment semantics.

## 16. Multi-User / Subscription Architecture

Model ownership from the beginning:

```text
User / Account
   ↓
Workspace
   ↓
owned resources
```

Capability-based subscription/entitlement hooks and account boundaries are defined now in [configuration architecture v0.6](TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md). Commercial plans, quotas, billing and usage accounting remain later implementation scope.

## 17. Authentication Direction

Separate:

- user authentication;
- application authorization;
- trading authority;
- broker authorization.

TWF-1.4 implements local password authentication and server-owned revocable sessions. Production IdP, MFA and account recovery remain separate decisions; realm/account administration is not yet implemented.

## 18. LLM Architecture

```text
TWF
  ↓
ActiveLLMConfiguration
  ↓
LLMService
  ↓
selected provider/model
```

Provider-neutral, one active primary LLM in normal runtime, actual producer identity preserved, and no authority to rewrite history/trading authority.

## 19. Service Contract Model

External capabilities should expose logical contracts with service identity, version, capabilities, health, and contract version. Endpoint/deployment details stay separate from semantic identity.

Each service may support LocalAdapter and RemoteAdapter implementations.

## 20. Realtime Architecture

Expected realtime sources include scanner events, orders, positions, broker state, alerts, TM monitoring, service health and console streams.

Use WebSocket where bidirectional interaction matters and SSE where one-way streaming is sufficient. Avoid distributed event infrastructure until justified.

## 21. State Ownership

Classify state as:

- durable TWF business state;
- service-authoritative state;
- UI/session state;
- streaming/transient state.

Do not copy external authoritative state into TWF as independently mutable truth.

## 22. Configuration Model

Runtime classes are Presentation, User/Workflow and System/Integration, with explicit permitted Platform/Account/User/Workspace/Workflow scopes and profile revisions. User/workspace/service configuration are ownership/use-case examples within that model. Bootstrap/security operations stay APS-owned; TM trading authority is outside ordinary settings. Section 34 and configuration architecture v0.6 govern the detailed separation.

## 23. Pluggability

Support pluggable scanners, LLM providers, brokers, TI/TM endpoints, notification providers and future analytics through explicit contracts/capabilities rather than arbitrary module loading.

## 24. Consoles

A reusable WebConsole should support timestamp, source/service, severity/state, correlation/workflow ID, message, structured metadata reference, filters and streaming. Command-enabled modes require explicit authority.

## 25. Auditability

Audit meaningful workflow transitions, such as candidate creation, TI analysis, TM handoff, risk rejection, trader approval, execution request, adoption and closure. TWF audit is not a replacement for service-owned histories.

## 26. Error / Degradation Model

Make scanner/TI/LLM/TM/broker unavailability, stale intelligence, stale positions, version mismatch and authorization failure visible. Never silently fallback in a way that changes authority or producer identity.

## 27. Security Principles

- least privilege;
- no secrets in browser code;
- no broker credentials in workflow records;
- encrypted transport in production;
- explicit remote-service authentication;
- audit authority transitions;
- separate login from trading authorization.

## 28. Deployment Evolution

### Development
Frontend + backend + SQLite + local/mock service adapters.

### Early Integration
Frontend + TWF backend + SQLite/PostgreSQL + local/remote TI/TM/scanners.

### Production
Cloud frontend/backend, managed PostgreSQL, optional Redis/worker, remote services, observability and subscription infrastructure.

Docker before Kubernetes.

## 29. Testing Strategy

Frontend component/interaction tests, backend unit/repository/API/adapter tests, synthetic service integration tests, and browser E2E for login → candidate → TI → TM → monitoring.

## 30. Observability

Design for request correlation, workflow ID, service latency/health, structured logs, error rates and realtime connection state.

## 31. Architectural Invariants

1. TWF is separate from TI/TM/scanners.
2. Web-first and cloud-ready.
3. Multi-user ownership is considered from the start.
4. Satellite systems remain independent services.
5. Local vs remote does not change semantics.
6. TWF does not duplicate TM authority.
7. TWF does not duplicate broker truth.
8. LLM provider remains replaceable.
9. One active primary LLM is normal operation.
10. Database implementation is replaceable.
11. SQLite-specific behavior stays out of application/domain logic.
12. Durable-state ownership is explicit.
13. External authoritative state is not silently copied as local truth.
14. Workflow lineage is traceable.
15. The first complete product checkpoint is the TWF-6 miniature; TWF-1 establishes its application foundation.
16. User settings cannot silently grant trading authority.
17. Degraded states are explicit.
18. Service contracts are versioned.
19. UI remains responsive under streaming updates.
20. IFL can be added later without fundamental redesign.

## 32. Initial Documentation Set

Initial authoritative docs:

- `TWF_HIGH_LEVEL_DISCUSSION_RECORD.md`
- `TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md`
- `TWF_DETAILED_ROADMAP.md`
- `TWF_TECHNOLOGY_DECISION_RECORD.md`

Specialist architecture and planning documents:

- `TWF_UX_ARCHITECTURE.md`
- `TWF_SERVICE_CONTRACT_ARCHITECTURE.md`
- `TWF_DATA_ARCHITECTURE.md`
- `TWF_SECURITY_AUTH_ARCHITECTURE.md`
- `TWF_DEPLOYMENT_ARCHITECTURE.md`
- `TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md`
- `TWF_UX_BUCKET_ROADMAP.md`

The detailed roadmap owns milestone/target sequencing; the documentation index maps current and historical implementation records.

## 33. Current Decision

TWF-0 passed its formal architecture gate; TWF-1.0 through TWF-1.4, including TWF-1.1A, are accepted. The [configuration reconciliation](TWF_CONFIGURATION_SETUP_ARCHITECTURE_REVIEW.md) now recommends `GO_TWF1_5` for a bounded Settings Foundation plan. TWF-1.5 remains not started; later service/trading milestones retain their own acceptance gates.

## 34. Configuration and UX Reconciliation

This 2026-09-25 clarification extends the accepted TWF-0 product boundary. The [configuration architecture v0.6](TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md) separates APS platform producers from ACS consumer tenants, COLD capability publication from HOT/WARM subscriber settings, and entitlement from permission and trading authority. The earlier settings categories are examples; canonical runtime classes are Presentation, User/Workflow and System/Integration, with explicit scopes and override policy. Platform bootstrap/security operations remain separate.

Capability registry/policy, entitlement, configuration/profile resolution, secret references, health and audit are logical backend responsibilities, not mandated microservices. Setup Center, ACS account administration and APS operations are distinct UX contexts. The master/component DOCX files remain TWF-0 reference snapshots; this clarification and the linked normative architectures govern subsequent configuration work.

The [UX Bucket Roadmap](TWF_UX_BUCKET_ROADMAP.md) tracks foundational, operational and mature UX across the unchanged functional sequence. TWF-1.5 builds only the bounded personal settings foundation; TWF-1.6 supplies service-client foundations; TWF-2–6 grow the trader workflow. Later administration/subscription/IFL UX does not block early trading integration. Synthetic adapters accelerate UX while preserving Scanner/TI/TM/LLM contracts and authority boundaries.

# TradingWorkFlow (TWF) — Technology Decision Record

> **2026-09-29 S&D architecture acceptance:** The dated S&D extension below is **ACCEPTED / IMPLEMENTATION AUTHORIZED** within the [Sprint-2 delivery plan](TWF_SPRINT2_SCAN_DISCOVER_DELIVERY_PLAN.md). The [independent acceptance record](TWF_SCAN_DISCOVER_ARCHITECTURE_ACCEPTANCE_REVIEW.md) supersedes its 2026-09-28 proposal status. Sprint 2 is **ACTIVE / NEXT; implementation not started**. Earlier acceptance history and separate TI/TM/provider/security gates remain unchanged; proposal wording in the dated extension records its origin, not the current review status.

## Status

**Accepted TWF-0 technology baseline, with implementation/configuration clarifications dated 2026-09-25**

The original proposal labels below retain decision history; the [TWF-0 acceptance](TWF_TWF0_ARCHITECTURE_ACCEPTANCE_REVIEW.md) governs accepted stack choices. Section 28 records subsequent authentication/theme selections and bounded configuration direction.

## 1. Decision Goal

Select a stack supporting fast/responsive trading UX, realtime updates, Python-native TI/TM/scanner integration, multi-user cloud deployment, local development, SQLite initially, PostgreSQL later, strong contracts, small-team maintainability and Docker-first deployment.

## 2. Proposed Stack Summary

| Layer | Proposed choice | Status |
|---|---|---|
| Web framework | Next.js | Proposed |
| UI runtime | React | Proposed |
| Frontend language | TypeScript | Proposed |
| Backend API | FastAPI | Proposed |
| Backend language | Python 3.12+ | Proposed |
| ORM/data access | SQLAlchemy 2.x | Proposed |
| Migrations | Alembic | Proposed |
| Initial DB | SQLite | Proposed |
| Production DB | PostgreSQL | Proposed |
| API contracts | OpenAPI / typed DTOs | Proposed |
| Realtime | WebSocket + SSE by use case | Proposed |
| Containers | Docker | Proposed |
| Frontend tests | Vitest/React Testing Library | Proposed |
| Browser E2E | Playwright | Proposed |
| Backend tests | pytest | Proposed |
| Frontend quality | TypeScript strict + ESLint + Prettier | Proposed |
| Backend quality | Ruff + mypy | Proposed |

## 3. Frontend Decision

### Proposed
Next.js + React + TypeScript.

### Rationale
Strong ecosystem, rich component model, complex dashboard suitability, TypeScript, routing, realtime support, cloud deployment and future SSR/public-page flexibility.

### Constraint
TWF's live trader surfaces should behave primarily as an interactive app; do not overuse server rendering where persistent client state is more appropriate.

## 4. Backend Decision

### Proposed
FastAPI + Python.

### Rationale
Python alignment with TI/TM/scanners, typed APIs, async support, WebSockets, OpenAPI/Pydantic ecosystem and simple container deployment.

## 5. Backend-for-Frontend Decision

Use the FastAPI backend as the principal TWF application API initially. Do not add a separate Node BFF unless requirements justify it. Keep core workflow/domain logic in Python rather than duplicating it across Python and TypeScript.

## 6. Database Decision

Development: SQLite.

Production: PostgreSQL.

Abstraction: SQLAlchemy + explicit repository/data-access boundaries where they add value.

## 7. SQLite → PostgreSQL Portability Rules

1. no SQLite-specific SQL in application/domain logic;
2. Alembic migrations;
3. avoid relying on permissive SQLite typing;
4. portable SQL types;
5. explicit constraints/indexes;
6. concurrency differences tested;
7. PostgreSQL included in production acceptance.

## 8. Repository Pattern

```text
domain/application
        ↓
repository protocol/interface
        ↓
SQLAlchemy repository
        ↓
engine/session
```

Avoid repository abstractions that add ceremony without ownership/testing/replaceability value.

## 9. Realtime Decision

Use WebSocket for interactive/bidirectional streams and SSE for simple server→browser streams. Do not force one transport globally.

## 10. Caching

Redis is not required initially. Add it only when distributed cache, shared ephemeral state, rate limiting, pub/sub or multi-instance coordination justify it.

## 11. Background Jobs

Define a task/worker boundary but defer framework choice. Potential future options include ARQ, Dramatiq, Celery or cloud queues, selected according to actual job semantics.

## 12. Authentication

TWF-1.4 implements bounded local password authentication and server-owned revocable sessions; see section 28 and the [security architecture](TWF_SECURITY_AUTH_ARCHITECTURE.md). Production identity/MFA/recovery remain later decisions. Preserve multi-user readiness, entitlement separation, broker authority and secret isolation.

## 13. API Contract Strategy

Prefer FastAPI/Pydantic canonical backend schemas, OpenAPI generation and generated/validated TypeScript clients/types where practical. Avoid independent handwritten duplicate schemas where safe generation can prevent drift.

## 14. Service Integration

Use logical service clients such as ScannerClient, TIClient, TMClient, LLMClient and BrokerClient, each with local/remote adapters as needed. Domain/workflow code should not know transport details.

## 15. LLM Provider Strategy

Provider-neutral. One active primary LLM in normal runtime. Provider SDK types must not leak into TWF domain contracts.

## 16. Frontend State Strategy

Prefer local/component state, server-state/query cache, then small global workspace state. Introduce a specialized global state library only if real complexity justifies it. Avoid a giant mutable global store.

## 17. Data Fetching

Use a server-state/query approach supporting cache, invalidation, refetch, stale state and carefully controlled optimistic updates. Freeze exact library during UX architecture.

## 18. UI Component Strategy

Choose a coherent accessible component system with keyboard navigation, dense layout support, dark mode, tables/forms/dialogs, theming and responsive behavior. Do not lock the architecture to a vendor before evaluation.

## 19. Charting

TBD. Requirements: performant timeseries rendering, overlays, markers, zoom/pan, streaming updates and responsive resizing. TradingView integration may be evaluated separately from generic app charting.

## 20. Frontend Testing

Proposed: Vitest, React Testing Library and Playwright for critical browser workflows.

## 21. Backend Testing

pytest with unit, repository, API, adapter contract and synthetic-service integration tests.

## 22. Type / Quality Tools

Backend: Ruff, mypy, packaging/compile checks.

Frontend: TypeScript strict mode, ESLint, Prettier, build/type-check gates.

## 23. Containerization

Docker-first. Local development may use native processes, but production artifacts should be container-friendly. Do not require Kubernetes initially.

## 24. Cloud Neutrality

Avoid tight cloud coupling. Later cloud-specific managed services may sit behind standard interfaces: container runtime, managed PostgreSQL, object storage, secrets, logging/monitoring.

## 25. Repository Structure

TWF is separate from TI/TM/scanners. Within TWF, a small monorepo layout is recommended:

```text
apps/
    web/
    api/

shared/ or packages/
    contracts/
    generated-client/   # if needed

docs/
```

Exact structure should be frozen during TWF-0.6.

## 26. Initial Recommendation

Unless architecture review finds a material blocker, proceed with:

```text
Next.js + React + TypeScript
FastAPI + Python
SQLAlchemy + Alembic
SQLite → PostgreSQL
WebSocket / SSE
Docker
pytest + Playwright
```

## 27. Decisions Still Open

- authentication provider/library;
- UI component library;
- charting library;
- frontend query/server-state library;
- background task framework;
- Redis timing;
- cloud platform;
- subscription/billing provider;
- secrets management;
- deployment topology;
- API gateway strategy;
- service discovery;
- notification providers.

Resolve these through bounded decision records as their milestones approach.

## 28. Configuration and UX Decisions on 2026-09-25

The [configuration architecture v0.6](TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md) adds typed/versioned setting and capability descriptors, explicit scope/ownership checks, optimistic revisions, secret references and profile/application lifecycle. Implement these using the accepted FastAPI/Pydantic/SQLAlchemy/Next.js foundations; no plugin framework, commercial feature-flag provider, billing SDK, policy engine or global form/state framework is selected or required now.

TWF-1.4 has selected local password authentication and revocable server-owned sessions. Its limited Next.js same-origin auth transport is not a second backend authority; FastAPI remains responsible for identity/session decisions. Production IdP/MFA/recovery remain later choices. Realm/admin features require their own design gate, not reinterpretation of the existing user model.

The accepted TWF-1.1A centralized dark/light tokens and guarded browser-local restoration remain the theme baseline. TWF-1.5 must specify user/device preference precedence and hydration/first-paint preservation before integrating persisted appearance settings. [UX buckets](TWF_UX_BUCKET_ROADMAP.md) do not preselect chart/grid/docking libraries. Synthetic contract adapters are required for early UX/testing; no real service SDK is added by this decision.


## 29. S&D technology direction — proposed ADR — 2026-09-28

Reuse the accepted Next.js/React, FastAPI/Pydantic, SQLAlchemy/Alembic and portable
SQLite/PostgreSQL foundation for [S&D](TWF_SCAN_AND_DISCOVER_ARCHITECTURE.md).
Start with logical modules and bounded durable user-triggered runs; do not prescribe
microservices, a queue/broker, scheduling framework or a market-data warehouse.
Stable IDs, typed contracts, immutable captures and optimistic revisions are design
requirements independent of provider SDK selection.

TradingView MCP is a planned scan adapter, separate from the earlier chart/widget
technology discussion. No specific MCP server, SDK, tool schema or entitlement is
selected here; verify those before implementation. Internal V0 requires an approved
independent data input and bounded deterministic indicator functions, not a clone of
all vendor features. Provider-neutral hosted LLM adapters are optional; no OpenAI,
Anthropic/Claude, Google or local inference framework is mandated or installed.

Discovery Relevance initially uses an explicit deterministic versioned policy and
coverage/dependence rules. Optional LLM output has zero score/authority weight.
Production ML ranking and self-learning remain later research/governance choices.
See [Sprint-2 S2-0](TWF_SPRINT2_SCAN_DISCOVER_DELIVERY_PLAN.md) for source, licensing,
calendar, profile and operating-limit decisions needed before dependent coding.

### Revision history addition

| Revision | Date | Status | Role / change |
| --- | --- | --- | --- |
| S&D reconciliation 1 | 2026-09-28 | PROPOSED / RECONCILED / READY FOR REVIEW | Normative design/planning extension: S&D technology direction — proposed ADR; prior history and acceptance preserved |
| S&D acceptance 1 | 2026-09-29 | ACCEPTED / IMPLEMENTATION AUTHORIZED | Independent S&D architecture acceptance; staged Sprint-2 scope only, no runtime delivery or prior milestone change; see [review](TWF_SCAN_DISCOVER_ARCHITECTURE_ACCEPTANCE_REVIEW.md) |

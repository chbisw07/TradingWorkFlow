# TradingWorkFlow (TWF) — Technology Decision Record

## Status

**Initial proposed technology baseline — review required before freeze**

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

Deferred to a dedicated security/auth decision. Requirements include secure browser login, multi-user production, future entitlements, separation from broker authorization and no secret exposure to browser bundles.

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

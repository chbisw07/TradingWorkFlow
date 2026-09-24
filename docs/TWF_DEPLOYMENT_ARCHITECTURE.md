# TradingWorkFlow (TWF) — Deployment Architecture

## Status
**TWF-0 normative deployment architecture — proposed for acceptance**

## 1. Purpose
Define how TWF evolves from local development to cloud-hosted multi-user SaaS while preserving logical service contracts and avoiding premature distributed-system complexity.

## 2. Deployment Principle
```text
Architecture defines logical services first.
Deployment may place them together or apart.
```

## 3. Development Topology
```text
Developer workstation
├── TWF Web (Next.js)
├── TWF API (FastAPI)
├── SQLite
├── Synthetic/local Scanner adapter
├── Synthetic/local TI adapter
└── Synthetic/local TM adapter
```
Goals:
- zero cloud dependency
- fast feedback
- deterministic testing
- end-to-end miniature workflow

## 4. Integrated Local Topology
```text
Developer / Integration host
├── TWF Web
├── TWF API
├── SQLite or PostgreSQL
├── TI service       local or remote
├── TM service       local or remote
├── Scanner service  local or remote
└── LLM provider     remote API
```
This is the preferred first real-integration stage.

## 5. Early Cloud Topology
```text
Internet
   ↓
HTTPS / WAF / ingress
   ↓
TWF Web + API containers
   ↓
Managed PostgreSQL
   ↓
Service adapters
   ├── TI endpoint
   ├── TM endpoint
   ├── Scanner endpoint
   ├── LLM provider
   └── Notification provider
```
Initially one application instance may be sufficient.

## 6. Production SaaS Topology
```text
Users
  ↓
CDN / HTTPS ingress
  ↓
TWF Web
  ↓
TWF API pool
  ├── auth/session
  ├── workflow services
  ├── service clients
  └── realtime gateway
        ↓
Managed PostgreSQL
Optional Redis / worker tier
        ↓
Satellite services / external providers
```
Scale components independently only when evidence justifies it.

## 7. Database Evolution
```text
Development: SQLite
      ↓
Integration: SQLite or PostgreSQL
      ↓
Production: Managed PostgreSQL
```
Domain/application code must remain database-neutral.

## 8. Containers
Use Docker as the portable deployment unit for:
- TWF Web
- TWF API
- optional worker

TI/TM/scanners keep their own deployment artifacts.

## 9. Kubernetes
Kubernetes is NOT required initially.
Adopt only if operational scale/availability justifies:
- many service instances
- autoscaling
- rolling deployments
- complex networking
- multi-service operations

## 10. Realtime Deployment
A single API instance can initially own WebSocket/SSE connections.
When scaling horizontally, evaluate:
- Redis pub/sub
- broker/event backplane
- sticky sessions only where unavoidable

Do not introduce distributed realtime infrastructure before needed.

## 11. Background Work
Initial lightweight background execution may be in-process for non-critical work.
Move to worker/queue when tasks require:
- durability
- retries
- long duration
- independent scaling
- scheduled execution

## 12. Service Placement Matrix
| Service | Development | Early integration | Production |
|---|---|---|---|
| TWF Web | local | container/local | cloud |
| TWF API | local | container/local | cloud |
| DB | SQLite | SQLite/Postgres | managed Postgres |
| TI | synthetic/local | local/remote | remote/logical service |
| TM | synthetic/local | local/remote | remote/logical service |
| Scanner | synthetic/local | local/remote | remote/logical service |
| LLM | mocked/remote | remote | remote provider |

## 13. Network Boundaries
Production trust zones:
- public browser edge
- TWF application zone
- database zone
- satellite-service zone
- external-provider zone
- TM/broker high-trust boundary

## 14. Authentication / Secrets
Production deployment requires:
- HTTPS
- secure session handling
- server-side provider secrets
- secret manager
- service authentication for remote TI/TM/scanners
- no broker secrets in browser/TWF ordinary records

## 15. Health / Readiness
Every deployable service should expose:
- liveness
- readiness
- version/contract metadata
- dependency health where appropriate

TWF UI should surface meaningful degraded states.

## 16. Observability
Production baseline:
- structured logs
- request ID
- workflow ID
- latency
- error counts
- service health
- realtime connection metrics
- audit events

Later add tracing/metrics backend as needed.

## 17. Backup / Recovery
Production DB:
- automated backups
- restore procedure
- migration backup discipline
- optional PITR

Configuration/secrets should also have controlled recovery processes.

## 18. Availability Philosophy
Do not overengineer HA before product usage requires it.
Initial priority:
- clear degradation
- safe failure
- recoverability
- no duplicate trading actions

## 19. Deployment Pipeline
Future CI/CD should perform:
```text
lint/typecheck
unit tests
contract tests
frontend build
backend package/build
container build
migration check
security scan
staging deploy
smoke/E2E
production deploy
```

## 20. Environment Model
Recommended environments:
- local
- test/CI
- staging
- production

Avoid hidden behavior differences between them.

## 21. Cloud Neutrality
TWF architecture should not require a specific cloud.
Managed services may be cloud-specific behind standard abstractions.

## 22. Scaling Order
Scale only when needed, approximately:
1. PostgreSQL production
2. multiple TWF API instances
3. Redis/shared transient state
4. worker queue
5. realtime backplane
6. advanced orchestration/Kubernetes

## 23. Deployment Invariants
1. Logical service semantics are deployment-neutral.
2. Secrets stay server-side.
3. Database migration does not change domain semantics.
4. Broker authority/truth remains outside TWF.
5. Horizontal scale cannot create duplicate authority-changing actions.
6. Every production deployment is observable and reversible enough for safe operation.

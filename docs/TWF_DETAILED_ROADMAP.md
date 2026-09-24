# TradingWorkFlow (TWF) — Detailed Roadmap

## Status

**Initial architecture-stage roadmap — proposed, not yet frozen**

Milestone/target identifiers are provisional until reviewed and accepted.

## 1. Roadmap Objective

Build a miniature TWF system that is complete end-to-end, then expand it incrementally. Optimize for architecture correctness, responsive UX, stable service boundaries, early usefulness, cloud/multi-user readiness, bounded milestones and clear acceptance criteria.

## 2. Major Sequence

```text
TWF-0  Product / Architecture Foundation
  ↓
TWF-1  Application Foundation
  ↓
TWF-2  Trader Workspace
  ↓
TWF-3  Scanner Integration
  ↓
TWF-4  TI + Active LLM Integration
  ↓
TWF-5  TM Integration
  ↓
TWF-6  Minimal Complete Trading Workflow
  ↓
TWF-7  Realtime / Notifications
  ↓
TWF-8  IFL / History / Learning Visibility
  ↓
TWF-9  Multi-user / Subscription Readiness
  ↓
TWF-10 Production Hardening
```

## 3. TWF-0 — Product / Architecture Foundation

### TWF-0.1 Product Vision and Boundaries
Product purpose, north star, goals/non-goals, trader workflows and responsibility boundaries.

### TWF-0.2 System Architecture
Frontend/backend split, service architecture, logical/local/remote adapters, DB abstraction, realtime model and identity/correlation principles.

### TWF-0.3 Technology Decisions
Frontend, backend, DB, migrations, testing, realtime and deployment baseline.

### TWF-0.4 UX Architecture
Shell layout, navigation, workspace, panels, console model and degraded states.

### TWF-0.5 Data / Security / Deployment Architecture
User/workspace ownership, DB repository model, auth/security boundaries, cloud evolution and secrets.

### TWF-0.6 Repository / Engineering Standards
Repo structure, coding standards, docs structure, testing policy and branch/release conventions.

### Acceptance
Coding can begin without unresolved foundational contradictions.

## 4. TWF-1 — Application Foundation

### TWF-1.1 Frontend Shell
Next.js/React/TypeScript shell, layout, navigation, error/loading states.

### TWF-1.2 Backend Shell
FastAPI app, health endpoint, config, structured logging and API version base.

### TWF-1.3 Database Foundation
Repository interfaces, SQLAlchemy, SQLite and Alembic with migration tests.

### TWF-1.4 User / Login Foundation
User identity, login/session and initial authorization boundary.

### TWF-1.5 Settings Foundation
User preferences, workspace configuration and service configuration separated from security/authority.

### TWF-1.6 Service Client Foundation
Logical service descriptors, health/status and local/remote adapter base.

### Acceptance
User can log in, see the shell, persist workspace/settings and see configured service status.

## 5. TWF-2 — Trader Workspace

### TWF-2.1 Workspace Layout
Panel system, navigation and selected-instrument context.

### TWF-2.2 Watchlists
Create/edit/delete lists and select instruments.

### TWF-2.3 Candidate Workspace
Candidate summary, selected instrument and workflow context.

### TWF-2.4 Web Console Foundation
Reusable console, filters, realtime append and correlation IDs.

### TWF-2.5 Persisted UX Preferences
Panel/layout preferences and defaults.

### Acceptance
Trader can navigate a responsive workspace, manage watchlists, select a candidate and use the base console.

## 6. TWF-3 — Scanner Integration

### TWF-3.1 Scanner Service Contract
Capabilities, request/result, identity/version and local/remote adapter.

### TWF-3.2 Synthetic Scanner Adapter
Deterministic candidate feed for development/tests.

### TWF-3.3 Candidate List UX
List/grid, filters, sort and status.

### TWF-3.4 Candidate → Workspace
Preserve scanner provenance and create/open workflow.

### Acceptance
Scanner results can create/open candidates without TWF knowing scanner internals.

## 7. TWF-4 — TI + Active LLM Integration

### TWF-4.1 TI Service Client
IntelligenceResponse, producer/version/provenance and local/remote semantics.

### TWF-4.2 Active LLM Configuration
Provider-neutral configuration with one active primary LLM.

### TWF-4.3 TI Analysis UX
Thesis, claims, horizon, evidence and producer/model identity.

### TWF-4.4 Trade Expression UX
Display advisory trade expression distinctly from execution authority.

### TWF-4.5 TI / LLM Console
Reasoning/activity/event surface with provider identity where appropriate.

### Acceptance
Candidate can be analyzed by TI and displayed correctly with provenance and no authority leakage.

## 8. TWF-5 — TM Integration

### TWF-5.1 TM Service Client
Authority/risk/position state and workflow correlation.

### TWF-5.2 Risk / Authority Panel
Explicit status and reasons.

### TWF-5.3 External / Existing Position View
Broker-external vs managed/adopted distinction.

### TWF-5.4 Manual Approval Handoff
Trader action, idempotent handoff and TM authority preservation.

### TWF-5.5 Position Monitoring View
Status, P&L, risk and monitoring state.

### Acceptance
TWF can hand an analyzed candidate to TM and present TM truth without duplicating ownership.

## 9. TWF-6 — Minimal Complete Trading Workflow

### TWF-6.1 Candidate Workflow State
Discovered → analyzed → reviewed → sent to TM → approved/rejected → monitored → closed.

### TWF-6.2 Correlation / Audit
Candidate, TI response, TM, order and position references where applicable.

### TWF-6.3 Manual Approval Flow
Manual trader approval remains mandatory.

### TWF-6.4 Outcome / Closure
Workflow closure, final state and audit history.

### TWF-6.5 E2E Acceptance Corpus
Synthetic/local scanner → TI → TM → monitored/closed scenarios.

### Acceptance
One coherent trading workflow works end-to-end. This is the first major product milestone.

## 10. TWF-7 — Realtime / Notifications

Targets: WebSocket/SSE infrastructure, reconnect/resume, scanner stream, TM position/order stream, notification center, alert routing and stale-state visibility.

## 11. TWF-8 — IFL / History / Learning Visibility

Targets: claim/history view, resolved outcome view, performance summaries, producer/model history and later IFL service integration. No autonomous retraining without separate governance.

## 12. TWF-9 — Multi-user / Subscription Readiness

Targets: tenant/user isolation, roles, subscription model, entitlements, quotas, usage accounting and administration.

## 13. TWF-10 — Production Hardening

Targets: PostgreSQL production migration, performance profiling, caching if justified, background workers, observability, backup/recovery, security hardening, cloud deployment, scale and runbooks.

## 14. Cross-Cutting Workstreams

Security, accessibility, responsive UX, service-version compatibility, auditability, observability, migration safety, contract tests, documentation and backward compatibility.

## 15. Documentation Rule

Each milestone should produce architecture/design updates if needed, implementation records, test/acceptance evidence, project-tree update and milestone closure. Historical accepted records should not be rewritten.

## 16. Codex Usage Strategy

Use ChatGPT web for architecture, planning, docs, reviews, acceptance reasoning and prompt creation. Use Codex mainly for bounded implementation, tests and mechanical repo updates.

## 17. Current Next Work

Complete/review TWF-0 architecture documents before implementation. Likely additional TWF-0 documents: UX architecture, service contract architecture, data architecture, security architecture and deployment architecture.

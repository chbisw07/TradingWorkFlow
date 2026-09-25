# TradingWorkFlow (TWF) — Detailed Roadmap

## Status

**Accepted TWF-0 functional sequence, reconciled on 2026-09-25 for configuration v0.6 and UX buckets.**

TWF-1.0, 1.1, 1.1A, 1.2, 1.3, 1.4 and 1.5 are accepted; TWF-1.5 is committed at
`664d4cf`. TWF-1.6 is implemented, pending independent review. Later functional
targets remain pending. The
[configuration review](TWF_CONFIGURATION_SETUP_ARCHITECTURE_REVIEW.md) records
`GO_TWF1_5` for the bounded scope below. Architecture readiness is not implementation
completion or a repository freeze.

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

### TWF-1.0 Repository and Project Scaffold
Accepted repository layout, runnable shells, development tooling and container baseline.

### TWF-1.1 Frontend Shell
Next.js/React/TypeScript shell, layout, navigation, error/loading states.

### TWF-1.1A Theme Switching Foundation
Accepted centralized dark/light tokens, dark default and safe browser-local restoration.

### TWF-1.2 Backend Shell
FastAPI app, health endpoint, config, structured logging and API version base.

### TWF-1.3 Database Foundation
Repository interfaces, SQLAlchemy, SQLite and Alembic with migration tests.

### TWF-1.4 User / Login Foundation
User identity, login/session and initial authorization boundary.

### TWF-1.5 Settings Foundation

**Accepted and committed at `664d4cf`.** See the historical
[implementation record](TWF_TWF1_5_SETTINGS_FOUNDATION.md) for the finite contract,
validation evidence and explicit deferrals. The governing boundary remains:

Dependency: the reviewed [configuration architecture v0.6](TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md),
especially section 34. Define a finite settings/profile contract before coding.
Implement typed personal Presentation and safe User/Workflow preferences, allowed-scope
resolution, optimistic revisions, non-secret profile foundation, capability/entitlement
interfaces with explicit foundation grants, secret-reference contracts, Setup UI and
change metadata. Preserve accepted auth and theme behavior.

Shared ACCOUNT/WORKSPACE/WORKFLOW persistence requires real ownership foundations and
an explicit bounded scope decision. Do not infer tenant membership from a user ID.
WARM metadata may be defined now; real connection/rebind behavior belongs to later
adapters. Full APS/ACS administration, subscription billing, production vaults, live
providers and dynamic plugin loading remain excluded.

### TWF-1.6 Service Client Foundation

**Implemented; pending independent review.** See the
[implementation record](TWF_TWF1_6_SERVICE_CLIENT_FOUNDATION.md) for bounded contracts,
operator configuration, security boundaries and validation.

Logical service descriptors, capability registration/identity, health/status and
local/remote adapter base. Establish deterministic SyntheticScannerService,
SyntheticTIService, SyntheticTMService and SyntheticLLMService fixtures behind versioned
logical contracts as needed to prove foundation behavior; full domain payloads mature
in their integration milestones. No real integrations or authority shortcuts.

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

Targets: ACS account/membership and role administration, APS realm/role/support/service
principal administration, versioned subscription grants, quotas, usage accounting,
rollout controls and lifecycle UX. These develop the architectural hooks accepted now;
pricing, plans and billing provider remain deferred. Account isolation must be proved
before any shared tenant feature ships, even if that feature is scheduled earlier.
Support/break-glass and machine access require their security gates before exposure.

## 13. TWF-10 — Production Hardening

Targets: PostgreSQL production migration, performance profiling, caching if justified, background workers, observability, backup/recovery, security hardening, cloud deployment, scale and runbooks.

## 14. Cross-Cutting Workstreams

Security, accessibility, responsive UX, service-version compatibility, auditability,
observability, migration safety, contract tests, documentation and backward compatibility.

The [UX Bucket Roadmap](TWF_UX_BUCKET_ROADMAP.md) defines an additional maturity track:

| Bucket | Milestone mapping | Dependency rule |
|---|---|---|
| UX-B1 Foundational Complete UX | TWF-1.x plus workspace/console foundations in TWF-2 | Partial today; synthetic/local UX does not require live services or admin backend |
| UX-B2 Operationally Useful Trading UX | TWF-2/3/4/5, end-to-end acceptance in TWF-6 and realtime refinement in TWF-7 | Layout/content evolve with real contracts; preserve source and authority semantics |
| UX-B3 Architecture-Complete UX | Progressive administration/subscriptions, IFL and operations in TWF-8/9/10 | Individual features advance when justified; the whole bucket never blocks core integrations |

Configuration checkpoint before TWF-1.5: reviewed v0.6 separates realms, scopes,
capability/entitlement gates, desired/effective/applied state, profiles and operations.
Later integration targets must implement the corresponding lifecycle, secret, schema
migration and revocation controls before exposing those features. TWF-10 owns evidence
for zero/minimal-downtime deployment, not an assumed guarantee today.

## 15. Documentation Rule

Each milestone should produce architecture/design updates if needed, implementation records, test/acceptance evidence, project-tree update and milestone closure. Historical accepted records should not be rewritten.

## 16. Codex Usage Strategy

Use ChatGPT web for architecture, planning, docs, reviews, acceptance reasoning and prompt creation. Use Codex mainly for bounded implementation, tests and mechanical repo updates.

## 17. Current Next Work

TWF-0 is accepted/frozen; TWF-1.4 was accepted after bounded fixes and committed at
`ba9bb8b`. TWF-1.5 was accepted and committed at `664d4cf`. The bounded
[TWF-1.6 implementation](TWF_TWF1_6_SERVICE_CLIENT_FOUNDATION.md) awaits independent
acceptance review before freeze. No whole-TWF-1 or UX bucket acceptance is asserted;
UX-B1 remains partial and UX-B2/B3 remain planned. TWF-2 remains separately gated.

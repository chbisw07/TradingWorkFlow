# TradingWorkFlow (TWF) — High-Level Product Discussion Record

## Status

**Initial product-direction record**

This document captures the high-level product intent and architectural direction agreed before detailed TWF design begins. It is not a final architecture specification and should not be treated as implementation authority where later architecture/decision records supersede it.

## 1. Product Name

The application is named **TradingWorkFlow (TWF)**.

TWF is a separate project and repository. It is not merely a UI for TradingIntelligence (TI) or TradeMonitor (TM); it is the trader-facing application that composes TI, TM, scanners, LLMs, brokers, and other current/future satellite systems into one coherent trading workflow.

## 2. Product Vision

TWF should become the primary operating surface for a trader. The long-term intent is to support discovery, watchlists, scanning, intelligence and analysis, LLM-assisted reasoning, candidate review, trade-expression review, risk and authority, broker state, execution coordination, position monitoring, alerts/notifications, history/audit, later feedback/learning, and future subscription/multi-user delivery.

The system should feel like one product even when the underlying capabilities are provided by independent services.

## 3. Core Product Principle

```text
Satellite services provide specialist capabilities.
TWF composes those capabilities into trader workflows.
```

```text
Scanner = discover / propose
TI      = assess / explain / forecast / advise
TM      = govern / authorize / supervise / reconcile
Broker  = execution truth
LLM     = reasoning / synthesis / interpretation
TWF     = trader-facing orchestration and workflow product
```

## 4. Separate Project / Repository

TWF should remain separate from TI and TM to preserve independent release cycles, deployment, product concerns, service boundaries, and future cloud/subscription flexibility. TWF may use generated clients, common schemas, or SDK packages later, but should not couple to another project's internals.

## 5. Web Application

TWF should be a web application because the target product requires a rich multi-panel workspace, cloud deployment, multi-user access, responsive UX, centralized updates, and realtime dashboards. The initial UX should be desktop-first while still being responsive.

## 6. Production Direction

Production TWF is expected to run in the cloud and serve multiple subscribed users. The miniature may begin in single-user/local-development mode, but the architecture should not assume one global user, one broker, one watchlist, or global mutable settings.

## 7. Minimal but Complete System

The first implementation should be a **miniature system that is complete in itself**. A representative workflow is:

```text
Login
  ↓
Trader workspace
  ↓
Watchlist / scanner
  ↓
Select candidate
  ↓
TI / active LLM analysis
  ↓
View thesis / claim / horizon / trade expression
  ↓
Send candidate into governed trade workflow
  ↓
TM risk / authority / position context
  ↓
Manual trader approval
  ↓
Execution/adoption boundary
  ↓
Position monitoring
  ↓
History / outcome
```

Some integrations may initially use mocks or local adapters, but the workflow itself should be coherent end-to-end.

## 8. Major TWF Areas

```text
Authentication / Users
Workspace / Session
Watchlists
Scanners
TradingIntelligence (TI)
TradeMonitor (TM)
Active LLM
Other Intelligence Services
Candidate Workflow
Trade Workflow
Orders / Positions / Monitoring
User Settings
Service / Plugin Configuration
Web Consoles
Notifications / Alerts
Audit / History
Future IFL feedback/learning visibility
```

## 9. UX Direction

The UX should feel application-like: persistent context, rapid instrument switching, live refresh, minimal page reloads, keyboard-friendly interactions where useful, user-configurable views, reusable panels, and explicit authority/risk state.

A possible long-term layout:

```text
┌─────────────────────────────────────────────────────────────────┐
│ User | Broker | Market | Active LLM | Alerts | System Status   │
├──────────────┬──────────────────────────────┬───────────────────┤
│ Watchlists   │ Instrument / Candidate       │ TI / LLM          │
│ Scanners     │ Analysis / Chart / Thesis    │ Intelligence      │
│ Alerts       │                              │                   │
├──────────────┴──────────────────────────────┼───────────────────┤
│ Positions / Orders / TM                    │ Risk / Actions    │
├─────────────────────────────────────────────┴───────────────────┤
│ Console / Events / Logs / Workflow History                    │
└─────────────────────────────────────────────────────────────────┘
```

This is directional, not frozen.

## 10. Web Consoles

Console surfaces should be first-class and reusable. Potential consoles include TI, TM, scanner, LLM/agent activity, system/event, and audit consoles. A reusable console should support timestamp, source/service, correlation/workflow ID, severity/state, filters, streaming updates, and optional command input where authority permits it.

## 11. LLM Direction

Normal operation should have one active primary top-tier LLM at a time, behind a provider-neutral logical service. OpenAI, Anthropic, Google, or future providers should be replaceable without redesigning TWF. The active LLM is configuration, not architecture.

## 12. Intelligence Services

TWF should consume stable logical services such as ScannerService, TIService, TMService, LLMService, BrokerService, NotificationService, and later IFLService. Each logical service may have LocalAdapter and RemoteAdapter implementations so deployment topology can evolve without changing business semantics.

## 13. Database Direction

Use a relational database. Start with SQLite if convenient, then move to PostgreSQL. Application/domain logic must not depend on SQLite-specific behavior.

```text
Application / Domain
        ↓
Repository interfaces
        ↓
Persistence adapters
        ↓
SQL abstraction / ORM
       ↓
SQLite → PostgreSQL
```

Migrations should be explicit and versioned from the beginning.

## 14. Multi-User / Subscription Readiness

Even before billing exists, model ownership cleanly:

```text
User
  ↓
Workspace / Account
  ↓
Watchlists
Settings
Broker connections
Candidates
Workflows
Layouts
History
```

Later subscription concepts such as plans, quotas, entitlements, and usage should be additive.

## 15. Configuration and Pluggability

TWF should support user/system configuration for active broker, active LLM, scanners, TI/TM endpoints, notification channels, watchlists, workspace layout, and defaults. The architecture must distinguish user preference, system configuration, service capability, security configuration, and trading authority configuration.

## 16. Security and Authority

The responsibility chain remains:

```text
TI advises.
TM governs.
Trader approves initially.
Broker is execution truth.
```

TWF coordinates and presents these states; it does not silently collapse them.

## 17. Service Integration Strategy

Preferred direction:

```text
TWF Backend
   ↓
Typed service clients/adapters
   ↓
Scanner / TI / TM / LLM / Broker services
```

Contracts should be versioned and local/remote adapters should share the same logical semantics.

## 18. Development Approach

Architecture/planning should primarily happen in ChatGPT web before major coding. Codex should be used mainly for bounded implementation tasks to conserve quota and reduce design churn.

```text
ChatGPT web
    architecture / design / docs / review
        ↓
Codex
    bounded coding
        ↓
Git repo
        ↓
changed files / ZIP back to ChatGPT when useful
```

## 19. Documentation Discipline

TWF should maintain strong authoritative documentation for product vision, architecture, roadmap, technology decisions, milestones, targets, contracts, UX, security, data, deployment, decisions, and acceptance records. Historical records should remain historical; current status should be maintained separately.

## 20. Milestone Philosophy

```text
Milestone
├── Target 1
├── Target 2
├── Target 3
└── Acceptance / closure
```

Milestones should be bounded and reviewable.

## 21. Preliminary Milestone Direction

```text
TWF-0  Product / Architecture Foundation
TWF-1  Application Foundation
TWF-2  Trader Workspace
TWF-3  Scanner Integration
TWF-4  TI Integration
TWF-5  TM Integration
TWF-6  Minimal Complete Trading Workflow
TWF-7  Realtime / Notifications
TWF-8  IFL / History / Learning Visibility
TWF-9  Multi-user / Subscription Readiness
TWF-10 Production Hardening
```

These identifiers remain provisional until roadmap acceptance.

## 22. Initial Architectural Invariants

1. TWF is a separate product/repository.
2. TWF is web-first.
3. Cloud/multi-user production is a design target from the start.
4. Satellite modules integrate as logical services.
5. Local/remote deployment must not change semantics.
6. LLM provider remains replaceable.
7. One active primary LLM is normal runtime configuration.
8. TI does not gain execution authority through TWF.
9. TM remains governance/risk/execution-supervision authority.
10. Broker state remains execution truth.
11. DB-specific behavior must not leak into application/domain logic.
12. SQLite-to-PostgreSQL replacement must be straightforward.
13. The first implementation should be miniature but end-to-end complete.
14. Configuration/pluggability are first-class concerns.
15. Workflow history and auditability should be preservable.
16. Responsive trader UX is a core product requirement.
17. Historical provenance survives model/service replacement.
18. Future IFL should fit without fundamental redesign.
19. Security/authority boundaries stay explicit.
20. TWF grows through bounded milestones.

## 23. Current Next Step

Create and review:

1. `TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md`
2. `TWF_DETAILED_ROADMAP.md`
3. `TWF_TECHNOLOGY_DECISION_RECORD.md`

Implementation scaffolding should begin only after these architecture documents are reviewed.

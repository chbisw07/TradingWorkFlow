# TradingWorkFlow (TWF) — UX Architecture

## Status
**TWF-0 accepted UX baseline, reconciled with configuration and UX buckets on 2026-09-25**

## 1. Purpose
Define the user-experience architecture for a fast, responsive, trader-oriented web application that unifies scanner, TI, TM, LLM, broker-facing state, alerts, consoles, and workflow history without collapsing their ownership boundaries.

## 2. UX North Star
> A trader should be able to discover, understand, decide, approve, monitor, and review without losing instrument or workflow context.

## 3. Core UX Principles
1. Desktop-first, responsive web application.
2. Persistent workspace rather than page-by-page navigation.
3. Minimal full-page reloads.
4. Instrument context remains visible while switching panels.
5. Service state and data freshness are explicit.
6. Analysis, recommendation, authority, and execution are visually distinct.
7. Fast keyboard/mouse workflows where safe.
8. Dense information without sacrificing legibility.
9. Every important action has clear state, ownership, and audit lineage.
10. Degraded service states are explicit, never silently hidden.

## 4. Primary Trader Journey
```text
Login
  ↓
Workspace
  ↓
Watchlist / Scanner
  ↓
Candidate / Instrument
  ↓
TI + Active LLM analysis
  ↓
Trader review
  ↓
TM risk / authority
  ↓
Manual approval
  ↓
Execution / adoption
  ↓
Position monitoring
  ↓
Close / history / future feedback
```

## 5. Application Shell
```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ User | Workspace | Broker | Market | Active LLM | Alerts | Service Health │
├──────────────┬────────────────────────────────────┬─────────────────────────┤
│ Watchlists   │ Instrument / Candidate Workspace   │ TI / LLM Intelligence   │
│ Scanners     │ Chart / Evidence / Thesis          │ Claims / Horizon         │
│ Alerts       │ Workflow State                     │ Trade Expression          │
├──────────────┴────────────────────────────────────┼─────────────────────────┤
│ Orders / Positions / TM                          │ Risk / Authority / Action │
├───────────────────────────────────────────────────┴─────────────────────────┤
│ Console / Events / Logs / Workflow History                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 6. Navigation Model
Primary areas:
- Home / Cockpit
- Watchlists
- Scanners
- Candidates
- Positions
- Orders
- Alerts
- History
- Consoles
- Setup / Settings

Navigation should preserve current instrument/workflow context where practical.

## 7. Workspace Model
A workspace is user-owned and may persist:
- selected watchlist;
- selected instrument;
- open panels/tabs;
- preferred layout;
- active broker/service configuration;
- active primary LLM;
- default horizons;
- display preferences.

## 8. Candidate Workspace
Must be able to show:
- scanner source/provenance;
- instrument details;
- chart/market context;
- TI thesis;
- primary/secondary claims;
- probability/category/value;
- horizon;
- evidence;
- producer/model provenance;
- advisory trade expression;
- TM status once handed off;
- workflow/audit timeline.

## 9. Distinct Visual Semantics
Do not visually conflate:
- intelligence/analysis;
- forecast;
- recommendation;
- trade expression;
- trader approval;
- TM authorization;
- broker execution truth.

Each should have distinct labels/state badges.

## 10. Realtime UX
Realtime updates may include:
- scanner candidates;
- market data snapshots;
- positions/orders;
- TM monitoring;
- alerts;
- service health;
- consoles.

Requirements:
- visible freshness timestamp;
- stale state indicator;
- reconnect state;
- no layout thrash;
- batched updates where needed;
- preserve user interaction during streams.

## 11. Console Architecture
Reusable `WebConsole` surface:
- timestamp;
- source/service;
- severity/state;
- correlation/workflow ID;
- message;
- structured metadata;
- filter/search;
- streaming append;
- optional command input only where explicitly authorized.

Potential instances:
- TI console
- TM console
- Scanner console
- LLM/Agent console
- System/Event console
- Audit console

## 12. Responsive Strategy
Priority:
1. desktop/laptop trading layout;
2. tablet review/monitoring;
3. mobile monitoring/alerts, not full dense trading cockpit initially.

## 13. Keyboard and Power-User UX
Potential shortcuts:
- instrument search;
- switch watchlist;
- next/previous candidate;
- open TI analysis;
- open TM panel;
- focus console;
- approve/reject only with safe confirmation policy.

No shortcut may bypass authority/security checks.

## 14. Loading / Empty / Stale / Error States
Every major panel must define:
- loading;
- empty;
- stale;
- unavailable;
- permission denied;
- version mismatch;
- degraded service;
- disconnected stream.

## 15. User Settings
Editable user preferences may include:
- theme;
- layout;
- watchlists;
- default panels;
- active primary LLM selection (within allowed providers);
- notification preferences;
- display precision.

Must not silently modify:
- trading authority;
- risk limits;
- broker permissions;
- service trust policy.

## 16. Accessibility
- keyboard navigation;
- focus visibility;
- sufficient contrast;
- semantic labels;
- scalable text;
- screen-reader-friendly controls where practical;
- avoid color as sole state indicator.

## 17. Performance UX Targets
Architectural targets:
- shell loads quickly;
- panel switching feels immediate;
- user input never blocked by slow external services;
- long TI/TM operations display progress/degraded state;
- streaming updates do not freeze UI.

Exact SLOs should be defined after prototype measurements.

## 18. Initial UX Acceptance
The complete miniature checkpoint belongs to TWF-6, with UX developed progressively through TWF-2–5. It should demonstrate:
- login;
- persistent shell;
- watchlist;
- scanner candidate;
- candidate workspace;
- TI response view;
- TM risk/authority view;
- manual approval state;
- position monitoring;
- console;
- workflow history.

## 19. Open Decisions
- component library;
- charting library;
- docking/resizable panel library;
- server-state library;
- keyboard command system;
- future theme preference synchronization; the local dark/light foundation is already accepted;
- browser notification strategy;
- TradingView embedding vs native charting.

## 20. UX Invariants
1. TWF remains the trader-facing orchestration product.
2. No UI state may silently become authority state.
3. Service ownership remains visible.
4. Staleness/failure is explicit.
5. Context is preserved across workflow stages.
6. Critical actions are auditable.
7. Fast/responsive feel is a product requirement.

## 21. Setup and UX Maturity

The [configuration architecture v0.6](TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md) defines Setup as feature → capability/provider → named profile, with progressive drill-down, clear ownership/scope and desired/effective/applied state. Show no more than about three navigation levels together on desktop; tablet/mobile use labelled nested views with breadcrumbs/back navigation, preserving unsaved edits and context.

Work/Administration contexts are useful in both APS and ACS when backend rights exist. Show realm, account and acting identity persistently. Switching context cannot elevate privilege. Unsupported administration remains an honest unavailable preview. Discovery may show sanitized unavailable/upgrade cards; internal capabilities stay hidden. Configuration repair must remain available to authorized actors even while capability use is disabled.

The [UX Bucket Roadmap](TWF_UX_BUCKET_ROADMAP.md) defines UX-B1 foundation, UX-B2 operational trading and UX-B3 mature architecture coverage. These complement functional milestones; TWF-1 completion does not require trading screens or all UX-B1 features assigned to TWF-2. UX-B2/B3 panel details evolve with real contracts. Preserve accepted token/theme quality, all eight shell states, responsive recomposition and authority/provenance across devices. Synthetic fixtures must be labelled and contract-tested; a successful mock is not live service or trading authorization.

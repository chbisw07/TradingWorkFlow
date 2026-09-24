# TradingWorkFlow (TWF) — Responsive Trading Application Architecture

## Status

**Normative architecture clarification**

This document extends the accepted TWF architecture with an explicit product principle:

> **TWF is not a responsive website. TWF is a responsive trading application.**

This clarification does not reopen or invalidate the accepted TWF-0 architecture baseline. It makes explicit a requirement that should govern UX, frontend architecture, testing, cloud deployment, and later trader-workflow implementation.

---

# 1. Purpose

Define the architectural requirements needed for TradingWorkFlow to:

- run locally and in cloud deployment without application redesign;
- provide a fast, professional, long-session trader UX;
- work across major modern browsers;
- recompose correctly across desktop, large desktop, ultrawide, tablet, and mobile;
- host dynamic charts, tables, grids, consoles, and streaming data;
- preserve workflow semantics and authority meaning across form factors;
- remain suitable for a primary power user while supporting future subscribers.

---

# 2. Product Principle

TWF should be designed as an application workspace, not as a collection of responsive web pages.

A responsive website often:

```text
reflows content
shrinks cards
stacks sections
```

A responsive trading application must additionally preserve:

```text
workflow context
instrument context
live state
authority semantics
information density
interaction speed
panel purpose
data freshness
decision continuity
```

Therefore:

> **Responsive behavior means recomposition, not merely shrinking.**

---

# 3. Primary User and Future Subscribers

The primary design target is a power-user trader who may use TWF for long sessions.

The architecture must simultaneously remain suitable for later multi-user/subscription deployment.

```text
Primary UX target:
    power-user trader

Architecture constraint:
    future multi-user / subscription readiness
```

Do not dilute the experience into a generic SaaS dashboard.

---

# 4. Cloud Portability Requirement

TWF must be deployable in the cloud without changing application/domain architecture.

Local and cloud environments may differ in:

- configuration;
- database engine;
- service endpoints;
- TLS/ingress;
- scaling;
- observability;
- secret management;
- caching/workers;
- deployment topology.

They must not require different:

- workflow semantics;
- domain models;
- service contracts;
- authority rules;
- frontend feature logic.

Conceptually:

```text
LOCAL
Browser
  ↓
Next.js
  ↓
FastAPI
  ↓
SQLite
  ↓
local/synthetic services
```

```text
CLOUD
Browser
  ↓ HTTPS/CDN
Next.js
  ↓
FastAPI
  ↓
PostgreSQL
  ↓
remote/local TI / TM / Scanner / LLM services
```

Infrastructure may evolve; business semantics must remain stable.

---

# 5. Browser Compatibility Requirement

TWF should explicitly support major modern browser families.

Target support:

```text
Desktop
├── Google Chrome / Chromium
├── Microsoft Edge
└── Apple Safari / WebKit

Mobile / Tablet
├── Safari on iOS / iPadOS
└── Chrome on Android
```

Support is intended for current/recent browser versions, not legacy browsers.

Browser compatibility must be treated as a tested product requirement.

---

# 6. Browser Architecture Rules

Frontend implementation should prefer mature web standards.

Avoid introducing browser-specific dependencies when a standards-based solution exists.

For browser-sensitive functionality:

- feature-detect when appropriate;
- provide safe fallbacks;
- avoid assuming Chromium-only behavior;
- validate date/time formatting;
- validate viewport units;
- validate sticky/fixed positioning;
- validate scrolling/overflow;
- validate WebSocket/SSE behavior;
- validate focus/keyboard behavior;
- validate touch interactions.

Safari/WebKit must be considered during frontend design, not only after desktop Chromium implementation.

---

# 7. Viewport / Form-Factor Matrix

TWF should be architected for at least these representative widths:

```text
390px       mobile monitoring shell
768px       tablet / portrait
1024px      compact desktop / tablet landscape
1440px      standard trading desktop
1920px      large desktop
2560px+     ultrawide / multi-panel workstation
```

These are architecture/test reference widths, not rigid device classes.

---

# 8. Desktop Trading Experience

Desktop is the primary full trading experience.

At approximately 1440px and above, the application should be capable of displaying:

- navigation;
- scanner/watchlist context;
- instrument/candidate workspace;
- TI/LLM intelligence;
- positions/orders/TM state;
- risk/authority/action context;
- console/events/history.

Large displays should use extra space intelligently rather than simply stretch controls.

---

# 9. Large Desktop / Ultrawide Experience

At 1920px–2560px+:

- additional panels may remain visible simultaneously;
- more rows/columns may be shown;
- intelligence/risk/console panels may coexist;
- useful whitespace should remain;
- typography/control sizes should not inflate unnecessarily.

TWF should eventually support multi-monitor-friendly workflows without requiring a new application architecture.

---

# 10. Tablet Experience

Tablet should recompose the desktop workspace.

Possible behavior:

```text
compact navigation
        ↓
main workspace
        ↓
tabbed / stacked intelligence + actions
        ↓
positions / console
```

Do not force all desktop panels side-by-side.

Touch targets and scrolling behavior must remain usable.

---

# 11. Mobile Experience

Mobile should initially prioritize:

- monitoring;
- alerts;
- selected instrument summary;
- position status;
- TI summary;
- approval/review where safe;
- workflow status.

The initial mobile experience is not required to reproduce the entire dense desktop cockpit.

It must remain semantically consistent with desktop.

---

# 12. Semantic Invariance Across Form Factors

Critical invariant:

> **Screen size may change presentation and composition, but must not change workflow meaning, authority state, data semantics, or provenance.**

For example:

```text
Desktop:
TM Authority = REJECTED

Mobile:
TM Authority = REJECTED
```

The mobile UI may present it differently, but must not reinterpret it.

---

# 13. Dynamic Content Readiness

The application shell and panel architecture must be able to host later dynamic components such as:

```text
Candlestick / price charts
P&L charts
forecast / probability charts
sector / ranking charts

Watchlist tables
scanner tables
candidate tables
orders
positions
trade history
option-chain style grids

Live consoles
event streams
alerts
service health
```

TWF-1.1 does not need to implement these components.

It must not make them difficult to add later.

---

# 14. Chart Readiness

Chart containers should support:

- responsive width/height;
- resize observation;
- loading/empty/error states;
- streaming updates later;
- overlays/annotations later;
- full-screen/expanded modes later.

The charting library remains a separate technology decision.

---

# 15. Table / Grid Readiness

Future large data surfaces may require:

- sorting;
- filtering;
- column resizing;
- pinning;
- keyboard navigation;
- row virtualization;
- live row updates;
- dense display modes.

Do not choose a grid library in TWF-1.1.

Layout architecture must leave room for these capabilities.

---

# 16. Streaming UI Readiness

Future streams may include:

- scanner candidates;
- market updates;
- orders;
- fills;
- positions;
- TM risk/authority changes;
- service-health changes;
- alerts;
- console events.

Frontend architecture should support localized state updates rather than full-page rerenders.

TWF-1.1 should establish stable panel boundaries that can later own their own live state.

---

# 17. Performance Philosophy

Trader-perceived performance is a product requirement.

Target behavior:

- shell interaction feels immediate;
- panel switching feels immediate;
- slow remote services do not freeze the UI;
- dynamic updates do not cause layout thrash;
- expensive charts/grids remain isolated;
- rendering work is localized;
- stale states remain visible;
- background requests are cancellable or replaceable where appropriate.

Exact numerical performance SLOs should be established after realistic prototypes.

---

# 18. Long-Session Ergonomics

TWF may remain open for hours.

Design should consider:

- low visual fatigue;
- restrained contrast;
- predictable layout;
- minimal unnecessary motion;
- clear focus states;
- persistent context;
- readable dense data;
- configurable workspace evolution.

---

# 19. Visual Quality Requirement

TWF should feel like a premium professional trading product.

Target qualities:

```text
PREMIUM
CALM
FAST
DENSE_BUT_READABLE
CONTEXT_PRESERVING
TRADER_FIRST
RESPONSIVE
CONSISTENT
TRUSTWORTHY
```

Avoid:

```text
GENERIC_ADMIN_DASHBOARD
OVER_ANIMATED
COLOR_HEAVY
GIMMICKY
CLUTTERED
TEMPLATE_LIKE
```

---

# 20. Motion / Animation

Motion should explain state, not decorate the application.

Use subtle transitions for:

- panel changes;
- disclosure;
- status transitions;
- loading/progress;
- responsive reflow.

Avoid:

- gratuitous entrance animation;
- constant motion;
- animation that delays user action;
- animation that obscures live state changes.

Respect reduced-motion preferences.

---

# 21. Touch and Pointer Input

Components should support both pointer and touch use where relevant.

Tablet/mobile controls should provide usable touch targets.

Hover-only information must not be essential.

Critical actions should not rely on gestures without visible alternatives.

---

# 22. Keyboard / Power-User Readiness

Desktop TWF should evolve toward strong keyboard workflows.

The shell should not block later support for:

- command palette;
- instrument search;
- candidate navigation;
- focus shortcuts;
- panel shortcuts;
- quick workflow actions.

Keyboard shortcuts must never bypass security or TM authority checks.

---

# 23. Accessibility

Baseline requirements:

- semantic landmarks;
- logical headings;
- keyboard navigation;
- visible focus;
- sufficient contrast;
- accessible labels;
- no color-only state indication;
- reduced-motion support;
- responsive text/layout behavior.

Accessibility supports power-user usability as well as inclusivity.

---

# 24. Cross-Browser Testing Strategy

Browser compatibility should eventually be automated.

Preferred browser engines for automated acceptance:

```text
Chromium
WebKit
```

Firefox may be added when justified.

TWF-1.1 may introduce a minimal Playwright smoke suite if it can be done without unnecessary complexity.

Representative test dimensions:

```text
1440px Chromium
1440px WebKit
1024px Chromium/WebKit
768px WebKit
390px WebKit / Chromium emulation
```

Exact matrix may evolve.

---

# 25. TWF-1.1 Requirements

The Frontend Shell target should establish:

- desktop-first shell;
- coherent tablet/mobile recomposition;
- centralized design tokens;
- responsive panel containers;
- accessible navigation;
- state primitives;
- browser-safe CSS patterns;
- visual-quality baseline;
- cross-browser smoke-test foundation where practical.

It must not yet implement real:

- scanner;
- charts;
- tables/grids;
- TI;
- TM;
- broker;
- LLM;
- streaming data.

---

# 26. Cloud and Browser Acceptance Invariants

1. No separate cloud codebase.
2. No Chromium-only product architecture.
3. No desktop-only layout architecture.
4. No mobile semantics that differ from desktop semantics.
5. No UI component may silently change authority meaning by form factor.
6. Dynamic content must fit within stable panel contracts.
7. Charts/tables may be added later without shell redesign.
8. Long-running streams must not require page-level rerender architecture.
9. TWF remains usable on large/ultrawide screens.
10. Progressive enhancement is preferred over browser-specific divergence.

---

# 27. Compatibility Matrix

| Capability | Requirement |
|---|---|
| Local development | REQUIRED |
| Docker deployment | REQUIRED |
| Cloud deployment without app redesign | REQUIRED |
| Chrome / Chromium | REQUIRED |
| Microsoft Edge | REQUIRED |
| Safari / WebKit | REQUIRED |
| iPad/tablet | REQUIRED |
| Mobile monitoring shell | REQUIRED |
| Large desktop | REQUIRED |
| Ultrawide readiness | REQUIRED |
| Dynamic tables/grids | ARCHITECTURE-READY |
| Live charts | ARCHITECTURE-READY |
| Streaming updates | ARCHITECTURE-READY |
| Web consoles | REQUIRED / architecture-ready |
| Keyboard navigation | REQUIRED baseline |
| Touch interaction | REQUIRED where applicable |
| Reduced motion | REQUIRED baseline |

---

# 28. Status

This clarification is normative for frontend and UX work beginning with TWF-1.1.

It should be referenced by:

- root README;
- documentation index;
- TWF-1.1 implementation record;
- future UX acceptance records.

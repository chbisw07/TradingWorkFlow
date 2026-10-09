# TradingWorkFlow (TWF) — Documentation Index

## Options O1 — active development

[Options architecture](TWF_OPTIONS_ARCHITECTURE.md) defines the provider-neutral
`OptionContract`, exact Zerodha execution mapping, capability model, lot/expiry/strike
semantics, Broker V2 preview and confirmation path, unmanaged external positions, and the
O1–O10 roadmap. O1 is active development and does not implement Derivatives Scanner,
option-chain analytics, multi-leg execution, or automated live trading.

## Scanner V2 — 2026-10-07 implementation

[Scanner V2 architecture and validation](TWF_SCANNER_V2_ARCHITECTURE.md) records
the fresh `/scanners` workspace, Dhan daily filter engine, immutable Watchlist
universes, saved configurations/runs, optional TapTide screens and Watchlist
handoff. Historical Discovery and accepted Broker V1/V2 remain intact.
Implemented / pending user validation, **not accepted or frozen**. Verified
constituent/sector/market universes and full derivatives remain capability gaps.

> **2026-10-02 active provider map:** Dhan is the first authoritative `MarketDataProvider`; TapTide is the first optional `MarketIntelligenceProvider`; TradingView is historical/decommissioned from active S&D. Generic MCP and historical provenance remain. The Dhan/TapTide migration is implemented and pending user validation; no commit/tag/freeze is claimed.

## Current Watchlists implementation

- [Watchlists architecture](TWF_WATCHLIST_ARCHITECTURE.md): owner-scoped editable
  collections plus centrally cached read-only Nifty system universes, canonical
  identities, official constituent provenance/staleness, copy semantics, Dhan
  overlays, broker independence and immutable Scanner V2 universe snapshots. F&O
  50/100 are explicitly Definition pending.
- [Watchlists implementation report](TWF_WATCHLIST_IMPLEMENTATION_REPORT.md): validation,
  screenshot evidence, live authorization limitations and scorecard. Implemented / ready
  for user validation; not accepted or frozen.

## Status

**Authoritative documentation map for TWF**

Current architecture gate:

```text
TWF-0 ACCEPTED / FROZEN
GO_TWF1
Configuration v0.6 reconciled / GO_TWF1_5
TWF-1.5 ACCEPTED / committed 664d4cf
TWF-1.6 ACCEPTED / committed e3852d3
TWF-1 ACCEPTED / FROZEN (twf-1-application-foundation)
Broker Workspace Architecture v0.3 REVIEWED / ACCEPTED / TAGGED (twf-broker-workspace-architecture-v0.3)
Broker V1 real broker read-only foundation ACCEPTED / FROZEN (twf-broker-v1)
Broker V2 manual trading foundation ACCEPTED / FROZEN (twf-broker-v2)
Options O1 extension ACTIVE DEVELOPMENT
BW-1–BW-6 retained as historical gate inventory; V1/V2 acceptance recorded separately
S&D / Opportunity-domain / Sprint-2 architecture ACCEPTED / IMPLEMENTATION AUTHORIZED
Scan-driven temporal state (2026-10-02) IMPLEMENTED / PENDING USER VALIDATION AND INDEPENDENT ACCEPTANCE
Sprint 2 IMPLEMENTED / READY FOR USER VALIDATION; final acceptance/freeze pending
S2-1 and S2-2 ACCEPTED / FROZEN; S2-3A integrated; historical TradingView S2-3 ACCEPTED / FROZEN WITH DEFERRED HARDENING; active Dhan/TapTide migration IMPLEMENTED / READY FOR USER VALIDATION
```

---

## 1. Documentation Authority Model

```text
Vision / Intent
Architecture
Planning / Engineering
Acceptance / Closure
Implementation Records
```

Where both Markdown and DOCX versions exist:

```text
Markdown = normative repository source
DOCX     = polished visual/reference companion
```

Historical/accepted records remain historical unless an explicit later record supersedes them.
The [configuration review](TWF_CONFIGURATION_SETUP_ARCHITECTURE_REVIEW.md) records the
2026-09-25 clarification without reopening TWF-0. Configuration Markdown v0.6
is the accepted design basis, with an accepted v0.7 S&D
extension. Its supplied DOCX remains an unchanged **v0.5 reference snapshot**.
Broker Workspace Markdown/DOCX remain synchronized at v0.3 and unchanged here.
The 2026-09-28 S&D reconciliation is Markdown-only: affected DOCX companions below
are stale and await regeneration. Four additional untracked DOCX companions were
present at the 2026-09-29 review start; their synchronization has not been verified.
No historical acceptance record is rewritten. The current S&D acceptance authorizes
only bounded implementation under the delivery plan, without reopening or falsely
freezing the baseline. Markdown remains normative; no DOCX overrides it.

---

Accepted implementation and exact local setup:
[Broker V1 read-only foundation](TWF_BROKER_V1_VERTICAL_SLICE.md) and
[Broker V2 manual trading foundation](TWF_BROKER_V2_MANUAL_ORDER_ENTRY.md).
The latter records opt-in manual authority, real smoke, LTP, read-model fixes,
validation and non-blocking limitations. Historical architecture and review
records remain unchanged; current runtime acceptance is in these versioned records.

## 2. Core Entry Documents

| Document                                        | Role                                                                                   | Authority                          |
| ----------------------------------------------- | -------------------------------------------------------------------------------------- | ---------------------------------- |
| [`README.md`](../README.md)                     | Human entry point and current-status dashboard                                         | Navigation / status                |
| `TWF_DOCUMENTATION_INDEX.md`                    | Canonical documentation map                                                            | Authoritative map                  |
| `TWF_HIGH_LEVEL_DISCUSSION_RECORD.md`           | Initial product discussion and intent                                                  | Historical / contextual            |
| `TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md` | Product purpose and high-level system design                                           | Normative architecture             |
| `TWF_DETAILED_ROADMAP.md`                       | Milestones, targets, sequencing                                                        | Normative planning                 |
| `TWF_TECHNOLOGY_DECISION_RECORD.md`             | Technology baseline and open decisions                                                 | Decision record                    |
| `TWF_TWF0_ARCHITECTURE_ACCEPTANCE_REVIEW.md`    | Formal TWF-0 architecture acceptance                                                   | Acceptance authority               |
| `TWF_LOCAL_DEVELOPMENT_SETUP_LINUX.md`          | Ubuntu/Linux local developer setup, validation, startup, shutdown, and troubleshooting | Developer operations / setup guide |

---

## 3. Architecture Documents

### Master / Component

- `TWF_MASTER_PRODUCT_ARCHITECTURE.docx` — visual/reference
- `TWF_COMPONENT_ARCHITECTURE.docx` — visual/reference
- `TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md` — normative

### UX

- [Responsive Trading Application Architecture](TWF_RESPONSIVE_TRADING_APPLICATION_ARCHITECTURE.md) — normative responsive application clarification
- `TWF_UX_ARCHITECTURE.md` — normative
- [UX Bucket Roadmap](TWF_UX_BUCKET_ROADMAP.md) — normative cross-cutting maturity plan v0.3; UX-B1/B2 partial, UX-B3 planned; accepted Broker V1/V2 evidence recorded
- `TWF_UX_ARCHITECTURE.docx` — reference

### Configuration / Setup

- [Configuration, Setup, Capability, Entitlement and Pluggability Architecture](TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md) — sole normative configuration source, reconciled v0.6
- `TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.docx` — supplied v0.5 reference, unchanged
- [Configuration Architecture Review](TWF_CONFIGURATION_SETUP_ARCHITECTURE_REVIEW.md) — corpus, decisions, gaps, changes and TWF-1.5 readiness; does not duplicate normative design

### Broker Workspace

- [Broker Workspace Architecture](TWF_BROKER_WORKSPACE_ARCHITECTURE.md) — sole normative broker design v0.3, independently reviewed and accepted at annotated tag `twf-broker-workspace-architecture-v0.3`
- `TWF_BROKER_WORKSPACE_ARCHITECTURE.docx` — synchronized v0.3 presentation companion
- [Broker Workspace Architecture Review](TWF_BROKER_WORKSPACE_ARCHITECTURE_REVIEW.md) — evidence, findings, reconciliation, gap timing and implementation gates; no competing design

### Data

- `TWF_DATA_ARCHITECTURE.md` — normative
- `TWF_DATA_ARCHITECTURE.docx` — reference

### Security / Authentication

- `TWF_SECURITY_AUTH_ARCHITECTURE.md` — normative
- `TWF_SECURITY_AUTH_ARCHITECTURE.docx` — reference

### Deployment

- `TWF_DEPLOYMENT_ARCHITECTURE.md` — normative
- `TWF_DEPLOYMENT_ARCHITECTURE.docx` — reference

---

## 4. Service / Integration Documents

| Document                                  | Authority                                                |
| ----------------------------------------- | -------------------------------------------------------- |
| `TWF_SERVICE_CONTRACT_ARCHITECTURE.md`    | Normative                                                |
| `TWF_SERVICE_CONTRACT_ARCHITECTURE.docx`  | Reference                                                |
| `TWF_SERVICE_INTEGRATION_ARCHITECTURE.md` | Normative                                                |
| `TWF_TI_INTEGRATION_CONTRACT.md`          | Architecture-stage normative                             |
| `TWF_TM_INTEGRATION_CONTRACT.md`          | Provisional until clean TM public-surface reconciliation |

---

## 5. Planning / Engineering

- `TWF_DETAILED_ROADMAP.md`
- `TWF_TECHNOLOGY_DECISION_RECORD.md`
- `TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.md`
- `TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.docx`

### Developer operations

- [Ubuntu/Linux Local Development Setup](TWF_LOCAL_DEVELOPMENT_SETUP_LINUX.md)
  — setup, validation, native and Docker workflows, shutdown, and troubleshooting.

---

## 6. Acceptance / Readiness

### Gate template

`TWF_TWF0_ARCHITECTURE_ACCEPTANCE_AND_CODING_READINESS.md`

`TWF_TWF0_ARCHITECTURE_ACCEPTANCE_AND_CODING_READINESS.docx` — historical reference companion

Purpose:

- defines the criteria;
- remains the gate specification.

### Accepted review

`TWF_TWF0_ARCHITECTURE_ACCEPTANCE_REVIEW.md`

Purpose:

- applies the gate;
- records `GO_TWF1`;
- authorizes bounded TWF-1 coding.

Authority:

```text
TWF_TWF0_ARCHITECTURE_ACCEPTANCE_REVIEW.md
    supersedes the template's NOT YET ACCEPTED status
    without rewriting the historical template.
```

---

### Configuration reconciliation checkpoint

[Configuration Architecture Review](TWF_CONFIGURATION_SETUP_ARCHITECTURE_REVIEW.md)
records `GO_TWF1_5` under configuration v0.6. This accepts the bounded next-target
architecture; it does not claim SaaS administration, billing or UX bucket completion.

## 7. Current Phase

```text
TWF-0 — ACCEPTED / FROZEN (twf-0-architecture-baseline)
       ↓
TWF-1 — APPLICATION FOUNDATION / ACCEPTED / FROZEN (twf-1-application-foundation)
├── TWF-1.0 — REPOSITORY SCAFFOLD / ACCEPTED
├── TWF-1.1 — FRONTEND SHELL / ACCEPTED (twf-1.1-frontend-shell)
├── TWF-1.1A — THEME SWITCHING / ACCEPTED (twf-1.1a-theme-switching)
├── TWF-1.2 — BACKEND SHELL / ACCEPTED (twf-1.2-backend-shell)
├── TWF-1.3 — DATABASE FOUNDATION / ACCEPTED
├── TWF-1.4 — USER / LOGIN FOUNDATION / ACCEPTED AFTER BOUNDED FIXES (ba9bb8b)
├── Configuration reconciliation — REVIEWED v0.6 / GO_TWF1_5
├── TWF-1.5 — SETTINGS FOUNDATION / ACCEPTED / committed 664d4cf
└── TWF-1.6 — SERVICE CLIENT FOUNDATION / ACCEPTED / committed e3852d3

UX workstream (parallel to functional milestones)
├── UX-B1 — FOUNDATIONAL COMPLETE UX / PARTIAL
├── UX-B2 — OPERATIONALLY USEFUL TRADING UX / PARTIAL (bounded Broker V1/V2 evidence)
└── UX-B3 — ARCHITECTURE-COMPLETE UX / PLANNED

Broker Workspace Architecture v0.3 — REVIEWED / ACCEPTED / TAGGED
Broker Workspace Workstream — current acceptances followed by historical gate inventory
├── Broker V1 real broker read-only foundation — ACCEPTED / FROZEN
├── Broker V2 manual trading foundation — ACCEPTED / FROZEN
├── BW-1 Synthetic Broker Read-Only Foundation — HISTORICAL GATE
├── BW-2 One real broker read-only — PENDING
├── BW-3 Broker watchlists and draft/preview — PENDING
├── BW-4 Synthetic command and recovery foundation — PENDING
├── BW-5 Controlled live manual orders — PENDING
├── BW-6 Second real broker proof — PENDING
└── Later managed workflow — PENDING (separate TWF-5 gate)
```

Implementation records:

- [Broker V1](TWF_BROKER_V1_VERTICAL_SLICE.md) — accepted/frozen read-only foundation;
  authoritative holdings and position read-model semantics, including V2 corrections.
- [Broker V2](TWF_BROKER_V2_MANUAL_ORDER_ENTRY.md) — accepted/frozen manual trading
  foundation; final tag target `twf-broker-v2`. Earlier working name: Broker V2.1.
- [Options Architecture](TWF_OPTIONS_ARCHITECTURE.md) — active O1 domain and Broker V2
  single-leg option extension; not accepted/frozen and no live order validation claim.

- [TWF-1.0 Repository / Project Scaffold](TWF_TWF1_0_REPOSITORY_PROJECT_SCAFFOLD.md)
  — authoritative bounded implementation record, developer commands, inventory,
  and validation evidence for the accepted historical scaffold.
- [TWF-1.1 Frontend Shell](TWF_TWF1_1_FRONTEND_SHELL.md)
  — historical implementation evidence for the accepted shell baseline.
- [TWF-1.1A Theme Switching Foundation](TWF_TWF1_1A_THEME_SWITCHING_FOUNDATION.md)
  — historical implementation evidence for the accepted theme foundation.
- [TWF-1.2 Backend Shell](TWF_TWF1_2_BACKEND_SHELL.md)
  — historical implementation evidence for the accepted backend shell.
- [TWF-1.3 Database Foundation](TWF_TWF1_3_DATABASE_FOUNDATION.md)
  — historical implementation evidence for the accepted database foundation.
- [TWF-1.4 User / Login Foundation](TWF_TWF1_4_USER_LOGIN_FOUNDATION.md)
  — historical identity, credential, session, login UI, CSRF and migration evidence.
  Its pending-re-review wording predates the accepted `ba9bb8b` commit; current status
  is recorded here and in README without rewriting that implementation history.
- [TWF-1.5 Settings Foundation](TWF_TWF1_5_SETTINGS_FOUNDATION.md)
  — implemented personal preferences, validated profiles, revision checks and Setup UI;
  accepted and committed at `664d4cf`; its record retains historical pre-review evidence.
- [TWF-1.6 Service Client Foundation](TWF_TWF1_6_SERVICE_CLIENT_FOUNDATION.md)
  — typed local/remote/synthetic health adapters, safe configuration/transport,
  authenticated status and minimal UX-B1 panel; accepted by commit `e3852d3`, part of
  tagged TWF-1 closure. Its pre-review record remains historical. The current status
  reconciliation and exact commit/tag evidence are recorded in the broker review.

---

## 8. TWF-1 Authorized Targets

```text
TWF-1.0 Repository / Project Scaffold
TWF-1.1 Frontend Shell
TWF-1.1A Theme Switching Foundation
TWF-1.2 Backend Shell
TWF-1.3 Database Foundation
TWF-1.4 User / Login Foundation
TWF-1.5 Settings Foundation
TWF-1.6 Service Client Foundation
```

The BW labels are a cross-cutting delivery workstream mapped into TWF-2/TWF-6;
they do not replace or renumber the TWF-0–10 milestones. Later milestones remain
separately gated. Broker V1/V2 are accepted; the [original broker delivery plan](TWF_BROKER_WORKSPACE_ARCHITECTURE.md#34-bounded-delivery-and-acceptance-gates)
is historical context, not a claim that manual trading remains unimplemented.
Modify/cancel, additional brokers, Alerts-managed exits and intelligence integrations
remain future work.

---

## 9. Recommended Reading Paths

### Product / Trader

```text
../README.md
→ TWF_HIGH_LEVEL_DISCUSSION_RECORD.md
→ TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md
→ TWF_UX_ARCHITECTURE.md
→ TWF_DETAILED_ROADMAP.md
```

### Architect

```text
TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md
→ master/component DOCX companions
→ TWF_SERVICE_CONTRACT_ARCHITECTURE.md
→ TWF_DATA_ARCHITECTURE.md
→ TWF_SECURITY_AUTH_ARCHITECTURE.md
→ TWF_DEPLOYMENT_ARCHITECTURE.md
→ TWF_TWF0_ARCHITECTURE_ACCEPTANCE_REVIEW.md
→ TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md
→ TWF_UX_BUCKET_ROADMAP.md
→ TWF_CONFIGURATION_SETUP_ARCHITECTURE_REVIEW.md
```

### Developer

```text
TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.md
→ TWF_LOCAL_DEVELOPMENT_SETUP_LINUX.md
→ TWF_TECHNOLOGY_DECISION_RECORD.md
→ TWF_SERVICE_INTEGRATION_ARCHITECTURE.md
→ TWF_DETAILED_ROADMAP.md
→ TWF_TWF0_ARCHITECTURE_ACCEPTANCE_REVIEW.md
```

---

## 10. Maintenance Rules

When new documents are added:

1. add them here;
2. state purpose and authority;
3. update root README when current status changes;
4. preserve prior acceptance/history;
5. avoid duplicate competing normative documents;
6. keep the broker DOCX synchronized with its normative Markdown when that architecture changes.

## Scan-driven temporal architecture amendment — 2026-10-01

[TWF_SND_SCAN_DRIVEN_TEMPORAL_STATE_ARCHITECTURE.md](TWF_SND_SCAN_DRIVEN_TEMPORAL_STATE_ARCHITECTURE.md) is the focused normative design and implementation record for immutable scan observations, semantic comparability/coverage, scan-driven lifecycle, bounded logical HOT/COLD storage, ordered recovery and additive migration. Decision: **ACCEPT WITH REFINEMENT / GO_IMPLEMENTATION**; implementation: **IMPLEMENTED / PENDING USER VALIDATION AND INDEPENDENT ACCEPTANCE**. It overrides earlier S&D time-derived lifecycle rules, including the dated data-architecture GET-expiry wording, with independent freshness/window-validity projections. Other accepted architecture and security boundaries remain, and Sprint 2 is not accepted/frozen by this implementation.

The current runtime is still governed as implemented by the Sprint-2 implementation record. U1/U2 and earlier acceptance history remain recorded separately; this amendment supplies no runtime acceptance or freeze. The S&D and Opportunity Markdown sources reference the amendment; their DOCX companions remain historical/stale and are not regenerated in this Markdown-only task. No DOCX overrides this design.

## 11. Scan & Discover acceptance — 2026-09-29

| Document                                                                                                            | Authority / status                                                                                                                                                                      |
| ------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [Scan & Discover Architecture](TWF_SCAN_AND_DISCOVER_ARCHITECTURE.md)                                               | Accepted normative subsystem design: providers, evidence, temporal/lifecycle/relevance policies, optional LLM, UX and diagrams                                                          |
| [Market Data Provider Architecture](TWF_MARKET_DATA_PROVIDER_ARCHITECTURE.md)                                       | Current normative Dhan-first authoritative market-data contract, exact-series Evidence Chart invariant, and Zerodha compatibility                                                       |
| [Market Intelligence Provider Architecture](TWF_MARKET_INTELLIGENCE_PROVIDER_ARCHITECTURE.md)                       | Current normative optional TapTide MI contract, bounded capabilities, generic MCP reuse, provenance, caching, and failure isolation                                                     |
| [Opportunity Domain Architecture](TWF_OPPORTUNITY_DOMAIN_ARCHITECTURE.md)                                           | Accepted normative shared identities, stage distinctions and ownership; future objects are not implemented                                                                              |
| [Sprint-2 Delivery Plan](TWF_SPRINT2_SCAN_DISCOVER_DELIVERY_PLAN.md)                                                | Accepted normative bounded delivery/gates; ends at DiscoveryCandidate                                                                                                                   |
| [Architecture Reconciliation Record](TWF_SCAN_DISCOVER_ARCHITECTURE_RECONCILIATION.md)                              | Reference audit: baseline, affected/unchanged documents, contradictions, companion staleness and review matrix                                                                          |
| [Independent Architecture Acceptance Review](TWF_SCAN_DISCOVER_ARCHITECTURE_ACCEPTANCE_REVIEW.md)                   | Acceptance authority: scorecard, findings, bounded implementation authorization and next gate                                                                                           |
| [S2-1 Domain Contracts & Synthetic Provider Foundation](TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION.md) | Implementation record: contracts, deterministic synthetic proofs, validation and deferred scope; ACCEPTED / FROZEN, not acceptance authority                                            |
| [S2-1 Independent Acceptance Review](TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION_ACCEPTANCE_REVIEW.md)  | Historical HOLD_S2_1 decision and S21-01/02/03 findings; preserved unchanged; superseded for current status by focused re-review                                                        |
| [S2-1 Focused Re-review](TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION_REREVIEW.md)                       | Independent acceptance: GO_S2_2; closes S21-01/02/03; S2-2 Internal Scanner V0 only                                                                                                     |
| [S2-2 Internal Scanner V0](TWF_S2_2_INTERNAL_SCANNER_V0.md)                                                         | Implementation record: offline native provider, 23 metrics, five profiles, look-ahead and interoperability proofs; ACCEPTED / FROZEN; implementation evidence, not acceptance authority |
| [S2-2 Focused Re-review](TWF_S2_2_INTERNAL_SCANNER_V0_REREVIEW.md)                                                  | Independent acceptance: closes S22-01; GO_S2_3 for Real Scan Provider Integration (TradingView MCP first) only                                                                          |
| [S2-3A Generic MCP Connection & Authentication](TWF_S2_3A_GENERIC_MCP_PROVIDER_CONNECTION_AUTH_FOUNDATION.md)       | DURABILITY REMEDIATED / INTEGRATED INTO S2-3; provider-neutral auth/transport durability incorporated into S2-3; live response verification outstanding                                 |
| [S2-3 TradingView MCP ScanProvider](TWF_S2_3_TRADINGVIEW_MCP_SCAN_PROVIDER_IMPLEMENTATION.md)                       | HISTORICAL / DECOMMISSIONED from active runtime; accepted implementation/evaluation evidence and original limitations preserved                                                         |
| [S2-3 Acceptance Record](TWF_S2_3_ACCEPTANCE_REVIEW.md)                                                             | Final disposition: ACCEPT_S2_3_WITH_DEFERRED_HARDENING; preserves historical HOLD and live 429 evidence                                                                                 |
| [S2-3 Deferred/Hardening Register](TWF_S2_3_DEFERRED_ISSUES_AND_HARDENING_REGISTER.md)                              | Mandatory Sprint-2 Hardening input: successful-live-row proof, remote revocation, provider/dependency/MCP/time follow-ups                                                               |
| [Integrated Sprint-2 Implementation](TWF_SPRINT2_SCAN_DISCOVER_IMPLEMENTATION.md)                                   | S2-4 through S2-8 implementation record: market context, discovery, optional Level-0 LLM, persistence, APIs, UX, and internal validation                                                |
| [Sprint-2 Hardening Register](TWF_SPRINT2_HARDENING_REGISTER.md)                                                    | Consolidated carried S2-3 obligations and nonblocking S2-4 through S2-8 implementation hardening                                                                                        |
| [Sprint-2 User Validation Plan](TWF_SPRINT2_USER_VALIDATION_PLAN.md)                                                | Product-owner workflows required before adversarial review, consolidated hardening, and final acceptance                                                                                |

The three normative documents are version 0.2, **ACCEPTED / IMPLEMENTATION
AUTHORIZED**; their v0.1 proposal entries remain historical. The reconciliation
record remains a v0.1 reference audit. Sprint 2 is **IMPLEMENTED / READY FOR USER VALIDATION**; S2-1 and S2-2 remain **ACCEPTED / FROZEN**, S2-3A is integrated, S2-3 remains **ACCEPTED / FROZEN WITH DEFERRED HARDENING**, S2-4 through S2-7 are **IMPLEMENTED**, and S2-8 is **IMPLEMENTED / INTERNAL VALIDATION COMPLETE**. Final acceptance and freeze remain pending. Read the implementation record, hardening register, and user validation plan with the accepted architecture.
Domain identity/ownership,
subsystem behavior and delivery scope each have one designated owner document;
the audit record is not a fourth competing architecture. Existing TI/TM/Broker
contracts retain their authority gates. If review finds a conflict outside the
explicitly reconciled scope, resolve it before implementation rather than assuming
a newer date silently overrides a security or execution rule.

### DOCX companions awaiting later regeneration

| Unchanged reference artifact                                                    | Staleness / required later synchronization                                                                      |
| ------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `TWF_MASTER_PRODUCT_ARCHITECTURE.docx`                                          | TWF-0 product diagram/generic Candidate predates configuration, broker and accepted S&D/domain progression      |
| `TWF_COMPONENT_ARCHITECTURE.docx`                                               | TWF-0 components predate accepted separate scan/discovery/context/LLM boundaries and current manual broker path |
| `TWF_DATA_ARCHITECTURE.docx`                                                    | Accepted intents/episodes/immutable snapshots, stage identities, lineage and retention rules                    |
| `TWF_SERVICE_CONTRACT_ARCHITECTURE.docx`                                        | Accepted provider families and provider-scan vs TWF-discovery ownership                                         |
| `TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.docx` | Already a v0.5 reference; accepted v0.6 and accepted v0.7 settings extension are not reflected                  |
| `TWF_UX_ARCHITECTURE.docx`                                                      | Accepted independent S&D modes, discovery history/relevance/grounding semantics                                 |
| `TWF_SECURITY_AUTH_ARCHITECTURE.docx`                                           | Accepted read-only MCP/LLM egress, citation isolation and untrusted-input rules                                 |
| `TWF_DEPLOYMENT_ARCHITECTURE.docx`                                              | Accepted bounded S&D runs, provider independence and restart/fencing behavior                                   |

No DOCX was created or edited by this review. The 2026-09-28 reconciliation was
Markdown-only; the following additional files were already present and untracked
at the 2026-09-29 review start. Their content parity and rendered layout have not
been verified, and current acceptance/status changes are Markdown-only:

- `TWF_OPPORTUNITY_DOMAIN_ARCHITECTURE.docx`
- `TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.docx`
- `TWF_SCAN_AND_DISCOVER_ARCHITECTURE.docx`
- `TWF_SPRINT2_SCAN_DISCOVER_DELIVERY_PLAN.docx`

Regenerate/verify reference companions against the accepted Markdown in a separate
document-artifact task; do not present these as synchronized accepted deliverables.
The unchanged broker v0.3 pair and historical
TWF-0 acceptance/engineering companions retain their existing reference roles;
they are not relabelled as newly accepted S&D artifacts.

### Revision history addition

| Revision             | Date       | Status                                   | Role / change                                                                                                                                              |
| -------------------- | ---------- | ---------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| S&D reconciliation 1 | 2026-09-28 | PROPOSED / RECONCILED / READY FOR REVIEW | Documentation-map revision; new scoped authorities, preserved milestone hierarchy and explicit stale companions                                            |
| S&D acceptance 1     | 2026-09-29 | ACCEPTED / IMPLEMENTATION AUTHORIZED     | Independent review, current status reconciliation and truthful untracked-DOCX inventory; see [review](TWF_SCAN_DISCOVER_ARCHITECTURE_ACCEPTANCE_REVIEW.md) |

## Historical S2-3 exact-universe correction — 2026-09-30

Generic MCP durability remediation and the TradingView exact-universe ScanProvider are
implemented together. The [implementation record](TWF_S2_3_TRADINGVIEW_MCP_SCAN_PROVIDER_IMPLEMENTATION.md),
[bounded review](TWF_S2_3_ACCEPTANCE_REVIEW.md) and
[hardening register](TWF_S2_3_DEFERRED_ISSUES_AND_HARDENING_REGISTER.md) govern current
status: **ACCEPT_S2_3_WITH_DEFERRED_HARDENING / ACCEPTED / FROZEN**. Live OAuth,
35-tool discovery, column/result envelopes and one bounded India screener are verified.
Exact requested-universe batch retrieval and local evaluation are implemented and synthetically validated through ScanRun, ScanMatch and lineage. Repeated minimal live exact calls reached the tool but returned typed RATE_LIMITED; no TWF defect was reproduced and limit scope remains unknown. Successful-live-row proof and remote revocation cleanup are mandatory Sprint-2 hardening. This is one integrated
S2-3 completion effort, not a renewed standalone S2-3A micro-gate. S2-0/1/2/3 and Broker
V2 acceptance remain unchanged; Sprint 2 is ACTIVE, S2-4 NEXT, S2-5 through S2-8 PENDING.
Historical S2-3A reviews remain unchanged. The S2-3 Git checkpoint is ready but is not created by this documentation task.

## Integrated S2-4 through S2-8 implementation — 2026-09-30

The [implementation record](TWF_SPRINT2_SCAN_DISCOVER_IMPLEMENTATION.md), [consolidated hardening register](TWF_SPRINT2_HARDENING_REGISTER.md), and [user validation plan](TWF_SPRINT2_USER_VALIDATION_PLAN.md) are the current implementation-handoff documents. They do not supersede accepted S2-0 through S2-3 records. Sprint 2 is IMPLEMENTED / READY FOR USER VALIDATION and remains unaccepted/unfrozen until user testing, adversarial review, hardening, and verification complete.

## Scan evidence chart implementation — 2026-10-02

The accepted [Scan & Discover Architecture](TWF_SCAN_AND_DISCOVER_ARCHITECTURE.md) now records the bounded evidence-chart amendment. The [integrated implementation record](TWF_SPRINT2_SCAN_DISCOVER_IMPLEMENTATION.md) owns the runtime/API/migration description; the [user validation plan](TWF_SPRINT2_USER_VALIDATION_PLAN.md) owns visual, responsive and keyboard checks; the [temporal-state architecture](TWF_SND_SCAN_DRIVEN_TEMPORAL_STATE_ARCHITECTURE.md) owns immutable run/match identity and no-lookahead integration; and the [detailed roadmap](TWF_DETAILED_ROADMAP.md) records status without changing milestone acceptance.

The implementation uses additive revision `0015_discovery_evidence_series` and remains **IMPLEMENTED / READY FOR USER VALIDATION**. Sprint 2 is not accepted or frozen. Live-provider historical retention still requires explicit provider capability/licensing evidence; synthetic validation data must not be presented as live.

## Active Dhan/TapTide provider integration map — 2026-10-02

- [Market Data Provider Architecture](TWF_MARKET_DATA_PROVIDER_ARCHITECTURE.md): normative Dhan-first contracts, data authority, scanner path, exact-series chart integrity, failure semantics, and Zerodha compatibility.
- [Market Intelligence Provider Architecture](TWF_MARKET_INTELLIGENCE_PROVIDER_ARCHITECTURE.md): normative optional TapTide claims, generic MCP reuse, failure isolation, and bounded call/cache policy.
- [Scan & Discover Architecture](TWF_SCAN_AND_DISCOVER_ARCHITECTURE.md): accepted subsystem with the current provider amendment.
- [Sprint-2 implementation record](TWF_SPRINT2_SCAN_DISCOVER_IMPLEMENTATION.md): runtime, API, UI, history, and validation implementation.
- [Scan-driven temporal-state architecture](TWF_SND_SCAN_DRIVEN_TEMPORAL_STATE_ARCHITECTURE.md): Dhan-backed `PRESENT`/`ABSENT`/`NOT_EVALUATED` semantics.
- [Sprint-2 user validation plan](TWF_SPRINT2_USER_VALIDATION_PLAN.md): bounded live Dhan/TapTide workflow and legacy-history checks.
- [S2-3 hardening register](TWF_S2_3_DEFERRED_ISSUES_AND_HARDENING_REGISTER.md): historical TradingView disposition plus active Dhan/TapTide and generic MCP obligations.

The TradingView implementation and acceptance documents remain indexed as historical evidence. They no longer configure or authorize active S&D. The current migration is **IMPLEMENTED / READY FOR USER VALIDATION** and does not change prior milestone tags.

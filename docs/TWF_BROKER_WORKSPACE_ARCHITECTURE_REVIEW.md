# TWF Broker Workspace Architecture — Independent Review and Reconciliation

## Decision and scope

**Review date: 2026-09-26. Decision: GO_BROKER_WORKSPACE.**

Accept the reconciled [Broker Workspace architecture v0.3](TWF_BROKER_WORKSPACE_ARCHITECTURE.md) as a design basis for **BW-1 Synthetic Broker Read-Only Foundation only**. The supplied v0.2 had material gaps; the findings below were resolved in the normative Markdown during this documentation task. This report records the review, not a second architecture.

This is not runtime acceptance, a new Git freeze, real-provider verification or authorization to place orders. BW-2 through BW-6 and TM integration require their own bounded implementation and acceptance gates. No provider API, market-data licence, sandbox, regulatory permission or live credential was investigated or certified here.

**Companion synchronization follow-up:** the subsequent user-requested DOCX update is
recorded in section 11. Earlier statements below about preserving the supplied v0.2
DOCX describe the initial review checkpoint, not the current companion version.

## 1. Preflight and exact project state found

- Branch: `main`.
- HEAD: `e3852d3ec8e6675248717b2b2799041ace53d5fd`.
- Commit subject: `TWF-1.6: implement and accept service client foundation`.
- Commit date: 2026-09-25 23:01:04 +0530.
- The supplied broker Markdown was **Version 0.2 — Proposed authoritative architecture for review before Broker Workspace implementation**; no freeze was asserted.
- Initial worktree had only the two supplied, untracked broker documents; no tracked changes or unrelated source edits.

Exact initial `git status --short`:

```text
?? docs/TWF_BROKER_WORKSPACE_ARCHITECTURE.docx
?? docs/TWF_BROKER_WORKSPACE_ARCHITECTURE.md
```

Exact README project tree as found, before reconciliation:

```text
TWF-0 — Product / Architecture Foundation                 ✅ ACCEPTED / FROZEN
│
├── Product vision / system architecture                  ✅ accepted
├── Master / component architecture                       ✅ accepted
├── Technology baseline                                   ✅ accepted for TWF-1
├── UX architecture                                       ✅ accepted
├── Data architecture                                     ✅ accepted
├── Security / authentication architecture                ✅ accepted
├── Service contract / integration architecture           ✅ accepted
├── Deployment architecture                               ✅ accepted
├── Repository / engineering standards                    ✅ accepted
└── Coding readiness                                      ✅ GO_TWF1

                         ↓

TWF-1 — Application Foundation                            ▶ IN_PROGRESS
│
├── TWF-1.0 Repository Scaffold                           ✅ accepted
├── TWF-1.1 Frontend Shell                                ✅ accepted
├── TWF-1.1A Theme Switching                              ✅ accepted
├── TWF-1.2 Backend Shell                                ✅ accepted
├── TWF-1.3 Database Foundation                          ✅ accepted
├── TWF-1.4 User / Login Foundation                      ✅ accepted (ba9bb8b)
├── Configuration architecture reconciliation             ✅ reviewed v0.6 / GO_TWF1_5
├── TWF-1.5 Settings Foundation                           ✅ accepted (664d4cf)
└── TWF-1.6 Service Client Foundation                     IMPLEMENTED / pending independent review

UX maturity — parallel workstream
├── UX-B1 Foundational Complete UX                        PARTIAL (TWF-1.x / TWF-2)
├── UX-B2 Operationally Useful Trading UX                  PLANNED (TWF-2–7)
└── UX-B3 Architecture-Complete UX                        PLANNED (progressive TWF-8–10)

Later functional milestones — separately gated
├── TWF-2 Trader Workspace
├── TWF-3 Scanner Integration
├── TWF-4 TI + Active LLM Integration
├── TWF-5 TM Integration
├── TWF-6 Minimal Complete Trading Workflow
├── TWF-7 Realtime / Notifications
├── TWF-8 IFL / History / Learning Visibility
├── TWF-9 Multi-user / Subscription Readiness
└── TWF-10 Production Hardening
```

### Repository evidence resolving the inconsistency

README, roadmap and index still showed TWF-1 in progress and TWF-1.6 pending review.
The TWF-1.6 implementation record more specifically said pending acceptance
**re-review**; TWF-1.5's record also retained its earlier pending-review status.
Product/configuration current-status prose was older still, saying TWF-1.5 was
not started. No separate TWF-1.5 or TWF-1.6 acceptance report exists in this repository.

The repository nevertheless contains explicit later closure evidence:

```text
tag:          twf-1-application-foundation
object type:  annotated tag
tag object:   0087a70295dc339064f0d2cc7ecc3925bc4454ea
target:       e3852d3ec8e6675248717b2b2799041ace53d5fd
message:      TWF-1 Application Foundation accepted
HEAD subject: TWF-1.6: implement and accept service client foundation
```

Therefore current dashboards now record TWF-1.6 accepted at `e3852d3` and TWF-1
accepted/frozen at the **existing** tag. This uses repository evidence, not memory
or an inference that every subtarget automatically closes its parent. Historical
implementation/review records remain unchanged; this review does not invent a
missing acceptance report or independently re-certify the foundation runtime.
UX-B1 stays partial; UX-B2/B3 and later functional milestones stay unaccepted.

## 2. Review corpus and method

Read the current Markdown authorities, including:

- [README](../README.md), [Detailed Roadmap](TWF_DETAILED_ROADMAP.md),
  [Documentation Index](TWF_DOCUMENTATION_INDEX.md) and [UX Bucket Roadmap](TWF_UX_BUCKET_ROADMAP.md).
- [Broker Workspace](TWF_BROKER_WORKSPACE_ARCHITECTURE.md), reviewed from supplied v0.2.
- [Product/System Architecture](TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md).
- [Service Contract](TWF_SERVICE_CONTRACT_ARCHITECTURE.md) and
  [Service Integration](TWF_SERVICE_INTEGRATION_ARCHITECTURE.md) architectures.
- [Security](TWF_SECURITY_AUTH_ARCHITECTURE.md) and [Data](TWF_DATA_ARCHITECTURE.md) architectures.
- [Configuration/Setup/Capability/Entitlement/Pluggability](TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md),
  including its historical [reconciliation review](TWF_CONFIGURATION_SETUP_ARCHITECTURE_REVIEW.md).
- [Engineering Standards](TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.md) and
  [Technology Decisions](TWF_TECHNOLOGY_DECISION_RECORD.md).
- [TM](TWF_TM_INTEGRATION_CONTRACT.md) and [TI](TWF_TI_INTEGRATION_CONTRACT.md) integration contracts.
- Existing [TWF-1.5](TWF_TWF1_5_SETTINGS_FOUNDATION.md) and
  [TWF-1.6](TWF_TWF1_6_SERVICE_CLIENT_FOUNDATION.md) implementation records.

Checked actual foundation contracts/configuration/registry and service routes at
`apps/api/src/twf/integrations/{contracts,config,registry}.py` and
`apps/api/src/twf/api/services.py`, as well as commit/tag evidence. The foundation
has only SCANNER/TI/TM/LLM health semantics under `foundation.health.v1`; it does
not already provide a BrokerClient, tenant registry, credential vault or order
contract. The 16 service-descriptor limit is not a broker-account architecture limit.

The review stress-tested ownership, request/response loss, crashes, stale inputs,
identity reuse, permission changes and provider differences, then traced each
decision into current authority documents. Provider examples were treated as
illustrations. The supplied DOCX was preserved as a reference, not used to override
current Markdown. Runtime/browser tests were intentionally outside this task.

## 3. Findings and dispositions

“Now” in this table means this architecture checkpoint. Runtime obligations are
attached to the first gate that uses them, rather than demanded in BW-1.

| ID | Severity | Timing | Finding in v0.2 / current corpus | Reconciliation and disposition |
|---|---|---|---|---|
| F01 | MAJOR | MUST ADDRESS NOW | Current dashboards and implementation-stage records contradicted explicit foundation closure evidence. | Reconciled current pages using section 1 evidence; preserved historical records. Resolved. |
| F02 | MAJOR | MUST ADDRESS NOW | Integration/security/configuration/TM prose assumed all broker activity passed through TM, conflicting with manual Broker Workspace. | Qualified TM-managed authority and defined the dedicated manual server-side adapter/vault path; initial exclusive command owner per broker account and explicit handoff. Broker sections 18.3, 23 and affected authorities agree. Resolved. |
| F03 | MAJOR | MUST ADDRESS NOW | A request ID and “reconcile before retry” alone did not define crash-safe dispatch or what a broker without idempotency permits. | Durable pre-send intent/confirmation/claim, uncertain restart handling, no lease-triggered resend, typed replay conflict and evidence-based resolution. Sections 19.3–19.4 and 26.1; must be implemented/tested before live commands. Architecture resolved. |
| F04 | MAJOR | MUST ADDRESS NOW | Broker account identity could be confused with ACS tenant identity; authentication/connection transitions lacked callback-race and returned-account binding rules. | Explicit owner/broker/tenant IDs and scoped permission checks; expiring one-use state, connection generations, account verification, refresh concurrency, endpoint and secret boundaries. Sections 6.2, 7.2–7.3 and 23.5. Architecture resolved; real auth remains BW-2-gated. |
| F05 | MAJOR | MUST ADDRESS NOW | Display symbols, aliases, broker tokens and derivative strings could be mistaken for durable IDs; master replacement/term changes could retarget a saved order. | Immutable IDs, versioned native bindings/terms, atomic catalog publication, token-reuse protection, expiry and historical preservation. Sections 9.5, 11.5 and 12.4. Optional canonical mapping remains safe only with valid exact native identity. Resolved. |
| F06 | MAJOR | MUST ADDRESS NOW | Confirmation was not explicitly bound to all consequential revisions; cancel/modify and external orders lacked independent command/observation semantics. | Immutable payload/account/binding/owner/policy confirmation, context-change invalidation; separate action IDs, fills, pending actions, corrections and nullable intent links for external orders. Sections 15.1, 17.3 and 19.4. Resolved. |
| F07 | MAJOR | MUST ADDRESS NOW | Unified totals could imply complete or fungible exposure/funds, or add unlike derivative/product quantities. | Qualified compatible-unit/currency/product aggregation, included/excluded/stale/unmapped coverage, unknown not zero, no implicit derivative delta/netting or margin pooling. Section 21.1. Resolved. |
| F08 | MAJOR | ARCHITECTURAL HOOK REQUIRED NOW | One connection/health/freshness state could hide a healthy read API with failed orders, stale funds or an incomplete paginated result. | Separate operation health and dataset source/as-of/received time, clock skew, completeness and per-operation policy. Sections 7.3, 8.2 and 22.1; numeric provider policies fixed before use. Resolved as a gate-bound hook. |
| F09 | MAJOR | MUST ADDRESS NOW | Basic Safety and later TM governance needed an explicit gap boundary; profile disable/revocation could abandon unknown submissions. | Versioned allow/warn/block policy, required unknown inputs block, manual UNMANAGED meaning, no TM fallback, continued safe reconciliation and audited handoff. Sections 8.2, 18.3–18.4, 26.1. Resolved in architecture; live policy/runbook still required. |
| F10 | MINOR | MUST ADDRESS NOW | Broker watchlist ownership, multiplicity, duplicates and missing/expired native bindings were underspecified. | TWF-owned revisioned lists per account; exact per-list native identity uniqueness, user ordering, tombstones and explicit re-resolution. Provider-native watchlist synchronization is deferred. Sections 9.2–9.5. Resolved. |
| F11 | MAJOR | MUST ADDRESS NOW | Generic TWF-1.6 client compatibility and “first broker” delivery were not concrete enough to prevent premature live implementation or a one-provider contract. | Separate versioned BrokerClient, preserved health API, exact BW-1 read scope, two synthetic providers/three accounts and BW-6 real-provider proof. Sections 24.1 and 34. Roadmap IDs retained with a delivery overlay. Resolved. |
| F12 | MINOR | ARCHITECTURAL HOOK REQUIRED NOW | Streaming, rate budgets and observation persistence lacked enough boundaries for later recovery/isolation. | Cursor/replay/resnapshot, dedupe, backend credential isolation, bounded provider/account budgets and durable recovery before live use; no event platform required now. Sections 8.2, 19.4, 26.1 and 32.1. Resolved as hooks. |
| F13 | OBSERVATION | DEFER SAFELY | Full global registry automation, global watchlists, paper-market simulation, provider-specific order extras and advanced analytics are not required for initial utility. | Retained explicit deferrals and prerequisites in sections 33–34; no implementation or dependency selection. |
| F14 | OBSERVATION | OUT OF SCOPE | Production certification, market-data licensing, provider/compliance verification and runtime acceptance cannot follow from a documentation review. | No such claim made. Required provider/environment evidence must precede the applicable real integration/live gate. |

No unresolved BLOCKING or MAJOR architecture finding prevents BW-1 after these
changes. This does **not** mean the architecture's future live prerequisites are
already implemented or verified.

## 4. Required gap classification

| Concern | Timing | Required boundary now / first use gate |
|---|---|---|
| Canonical instrument registry | ARCHITECTURAL HOOK REQUIRED NOW | Immutable identity and optional mapping fixed; full population/automation later. BW-1 may show unmapped fixtures. |
| Exchange listing mapping | ARCHITECTURAL HOOK REQUIRED NOW | Separate venue/segment/currency/share class identity; do not merge display-symbol matches. |
| Broker instrument master sync | ARCHITECTURAL HOOK REQUIRED NOW | Versioned atomic publication, provenance, stale/expired rules; implement with real catalog/search at BW-2. |
| Broker watchlists | ARCHITECTURAL HOOK REQUIRED NOW | TWF ownership, account scope, revisions, native bindings and tombstones fixed; CRUD at BW-3. |
| Global watchlist | DEFER SAFELY | Canonical analysis surface later; never implicit broker routing or a prerequisite for native watchlists. |
| Quotes/LTP | ARCHITECTURAL HOOK REQUIRED NOW | Typed source/as-of/units and access/quota hooks; implement when displayed or needed for a safety check, not mandatory streaming in BW-1. |
| Historical candles | DEFER SAFELY | Separate later query/licensing/retention contract; no charting requirement in BW-1. |
| Order intent persistence | MUST ADDRESS NOW | Durable pre-send requirements fixed now; implement and prove crash/restart at BW-4 before BW-5. |
| Broker callbacks | ARCHITECTURAL HOOK REQUIRED NOW | Auth state/account/generation security before BW-2; order callbacks authenticated/deduped and re-queried before trusting them. |
| WebSocket streams | DEFER SAFELY | REST/polling suffices initially; section 32.1 fixes authorization/cursor/backpressure/recovery seam. |
| Order reconciliation worker | MUST ADDRESS NOW | Durable bounded recovery independent of browser mandatory before live; no generic queue infrastructure now. |
| Audit | MUST ADDRESS NOW | Ownership, redaction, immutable command/confirmation evidence and recovery history fixed; persist at corresponding real auth/command gate. |
| Basic Execution Safety | MUST ADDRESS NOW | Required inputs, fail-closed conditions and TM boundary fixed; numeric policy and tests before BW-5. |
| Margin estimation | ARCHITECTURAL HOOK REQUIRED NOW | Provider-specific capability, freshness and estimate exclusions; do not promise reserves or pool margins. Unsupported mandatory check blocks. |
| Charges | DEFER SAFELY | Later estimates with explicit coverage; do not represent gross P&L as net of unknown fees. |
| Basket orders | DEFER SAFELY | Separate multi-command/partial-outcome design later; no implied atomic basket. |
| GTT | DEFER SAFELY | Manifest capability only; provider lifecycle/trigger semantics require a dedicated gate. |
| Commodity support | DEFER SAFELY | Identity/units/expiry extension hook exists; no unsupported segment enabled. |
| Corporate actions | ARCHITECTURAL HOOK REQUIRED NOW | Versioned aliases/contract terms and preserved history; ambiguous current binding blocks execution. Automated processing later. |
| Market holidays | ARCHITECTURAL HOOK REQUIRED NOW | Session/timezone/calendar capability and unknown policy fixed before live; no universal calendar build now. |
| Subscription broker quotas | ARCHITECTURAL HOOK REQUIRED NOW | Configurable eligibility, separate from provider capability/health and current health-descriptor limit; never delete unresolved exposure. Commercial plans later. |
| Synthetic broker | MUST ADDRESS NOW | Mandatory BW-1 read proof; BW-4 deterministic command/failure/restart proof before live. |
| Paper broker | DEFER SAFELY | Market-driven simulated matching/P&L is a separate product, not required deterministic fixtures. |
| Broker sandbox/test environments | ARCHITECTURAL HOOK REQUIRED NOW | Verify availability/limits for chosen provider; not assumed, and not a substitute for synthetic fault tests or controlled real evidence. |

## 5. Failure-case stress test

These are design traces, not executed runtime tests. Broker section 28 carries the
normative failure matrix; the following gives the review's expected safe outcome.

| Scenario | Required outcome |
|---|---|
| Intraday token expiry / stale callback / refresh race | Block new affected use; explicit reconnect and generation check; sibling accounts unaffected. |
| Broker outage / one account fails | Local degraded room; last observation labelled stale/unknown; no fallback account or shared failure cascade. |
| Reads healthy, order API fails | Separate command health; keep usable reads without implying permission to submit. |
| Network drops after send / acknowledgement missed | Persist UNKNOWN and reconcile exact broker evidence; a missing list row is not proof of rejection. |
| TWF crash before or after send / failed acknowledgement commit | Durable pre-send marker and recovery claim; restart cannot blindly dispatch again. |
| Double click / concurrent worker / second tab | Same action key returns same outcome; mismatched payload conflicts; distinct keys are not magically deduplicated trades. |
| Partial fill / cancel-modify race | Preserve fills and remaining quantity separately from pending command; stale revision rejected, broker truth refreshed. |
| Stale funds / stale quote | Unknown or out-of-policy mandatory inputs block; cached funds never reserve buying power. |
| Stale master / expired derivative / reused token | Re-resolve exact current native binding and terms; never retarget a stale watchlist/preview silently. |
| Symbol/corporate-action change | Preserve immutable identities and historical contract terms; ambiguous mapping remains unmapped/blocked as appropriate. |
| Account disabled / grant revoked mid-session | Invalidate new dispatch/callback generation; retain existing unresolved work and governed safety/recovery access. |
| Provider-wide rate limit | Shared bounded/fair budget and safe read backoff; no generic retry of possibly sent orders. |
| Order-status lag / partial pagination | Mark incomplete; absence does not erase orders or prove non-submission. |
| Out-of-order/duplicate event or correction | Dedupe, preserve provenance/corrections, reconcile conflicts; do not regress confirmed fills to OPEN. |
| Market closed / holiday / session mismatch | Approved provider-specific order/session policy; no implicit conversion to an after-market order. |
| Cross-account request/callback/cache/stream | Reject unauthorized scope; no ID-based access or credential reuse. |
| TM downtime / conflicting ownership / external broker-terminal trade | No manual fallback on managed account; reconcile external facts without inventing approval or adoption. |
| DB loss / old backup restore | Block unsafe dispatch until broker state and durable recovery evidence are reconciled; document recovery before live. |
| Unmapped or stale contributor in unified view | Expose coverage/exclusions and operational rows; no false complete total or fungible funds. |

## 6. Architecture checks after reconciliation

PASS means the architecture defines a coherent boundary and gate. It does not
claim an adapter or runtime test passed.

```ini
MULTI_BROKER_MODEL = PASS
BROKER_SETTINGS_MODEL = PASS
BROKER_AUTH_LIFECYCLE = PASS
BROKER_ROOM_UX = PASS
UNIFIED_CONTROL_ROOM = PASS
CANONICAL_INSTRUMENT_MODEL = PASS
DERIVATIVE_IDENTITY_MODEL = PASS
BROKER_INSTRUMENT_CATALOG = PASS
BROKER_WATCHLIST_MODEL = PASS
WATCHLIST_SEPARATION = PASS
ORDER_DOMAIN_MODEL = PASS
ORDER_WORKFLOW = PASS
ORDER_IDEMPOTENCY_RECONCILIATION = PASS
TWF_TM_RISK_BOUNDARY = PASS
BROKER_TRUTH_MODEL = PASS
BROKER_FRESHNESS_MODEL = PASS
MULTI_BROKER_AGGREGATION = PASS
BROKER_SECURITY_MODEL = PASS
SERVICE_CLIENT_COMPATIBILITY = PASS
PERSISTENCE_BOUNDARIES = PASS
REALTIME_EXTENSION_PATH = PASS
```

SyntheticBroker is mandatory because real-provider happy paths cannot reliably
exercise response loss, token expiry, partial data, out-of-order updates and crashes
at deterministic boundaries. Two differently shaped synthetic providers also expose
a provider-specific common model before a real adapter entrenches it. Fixtures are
explicitly synthetic; they do not demonstrate production compatibility.

## 7. First implementation target and neutrality proof

**BW-1 Synthetic Broker Read-Only Foundation** is exactly
[Broker section 34.1](TWF_BROKER_WORKSPACE_ARCHITECTURE.md#341-first-implementation-target-bw-1):

- Versioned provider/account identity, capabilities, auth/operation health, typed
  query outcomes and dataset observations; adapter registry with no vendor SDK leakage.
- Three explicitly owned fixture accounts across two fictional providers, two of
  those accounts under one provider; injected fixed clock and no provider network.
- Authenticated account rooms and read-only overview with Dashboard, Holdings,
  Positions, Orders and Funds. Current account/mode/source/as-of/completeness remain visible.
- Equivalent contract tests for differently shaped fixtures, ownership denials,
  failure isolation, stale/partial/empty/unknown data and safe rate-limit/timeout behavior.
- Both themes and 390, 768, 1024, 1440, 1920 and 2560+ responsive/accessibility review;
  protect account context through navigation and request races.
- No real credentials/OAuth, broker-account administration, shared tenant model,
  catalog import, watchlist CRUD, order draft/submit endpoint, broker DB rollout,
  streaming platform, Scanner/TI/TM/LLM integration or commercial quota framework.

This advances UX-B2 through TWF-2 workspace foundations; it neither completes UX-B1
nor closes TWF-2/6. The [roadmap delivery overlay](TWF_DETAILED_ROADMAP.md#18-broker-workspace-delivery-overlay)
keeps the existing IDs while prioritizing Broker Workspace → Basic Execution Safety
→ TM → Scanner → TI. Advanced administration/diagnostics contribute to UX-B3 later.

BW-1 provides an early synthetic neutrality check. **BW-6 provides the real
second-broker proof**: add a new adapter/manifest and run the same contracts and UI
semantics without rewriting common order meaning, identity or persistence ownership,
or adding provider-name branches through the frontend. Test concurrent providers,
two accounts of one provider, native identity differences, unsupported capabilities,
partial/unknown outcomes, auth expiry and denial/isolation. If a new common concept
is needed, version and review it explicitly; do not claim an unchanged proof passed.

Recommended implementation level: **GPT-6 Astra High**, with a separate independent
acceptance review. This is a task-specific judgment for bounded cross-layer contracts,
ownership checks and responsive UI work; the [official model documentation](https://developers.openai.com/api/docs/models/gpt-6-astra)
describes its reasoning/coding suitability and supported reasoning levels. The implementation recommendation is separate from this documentation review.

## 8. Exact documentation reconciliation inventory

| File | Change |
|---|---|
| `docs/TWF_BROKER_WORKSPACE_ARCHITECTURE.md` | Supplied untracked v0.2 → sole normative v0.3; closed architecture gaps and fixed bounded gates. |
| `docs/TWF_BROKER_WORKSPACE_ARCHITECTURE_REVIEW.md` | New review evidence, findings, classifications, checks and decision. |
| `README.md` | Reconciled status from commit/tag evidence; preserved hierarchy and added broker links/current target. |
| `docs/TWF_DETAILED_ROADMAP.md` | Reconciled closure; added delivery overlay without renumbering or closing later scope. |
| `docs/TWF_DOCUMENTATION_INDEX.md` | Added broker authority/review/reference roles and current status/target. |
| `docs/TWF_UX_BUCKET_ROADMAP.md` | v0.2 broker contribution, manual/TM distinction and unchanged partial/planned bucket status. |
| `docs/TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md` | Current closure, independent manual path and staged product priority. |
| `docs/TWF_SERVICE_CONTRACT_ARCHITECTURE.md` | Separate versioned BrokerClient; preserved foundation.health contract and command uncertainty. |
| `docs/TWF_SERVICE_INTEGRATION_ARCHITECTURE.md` | Replaced TM-only broker assumption and old delivery priority; clarified adapter boundary. |
| `docs/TWF_SECURITY_AUTH_ARCHITECTURE.md` | Dedicated manual broker trust zone, scoped callbacks/secrets and explicit authority separation. |
| `docs/TWF_DATA_ARCHITECTURE.md` | Broker ownership, immutable bindings, durable command/recovery and migration gate. |
| `docs/TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md` | Corrected current status and unqualified TM-only assumptions; dated section 51 clarification, retaining v0.6 configuration baseline. |
| `docs/TWF_TM_INTEGRATION_CONTRACT.md` | Scoped managed authority and defined coexistence/handoff; public-contract reconciliation gate retained. |

The supplied broker DOCX is unchanged. Historical acceptance/implementation records,
TWF-0 closure, TI advisory contract, engineering/technology decisions and runtime
files are unchanged. The latter authorities were inspected but required no new
technology or altered TI authority. No package, migration, configuration file or
dependency was added.

## 9. Documentation validation

- **PASS — Markdown parsing:** all 32 Markdown files (README plus docs) parsed in
  memory with the repository's installed Prettier Markdown parser; no formatting
  rewrite. Structural checks found balanced fences, consistent columns across 57
  tables and numbered broker/configuration sections. The 14 Mermaid fences were
  checked structurally, not rendered.
- **PASS — Local links/anchors:** 211 resolved; no missing repository target or
  referenced Markdown heading. External provider links were not treated as proof
  of API support.
- **PASS — Documentation index:** all 42 Markdown/DOCX documents under docs covered.
- **PASS — Project-state/matrix checks:** exact preflight README tree preserved;
  full milestone/UX hierarchy retained; all 29 required matrix fields and 21
  architecture checks present.
- **PASS — Cross-document review:** manual/TM authority, secret boundaries, native
  identity, durable command recovery, synthetic-first scope and delivery priority
  reconciled. Remaining pending-review status text belongs to historical records
  or the verbatim preflight excerpt, not current dashboards.
- **PASS — Whitespace:** `git diff --check`; separate
  `git diff --no-index --check /dev/null <file>` checks for both untracked broker
  Markdown files produced no diagnostics (exit 1 indicates the expected file diff).
- **PASS — Scope/history:** 11 tracked Markdown changes, one supplied Markdown
  revised and one new Markdown review; no runtime/dependency/configuration or
  historical record changes. HEAD and the existing foundation tag remain unchanged.
- **PASS — Reference preservation:** supplied broker DOCX SHA-256 remains
  `637383eb6c04c3682d98db62967b830744dd88974fa376d2e2ceedf136e901f6`;
  the configuration reference DOCX also matches its original hash.
- Runtime tests, builds, Docker and browser/provider checks were not run: this is
  documentation-only validation, as requested. No commit, tag or push was performed.

## 10. Required acceptance matrix

These are **post-reconciliation architecture** results, bounded by section 7.

```ini
PROJECT_STATE_RECONCILED = YES
BROKER_WORKSPACE_ARCHITECTURE_COHERENT = YES
MULTI_BROKER_MODEL_ACCEPTED = YES
BROKER_SETTINGS_MODEL_ACCEPTED = YES
BROKER_AUTH_LIFECYCLE_ACCEPTED = YES
BROKER_ROOM_UX_ACCEPTED = YES
UNIFIED_CONTROL_ROOM_ACCEPTED = YES
CANONICAL_INSTRUMENT_MODEL_ACCEPTED = YES
DERIVATIVE_IDENTITY_MODEL_ACCEPTED = YES
BROKER_INSTRUMENT_CATALOG_ACCEPTED = YES
BROKER_WATCHLIST_MODEL_ACCEPTED = YES
WATCHLIST_SEPARATION_ACCEPTED = YES
ORDER_DOMAIN_MODEL_ACCEPTED = YES
ORDER_WORKFLOW_ACCEPTED = YES
ORDER_IDEMPOTENCY_RECONCILIATION_ACCEPTED = YES
TWF_TM_RISK_BOUNDARY_ACCEPTED = YES
BROKER_TRUTH_MODEL_ACCEPTED = YES
BROKER_FRESHNESS_MODEL_ACCEPTED = YES
MULTI_BROKER_AGGREGATION_ACCEPTED = YES
BROKER_SECURITY_MODEL_ACCEPTED = YES
SERVICE_CLIENT_COMPATIBILITY_ACCEPTED = YES
PERSISTENCE_BOUNDARIES_ACCEPTED = YES
REALTIME_EXTENSION_PATH_ACCEPTED = YES
SYNTHETIC_BROKER_REQUIRED = YES
FIRST_IMPLEMENTATION_SLICE_DEFINED = YES
SECOND_BROKER_PROOF_DEFINED = YES
ROADMAP_RECONCILED = YES
DOCUMENTATION_RECONCILED = YES
READY_FOR_BROKER_WORKSPACE_IMPLEMENTATION = YES
```

**Final decision: GO_BROKER_WORKSPACE — BW-1 only.** Stop at this documentation
review; implementation, real-provider activation and live orders require subsequent
bounded work. No commit, tag or push was performed.


## 11. DOCX synchronization follow-up — 2026-09-26

At the user's subsequent request, the broker DOCX is now a synchronized v0.3
presentation companion to the normative Markdown. This supersedes the initial
review checkpoint's decision to retain the supplied v0.2 DOCX unchanged. Sections
1–10 retain that checkpoint's evidence and original hashes as historical records;
the architecture decision and BW-1 boundary remain unchanged.

This follow-up updates exactly these five files:

- `docs/TWF_BROKER_WORKSPACE_ARCHITECTURE.docx`: regenerated all current prose,
  headings, tables and diagrams from the v0.3 Markdown.
- `docs/TWF_BROKER_WORKSPACE_ARCHITECTURE.md`: identifies the synchronized companion
  and requires both formats to be updated together when this architecture changes.
- `README.md`: updates the broker companion's version and maintenance role.
- `docs/TWF_DOCUMENTATION_INDEX.md`: records the same companion/version rule.
- `docs/TWF_BROKER_WORKSPACE_ARCHITECTURE_REVIEW.md`: records this follow-up while
  preserving the earlier review checkpoint.

Content verification matched 742 source text blocks in order, 104 headings, 10
native Word tables and 14 figures. Figures were regenerated from the current
Markdown definitions, including confirmation before durable dispatch; the source
diagram definitions are retained in image alternative text. All 37 rendered pages
were visually inspected, including tables spanning pages and diagram connectors.
DOCX archive integrity, repeated table headers and the embedded Markdown source
fingerprint passed validation.

Current synchronized fingerprints:

- Markdown SHA-256:
  `f4b33ed96a27bd2e92e19781ba21b8dea666e6842bed5ceebf24b715a1326708`.
- DOCX SHA-256:
  `6d90a9620e64d5aa76c10f21739f60a0190171da0ed1787cee4adcf2dc64a4b4`.

No runtime, dependency or architecture behavior was changed by this follow-up.
No commit, tag or push was performed.

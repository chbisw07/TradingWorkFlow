# TWF Scan & Discover — Independent Architecture Acceptance Review

## Decision and evidence boundary

**Review date: 2026-09-29. Decision: GO_S2_SD_IMPLEMENTATION.**

Accept the Scan & Discover (S&D), Opportunity-domain and Sprint-2 architecture as a
bounded implementation basis. There is no open **MUST FIX BEFORE IMPLEMENTATION**
finding. One non-blocking relevance-colour specification remains for the UI slice;
provider/data/policy decisions remain prerequisites for their dependent slices.
Acceptance does not waive those gates or assert that all of S2-0 is closed.

Architecture status is **ACCEPTED / IMPLEMENTATION AUTHORIZED**. Sprint 2 is
**ACTIVE / NEXT; implementation not started**. The next implementation gate is a
bounded S2-1 domain/contracts and deterministic synthetic-fixture prompt under the
[Sprint-2 delivery plan](TWF_SPRINT2_SCAN_DISCOVER_DELIVERY_PLAN.md).

This record reviews the uncommitted architecture independently of its author's
report. It does not implement or accept S&D runtime, certify a provider or data
licence, create a Git freeze, or reopen Broker V2. No external service was contacted,
no broker order was placed and no runtime suite was claimed as S&D evidence.

## A. Preflight

- Branch: `main`.
- Reviewed HEAD: `69a643e372c48a6d3d85ce57962ca05c38c4c3dc`.
- `git status --short`, `git diff --stat`, `git diff --name-status` and the complete
  tracked documentation diff were inspected, along with every new Markdown file.
- Incoming tracked diff: **15 Markdown files, 610 insertions, 25 deletions**.
- Incoming untracked files: **four Markdown architecture/reconciliation files and
  four DOCX companions**. There were no staged changes or runtime source changes.
- SHA-256 fingerprints of all **225 incoming tracked/untracked files** establish
  the review-start boundary. Review changes are separately inventoried below.
- Git objects/references were only read. No fetch, commit, tag, push, merge, rebase,
  reset or branch switch was performed.

Relevant local tags, with peeled target commits:

| Tag                                            | Target    | Meaning                                              |
| ---------------------------------------------- | --------- | ---------------------------------------------------- |
| `twf-0-architecture-baseline`                  | `86d4dda` | Accepted original architecture                       |
| `twf-1-application-foundation`                 | `e3852d3` | Accepted application foundation                      |
| `twf-broker-workspace-architecture-v0.3`       | `0b73492` | Accepted broker architecture                         |
| `twf-bw1-synthetic-broker-readonly`            | `44e53d5` | Historical BW-1 acceptance                           |
| `twf-bw2-1-secure-provider-account-foundation` | `b139d35` | Historical secure-account foundation                 |
| `twf-bw2-2-zerodha-auth-account-binding`       | `58ed806` | Historical authentication/binding                    |
| `twf-bw2-3-zerodha-catalog-search`             | `3546d7a` | Historical native catalog/search                     |
| `twf-broker-v1`                                | `aae52e9` | Accepted read-only broker foundation                 |
| `twf-broker-v2`                                | `69a643e` | Accepted manual trading foundation, at reviewed HEAD |

`twf-broker-v2` is an annotated tag (tag object `9c97aad`); its target, rather than
its tag-object hash, matches HEAD. Earlier frontend/theme/backend/database tags
also remain present. Nothing here creates a new architecture tag.

## B. Repository-derived project status and authority

[TWF-0 acceptance](TWF_TWF0_ARCHITECTURE_ACCEPTANCE_REVIEW.md), the TWF-1 tag,
README hierarchy and the [Broker V1](TWF_BROKER_V1_VERTICAL_SLICE.md)/
[Broker V2](TWF_BROKER_V2_MANUAL_ORDER_ENTRY.md) records establish the accepted
baseline. Broker V2 is **ACCEPTED / FROZEN**, not pending implementation review.
Its old working name V2.1 and intermediate test reports remain historical.
The BW-1–BW-6 inventory is historical planning, not a replacement for V1/V2 status.
UX-B1 and UX-B2 remain **PARTIAL**; UX-B3 remains **PLANNED**.

The current runtime settings contract contains only `density` and
`default_horizon=5d/15d`; the service-client contract remains `foundation.health.v1`.
Neither supplies S&D domain operations. Runtime/migration searches found no
DiscoveryCandidate, DiscoveryEpisode or ScanMatch implementation. Architecture
acceptance does not reinterpret the existing horizon preference, extend a health
DTO implicitly, or make unfinished APS/ACS administration available.

Markdown is normative under the
[engineering standards](TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.md) and
[documentation index](TWF_DOCUMENTATION_INDEX.md). DOCX is a reference companion;
lag is permitted when explicitly inventoried. The four incoming untracked DOCX
files were not created by this review, opened for content comparison or rendered.
Their parity is **unverified**, not certified. Current acceptance/status edits are
Markdown-only. The 2026-09-28 reconciliation's statements about files present then
remain historical; the index now records the actual 2026-09-29 inventory.

The TI integration contract remains proposed and not implementation-frozen. The
TM contract remains provisional pending committed public-surface reconciliation.
Accepting their S&D alignment does not accept a real TI/TM integration. Prior
review records and accepted implementation records remain byte-identical.

## C. Review sources and scorecard

Fully read: [README](../README.md),
[S&D architecture](TWF_SCAN_AND_DISCOVER_ARCHITECTURE.md),
[Opportunity domain](TWF_OPPORTUNITY_DOMAIN_ARCHITECTURE.md),
[Sprint-2 delivery plan](TWF_SPRINT2_SCAN_DISCOVER_DELIVERY_PLAN.md), and the
[2026-09-28 reconciliation record](TWF_SCAN_DISCOVER_ARCHITECTURE_RECONCILIATION.md).
The latter was treated as a claim to verify, not as acceptance authority.

Relevant baseline and extension sections were cross-checked in every normative
source listed in the modification inventory below, plus the unchanged sources
in section H. Actual settings and service-client types were inspected to test
whether the proposal falsely assumes already implemented capabilities.

These are **architecture** PASS results, not runtime/test/browser certifications.
Gate M passes the score/meaning/boundary model with the explicit non-blocking
presentation qualification SD-01; it is not a claim that the palette already exists.

```ini
SND_PRODUCT_COHERENCE = PASS
DOMAIN_LADDER_COHERENT = PASS
DISCOVERY_IDENTITY_MODEL = PASS
SNAPSHOT_TEMPORAL_MODEL = PASS
HORIZON_MODEL = PASS
DISCOVERY_LIFECYCLE = PASS
TOLERANCE_MODEL = PASS
DISCOVERY_EVIDENCE_MODEL = PASS
SND_MARKET_INTELLIGENCE = PASS
LLM_LEVEL0_BOUNDARY = PASS
SND_PROVIDER_NEUTRALITY = PASS
INTERNAL_SCANNER_SCOPE = PASS
DISCOVERY_RELEVANCE_MODEL = PASS
FUTURE_ML_READINESS = PASS
SND_SETTINGS_ALIGNMENT = PASS
SPRINT2_SCOPE_DISCIPLINE = PASS
AUTHORITY_BOUNDARIES_PRESERVED = PASS
SND_DATA_OWNERSHIP = PASS
SND_DEGRADATION_MODEL = PASS
SND_UX_COHERENCE = PASS
SND_TESTABILITY = PASS
ROADMAP_RECONCILED = PASS
```

| Gate               | Independently assessed basis                         | Why the boundary holds                                                                                                                                                                     |
| ------------------ | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| A Product          | S&D §§1–5; plan §§1–2                                | Scan-only can end at ScanMatch; discovery also accepts another source. Neither TI, TM nor a broker login is a dependency.                                                                  |
| B Domain ladder    | Domain §§1, 3, 8; product extension                  | Attention, qualification, construction, readiness and execution have different records/owners; historical generic Candidate terminology is explicitly mapped.                              |
| C Identity         | Domain §§2–3; S&D §§6, 14                            | Stable underlying/listing/native IDs, intent fingerprints and separate episode IDs prevent symbol-only merges and history cloning.                                                         |
| D Temporal         | Domain §3.4; S&D §7                                  | Source-data/observation/receipt/evaluation times differ. Corrections append; two distinct comparable observations, not repeated polls, establish change.                                   |
| E Horizon          | Domain §3.2; S&D §§6, 16                             | Elapsed, trading-session, calendar and event horizons pin calendar/timezone/window semantics. Refresh cannot extend the original opportunity window.                                       |
| F Lifecycle        | Domain §5; S&D §17                                   | Freshness and thesis state are separate. Explicit precedence, expiry, controlled recovery, terminal rejection and closure-before-recurrence prevent resurrection.                          |
| G Tolerance        | S&D §17; domain §§3.2, 5                             | Versioned multidimensional policy uses structure, momentum, volume/context and time; raw drawdown is not a universal invalidator.                                                          |
| H Evidence         | S&D §§7–9, 14; domain §4                             | Typed measures, units, sources, versions, dependence groups and missingness survive; negative and positive evidence can coexist.                                                           |
| I Market context   | S&D §§9, 12; plan §§2–3                              | Benchmark trend, historical volatility and session context are bounded. Sector/news/flows require capability and source evidence; EOD is not labelled live.                                |
| J LLM              | S&D §18; security §31                                | OFF makes no inference call. Citations are checked server-side against eligible supplied evidence; context-only is disclosed. LLM cannot write facts, score, lifecycle or authority.       |
| K Providers        | S&D §§10–12; contracts extension                     | Six domain families have identity/version/capability/health/failure semantics. Separate S&D contracts extend the foundation without turning health DTOs into domain payloads.              |
| L Internal scanner | S&D §12; plan §3                                     | A small price/volume/SMA/relative-volume/breakout set proves independence. The independent data gate prevents a disguised TV dependency.                                                   |
| M Relevance        | S&D §15; domain §4                                   | Score is policy fit, not profit probability; quantization precedes band assignment. Missing evidence cannot inflate a score. SD-01 qualifies the visual specification.                     |
| N Evaluation       | S&D §19; domain §3.12                                | Non-trades, declines, rejected episodes and source availability remain eligible future evaluation inputs; production ML is excluded.                                                       |
| O Settings         | S&D §20; configuration §52                           | Descriptor/scoping/apply-revision model is reused. Initial USER ownership does not invent tenant membership. Security limits and entitlement are distinct from preference.                 |
| P Scope            | Plan §§2–5, 10                                       | Contracts through bounded discovery UX have gates; full TI, construction, LOB, TM and automation are explicitly excluded.                                                                  |
| Q Authority        | Domain §7; S&D §25; broker §§18–19; TI/TM extensions | S&D has no execution credentials or commands. Manual and managed paths remain distinct; TM downtime cannot enable a manual fallback.                                                       |
| R Persistence      | Domain §6; S&D §19; data extension                   | TWF owns runs, episodes, snapshots and annotations; producer facts/provenance are retained. Portable constraints, CAS, short transactions and Alembic are required.                        |
| S Failure          | S&D §21; plan §§7–8                                  | LLM/provider failure is visible; no silent replacement or stale-as-current result. Deterministic use survives optional-provider loss when required evidence remains valid.                 |
| T UX               | S&D §22; UX §22                                      | Raw matches, candidates, score, coverage, freshness, state and grounding stay distinct. No Buy/Sell or LOB-ready implication. Six widths, both themes and eight shell states are required. |
| U Testability      | Plan §§7–9; domain §9                                | Injected clocks, synthetic providers, fault/identity/revision fixtures and disposable databases permit deterministic validation independent of live services.                              |
| V Roadmap          | Detailed roadmap §19; UX-bucket v0.4; README/index   | Sprint 2 overlays existing TWF-3/TWF-2.3 work without renumbering it or completing whole milestones/buckets. Current statuses are reconciled after GO.                                     |

### Adversarial scenario checks

These are document-contract evaluations, not executed S&D runtime tests.

| Scenario                                                         | Required result already specified                                                                                                    | Assessment                                                                         |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------- |
| Same symbol on two exchanges or ambiguous vendor mapping         | Keep listing/native identity and uncertainty; merge only via verified exact mappings                                                 | No symbol-only identity collapse                                                   |
| Same source observation polled twice                             | Retain run evidence without counting two comparable market observations                                                              | S1 cannot become a trend merely by polling                                         |
| Old EOD evidence received now                                    | Preserve original source time and EOD mode; freshness uses applicable evidence policy                                                | Receipt time cannot manufacture live data                                          |
| Clock passes expiry while evidence is refreshed                  | Fixed window wins; GET projects state without hidden writes; mutation records transition                                             | Refresh cannot resurrect an expired episode                                        |
| DEFUNCT recovers; REJECTED later looks attractive                | Only pinned, pre-expiry recovery is permitted; rejected history remains terminal, new linked episode follows closure/cooldown policy | Distinct recovery and recurrence                                                   |
| Expired but not yet rejected episode receives another nomination | One-nonrejected-episode constraint holds until explicit terminal closure; no silent parallel episode                                 | Closure and fresh creation need transactional tests, not a new domain model        |
| Optional evidence disappears; all required evidence is missing   | No denominator renormalization uplift; missing required evidence yields unscored/ineligible output                                   | Missing is neither zero nor false certainty                                        |
| Two providers repeat one underlying source                       | Dependence/lineage policy prevents treating copies as independent confirmation                                                       | No confidence inflation from duplicates                                            |
| LLM fabricates a citation/value or requests an order             | Reject/downgrade unsupported grounding; output has no fact/score/execution authority                                                 | LLM is an optional interpretation consumer                                         |
| TV fails or provider schema changes                              | Typed unavailable/mismatch; no implicit swap; new eligible applied binding and run required                                          | Internal operation is independent, not silent semantic failover                    |
| Concurrent refresh and process restart                           | Expected revision, unique active key, atomic snapshot/head/event update and generation fencing; interrupted attempts remain visible  | Portable invariant with separate SQLite/PostgreSQL acceptance required             |
| Retention removes raw licensed input                             | Preserve permitted lineage/tombstone and disclose replay limits                                                                      | No promise of perfect reconstruction after deletion                                |
| Late result arrives after profile revocation                     | Pinned provenance is not authorization; generation/current permission check blocks application                                       | Saved history does not grant perpetual rights                                      |
| HIGH relevance appears beside an existing broker account         | No discovery dispatch/LOB promotion or TM adoption                                                                                   | Broker V2 confirmation, identity and at-most-one-dispatch invariants remain intact |

## D. Findings

No substantive blocking architecture defect was found. No open CRITICAL, HIGH or
MEDIUM finding, and no missing **ARCHITECTURAL HOOK REQUIRED NOW**, remains.

| ID    | Severity | Timing        | Document/Area                        | Finding                                                                                                                                                    | Required Action                                                                                                                                                                                                                                                                            |
| ----- | -------- | ------------- | ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| SD-01 | LOW      | SAFE TO DEFER | S&D §§15, 22; relevance presentation | Numeric bands and non-colour labels are specified, but the review brief's red/cyan/green families and within-band shading are absent from the design text. | Before S2-6 UX acceptance, specify centralized tokens: LOW red, MEDIUM cyan, HIGH green, lighter-to-darker as score rises within each band. Keep numeric score and text category, and verify contrast/focus in both themes. Recorded here; no visual implementation or token changes made. |
| SD-02 | LOW      | SAFE TO DEFER | README current status                | One paragraph still called UX-B2 planned while its hierarchy correctly recorded partial accepted broker evidence.                                          | **Resolved in this review:** paragraph now says UX-B1/UX-B2 partial, UX-B3 planned. No bucket completion or old acceptance was changed.                                                                                                                                                    |
| SD-03 | NOTE     | SAFE TO DEFER | Documentation index / DOCX inventory | Four untracked domain/product/S&D/plan companions exist now, beyond the earlier reconciliation's inventory; their parity was not established.              | **Inventory resolved:** index and README identify them as pre-existing, unverified companions. Verify/regenerate with rendered-page QA in a separately scoped document-artifact task before claiming synchronization. Markdown governs meanwhile.                                          |

SD-01 does not require redesign of the scoring, persistence or provider contracts.
It is not a reason to block S2-1. The palette requirement above carries into the
UI acceptance gate; this review does not claim it was already present or tested.

## E. Exact reconciliation performed

Only after the GO decision:

1. Recorded current acceptance and the next gate in README, the documentation index,
   detailed roadmap and UX bucket roadmap, retaining the full milestone hierarchy.
2. Added v0.2 acceptance entries/current notices to the three new normative
   documents, retaining their v0.1 proposal history. Clarified S2-0's architecture
   acceptance versus still-open dependent-provider decisions.
3. Superseded the current proposal-status banners in directly affected normative
   documents with dated acceptance notices and history rows. The original dated
   design extensions retain their provenance and separate TI/TM gates.
4. Corrected SD-02 and the current DOCX inventory. Recorded SD-01 for S2-6.
5. Created this review record and registered it in README/index.

No domain algorithm, lifecycle rule, provider contract, runtime file, dependency,
migration, historical review, broker document or DOCX binary was changed.

## F. Exact file created by this review

- [TWF_SCAN_DISCOVER_ARCHITECTURE_ACCEPTANCE_REVIEW.md](TWF_SCAN_DISCOVER_ARCHITECTURE_ACCEPTANCE_REVIEW.md)

## G. Exact files modified by this review

These 18 Markdown files were already present/changed at review start. This inventory
means changes made by the review, not authorship of the entire incoming worktree.

- [README.md](../README.md)
- [TWF_DOCUMENTATION_INDEX.md](TWF_DOCUMENTATION_INDEX.md)
- [TWF_DETAILED_ROADMAP.md](TWF_DETAILED_ROADMAP.md)
- [TWF_UX_BUCKET_ROADMAP.md](TWF_UX_BUCKET_ROADMAP.md)
- [TWF_SCAN_AND_DISCOVER_ARCHITECTURE.md](TWF_SCAN_AND_DISCOVER_ARCHITECTURE.md)
- [TWF_OPPORTUNITY_DOMAIN_ARCHITECTURE.md](TWF_OPPORTUNITY_DOMAIN_ARCHITECTURE.md)
- [TWF_SPRINT2_SCAN_DISCOVER_DELIVERY_PLAN.md](TWF_SPRINT2_SCAN_DISCOVER_DELIVERY_PLAN.md)
- [TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md](TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md)
- [TWF_DATA_ARCHITECTURE.md](TWF_DATA_ARCHITECTURE.md)
- [TWF_SERVICE_CONTRACT_ARCHITECTURE.md](TWF_SERVICE_CONTRACT_ARCHITECTURE.md)
- [TWF_SERVICE_INTEGRATION_ARCHITECTURE.md](TWF_SERVICE_INTEGRATION_ARCHITECTURE.md)
- [TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md](TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md)
- [TWF_UX_ARCHITECTURE.md](TWF_UX_ARCHITECTURE.md)
- [TWF_SECURITY_AUTH_ARCHITECTURE.md](TWF_SECURITY_AUTH_ARCHITECTURE.md)
- [TWF_DEPLOYMENT_ARCHITECTURE.md](TWF_DEPLOYMENT_ARCHITECTURE.md)
- [TWF_TI_INTEGRATION_CONTRACT.md](TWF_TI_INTEGRATION_CONTRACT.md)
- [TWF_TM_INTEGRATION_CONTRACT.md](TWF_TM_INTEGRATION_CONTRACT.md)
- [TWF_TECHNOLOGY_DECISION_RECORD.md](TWF_TECHNOLOGY_DECISION_RECORD.md)

## H. Inspected but unchanged

The following Markdown/source files were read for scope, contracts or acceptance
history and left byte-identical to review start:

- [2026-09-28 reconciliation](TWF_SCAN_DISCOVER_ARCHITECTURE_RECONCILIATION.md)
- [Engineering standards](TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.md)
- [TWF-0 acceptance review](TWF_TWF0_ARCHITECTURE_ACCEPTANCE_REVIEW.md)
- [TWF-0 earlier readiness template](TWF_TWF0_ARCHITECTURE_ACCEPTANCE_AND_CODING_READINESS.md)
- [Broker Workspace architecture](TWF_BROKER_WORKSPACE_ARCHITECTURE.md)
- [Broker Workspace review](TWF_BROKER_WORKSPACE_ARCHITECTURE_REVIEW.md)
- [Broker V1 record](TWF_BROKER_V1_VERTICAL_SLICE.md)
- [Broker V2 record](TWF_BROKER_V2_MANUAL_ORDER_ENTRY.md)
- [Configuration review](TWF_CONFIGURATION_SETUP_ARCHITECTURE_REVIEW.md)
- [TWF-1.5 settings record](TWF_TWF1_5_SETTINGS_FOUNDATION.md)
- [TWF-1.6 service-client record](TWF_TWF1_6_SERVICE_CLIENT_FOUNDATION.md)
- [Settings contracts](../apps/api/src/twf/settings_contracts.py)
- [Service-client contracts](../apps/api/src/twf/integrations/contracts.py)

The runtime/migration trees were also searched for domain implementation and their
Git status checked. All incoming DOCX files were inventoried/fingerprinted only,
not content-reviewed; all are unchanged. In particular, the four pre-existing
untracked companions are:

- `docs/TWF_OPPORTUNITY_DOMAIN_ARCHITECTURE.docx`
- `docs/TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.docx`
- `docs/TWF_SCAN_AND_DISCOVER_ARCHITECTURE.docx`
- `docs/TWF_SPRINT2_SCAN_DISCOVER_DELIVERY_PLAN.docx`

## I. Remaining gate-bound decisions

These do not block the S2-1 contract/fixture slice. They **do** block their dependent
real-provider, live-data or production claims until resolved; GO is not a waiver.

| Decision                                                                                                                   | Required before                                                                                                    |
| -------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Exact TradingView MCP server/version/tools/auth, schemas and bounded limits                                                | S2-3 real adapter coding and verification; explicitly review any scope substitution                                |
| Independent historical/current data source, usage/retention/egress rights, benchmark/calendar and mapping coverage         | S2-2 real data adapter and live internal/context acceptance                                                        |
| Initial approved universe/horizon, fixed policy/rounding/calendars, score/tolerance/freshness values and missing-bar rules | Corresponding deterministic schema/fixture implementation first; approved real-data profile before live nomination |
| Optional hosted LLM binding/model, egress/secret policy, grounding contract and token/cost limits                          | LLM-enabled slice/activation; LLM OFF remains a complete supported mode                                            |
| Capture/retention/deletion limits and operational budgets                                                                  | Relevant persistence/provider slice and production acceptance; no implicit unlimited defaults                      |
| Relevance palette/shading tokens and accessible contrast                                                                   | S2-6 UX acceptance (SD-01)                                                                                         |
| DOCX content/layout synchronization                                                                                        | A claim of synchronized companions or a document-artifact freeze (SD-03)                                           |

Numerical fixtures and wire schemas are bounded implementation outputs, not licence
to invent new state ownership or reinterpret the accepted lifecycle. Source-specific
rules must be versioned and reviewable before their consumers are implemented.
Full TI/TM public contract resolution, construction/LOB and production ML remain
**OUT OF SCOPE**, not hidden Sprint-2 dependencies.

## J–K. Decision and exact authorization boundary

**GO_S2_SD_IMPLEMENTATION** authorizes the architecture basis and staged Sprint-2
implementation under the delivery plan. It does not begin implementation in this
review. Start with a bounded S2-1 prompt fixing typed domain/provider contracts,
identity/horizon/evidence/failure semantics and deterministic synthetic fixtures.
S2-0 decisions needed by that slice must be recorded in its prompt; real adapters
and production modes wait on their own source/security/policy gates.

The overall authorized design ends at DiscoveryCandidate: scan-only and scan +
discover, synthetic alternative candidate-source proof, bounded internal scanning
and market context, gated TV adapter, optional LLM Level-0/OFF, versioned settings,
immutable history, deterministic relevance/lifecycle and responsive discovery UX.
Each slice needs implementation validation and independent acceptance; architecture
GO does not complete TWF-2, TWF-3, UX-B1 or UX-B2.

This acceptance **does not authorize** TI deep intelligence, Opportunity
qualification, Trade Construction, LOB implementation, TM integration/adoption,
autonomous trading, direct LLM execution, production ML/self-learning, generic
continuous alerts, every external provider or unrestricted real-money automation.
It adds no S&D broker command, no permissions bypass and no weakening of frozen
Broker V2 or future TM-managed account ownership.

## L–M. Recommended Git action and next implementation gate

Recommend an explicit architecture/docs commit after reviewing this acceptance
record and the complete Markdown diff, for example:
`docs: accept Scan and Discover architecture and Sprint-2 scope`.
Stage only reviewed Markdown paths; do not blindly include the unverified incoming
DOCX companions. An annotated `twf-scan-discover-architecture-v0.2` tag on that
reviewed documentation commit would identify architecture acceptance, not a runtime
freeze. These are recommendations only; no Git mutation was performed.

Next prepare **S2-1 Domain Contracts and Synthetic Provider Foundation** with an
exact file/schema/fixture scope and explicit exclusions. Require deterministic
identity collisions, multiple intents, immutable timestamps, S1/S2 comparability,
window boundaries, missing/conflicting evidence, lifecycle precedence/recovery,
relevance boundaries, provider mismatch, LLM OFF and no-execution-authority cases.
Select only the slice's necessary policy fixtures. Do not start real TradingView,
market-data or LLM clients under a generic “implement Sprint 2” instruction before
their remaining gates are satisfied.

## Validation evidence

Before status changes, independently reproduced **19 Markdown parses, 186 local
links/anchors and 27 Mermaid diagrams**, with no failures. All 27 diagrams were
re-parsed and rendered in local headless Chromium; no external provider was used.
That validates diagram construction, not rendered product UX or Safari compatibility.

Post-reconciliation validation covers the full incoming-and-review Markdown set:
Markdown parsing, local links/anchors, new-document index coverage, status and key
terminology consistency, `git diff --check`, and incoming-file hash/Git checks.
Final results: **20 Markdown files parsed, 281 local links/anchors valid, all five
new Markdown records covered by the index, and all 27 diagram definitions unchanged
from the successful independent render**. Current-status and the 17 required-term
searches were reviewed; historical proposal rows and TI/TM provisional wording remain
intentional. The new acceptance record passes Prettier. `git diff --check` passes.
Hash comparison confirms exactly the 18 listed existing Markdown files changed and
this one review record was created; all other incoming files, including every DOCX
and historical record, remain unchanged. Branch, HEAD, Broker V2 tag and empty index
are preserved. Runtime tests,
production builds, migrations and provider smoke were not run for documentation-only
acceptance; earlier Broker V2 test results remain historical evidence.

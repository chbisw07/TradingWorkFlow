# TWF Scan & Discover Architecture Reconciliation Record

## Status and role

| Version | Date       | Status                                   | Role / change                                                                                                                                  |
| ------- | ---------- | ---------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| 0.1     | 2026-09-28 | PROPOSED / RECONCILED / READY FOR REVIEW | Reference audit of repository truth, documentation changes, explicit design decisions, unresolved implementation gates and acceptance coverage |

This is a documentation-work record, not an independent acceptance review, a fourth
competing domain specification or an implementation report. The request is the
2026-09-28 “Scan & Discover Architecture + Product Architecture Reconciliation”
brief. No runtime source, DOCX, Git commit, tag or push is part of this task.

## 1. Phase A — repository evidence

| Check                           | Observed starting state                                                                                                                                                                          |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Branch                          | `main`                                                                                                                                                                                           |
| HEAD                            | `69a643e372c48a6d3d85ce57962ca05c38c4c3dc`                                                                                                                                                       |
| HEAD subject                    | `TWF Broker V2: complete manual trading foundation`                                                                                                                                              |
| Working tree before this task   | Clean; no pre-existing uncommitted edits                                                                                                                                                         |
| Broker V2 freeze                | Annotated `twf-broker-v2` resolves to HEAD                                                                                                                                                       |
| Earlier foundations             | `twf-0-architecture-baseline`, `twf-1-application-foundation`; TWF-1 closure at `e3852d3`                                                                                                        |
| Broker architecture             | v0.3 reviewed/accepted/tagged at `0b73492`; Markdown/DOCX pair unchanged                                                                                                                         |
| Broker V1                       | Accepted implementation `4ffff9d`, main integration `aae52e9`, `twf-broker-v1`                                                                                                                   |
| Historical branches/records     | Prior broker work/archive and BW milestone evidence retained; no history rewrite                                                                                                                 |
| Requested source documents      | Present; no competing S&D or Opportunity-domain authority found                                                                                                                                  |
| Runtime reality relevant to S&D | Existing scanner/TI/TM/LLM clients expose `foundation.health.v1`; settings implement bounded personal preferences. No implemented S&D domain pipeline or generic candidate persistence was found |

Inspected documentation and selected runtime contracts/schema inventory independently
of previous implementation claims. Master/component DOCX text was inspected as a
historical reference; no DOCX was modified. Repository status/tag evidence takes
precedence over stale “pending” wording inside historical implementation records.
No remote fetch/push, provider request, credential read or real order was needed.

### Reconciliation outcome before writing

No unresolved authority contradiction required stopping. The request explicitly
evolves the generic Candidate concept and makes independently useful S&D the next
proposed delivery. The current broker architecture already permits independent
manual utility, while TI remains advisory and TM governs its managed scope.
The older schedule is a sequencing decision, not a safety prerequisite for scans.

External provider selection/data rights, initial thresholds/calendars and later
satellite schemas remain gated choices. They block their dependent implementation
or production activation, not the definition of provider-neutral discovery semantics.

## 2. Authority and scope of the revision

| Topic                                                          | Design owner                                                                 |
| -------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Product direction/current milestone truth                      | Product/system architecture plus README/index and accepted milestone records |
| Shared stage identities, lineage and ownership                 | [Opportunity domain](TWF_OPPORTUNITY_DOMAIN_ARCHITECTURE.md)                 |
| S&D behavior, providers, evidence, relevance, lifecycle and UX | [S&D architecture](TWF_SCAN_AND_DISCOVER_ARCHITECTURE.md)                    |
| Sprint-2 deliverables, exclusions and gates                    | [Sprint-2 plan](TWF_SPRINT2_SCAN_DISCOVER_DELIVERY_PLAN.md)                  |
| Configuration/security/integration/deployment invariants       | Existing normative architecture with the explicit dated proposed extensions  |
| TI/TM/Broker authority                                         | Existing contracts and accepted broker records; no new execution authority   |
| Evidence of this reconciliation                                | This reference record                                                        |

For proposed S&D work, the new precise definitions supersede only explicitly
identified generic/scheduling wording. Accepted historical records remain unchanged.
The proposal does not silently override security, satellite public-contract gates or
Broker V2 semantics. Review must resolve any new conflict before implementation.

## 3. Phase B — exact files created

| File                                                                                                 | Purpose                                                                                                                                                     |
| ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [TWF_SCAN_AND_DISCOVER_ARCHITECTURE.md](TWF_SCAN_AND_DISCOVER_ARCHITECTURE.md)                       | Comprehensive normative S&D proposal with provider contracts, diagrams, deterministic discovery, optional LLM, temporal/history model, settings, UX and FAQ |
| [TWF_OPPORTUNITY_DOMAIN_ARCHITECTURE.md](TWF_OPPORTUNITY_DOMAIN_ARCHITECTURE.md)                     | Normative shared entity/ownership/lifecycle proposal, including future-stage boundaries                                                                     |
| [TWF_SPRINT2_SCAN_DISCOVER_DELIVERY_PLAN.md](TWF_SPRINT2_SCAN_DISCOVER_DELIVERY_PLAN.md)             | Normative bounded delivery, provider/data gates and acceptance plan                                                                                         |
| [TWF_SCAN_DISCOVER_ARCHITECTURE_RECONCILIATION.md](TWF_SCAN_DISCOVER_ARCHITECTURE_RECONCILIATION.md) | This reference audit and change inventory                                                                                                                   |

All four are v0.1 proposed/reconciled/ready for review. “Normative proposal” identifies
the intended source of design truth for review, not a new acceptance/freeze decision.

## 4. Phase C — exact files updated and why

All paths below are repository-relative. Updates retain earlier text/history and
add dated revisions, with targeted current-status/supersession wording where needed.
There is no mechanical rewrite of the historical corpus.

| File                                                                               | Required minimum reconciliation                                                                                                     |
| ---------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `README.md`                                                                        | Preserve hierarchical accepted milestones; identify proposed S&D next; link new authorities and companion policy                    |
| `docs/TWF_DOCUMENTATION_INDEX.md`                                                  | Add four records, scoped authority, review status and exact stale companion inventory                                               |
| `docs/TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md`                               | Explicit product ladder, implemented/proposed/future distinction and changed delivery priority                                      |
| `docs/TWF_DATA_ARCHITECTURE.md`                                                    | Stage-specific identities, TWF-owned discovery aggregates, immutable evidence/history and retention/transaction rules               |
| `docs/TWF_SERVICE_CONTRACT_ARCHITECTURE.md`                                        | Refine external scan vs TWF discovery ownership; proposed families separate from health-only/Broker contracts                       |
| `docs/TWF_SERVICE_INTEGRATION_ARCHITECTURE.md`                                     | S&D composition and next-delivery overlay; local/remote/provider independence and no silent fallback                                |
| `docs/TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md` | Proposed v0.7 S&D descriptor/profile extension to accepted v0.6 basis; scopes, capabilities, entitlements and secrets stay separate |
| `docs/TWF_UX_ARCHITECTURE.md`                                                      | Independent modes, queue/details/history, relevance vs TI confidence, grounding and temporal states                                 |
| `docs/TWF_TI_INTEGRATION_CONTRACT.md`                                              | Exact candidate/snapshot handoff; future separate qualification record preserves TI claims/advisory role                            |
| `docs/TWF_TM_INTEGRATION_CONTRACT.md`                                              | Future LOB/construction are not authority; pre-execution managed governance and explicit adoption remain mandatory                  |
| `docs/TWF_DETAILED_ROADMAP.md`                                                     | Proposed Sprint-2 overlay after Broker V2, no renumbering/completion of TWF-2/3/4/5/6                                               |
| `docs/TWF_UX_BUCKET_ROADMAP.md`                                                    | Proposed v0.4 discovery contribution; UX-B1/B2 partial and UX-B3 planned unchanged                                                  |
| `docs/TWF_TECHNOLOGY_DECISION_RECORD.md`                                           | Bounded modular S&D direction; no SDK/server/vendor/queue/ML dependency silently chosen                                             |
| `docs/TWF_SECURITY_AUTH_ARCHITECTURE.md`                                           | MCP allowlists, untrusted criteria/output, LLM egress/citation isolation and no authority                                           |
| `docs/TWF_DEPLOYMENT_ARCHITECTURE.md`                                              | Existing deployment reused; bounded durable runs, restart/fencing, no new readiness semantics                                       |

Security and deployment need small amendments because MCP/LLM data egress and durable
user-triggered scans add explicit operational boundaries. Engineering standards,
broker architecture and accepted implementation records require no semantic change.

## 5. Files inspected but intentionally unchanged

Inspection included full governing sections and targeted status/contract/ownership
sections of supporting historical records, not a claim to reaccept all past work.

| Exact repository path(s)                                        | Reason left unchanged                                                                                                      |
| --------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `docs/TWF_HIGH_LEVEL_DISCUSSION_RECORD.md`                      | Historical intent explicitly yields to later normative architecture                                                        |
| `docs/TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.md`              | Existing typed contracts, modularity, tests, migration and secret rules already apply                                      |
| `docs/TWF_RESPONSIVE_TRADING_APPLICATION_ARCHITECTURE.md`       | Existing responsive/token/state-primitives baseline reused; no shell redesign                                              |
| `docs/TWF_BROKER_WORKSPACE_ARCHITECTURE.md`                     | Accepted v0.3 authority/identity/command gates preserved; old schedule is historical under the new current-roadmap overlay |
| `docs/TWF_BROKER_WORKSPACE_ARCHITECTURE_REVIEW.md`              | Historical independent acceptance evidence must not be rewritten                                                           |
| `docs/TWF_BROKER_V1_VERTICAL_SLICE.md`                          | Accepted/frozen runtime and setup record unchanged                                                                         |
| `docs/TWF_BROKER_V2_MANUAL_ORDER_ENTRY.md`                      | Accepted/frozen manual-order, LTP and read-model record unchanged                                                          |
| `docs/TWF_BROKER_UX_INFORMATION_ARCHITECTURE.md`                | Historical pre-rebuild UX record; not current S&D design authority                                                         |
| `docs/TWF_BW1_SYNTHETIC_BROKER_READ_ONLY_FOUNDATION.md`         | Historical bounded implementation/evidence                                                                                 |
| `docs/TWF_BW2_ONE_REAL_BROKER_READ_ONLY_PLAN.md`                | Historical provider/gate selection, not S&D external-provider selection                                                    |
| `docs/TWF_BW2_1_SECURE_PROVIDER_ACCOUNT_FOUNDATION.md`          | Historical security foundation record                                                                                      |
| `docs/TWF_BW2_2_ZERODHA_AUTH_ACCOUNT_BINDING.md`                | Historical authentication binding record                                                                                   |
| `docs/TWF_BW2_3_ZERODHA_NATIVE_CATALOG_SEARCH.md`               | Historical catalog/search acceptance; does not supply a stock-classification or historical market-data service             |
| `docs/TWF_BW2_4_ZERODHA_HOLDINGS_POSITIONS.md`                  | Historical pre-rebuild hold, not current Broker V2 acceptance state                                                        |
| `docs/TWF_CONFIGURATION_SETUP_ARCHITECTURE_REVIEW.md`           | Accepted v0.6 design decisions preserved; proposed extension recorded in normative Markdown                                |
| `docs/TWF_TWF0_ARCHITECTURE_ACCEPTANCE_REVIEW.md`               | Original acceptance evidence                                                                                               |
| `docs/TWF_TWF0_ARCHITECTURE_ACCEPTANCE_AND_CODING_READINESS.md` | Historical coding-readiness scope                                                                                          |
| `docs/TWF_TWF1_0_REPOSITORY_PROJECT_SCAFFOLD.md`                | Accepted scaffold implementation record                                                                                    |
| `docs/TWF_TWF1_1_FRONTEND_SHELL.md`                             | Accepted shell/state/accessibility record                                                                                  |
| `docs/TWF_TWF1_1A_THEME_SWITCHING_FOUNDATION.md`                | Accepted theme/first-paint record                                                                                          |
| `docs/TWF_TWF1_2_BACKEND_SHELL.md`                              | Accepted API/readiness/observability semantics                                                                             |
| `docs/TWF_TWF1_3_DATABASE_FOUNDATION.md`                        | Accepted persistence/session/migration foundation                                                                          |
| `docs/TWF_TWF1_4_USER_LOGIN_FOUNDATION.md`                      | Accepted personal identity boundary                                                                                        |
| `docs/TWF_TWF1_5_SETTINGS_FOUNDATION.md`                        | Bounded settings implementation; no claims that all proposed S&D settings exist                                            |
| `docs/TWF_TWF1_6_SERVICE_CLIENT_FOUNDATION.md`                  | Health-only implementation; domain methods need separately versioned contracts                                             |
| `docs/TWF_MASTER_PRODUCT_ARCHITECTURE.docx`                     | Inspected historical text; stale companion, regeneration deferred                                                          |
| `docs/TWF_COMPONENT_ARCHITECTURE.docx`                          | Inspected historical text; stale companion, regeneration deferred                                                          |

Selected runtime cross-checks were read-only: `apps/api/src/twf/integrations/contracts.py`,
`apps/api/src/twf/settings_contracts.py`, `apps/api/src/twf/infrastructure/database.py`
and the infrastructure/Alembic inventory. These confirm health-only service contracts,
finite USER preference values and explicit portable session/migration ownership.
No live database or secret values were read to construct this architecture.

## 6. DOCX staleness and publication handoff

The following artifacts were left byte-for-byte unchanged and require regeneration
or synchronization **after Markdown acceptance**, not in this task:

1. `docs/TWF_MASTER_PRODUCT_ARCHITECTURE.docx`
2. `docs/TWF_COMPONENT_ARCHITECTURE.docx`
3. `docs/TWF_DATA_ARCHITECTURE.docx`
4. `docs/TWF_SERVICE_CONTRACT_ARCHITECTURE.docx`
5. `docs/TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.docx`
6. `docs/TWF_UX_ARCHITECTURE.docx`
7. `docs/TWF_SECURITY_AUTH_ARCHITECTURE.docx`
8. `docs/TWF_DEPLOYMENT_ARCHITECTURE.docx`

Master/component already predate configuration and broker evolution; configuration
DOCX remains v0.5. The others do not reflect these new S&D amendments. The broker
v0.3 Markdown/DOCX pair is unchanged and is not relabelled stale by unrelated S&D
work. Engineering and historical acceptance companions retain reference roles.
No DOCX counterpart exists yet for the three new normative records; publication
is a separate later task, not an omitted implementation deliverable.

## 7. Contradictions resolved and decisions applied

| Earlier ambiguity / apparent conflict                               | Explicit reconciliation                                                                                                       |
| ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| One generic Candidate from scan through trading                     | Distinct ScanMatch, DiscoveryCandidate, Opportunity, TradeOpportunity, LOBEntry and execution/managed references              |
| “Scanner owns discovery logic” vs TWF S&D                           | External provider owns native criteria/output; TWF owns cross-source intent/context evaluation and candidate lifecycle        |
| TM-before-Scanner delivery sequence                                 | Dated sequence retained; S&D is next proposed independent product slice; TM managed authority not weakened                    |
| Product ladder puts TM after broker                                 | That node is post-execution supervision; managed assessment/approval is also required before dispatch, with explicit adoption |
| Broker utility vs managed full-workflow diagrams                    | Existing independent unmanaged manual Broker V2 path remains unchanged; S&D never invokes it                                  |
| “Candidate score” could imply probability                           | Discovery Relevance is configurable deterministic fit/coverage, not PoP/TI confidence; LLM has zero score weight              |
| Market context deferred to future TI                                | Bounded benchmark/regime/session intelligence is Sprint-2 input; TI deeper claims/qualification remain future                 |
| TradingView integration might determine core model                  | Provider-neutral contracts and independent internal data/scanner path; real MCP schema/service is a verification gate         |
| LLM explanation might imply factual authority                       | Optional Level-0 with server-validated grounding/citations, no score/lifecycle/permission authority                           |
| One row overwritten as candidate changes                            | Stable episode plus immutable S1…Sn, distinct observations, correction lineage and versioned decisions                        |
| Stale/defunct/expired/rejected conflated                            | Freshness projection, pre-terminal tolerance breach, ended opportunity window and terminal reasoned rejection are distinct    |
| Same stock always one candidate                                     | Subject × intent/horizon × episode with explicit observation basis and recurrence                                             |
| Existing `5d`/`15d` preference treated as sufficient horizon schema | Extensible HorizonSpec; no silent reinterpretation of saved values without a migration/confirmation decision                  |
| Configuration architecture mistaken for implemented settings        | Accepted finite preferences/health clients preserved; explicit domain extension needed                                        |
| Future ML learns only executed trades                               | Retain nomination/episode/evidence history and later evaluate untraded candidates too; no ML runtime now                      |
| DOCX synchronization would expand task                              | Mark exact companions stale; regenerate after Markdown acceptance, leave binaries untouched                                   |

No changes were made to frozen broker contracts, native identities, preview,
confirmation, idempotency, unknown-submission handling, LTP truth or account permissions.

## 8. Diagram and requirement coverage

The main S&D document contains 20 Mermaid diagrams; the domain document adds shared
entity/lifecycle/sequence diagrams, the plan a gate diagram and product architecture
the updated conceptual ladder. The diagram set is repository-native text; no DOCX
or image-generation artifact is needed for this phase.

| Required diagram                                             | Location                                |
| ------------------------------------------------------------ | --------------------------------------- |
| TWF high-level architecture                                  | S&D §3 and product/system §36           |
| S&D context and components                                   | S&D §4 (two diagrams)                   |
| Scan-only / Scan + Discover / external-source flows          | S&D §5 (three diagrams)                 |
| Provider/pluggability                                        | S&D §10                                 |
| Market intelligence                                          | S&D §9                                  |
| LLM Level-0 grounded flow                                    | S&D §18                                 |
| DiscoveryCandidate conceptual model                          | Opportunity domain §3.6                 |
| Underlying ↔ intent graph                                    | S&D §6 and Opportunity domain §2        |
| Episodes and S1…Sn                                           | S&D §7                                  |
| Candidate lifecycle                                          | S&D §17 and Opportunity domain §5       |
| Evidence model                                               | S&D §8                                  |
| Relevance/calibration flow                                   | S&D §15                                 |
| Future candidate → TI → Opportunity → TradeOpportunity → LOB | S&D §25                                 |
| Execution/TM/feedback                                        | S&D §25                                 |
| Principal use cases                                          | S&D §23                                 |
| Main sequences                                               | S&D §23 (two) and Opportunity domain §7 |
| Deployment/local vs remote                                   | S&D §24                                 |

### Final architectural statements checked

| Requirement                                            | Design evidence                                                                     |
| ------------------------------------------------------ | ----------------------------------------------------------------------------------- |
| Scan can be used without Discovery                     | Explicit scan-only flow and acceptance journey                                      |
| Scan + Discovery works                                 | Separate evaluator and run lineage                                                  |
| External source can feed Discovery later               | CandidateSource seam, synthetic non-scan test; real external ingestion later        |
| No LLM required                                        | Deterministic eligibility/relevance/lifecycle; OFF acceptance                       |
| Hosted LLM replaceable                                 | One applied binding through provider-neutral LLMService; actual provenance retained |
| Removing TV leaves viable architecture                 | Independent approved data reader/internal V0; real data gate explicit               |
| TV does not define core domain                         | Native MCP schema stays adapter-side                                                |
| Several market-intelligence providers fit              | Separate family; internal benchmark/session baseline and optional future adapters   |
| Candidate is intent/horizon/evidence-relative          | Domain identity and pinned episode/profile/window                                   |
| Stale is not invalid                                   | Orthogonal freshness/effective-state projection                                     |
| Defunct can be evaluated before rejection              | Tolerance breach/recovery and reasoned rejection                                    |
| Expired then rejected                                  | Fixed-window projection and explicit EXPIRED closure reason                         |
| Same underlying can recur                              | New linked episode after terminal closure, no resurrection                          |
| Snapshots remain immutable                             | Append/correction records, CAS head and replay distinction                          |
| User sees why candidate exists                         | Evidence/contributions/context/reasons in details and history                       |
| Grounded vs context-only is clear                      | Validated citation metadata and distinct UX badge                                   |
| Relevance is not profit probability                    | Explicit semantics, coverage/threshold rules and FAQ                                |
| Future ML can evaluate non-trades                      | Episode/declined-decision lineage and future labels                                 |
| Clean TI handoff                                       | Exact immutable candidate/evidence references, separate TI authority                |
| Trade construction does not change candidate semantics | Distinct qualified and constructed objects                                          |
| LOB consumes prepared TradeOpportunities               | Future readiness projection, no order/execution ownership                           |
| Broker/TM authority intact                             | No S&D dispatch; explicit managed pre-assessment/adoption and no fallback           |

## 9. Remaining decisions and review gate

1. Select and verify the actual TradingView MCP service/version/tools/auth and
   permitted data operations; do not assume an official/universal API exists.
2. Approve independent internal-scanner data, benchmark/calendar/reference identity,
   adjustment/correction handling, retention rights and LLM egress rights.
3. Accept the initial listed-underlying universe, profile/horizon presets, required
   evidence, scan windows, relevance weights/coverage, tolerance and freshness policy.
4. Set deployment-specific work/deadline/page/body/concurrency, inference cost and
   retention limits; define deletion/tombstones and interrupted-run recovery.
5. Choose the first optional hosted LLM binding/model and validated structured
   grounding contract; other real providers remain replaceable future adapters.
6. Keep TI qualification, Trade Construction, LOB readiness, TM public schema/adoption
   and evaluation/ML calibration for their own later design/implementation gates.

These are not hidden “AI will solve it” gaps: each maps to a blocked dependent slice
in Sprint-2 S2-0. No runtime GO, provider activation or claim of calibrated trading
performance follows from completing these documents.

**Readiness:** the documentation package is ready for independent architecture
review. The recommended next gate is review of all three normative proposals,
changed authority/ownership statements, diagram consistency and S2-0 resolutions,
then a separately authorized bounded implementation prompt. No new architecture
or implementation is accepted/frozen by the authoring task.

## 10. Documentation validation

| Check                         | Result                                                                                                                                                                                |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Changed-file Markdown parsing | PASS — all 19 Markdown files parse with the repository's Prettier Markdown parser                                                                                                     |
| New-document formatting       | PASS — all four new records pass Prettier; historical documents were not mechanically reformatted                                                                                     |
| Local links and anchors       | PASS — 186 references across changed files resolve                                                                                                                                    |
| Mermaid syntax and rendering  | PASS — all 27 diagrams parse and render using Mermaid 11 in headless Chromium; representative product/lifecycle renders inspected                                                     |
| Terminology and ownership     | Checked stage distinctions, source/time semantics, no-LLM/TV independence, grounding, lifecycle and TI/TM/Broker boundaries; coverage matrix above                                    |
| Scope and baseline hashes     | PASS — 15 existing Markdown files changed, four Markdown files created; the other 202 originally tracked files, including runtime, DOCX and historical records, remain byte-identical |
| Git references                | PASS — `main`, HEAD and the Broker V2 tag unchanged                                                                                                                                   |
| Whitespace                    | PASS — `git diff --check`                                                                                                                                                             |

Runtime tests/builds were not rerun: no runtime source/dependency/schema changed,
and those suites cannot accept a documentation-only S&D proposal. Provider servers,
licenses, live data and model bindings remain unverified gated decisions, not passed
runtime checks. Validation tools and rendered artifacts were confined to `/tmp`;
no project dependency, package manifest or lockfile changed.

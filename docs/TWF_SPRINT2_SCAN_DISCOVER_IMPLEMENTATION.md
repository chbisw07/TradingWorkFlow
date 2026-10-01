# Sprint 2 Scan & Discover — integrated implementation record

**Date:** 2026-09-30  
**Starting checkpoint:** `a5d7859944cbb25e143488f129cc0bab99dc262b` (`twf-s2-3-tradingview-mcp-provider`)  
**Program state:** **IMPLEMENTED / READY FOR USER VALIDATION**  
**Acceptance state:** pending user validation, adversarial review, consolidated hardening, and final freeze

This record covers the integrated S2-4 through S2-8 implementation. It does not alter the accepted/frozen status of S2-0 through S2-3 and does not claim final Sprint-2 acceptance. Scan & Discover ends at `DiscoveryCandidate`; it has no Opportunity, LOB, execution, or TM authority.

## Product capability

The user can now select a bounded symbol universe, provider validation path, scan profile, discovery intent, and time horizon; run a scan; inspect normalized matches; evaluate owner-scoped candidates with context, evidence, deterministic relevance, horizon-aware tolerance, lifecycle, and provenance; review immutable snapshot history; request an optional grounded Level-0 explanation; and manage bounded discovery settings. Internal Scanner V0 works without TradingView or an LLM. TradingView mode uses the deterministic synthetic exact-batch path for CI and product validation; it does not make a live provider call.

## Product refinement / user-validation stabilization pass

The pre-validation refinement keeps every Sprint-2 API, persistence, relevance, tolerance, lifecycle, evidence, owner-isolation, and provider contract unchanged while making the surface read as an operator workspace. Scan setup is grouped by universe, scan logic, discovery intent, horizon, provider, and context requirement. The latest-run summary now distinguishes universe size, matches, discovery candidates, and typed market-context availability. Human-readable match explanations and concise metrics are primary; raw reason codes, match IDs, native IDs, transformation versions, and lineage remain available inside expandable details.

Provider cards now pair an explicit operational state with a separate `LIVE`, `SYNTHETIC DATA`, or `VALIDATION / SYNTHETIC` mode label, last success/error information, and capabilities. Synthetic/live truth is carried by this persistent status strip without a separate page-wide banner. Candidate rows combine numeric relevance with LOW/MEDIUM/HIGH bands and use explicit freshness wording: `FRESH`, `STALE`, or **Source time unavailable** when the provider supplied no timestamp. Missing evidence and conflicting evidence are visually distinct and are never assigned a fabricated neutral value.

Candidate review now explains relevance as an attention score, coverage as the available share of expected evidence, episode as the current discovery episode, and tolerance as a horizon-aware envelope. Backend tolerance states remain unchanged; the presentation maps `DEGRADED` to **Near limit** and `BREACHED` to **Outside**, with the internal state retained in accessible detail. Evidence cards lead with evidence type/state/summary and place raw provenance one level deeper. Market context uses human wording for absent evidence, snapshot history shows the newest immutable observation and its first material change, and optional Level-0 output is presented as **Optional AI explanation** with explicit disabled/available/generating/grounding states and unchanged authority limits.

Manual dismiss, defunct, and recovery actions now explain their consequence, require confirmation, and submit action-specific audit reasons through the existing revisioned lifecycle contract. Selected candidate rows remain visibly associated with the focused review panel; the panel receives focus and scrolls predictably. At narrow widths, data tables recompose into labeled row cards while keeping semantic table markup, keyboard focus, visible state text, and technical details available. Discovery settings are grouped into General, Providers, Scan profiles, Freshness, LLM, History / retention, and expandable advanced relevance/experimental controls.

## Final product stabilization before formal user validation

The final pre-validation stabilization keeps the sidebar as the sole route navigation for **Scanners** and **Candidates**. The duplicate page-level destination tabs were removed. The Scanners route now uses one workstation composition: a compact setup-and-history rail at left and the latest result plus active discovery queue in the center. The candidate inspector is conditional: no empty inspector card or reserved column is rendered until **Review** is selected, so the center consumes the available width; an open inspector creates an intentional third desktop region, keeps the selected row highlighted, and disappears completely when closed. A compact status strip above the workstation owns provider readiness, market-context state, optional AI state, and latest-scan state. Provider status no longer consumes a tall left-rail card. At narrower widths the regions recompose into two columns and then one column; the open inspector stacks below the workflow and semantic tables become labeled cards at mobile widths.

Scan Profile and Discovery Intent are presented as separate concepts. A profile states the mechanical pattern TWF searches for, while intent states how a resulting setup should be interpreted and tracked. Profile selection recommends an intent and horizon. After a user explicitly changes either field, later profile changes preserve that override until **Apply suggestion** is selected. The context policy is expressed as **Require complete context**, **Allow partial context**, or **Context optional**. Missing context always remains visible. It blocks admission when complete context is required, reduces the expected evidence coverage when partial context is allowed, and remains outside the required relevance/coverage denominator when context is optional.

The top status strip separates informational **Mode** from operational **Status**. Internal Scanner V0 is identified as deterministic **Synthetic Data**. TradingView distinguishes **Validation · Synthetic** from **Live** mode and uses text states such as Ready, Rate limited, Authentication required, Unavailable, Disabled, and Degraded in addition to semantic color. Status elements are informational rather than button-shaped. Rate limiting is shown as an operational constraint and does not imply that live exact-row proof succeeded.

Internal Scanner fixtures now provide deterministic, differentiated market-shaped archetypes for RELIANCE, MCX, HDFCBANK, INFY, BSE, NIFTY, BANKNIFTY, and TCS. Breakout, pullback, momentum, relative-volume, trend, weak, and bearish cases naturally produce different match sets. Repeated scans progress deterministically and append immutable snapshots with changed relevance/evidence where the fixture state advances. The provider status strip persistently identifies synthetic mode and prevents a live-market claim.

Canonical product identity now classifies NIFTY, BANKNIFTY, FINNIFTY, and MIDCPNIFTY as `INDEX`; equities remain `EQ`. Existing stable instrument IDs are preserved. Result rows lead with human explanations derived from the actual matched metrics, formatted price/momentum/RVOL/RSI fields, and an explicit freshness state. Raw observation bases, provider IDs, lineage, and technical identifiers remain available under details. Candidate evidence leads with **Scan + market context**, while exact provider provenance remains inspectable.

A dedicated **Scan History** block sits immediately below **Scan Setup** in the left rail. It shows the five most recent active scans as compact entries with profile, provider, universe size, result count, time, and status. **View** selects the persisted execution summary without creating candidates. **Use setup** restores universe, profile, discovery intent, horizon, provider, and context requirement without automatically running a scan. **Archive** hides a run from the recent operational list while retaining the run, normalized matches, lineage, and evidence in the database.

**Past scans** opens on demand as a modal rather than widening the rail. It supports Today, Last 7 days, Last 30 days, all-time, and custom datetime filtering, plus provider, profile, status, and active/archived filters. Archived scans remain owner-scoped, visible there, and can be restored. There is no Clear history, permanent delete, purge, or physical deletion path. The prior central history block was removed so the center remains focused on the latest summary/result and discovery queue. Before a candidate is selected there is also no empty inspector placeholder or reserved right column.

Candidate review remains sticky on wide screens and keeps symbol, intent, horizon, and instrument identity above the fold. Evidence states use text plus consistent Present, Missing, Conflicting, Unavailable, and Stale colors; tolerance uses Within, Near limit, Outside, Unknown, and Unavailable. Boolean/category measurements are translated into phrases such as **Condition matched** and **Broad regime: Constructive** while raw typed values remain under provenance details. The theme toggle now uses the same accessible navy/white control language as the workstation. The discovery queue uses the existing owner-scoped candidate persistence and does not introduce Opportunity, LOB, recommendation, risk, sizing, or execution authority.

## U1 behavioral stabilization

Formal U1 validation found six related correctness problems and this bounded pass addresses them without beginning U2 lifecycle validation or final hardening:

- Match explanations now come from the matched provider predicates. The web surface renders those authoritative reasons directly, so breakout, pullback, momentum, relative-volume, and continuation scans no longer collapse into one generic label.
- Scan definitions carry an explicit `LONG`, `SHORT`, or legacy-neutral direction. Long and short profiles use corresponding bullish or bearish predicates; candidate admission requires provider evidence polarity that supports the selected intent. Pullback in uptrend is long-only.
- The request contract and UI enforce repository-native intent/horizon rules: intraday intent accepts `intraday`/`1d`, positional intent accepts `5d`/`15d`, and incompatible choices produce concise guidance. Explicit valid overrides remain intact until **Apply suggestion** is selected.
- After execution, the queue defaults to **Current scan** and exposes separate **Active** and **All** views with counts. A zero-result run therefore remains visibly zero while prior owner-scoped candidates remain available. Candidate summaries expose originating and latest scan run IDs without changing the strict episode schema.
- Synthetic fixtures now include distinct bullish, bearish, breakout, pullback, trend, weak, and mixed archetypes. Profile result sets differ by evaluated conditions, contain real non-matches, and retain deterministic repeat-scan progression.
- Relevance saturation traced to binary category presence and full credit for partial context. Policy `deterministic-relevance-v2` retains the existing bounded factor weights while measuring matched-predicate strength and assigning partial context half credit. Missing inputs still reduce score and coverage, incompatible direction creates no candidate, and older v1 episodes roll forward into a new policy episode rather than mixing policies in one history.

No schema migration was required. Direction belongs to the immutable scan definition, and candidate run lineage fits the existing JSON persistence boundary. Owner isolation, zero-match truthfulness, archive/restore, provider status, tolerance, optional LLM authority, and the no-trading boundary remain unchanged.

## U2 discovery queue, ranking, and triage stabilization

Formal U2 validation found queue-ordering, explanation parity, admission-transparency, context-policy, and inspector usability gaps. This bounded stabilization keeps the accepted Scan & Discover architecture and no-trading boundary intact:

- Candidate lists use one deterministic **Attention priority** policy. Current `deterministic-relevance-v2` candidates are compared first; within that bucket the order is relevance descending, lifecycle `CURRENT`, `NEW`, `STALE`, `DEFUNCT`, `EXPIRED`, `REJECTED`, freshness `FRESH`, unknown/currently observed without provider source time, `STALE`, most recently updated, canonical symbol, and candidate ID. Legacy-only relevance remains visible in a lower comparability bucket and retains its immutable score. **Relevance**, **Updated**, **Lifecycle**, and **Symbol** remain explicit alternate sorts. This is an ordering policy, not a new score or a conversion between versions.
- **Current scan** contains only candidates admitted or updated by the selected latest execution. **Active** contains `NEW`, `CURRENT`, and `STALE`; **All** also includes terminal `DEFUNCT`, `EXPIRED`, and `REJECTED` episodes. All counts and rows are owner-scoped. The existing candidate endpoint remains bounded and paginated with a default of 50 and maximum page size of 100, so no new pagination contract was required.
- Queue controls filter by symbol/native identity, relevance band, lifecycle, intent, horizon, profile, freshness, and evidence provider. Controls collapse into a compact disclosure and responsive grid; the current sort policy is announced in text. Setup cells now show profile above intent and horizon, and lifecycle reason comes from the persisted backend transition/snapshot contract.
- Internal Scanner and TradingView synthetic validation now share the same profile evaluator and normalized matched-predicate reasons. Provider identity and provenance differ, while downstream explanations remain semantically equivalent and never invent unsupported evidence.
- Each scan result carries an explicit typed admission summary. Match count reconciles to admitted plus excluded; every match has an `ADMITTED`, `EXCLUDED_DIRECTION`, or `EXCLUDED_CONTEXT_POLICY` decision. The workspace shows concise counts with expandable per-symbol reasons rather than inferring exclusions in the browser.
- Context policy is authoritative. **Require complete context** rejects admission when context is incomplete. **Allow partial context** admits bounded partial/unavailable evaluations and gives only proportional context credit, so missing dimensions reduce score and coverage. **Context optional** excludes market context from the required denominator for complete, partial, stale, and unavailable modes; absence alone cannot reduce relevance/coverage, add a freshness penalty, or make the candidate stale. Context state and limitations remain visible in all three policies.
- A candidate snapshot now owns only its current evidence set. The inspector selects the latest authoritative item per semantic category/producer slot, while immutable earlier evidence remains available in snapshot history. Candidate, episode, run, native, and evidence identifiers live under expandable provenance with wrapping monospace values and labeled Copy controls; the inspector suppresses horizontal overflow.
- Repeated equivalent scans continue the same eligible active episode and append immutable snapshots. Distinct symbol/intent/horizon/episode identities remain separate. Relevance bands still derive from the configured thresholds and remain consistent with numeric scores.

No schema migration was required. Admission decisions are returned with the execution result, while profile, lifecycle reason, context policy, scan lineage, and current evidence fit the existing typed JSON persistence boundary. No U2 issue was deferred to the hardening register.

### U2 follow-up: observable history and legacy comparability

- **View** now retrieves an owner-scoped stored execution detail and opens a clearly labeled read-only historical mode in the center workspace. It shows timestamp, provider, profile, universe, stored match rows, market-context state, and execution status. **Back to latest scan** restores the preserved current result without reload. Detail retrieval never runs a scan or mutates a candidate, snapshot, or lifecycle.
- **Use setup** restores universe, profile, intent, horizon, provider, context mode, and the persisted context policy without execution, then emits a transient accessible confirmation even when values did not visibly change. **Archive** removes a run from Recent scans immediately, retains the stored run/evidence graph for active-and-archived or archived-only Past scans, and emits a transient confirmation. Typed failures are visible for load, restore, archive, and history refresh.
- Legacy candidate profile display is derived without rewriting history. When the current snapshot has no profile, the service checks originating scan, latest scan, older persisted snapshot metadata, then candidate metadata. Recovered values are marked **Legacy**; records with no authoritative lineage show **Profile unavailable**, with help text explaining that they predate current profile-lineage persistence.
- Relevance model/version remains part of each immutable `DiscoveryRelevance` value and snapshot. A v1-only score is displayed as **Legacy score** with a comparability explanation. Current v2 candidates occupy the first ranking bucket, so an old 100% does not automatically outrank current v2 values. No numeric conversion is invented and historical scores remain unchanged.

No schema migration was required for the follow-up. Compatibility labels are derived at read time from existing owner-scoped lineage and immutable payloads. No follow-up item was deferred.

## CP-4 — bounded market context

`MarketContextSnapshot` distinguishes `observed_at` from optional `source_data_time` and carries owner, market/session, producer/version, evidence IDs, limitations, and typed dimensions. Broad regime, NIFTY, BANKNIFTY where available, breadth, volatility, and sector strength are represented as `PRESENT`, `MISSING`, `UNAVAILABLE`, or `STALE`. Aggregate state is `COMPLETE`, `PARTIAL`, `STALE`, or `UNAVAILABLE`.

The deterministic producer never invents a neutral value when evidence is absent. Missing, stale, and unavailable context remains visible and discovery continues with explicit limitations. Context is persisted per scan and linked into candidate snapshots.

`CP4_MARKET_CONTEXT_COMPLETE = YES`

## CP-5 — discovery engine

The product service preserves separate candidate lifecycles for each owner, broker-native instrument identity, discovery intent, and time horizon. Seven typed intents and four named horizons are available. Terminal episodes are never resurrected: a later valid setup creates a new episode linked through `previous_episode_id`.

Each observation creates a new immutable snapshot containing scan lineage, provider provenance, evidence, source and observation times, deterministic relevance inputs, context linkage, and lifecycle projection. Earlier snapshots are never rewritten. Scan evidence from Internal Scanner and TradingView synthetic validation can coexist in one active episode with distinct provenance.

Relevance is a deterministic policy-fit score in `[0,1]`, not profit probability. The persisted explanation includes weighted contributions, missing inputs, freshness penalty, horizon adjustment, coverage, and the selected LOW/MEDIUM/HIGH threshold policy.

Candidate tolerance is an evaluated, typed, horizon-aware envelope across price, volume, market, sector, and time decay. Each dimension records its observed value when known, threshold, state, and reason. Confirmation rules and recovery policy are explicit. The aggregate assessment is persisted with every immutable snapshot and exposed in the candidate UI. Two consecutive confirmed `BREACHED` assessments can move an episode to `DEFUNCT`; missing evidence remains `UNKNOWN` and is not silently treated as failure.

Lifecycle supports `NEW`, `CURRENT`, `STALE`, `DEFUNCT`, `EXPIRED`, and `REJECTED`. Owner actions use revision compare-and-set and append transition audit records. Context freshness can make the current view stale without corrupting the durable episode projection. A controlled recovery from defunct preserves the immutable historical snapshot and transition history.

`CP5_DISCOVERY_ENGINE_COMPLETE = YES`

## CP-6 — optional Level-0 intelligence

Discovery is complete with LLM disabled. When the controlled synthetic provider is enabled, an explanation is saved with provider/model/version, prompt version, generation time, grounding classification, evidence references, narrative, and limitations. The explanation has no scoring, lifecycle, promotion, sizing, execution, or risk authority. Configured non-synthetic providers currently return typed `LLM_UNAVAILABLE`; no synthetic answer is substituted for a named remote provider.

`CP6_LLM_LEVEL0_COMPLETE = YES`

## CP-7 — persistence, API, settings, and UX

Alembic revision `0012_sprint2_scan_discover` adds owner-scoped settings, scan runs, scan matches, market context, discovery episodes, immutable snapshots, lifecycle transitions, and LLM explanations. Forward revision `0013_discovery_scan_archive` adds nullable `archived_at` state and its lookup index without rewriting historical migrations or deleting historical rows. Queries and mutations apply the authenticated owner ID. List and history endpoints are bounded; scan universes are capped at 20 symbols and candidate/snapshot page sizes at 100. Normal history excludes archived runs unless `include_archived=true`; archive and restore both preserve the existing run and evidence graph.

The API surface is:

| Method        | Route                                                   | Purpose                                                 |
| ------------- | ------------------------------------------------------- | ------------------------------------------------------- |
| `GET`         | `/api/v1/discovery/status`                              | provider capability and typed readiness                 |
| `GET`, `PUT`  | `/api/v1/discovery/settings`                            | bounded owner defaults and revisioned updates           |
| `POST`, `GET` | `/api/v1/discovery/scans`                               | execute a bounded scan and read active/all scan history |
| `GET`         | `/api/v1/discovery/scans/{run_id}`                      | owner-scoped read-only stored execution detail          |
| `POST`        | `/api/v1/discovery/scans/{run_id}/archive`              | owner-scoped reversible scan archival                   |
| `POST`        | `/api/v1/discovery/scans/{run_id}/restore`              | restore an owner-scoped archived scan                   |
| `GET`         | `/api/v1/discovery/candidates`                          | paginated candidate ledger                              |
| `GET`         | `/api/v1/discovery/candidates/{candidate_id}`           | evidence, context, snapshots, transitions, explanations |
| `POST`        | `/api/v1/discovery/candidates/{candidate_id}/lifecycle` | revisioned owner lifecycle action                       |
| `POST`        | `/api/v1/discovery/candidates/{candidate_id}/explain`   | optional Level-0 explanation                            |
| `GET`         | `/api/v1/discovery/market-context`                      | latest owner context snapshot                           |

The Next.js proxy uses a strict discovery-route allowlist, same-origin session semantics, no-store responses, bounded bodies, and safe error mapping. The main shell now enables Scanners and Candidates. The responsive workspace has bounded scan controls, provider readiness, normalized results, conditional candidate detail, compact recent history, filtered past history, reversible archival, evidence/context/relevance/tolerance detail, immutable candidate history, optional LLM, typed empty/error/degraded states, and integrated settings. It uses existing tokens, themes, surface-state semantics, keyboard-accessible native controls, and an Escape-closeable focus-restoring history dialog. Chromium validation covers widths 390, 768, 1024, 1440, 1920, and 2560 pixels.

Safe scan telemetry records provider, duration, match count, candidate count, and context availability through the existing explicit structured-log allowlist; arbitrary extras and request data remain excluded.

`CP7_PRODUCT_UX_COMPLETE = YES`

## CP-8 — integrated internal validation

The automated suite covers:

- Internal Scanner → matches → context → candidates → persistence → UI;
- deterministic TradingView synthetic exact-batch path through the same domain;
- Internal and TradingView evidence merged without duplicate active episodes;
- complete, partial, stale, and unavailable context;
- no-match behavior and explicit provider state;
- relevance explanation and horizon-aware tolerance thresholds;
- first and subsequent snapshots, immutable history, stale/defunct/recovery/rejection, and fresh episodes after terminal state;
- LLM disabled, controlled grounded LLM enabled, unavailable named LLM, and no LLM authority;
- restart persistence and owner isolation;
- five-item recent history, complete setup reuse, filtered past history, owner-scoped archive/restore, retained scan-match rows, and absence of permanent deletion;
- API bounds, settings revision conflicts, OpenAPI construction, and migration metadata;
- responsive discovery flow at all six target Chromium widths.

WebKit still cannot launch successfully on this host because the Playwright runtime reports an internal browser error at navigation. This is retained as environment validation uncertainty; the implementation uses standard React, Fetch, CSS Grid/Flexbox, native controls, and no known Chromium-only API.

`CP8_END_TO_END_IMPLEMENTATION_COMPLETE = YES`

### Internal validation evidence

| Check                             | Result                                                                                         |
| --------------------------------- | ---------------------------------------------------------------------------------------------- |
| Backend full regression           | 940 passed                                                                                     |
| Ruff lint / format                | passed; 127 files formatted                                                                    |
| Strict mypy                       | passed; 126 source files                                                                       |
| Python compilation / `pip check`  | passed                                                                                         |
| OpenAPI construction              | passed; 52 paths, 122 schemas                                                                  |
| Offline package build             | wheel and sdist built                                                                          |
| Frontend unit tests               | 132 passed across 16 files                                                                     |
| ESLint / TypeScript / Prettier    | passed                                                                                         |
| Next.js production build          | passed; Scanners, Candidates, and discovery proxy routes emitted                               |
| Discovery responsive Chromium     | 6 passed at 390, 768, 1024, 1440, 1920, and 2560                                               |
| Full Chromium browser suite       | 66 passed across all six target widths, including Broker V2                                    |
| Focused discovery backend tests   | 39 passed                                                                                      |
| SQLite migration lifecycle        | upgrade/repeat/downgrade/re-upgrade and data-preservation probe passed                         |
| PostgreSQL 16 migration lifecycle | upgrade/repeat/downgrade/re-upgrade and data-preservation probe passed                         |
| Documentation links / whitespace  | 63 Markdown files passed; `git diff --check` passed                                            |
| Dependency vulnerability audit    | unchanged seven records/four accepted `cryptography==47.0.0` advisories; not reported as clean |

## Architecture choices and boundaries

- The accepted S2-1 domain contracts remain the authority for evidence, lineage, relevance, snapshots, lifecycle, and tolerance.
- Product persistence is relational under the existing SQLAlchemy/Alembic ownership model.
- Internal context and market series are deterministic validation producers. They are identified as such in UI and provenance.
- The TradingView product option is explicitly synthetic validation until the carried live-row hardening proof is complete.
- The optional LLM is a bounded contributor, never an authority.
- No trade, order, risk, Opportunity, LOB, TI, TM, autonomous execution, or advanced market-intelligence capability was introduced.

## Known limitations

The consolidated [Sprint-2 hardening register](TWF_SPRINT2_HARDENING_REGISTER.md) carries every open S2-3 item and records new nonblocking implementation limitations. Most visibly, successful real TradingView exact-row normalization remains unproven because the authorized provider returned typed rate limits, remote token revocation remains pending reconciliation, current context/internal market series are deterministic validation data, remote LLM integrations are contract seams rather than active providers, and WebKit execution remains blocked by its host runtime failure.

## User-validation readiness

The owner workflow is documented in [TWF Sprint-2 User Validation Plan](TWF_SPRINT2_USER_VALIDATION_PLAN.md). S2-4, S2-5, S2-6, and S2-7 are **IMPLEMENTED**. S2-8 is **IMPLEMENTED / INTERNAL VALIDATION COMPLETE**. Sprint 2 is **IMPLEMENTED / READY FOR USER VALIDATION** and is not accepted or frozen by this implementation task.

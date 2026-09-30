# Sprint 2 Scan & Discover — integrated implementation record

**Date:** 2026-09-30  
**Starting checkpoint:** `a5d7859944cbb25e143488f129cc0bab99dc262b` (`twf-s2-3-tradingview-mcp-provider`)  
**Program state:** **IMPLEMENTED / READY FOR USER VALIDATION**  
**Acceptance state:** pending user validation, adversarial review, consolidated hardening, and final freeze

This record covers the integrated S2-4 through S2-8 implementation. It does not alter the accepted/frozen status of S2-0 through S2-3 and does not claim final Sprint-2 acceptance. Scan & Discover ends at `DiscoveryCandidate`; it has no Opportunity, LOB, execution, or TM authority.

## Product capability

The user can now select a bounded symbol universe, provider validation path, scan profile, discovery intent, and time horizon; run a scan; inspect normalized matches; evaluate owner-scoped candidates with context, evidence, deterministic relevance, horizon-aware tolerance, lifecycle, and provenance; review immutable snapshot history; request an optional grounded Level-0 explanation; and manage bounded discovery settings. Internal Scanner V0 works without TradingView or an LLM. TradingView mode uses the deterministic synthetic exact-batch path for CI and product validation; it does not make a live provider call.

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

Alembic revision `0012_sprint2_scan_discover` adds owner-scoped settings, scan runs, scan matches, market context, discovery episodes, immutable snapshots, lifecycle transitions, and LLM explanations. Existing historical migrations were not rewritten. Queries and mutations apply the authenticated owner ID. List and history endpoints are bounded; scan universes are capped at 20 symbols and candidate/snapshot page sizes at 100.

The API surface is:

| Method        | Route                                                   | Purpose                                                 |
| ------------- | ------------------------------------------------------- | ------------------------------------------------------- |
| `GET`         | `/api/v1/discovery/status`                              | provider capability and typed readiness                 |
| `GET`, `PUT`  | `/api/v1/discovery/settings`                            | bounded owner defaults and revisioned updates           |
| `POST`, `GET` | `/api/v1/discovery/scans`                               | execute a bounded scan and read scan history            |
| `GET`         | `/api/v1/discovery/candidates`                          | paginated candidate ledger                              |
| `GET`         | `/api/v1/discovery/candidates/{candidate_id}`           | evidence, context, snapshots, transitions, explanations |
| `POST`        | `/api/v1/discovery/candidates/{candidate_id}/lifecycle` | revisioned owner lifecycle action                       |
| `POST`        | `/api/v1/discovery/candidates/{candidate_id}/explain`   | optional Level-0 explanation                            |
| `GET`         | `/api/v1/discovery/market-context`                      | latest owner context snapshot                           |

The Next.js proxy uses a strict discovery-route allowlist, same-origin session semantics, no-store responses, bounded bodies, and safe error mapping. The main shell now enables Scanners and Candidates. The responsive workspace has bounded scan controls, provider readiness, normalized results, candidate ledger, evidence/context/relevance/tolerance detail, immutable history, optional LLM, typed empty/error/degraded states, and integrated settings. It uses existing tokens, themes, surface-state semantics, and keyboard-accessible native controls. Chromium validation covers widths 390, 768, 1024, 1440, 1920, and 2560 pixels.

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
- API bounds, settings revision conflicts, OpenAPI construction, and migration metadata;
- responsive discovery flow at all six target Chromium widths.

WebKit still cannot launch successfully on this host because the Playwright runtime reports an internal browser error at navigation. This is retained as environment validation uncertainty; the implementation uses standard React, Fetch, CSS Grid/Flexbox, native controls, and no known Chromium-only API.

`CP8_END_TO_END_IMPLEMENTATION_COMPLETE = YES`

### Internal validation evidence

| Check                              | Result                                                                                         |
| ---------------------------------- | ---------------------------------------------------------------------------------------------- |
| Backend full regression            | 917 passed                                                                                     |
| Ruff lint / format                 | passed; 126 files formatted                                                                    |
| Strict mypy                        | passed; 125 source files                                                                       |
| Python compilation / `pip check`   | passed                                                                                         |
| OpenAPI construction               | passed; 50 paths, 118 schemas                                                                  |
| Offline package build              | wheel and sdist built                                                                          |
| Frontend unit tests                | 119 passed across 16 files                                                                     |
| ESLint / TypeScript / Prettier     | passed                                                                                         |
| Next.js production build           | passed; Scanners, Candidates, and discovery proxy routes emitted                               |
| Discovery responsive Chromium      | 6 passed at 390, 768, 1024, 1440, 1920, and 2560                                               |
| Representative full Chromium suite | 11 passed, including Broker V2                                                                 |
| SQLite migration lifecycle         | upgrade/repeat/downgrade/re-upgrade and data-preservation probe passed                         |
| PostgreSQL 16 migration lifecycle  | upgrade/repeat/downgrade/re-upgrade and data-preservation probe passed                         |
| Documentation links / whitespace   | 62 Markdown files passed; `git diff --check` passed                                            |
| Dependency vulnerability audit     | unchanged seven records/four accepted `cryptography==47.0.0` advisories; not reported as clean |

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

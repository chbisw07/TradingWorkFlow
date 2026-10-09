# Scanner V2 — architecture and implementation evidence

Status: **implemented, pending user validation; not accepted or frozen**.

## A. Preflight

Work began on `main`, HEAD `d2a35176fd01efa095871ac6f5347af314dc7b33`, with a clean worktree. No commit, tag, push, reset, or historical data rewrite was performed. The user’s approved Scanner wireframe replaces the old `/scanners` page as the visual target.

## B. Existing scanner classification

| Classification | Existing capability                                                                                                 | Treatment                                                                                     |
| -------------- | ------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| KEEP           | Dhan credentials, canonical catalog, MarketSeries, Broker V2, Watchlists, Discovery observations and Evidence Chart | Reused without changing their authority or data model                                         |
| ADAPT          | Internal Scanner indicator library                                                                                  | Adds shared MACD, ADX, Bollinger and Supertrend functions; existing formulas remain unchanged |
| REPLACE        | Old `/scanners` DiscoveryWorkspace layout                                                                           | New ScannerWorkspace with universe, filters, results, analysis, saved scans and movers        |
| HISTORICAL     | S&D ScanRun, profile and temporal observation records                                                               | Remain intact under Discovery; no conversion into Scanner V2 runs                             |

## C–E. Product and provider boundaries

Scanner performs explicit candidate generation. Discovery performs downstream interpretation and temporal tracking. Scanner V2 does not automatically create Discovery candidates or authorize orders. A persisted match contains canonical instrument identity, versioned filters, predicate diagnostics, observed metrics, provider lineage, source/received timestamps and archived bars for a future explicit Discovery handoff.

Equity/Index is functional. Derivatives has a separate truthful shell: no IV, Greeks, option-chain filters or synthetic derivative analytics. Futures/options in a mixed Watchlist receive `NOT_EVALUATED / DERIVATIVES_UNSUPPORTED`.

The internal scanner evaluates Dhan data. TapTide technical screening is a separate bounded provider capability, not a MarketIntelligenceProvider policy gate. Its provider-wide suggestions remain separately identified and can be loaded into a Custom universe for canonical Dhan verification. Unresolved external suggestions are not silently merged into Dhan results, given a Dhan identity, or added to Watchlists. There is no claim of cross-provider agreement scoring.

## F. Universe sources

- **Watchlist:** canonical instruments from the owner’s collection, optional subset, immutable snapshot including revision at execution. Later collection edits do not rewrite runs.
- **Custom:** one to twenty uppercase NSE symbols, comma/space separated, `&` supported. Duplicate symbols are rejected and identities are resolved by Dhan.
- **Index / Sector / Market:** typed sources and visible capability boundaries, currently unavailable. No verified complete constituent/sector/universe feed is configured. TapTide’s bounded mover sample and single-symbol index membership tool do not prove a complete membership list. Use an explicit Watchlist/Custom set, including index instruments such as NIFTY, instead.

No exchange-wide per-symbol request expansion is performed.

## G–H. Filter contract and internal calculations

Filters store `field`, `operator`, `value`, `timeframe`, `source` and `version`. Version 1 uses completed daily bars and AND semantics. Operators include comparison, inclusive between, equality and previous/current-bar crossover. Unknown fields, duplicate filters, non-finite values, invalid oscillator ranges, self-comparison, unsupported direction operators and historical fundamental crossovers are rejected.

| Family                  | Calculation / time basis                                                                                                  |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| LTP                     | Separate owner-scoped Dhan batch quote snapshot; never substituted with a completed close                                 |
| Price / change / gap    | Latest completed close; close versus prior completed close; current bar open versus prior completed close                 |
| Volume / RVOL           | Completed-bar volume; average of **prior** 20 bars excluding current; current volume divided by that average              |
| RSI, SMA, EMA, ATR, ROC | Existing shared library; Wilder RSI/ATR, SMA-seeded EMA, explicit periods in labels                                       |
| MACD                    | SMA-seeded EMA12 minus EMA26, signal SMA-seeded EMA9 of the MACD line                                                     |
| ADX14                   | Wilder-smoothed directional movement and DX, first ADX average of 14 DX values                                            |
| Bollinger               | SMA20 plus/minus two population standard deviations                                                                       |
| Supertrend10,3          | Wilder ATR10 trailing bands, bullish initial state at first calculable bar; direction switches across prior trailing band |
| Stochastic              | Unsmoothed %K14; zero range is unavailable                                                                                |
| Trend                   | Completed close versus SMA20: Up / Down / Sideways                                                                        |
| Breakout / breakdown    | Completed close versus **prior** 20-bar high/low, excluding current bar                                                   |
| Range expansion         | Current high-low divided by ATR14                                                                                         |
| Pivot / R1 / S1         | Prior bar pivot `(H+L+C)/3`; R1 `2P-L`; S1 `2P-H`                                                                         |
| Proximity               | Close distance from SMA20 or prior 252-session high/low, percent; “Near 52W” templates use an editable 3% band            |

The UI distinguishes quote LTP from completed-bar indicators and 1D change. This is not a streaming intraday scanner. Filters unavailable from provider data are not fabricated. In particular, delivery, ROE, growth, and debt/equity are not exposed. All matched predicates include observed value, threshold and pass state; missing any required input yields `NOT_EVALUATED`, never a non-match.

Shared formulas are deterministic definitions, not a claim of identical warm-up/seed conventions to every chart vendor.

## I. Optional TapTide

Empirically inspected tools:

- `screen_stocks_technical`: explicit supported field/operator mapping, bounded limit 20, server allowlist restricted to that tool for the request.
- `get_trending_stocks`: bounded provider buckets, at most 20 rows per bucket and 80 normalized suggestions before presentation.
- `get_stock_quote`: existing normalized reference adapter for market cap (converted from INR crore to INR) and PE.

Raw tool envelopes are discarded. Normalized suggestions contain symbol, provider, tool, numeric metrics, bucket/reasons and receipt/freshness metadata. Duplicate provider symbols retain multiple reasons. The provider did not supply source timestamps for the tested screen/movers, so freshness is explicitly `SOURCE_TIME_UNAVAILABLE`. UI mover rankings are over a bounded sample, **not exhaustive exchange gainers/losers**. Loading a suggestion populates Custom setup; the user must run Dhan evaluation.

Fundamental filters are disabled when provider readiness is absent. If a user explicitly requests a fundamental predicate and the value is missing, that instrument is not evaluated. Technical-only runs never call TapTide. Optional news/fundamentals failures do not retroactively alter a technical run.

## J–M. Product flows

Sixteen built-in templates populate editable filter expressions, not opaque profiles. Users can save, rename/update or archive owner-scoped configurations. Recent runs can be viewed or used as setup; restored setup emits a transient review notice. A result/config mismatch is explicitly shown.

Results expose requested, resolved, evaluated, not-evaluated and match counts, table/charts views, columns, sorting, CSV, selection and predicate diagnostics. “Relevance” does not claim a probability; deterministic matches have no invented confidence score and tie by symbol.

Selected/all matched canonical instruments can be added to an existing or newly created Watchlist. Existing Watchlist membership deduplicates them, retaining optional `scanner` source/run metadata. No scan-to-trade-all action exists.

The analysis panel uses archived Dhan daily bars and metrics, source timestamps, optional normalized reference/news and Broker V2 order-ticket preview. The existing exact broker-contract lookup is required before opening a ticket; indices cannot be traded directly. No real orders were placed during validation. Details become a focus-managed modal on tablet/mobile.

## N. Persistence and security

Migration `0018_scanner_v2` adds `scanner_v2_saved` and `scanner_v2_runs`, owner foreign keys and owner indexes. Existing Watchlists/S&D tables are untouched. Run JSON is immutable through the API and archives exact configurations, canonical universe snapshots, metrics, diagnostics, quotes and bars. Saved config updates do not rewrite historical runs. Downgrade removes only the new Scanner tables and therefore discards Scanner V2 records; never downgrade an active database to perform validation.

All endpoints enforce current owner, existing session/origin protections and matched-result membership on handoff. Guessed run/save/Watchlist identifiers cannot cross owners. Credentials remain behind existing encrypted credential managers. No SQL transaction spans Dhan/TapTide I/O. The Dhan cache is keyed by owner, generation and canonical instrument; cached series must have Dhan provenance, exact identity and daily interval. Synthetic series cannot enter this real-only path.

## Q. Provider-call budget

- Maximum 20 requested instruments, 12 AND filters, 300 requested completed daily bars per instrument.
- One batch quote request per run, bounded at 10 seconds. Quote loss does not block daily-bar predicates; LTP-dependent predicates are unavailable.
- Historical requests are serialized with at least 1.1 seconds between starts; owner/generation cache TTL 300 seconds, maximum 256 entries. Resolution, quotes and historical acquisition share a 120-second budget; expired work is marked unavailable without starting another provider request.
- Custom resolution reuses the existing bounded Dhan instrument master cache. No remote resolution call per predicate.
- Explicit fundamental filters use the existing bounded reference cache; technical-only runs make zero MI calls.
- TapTide screen/movers are on-demand, one bounded tool call per action, no added retry loop or background polling.
- The cache/pacing is process-local, not a cross-worker global rate limiter. Multi-worker global quotas remain future hardening.

## R. Live evidence

Live tests used the connected owner’s **My Core** Watchlist and Dhan credential generation 3. All five runs requested/resolved/evaluated all four instruments; none fell back to fixtures. Historical data was reused from four acquisitions across these five configurations.

| Configuration       | Run ID                                 |             Matches | Not evaluated |
| ------------------- | -------------------------------------- | ------------------: | ------------: |
| RSI below 40        | `906f3a54-5679-4bac-b6a1-fa86574cf5e6` | 2 (RELIANCE, NIFTY) |             0 |
| Volume > 10,000,000 | `6e4cf89d-c147-442c-b09d-24289c06e7fb` |                   4 |             0 |
| Trend Down          | `08b454a9-8926-4da7-8663-d92739d06b5b` |                   4 |             0 |
| Bullish Breakout    | `ec5d9483-7a45-4dfc-9920-edca88dc3298` |                   0 |             0 |
| Supertrend Bullish  | `71e1a543-7a8b-4e34-856e-8826818c2594` |        1 (HDFCBANK) |             0 |

These initial runs preceded the separate quote-snapshot addition. Their bars ended at provider timestamp `2026-10-04T18:30:00Z`; that is historical source time, not a claim of current streaming prices. Breakout zero matches is a legitimate result; no thresholds were altered to produce matches.

One live TapTide technical screen returned SBIN (RSI 34.8624) and BAJFINANCE (RSI 36.1191). One mover call returned bounded bullish/bearish/near-52W buckets. RELIANCE reference lookup supplied PE 22.06 and market cap INR 16,482,632,200,000, source time `2026-10-06T10:29:59Z`. These are observations at validation time, not recommendations or current quotes.

Live Watchlist handoff created **Scanner V2 validation** with two canonical matches and **Scanner V2 all results validation** with all four high-volume results. Repeating each add created zero duplicates. No existing membership was removed.

## T. Visual and functional deviations

The approved layout is implemented with left universe/filter controls, center chips/results/bulk actions/bottom panels and right analysis. Mobile uses collapsible controls and a detail sheet. No annotated design-note footer is included in the product.

Truthful bounded differences: unconfigured Index/Sector/Market membership sources; separate provider-wide TapTide suggestions; completed daily technical basis with separate quote LTP; bounded sample mover rankings; Compare and full derivatives deferred. These limits are visible, not simulated controls. Historical Discovery data remains accessible under Discovery.

## U. Related documentation

- [README](../README.md)
- [Detailed roadmap](TWF_DETAILED_ROADMAP.md)
- [Documentation index](TWF_DOCUMENTATION_INDEX.md)
- [Watchlists architecture](TWF_WATCHLIST_ARCHITECTURE.md)
- [Broker V2](TWF_BROKER_V2_MANUAL_ORDER_ENTRY.md)

## O. Exact changed files

The following inventory includes new files and changes to existing files; no backend Broker/Watchlist implementation or Discovery product UI file was changed. Two existing frontend test files were adjusted only to await asynchronous completion (news, row hydration and chart errors), after scheduler-dependent failures were reproduced.

```text
README.md
apps/api/alembic/env.py
apps/api/alembic/versions/0018_scanner_v2.py
apps/api/src/twf/api/scanner_v2.py
apps/api/src/twf/discovery/internal_scanner/indicators.py
apps/api/src/twf/infrastructure/scanner_v2.py
apps/api/src/twf/main.py
apps/api/src/twf/scanner_v2/__init__.py
apps/api/src/twf/scanner_v2/contracts.py
apps/api/src/twf/scanner_v2/engine.py
apps/api/src/twf/scanner_v2/service.py
apps/api/src/twf/scanner_v2/tapetide.py
apps/api/src/twf/scanner_v2/templates.py
apps/api/tests/test_backend_shell.py
apps/api/tests/test_database_foundation.py
apps/api/tests/test_foundation.py
apps/api/tests/test_scanner_v2.py
apps/web/src/app/(protected)/scanners/page.tsx
apps/web/src/app/api/v1/scanner/[[...path]]/route.ts
apps/web/src/app/globals.css
apps/web/src/components/scanner/scanner-workspace.tsx
apps/web/src/lib/scanner.ts
apps/web/src/styles/scanner.css
apps/web/tests/browser/scanner-v2.spec.ts
apps/web/tests/browser/service_fixture_api.py
apps/web/tests/discovery.test.tsx
apps/web/tests/scanner-v2.test.tsx
apps/web/tests/watchlists.test.tsx
docs/TWF_DETAILED_ROADMAP.md
docs/TWF_DOCUMENTATION_INDEX.md
docs/TWF_SCANNER_V2_ARCHITECTURE.md
```

## P. Validation

| Check                                                                        | Result                                                                                                                                                                                  |
| ---------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Full backend pytest suite                                                    | 1,022 passed                                                                                                                                                                            |
| Focused Scanner V2 tests                                                     | 29 passed (also included in full suite)                                                                                                                                                 |
| Full frontend unit suite                                                     | 205 passed, 20 files                                                                                                                                                                    |
| Scanner Chromium browser workflow                                            | 6 passed, widths 390 / 768 / 1024 / 1440 / 1920 / 2560                                                                                                                                  |
| Existing Watchlists, Brokers, Broker V2 order-ticket browser workflows       | 3 passed at 1440, disposable test credentials/provider transport only                                                                                                                   |
| Documentation formatting, 153 local documentation links, git diff whitespace | PASS                                                                                                                                                                                    |
| TypeScript, ESLint, production build                                         | PASS                                                                                                                                                                                    |
| Ruff lint/format, Python compilation, pip check, offline package wheel build | PASS                                                                                                                                                                                    |
| Strict mypy source                                                           | PASS, 93 files                                                                                                                                                                          |
| Repository-wide strict mypy including old tests                              | Two pre-existing errors remain in `test_discovery_product.py:1321` and `test_dhan_credentials.py:126`; both lines verified unchanged against starting HEAD. No Scanner V2 typing errors |
| SQLite migration upgrade/downgrade/upgrade and metadata                      | PASS in full foundation suite on disposable databases                                                                                                                                   |
| PostgreSQL migration                                                         | Offline SQL compilation PASS; no new live PostgreSQL round trip was run                                                                                                                 |
| Live migration preservation                                                  | Existing Watchlist row count unchanged when applying additive 0018; no historical S&D migration                                                                                         |

Backend/Frontend regression scorecards mean the executed suites passed; they do not claim resolution of unrelated baseline mypy debt or exhaustive external-provider behavior.

Final live run `6765d4d1-c0e5-4f08-a168-77e7e35124b1` additionally validated one Dhan batch-quote call plus four OHLCV acquisitions through the final quote/indicator separation: requested/resolved/evaluated 4, not evaluated 0, RSI matches 2. Every quote was Dhan-backed. RELIANCE LTP 1218 and completed close 1186.4 were preserved separately; no quote value was substituted into completed-bar indicators.

## S. Screenshot evidence

The Chromium test captures four images at each of the six widths: `scanner-filters-light.png`, `scanner-results-light.png`, `scanner-detail-light.png`, `scanner-dark.png`. Screenshots use a disposable normalized provider transport with three instruments; they are visual fixtures, not live-market screenshots. Live data evidence is recorded separately above.

Local artifact directories:

```text
apps/web/test-results/scanner-v2-Scanner-V2-edit-1daa4-ndoff-and-responsive-review-chromium-390/
apps/web/test-results/scanner-v2-Scanner-V2-edit-1daa4-ndoff-and-responsive-review-chromium-768/
apps/web/test-results/scanner-v2-Scanner-V2-edit-1daa4-ndoff-and-responsive-review-chromium-1024/
apps/web/test-results/scanner-v2-Scanner-V2-edit-1daa4-ndoff-and-responsive-review-chromium-1440/
apps/web/test-results/scanner-v2-Scanner-V2-edit-1daa4-ndoff-and-responsive-review-chromium-1920/
apps/web/test-results/scanner-v2-Scanner-V2-edit-1daa4-ndoff-and-responsive-review-chromium-2560/
```

Desktop light/dark and mobile filter/results/detail surfaces were inspected. Mobile metrics have explicit labels and separate grid cells; modal detail scrolls within the viewport. Browser assertions check absence of horizontal page overflow. Tabs support arrow/Home/End keys; existing dialog focus handling, semantic controls and textual metrics accompany charts. No pixel-perfect or independent accessibility certification is claimed.

## V. Required scorecard

```text
SCANNER_V2_UI_IMPLEMENTED = PASS
REFERENCE_VISUAL_MATCH = PASS
EQUITY_INDEX_SCANNER = PASS
DERIVATIVES_SCANNER_BOUNDARY = PASS
WATCHLIST_UNIVERSE = PASS
INDEX_UNIVERSE = FAIL
SECTOR_UNIVERSE = FAIL
MARKET_UNIVERSE = FAIL
CUSTOM_UNIVERSE = PASS
FILTER_BUILDER = PASS
PRICE_VOLUME_FILTERS = PASS
TECHNICAL_FILTERS = PASS
TREND_MOMENTUM_FILTERS = PASS
BREAKOUT_FILTERS = PASS
SUPPORT_RESISTANCE_FILTERS = PASS
INTERNAL_SCANNER_DHAN = PASS
TAPTIDE_SCAN_PROVIDER = PASS
TAPTIDE_OPTIONAL = PASS
SCAN_TEMPLATES = PASS
SAVED_SCANS = PASS
SCAN_HISTORY = PASS
MARKET_MOVERS = PASS
RESULT_REASON_FOR_MATCH = PASS
NOT_EVALUATED_TRUTHFUL = PASS
RESULT_DETAIL_PANEL = PASS
ADD_SELECTED_TO_WATCHLIST = PASS
ADD_ALL_TO_WATCHLIST = PASS
BROKER_V2_QUICK_ACTIONS_PRESERVED = PASS
DISCOVERY_CONTRACT_PRESERVED = PASS
OLD_SCANNER_UI_REMOVED = PASS
RESPONSIVE_VALIDATION = PASS
ACCESSIBILITY_VALIDATION = PASS
BACKEND_REGRESSION_FREE = PASS
FRONTEND_REGRESSION_FREE = PASS
WATCHLIST_REGRESSION_FREE = PASS
BROKER_REGRESSION_FREE = PASS
SCANNER_V2_STATUS = READY_FOR_USER_VALIDATION
```

The three universe FAILs are unavailable membership capabilities, not silent fallbacks. The required Equity/Index-first Watchlist/Custom acceptance flow is ready for user validation. TapTide PASS covers the explicit bounded technical/mover capabilities documented above; it does not assert exhaustive exchange screening, canonical cross-provider merge, or advanced derivatives. Visual PASS covers the requested structural layout and responsive checks, with the bounded deviations in section T.

## W. Final disposition and how to validate

Open `/scanners`, select **Watchlist → My Core**, load a template, inspect/edit the filters and select **Run Scan**. Review counts and per-symbol diagnostics before interpreting results. Select a result to inspect its archived Dhan chart; use Fundamentals/News only when optional provider evidence is needed. Add Selected/Add All supports an existing or new Watchlist. Saved scans and recent executions persist across refresh.

Two validation collections were intentionally added by the authorized live handoff: **Scanner V2 validation** (2 instruments) and **Scanner V2 all results validation** (4 instruments). They may be retained or moved to Trash through the existing Watchlists UI.

Implementation is ready for user validation of the documented scope. It is not accepted or frozen. No commit, tag or push was performed.

## X. Market Context ranking and explainable analysis

Scanner matching and relevance are separate contracts. Instrument predicates over Dhan data determine `technical_match`. A matched row receives the current V1 technical baseline of 80; this is a deterministic ordering basis, not a probability, confidence score, or mature technical-quality model. Market Context contributes a signed adjustment and final relevance is `clamp(technical_score + context_adjustment, 0, 100)`. In **Ranking** mode an adverse context never changes a technical match into a non-match. **Hard filter** can reject a technical match only when an explicit user-selected context predicate fails. **Off** performs no Market Intelligence acquisition and contributes zero. Ranking is the default for new and legacy configurations.

The backend acquires one bounded, scan-level provider-neutral `MarketContextSnapshot` after Dhan technical evaluation. TapTide is the current optional implementation and its operation has a 30-second total bound. The existing owner/connection/generation-fenced normalized snapshot cache may reuse an available or stale batch for at most 300 seconds. That interval only bounds request reuse; it is not a shared freshness policy for every dimension. Every claim still retains its independent provider source time and freshness. There are no candidate-level context calls or retries. TapTide failure produces `PARTIAL` or `UNAVAILABLE`; it does not fail or reinterpret Dhan evaluation. The snapshot and every `CandidateAnalysisPacket` are stored inside the immutable Scanner run JSON, so opening history uses the evidence and scores captured at execution time. No current-context refresh rewrites a historical result. Raw MCP/provider envelopes and credentials are not persisted in Scanner domain records.

### V1 dimensions and truthful source boundaries

| Dimension                  | V1 normalized contract                                                 | Current reliable source / limitation                                                                                                                                                                   |
| -------------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Broad market regime        | Strongly bullish through strongly bearish, or unknown                  | **Not available:** current accepted TapTide index evidence is sectoral and cannot establish an authoritative NIFTY/BANKNIFTY regime. Remains `UNKNOWN`.                                                |
| Sector strength / rotation | Strength, relative strength and rotation state, or unknown             | **Not available:** no accepted candidate-to-sector map plus comparable sector series. No sector is guessed.                                                                                            |
| India VIX                  | Low, normal, elevated, high, or unknown                                | TapTide normalized volatility/pulse claim. Thresholds: low below 12, normal 12 to below 18, elevated 18 to below 25, high 25 or above.                                                                 |
| Institutional flows        | FII, DII and net state, or unknown                                     | TapTide normalized market-flow/pulse claim. V1 uses the supplied current values. Rolling velocity and streak remain explicit `UNKNOWN` because the provider contract does not supply accepted history. |
| Market breadth             | Strong, positive, mixed, weak, or unknown                              | **Not available:** no authoritative advance/decline or complete-constituent participation source. Remains `UNKNOWN`.                                                                                   |
| Event/news risk            | Positive catalyst, supportive, neutral, caution, high risk, or unknown | Only an explicit provider-supplied normalized sentiment is used. Headline text is never classified with string heuristics. Current coverage can therefore be partial or unknown.                       |

Missing dimensions contribute exactly zero and remain listed in `missing_evidence`. They are never treated as neutral, positive, or negative observations. The typed Hard-filter editor exposes only enum operators (`equals`, `not_equals`). Fields without a reliable current source are shown disabled rather than presented as functioning controls.

### Direction, weights and classification

Direction is inferred only from unambiguous deterministic filters: Up/Down trend or Supertrend equality and directional price/moving-average comparisons. Conflicting or absent direction signals produce `UNKNOWN` and all direction-dependent dimensions contribute zero.

The centralized V1 maximum absolute contribution is 20:

| Factor              | Maximum absolute contribution | Direction-aware |
| ------------------- | ----------------------------: | --------------- |
| Broad regime        |                             5 | Yes             |
| Sector              |                             5 | Yes             |
| India VIX           |                             2 | No in V1        |
| Institutional flows |                             4 | Yes             |
| Breadth             |                             3 | Yes             |
| Event/news          |                             1 | No in V1        |

For VIX, Low/Normal contributes +1, Elevated -1 and High -2. For event/news, Positive Catalyst/Supportive contributes +1 and Caution/High Risk -1. Each factor records observed state, directional interpretation, contribution, explanation, source and freshness. Context classifications are centralized: at least +12 strongly supportive, +4 supportive, -4 adverse, -12 strongly adverse, and values between those bounds mixed. No available evidence, or Off mode, yields unavailable classification.

### Single analysis source and presentation

`CandidateAnalysisPacket` is the only reasoning source for the compact Reason cell, detailed Evidence view, CSV reason, chart-card reason and historical replay. It includes the immutable run identifier and canonical candidate instrument identifier, technical diagnostics, setup direction, match state, scores, context status/coverage, all factor contributions, supporting factors, contradictions, neutral factors, missing evidence, explicit Hard-filter diagnostics, provenance, freshness and warnings. The Reason cell is bounded to 180 characters and links to the existing result inspector through a keyboard-accessible **Why?** button.

The no-LLM Evidence view is complete and immediate. It shows the V1 baseline limitation, exact technical diagnostics, each context contribution, ranking math, supporting factors, contradictions, missing evidence, Hard-filter checks and collapsible provenance/freshness. The repository currently has no active Scanner narrative adapter, so optional LLM narrative, lazy synthesis and LLM-failure fallback are not applicable in this version. If added later, synthesis must consume only the stored packet, run lazily on explicit request, remain bounded, and cannot alter any match or score.

Future providers can populate currently unavailable normalized dimensions without changing Scanner matching, scoring consumers, history, or UI contracts. A future technical-quality policy may replace the documented 80-point match baseline only through a separately versioned deterministic contract.

## Instrument metadata presentation — 2026-10-09

Scanner V2 enriches persisted result rows from the system-global
`InstrumentMetadataService` with one bounded, indexed bulk lookup after technical
evaluation and Market Context ranking have completed. Sector is visible by default;
industry, readable INR market cap, stored NSE size band, stored TWF analytical tier,
and analytical context benchmark appear in the result inspector. Missing data stays
unknown and last-known metadata is labelled stale. The enrichment makes no external
provider request and cannot alter technical matches, context contributions, or rank.
Dynamic Sector Context remains future work.

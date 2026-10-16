# Scanner Data Readiness Hardening

Date: 16 October 2026. Scope: F&O liquidity collection/readiness and Futures evidence diagnostics. No commit, tag, push, schema migration, execution worker, or Broker submission.

## A. Executive verdict

**SCANNER_DATA_READINESS_STATUS = PASS. READY_FOR_USER_VALIDATION = YES.** Both complete backend gates pass on the final source. Live F&O enablement remains pending real completed-session accumulation, as required.

The F&O lists had **zero valid persisted sessions**, not three hidden sessions. The compact Dhan master could not join stock derivatives to their underlying equities. The replacement uses structured detailed-master identity in both collection and ready-list membership validation, resolves 213 eligible underlyings, and preserves the three-session rule. Current live state is **ACCUMULATING — 0/3 completed sessions collected**. All three lists remain disabled intentionally.

The reproduced Futures failure was a Dhan `RATE_LIMITED` quote request after successful contract resolution. The previous UI concealed that cause. A bounded live validation subsequently resolved and evaluated all five requested contracts, with two matches. A deliberate one-contract percentile scan remains NOT_EVALUATED with an explicit minimum-cohort reason.

## B. Preflight

- Branch: `main`; starting HEAD: `65a4842397820222061522fa29efacf1c2de5fee`.
- Workspace was clean before this work; the prior UX-unification work was committed.
- Runtime: PostgreSQL; `/ready` reports application/database ready. SQLite remains explicit fallback.
- Date/time: 16 October 2026, Asia/Kolkata; live validation at approximately 13:06–13:07 IST, before completed-session collection cutoff.
- Dhan: READY, generation 10. No tokens, client IDs, connection secrets, or owner identifiers are included here.
- Live API uses reload; changed lifespan starts the collector on application startup and cancels it on shutdown.
- Initial F&O payload: `observations=[]`, `ranked=[]`, `last_error_category=NO_ELIGIBLE_FUTURES`, last attempt `2026-10-15T16:29:59.758859+00:00`.
- The reproduced failing Futures scan had five resolved contracts, zero evaluated, five not evaluated, with the provider error `RATE_LIMITED`.

## C. F&O Liquidity issue reproduction

F&O Liquidity 50, 100 and 200 were unavailable because no ranked universe existed. API readiness used a coarse unavailable label; inspecting the persisted cache identified `NO_ELIGIBLE_FUTURES`. The compact master contained 210,226 records but blank stock-derivative underlying fields, yielding zero eligible joins. Both initial collection and ready-list detail revalidation used that compact join; both now use the structured detailed master. Detailed-master structured fields resolved 213 current eligible equity underlyings.

This was collection failure, not a reason to bypass readiness. Calendar days since installation do not establish completed observations.

## D. Readiness collection pipeline

1. After 15:45 IST on weekdays, the application background task checks for a ready Dhan connection. Watchlist listing can also trigger refresh.
2. A bounded cached detailed-master fetch supplies NSE EQ, FUTSTK and OPTSTK identities using structured `UNDERLYING_SYMBOL`; the provider's existing master TTL applies (default six hours).
3. Current NSE EQ must have active stock futures and stock options. The nearest unexpired future is selected deterministically; no symbol-string heuristic or cash-volume proxy is used.
4. One partial-tolerant quote batch, bounded to 1,000 contracts, fetches exact futures identities. The current eligible set has 213 contracts.
5. Only Dhan snapshots fetched after the completion cutoff with same-IST-date provider trade time and positive volume/OI are admitted. Missing, invalid, prior-date or zero-volume/OI samples do not count.
6. Persistence merges missing symbols into the same session. Previously accepted samples are retained; retries do not create another observation for the same symbol/session. Failed/partial attempts have a persisted 15-minute retry cooldown.
7. Up to 20 distinct sessions feed per-underlying medians. Each ranked underlying needs at least three valid sessions. Cross-sectional percentiles retain the original 60% volume / 40% OI score, deterministic tie ordering, and nested rank slices.
8. Readiness is derived from persisted evidence and returned to both Watchlists and the shared Scanner selector. A valid ranking becomes selectable automatically.

No transaction spans provider I/O. PostgreSQL locks the cache row while merging; initialization retries an insertion conflict. The API process lock also serializes its own refreshes. SQLite remains the existing managed-process fallback, not a new distributed collection service.

## E. Persisted session inventory

At live validation there were **no completed session records** to inventory. Consequently no session-specific contract/volume/OI claims can be made for earlier dates. The only persisted prior attempt identified the eligibility failure above.

| Inventory item | Live value |
| --- | --- |
| Successful completed sessions | 0 |
| Minimum required per ranked underlying | 3 |
| Current eligible exact futures | 213 |
| Ranked symbols | 0 |
| Last successful session | None |
| Latest eligibility verification | 2026-10-16T07:35:33.493964+00:00 |

New successful observations retain session date, exact Dhan contract ID, expiry, volume, OI, provider source time, attempted/quoted counts and per-symbol failures on partial capture. A provider-wide failure records its category and attempt time while retaining prior valid observations/ranking. It does not create a fictitious session.

## F. Root causes

- **Eligibility:** the compact master did not carry the structured stock-underlying join needed by this collector. The already-established detailed parser can supply it.
- **Lifecycle:** collection depended on a watchlist request after close. No background task progressed readiness independently of UI visits.
- **Retry:** a partial response could invalidate an entire batch; once a date was stored, missing instruments were not safely replenished.
- **Presentation:** readiness errors and Futures missing evidence were collapsed into broad messages.
- **Futures live reproduction:** quote rate limiting, not failed canonical contract resolution, caused the observed 5/5 NOT_EVALUATED run.

## G. F&O readiness fix

Readiness states are `READY`, `ACCUMULATING`, `STALE`, `CREDENTIAL_UNAVAILABLE`, `PROVIDER_UNAVAILABLE` and `ERROR`, each with textual reason and progress. Counts represent the highest valid per-symbol distinct-session coverage, not a union of disjoint partial days. Every actually ranked symbol independently satisfies the three-session minimum.

The background collector runs approximately every five minutes in the completion window; the persisted 15-minute cooldown bounds retries. A fully captured date is not requoted. Restarting the API does not reset progress or cooldown. A prior obsolete eligibility error may be cleared before close only after current detailed-master eligibility is verified; this writes no session sample.

A last-good ranking remains usable for at most seven days; age over 24 hours, a newer completed date, or a failed/partial refresh makes it visibly stale, including same-day failures. A failed refresh retains that rank. After seven days it is disabled. Current owner credentials remain required. Lists may contain fewer than their nominal 50/100/200 if fewer names meet all rules; they are never padded.

Weekends are excluded by the ordinary weekday completion window. On a weekday exchange holiday, a prior-session quote fails the same-date check and adds no observation. There is no fabricated holiday calendar or historical backfill. Special weekend sessions are conservatively not collected in V1. Provider `last_trade_time` is a trade timestamp, not a field-level volume/OI publication timestamp; completion relies on an actual post-cutoff quote request plus same-session trade evidence. No cached intraday quote is reused for collection.

Rollover uses a newly resolved nearest non-expired contract and persists its exact identity. The existing methodology intentionally normalizes liquidity by underlying/session across rollover; OI change in the Futures scanner separately requires the *same exact contract*.

## H. F&O live validation

| Question | Result |
| --- | --- |
| At least three valid completed sessions exist? | **No — zero** |
| State before fix | Unavailable; persisted `NO_ELIGIBLE_FUTURES` |
| State after fix | `ACCUMULATING`, `0/3 completed sessions collected` |
| F&O Liquidity 50 available | No |
| F&O Liquidity 100 available | No |
| F&O Liquidity 200 available | No |
| Why unavailable | No completed-session observations have yet been captured |
| Threshold or score changed | No |
| Historical/synthetic evidence inserted | No |

Automatic enablement and nesting are demonstrated with controlled valid three-session fixtures; live enablement cannot honestly be demonstrated before the evidence exists. Keeping the API running through future completion windows is necessary for prospective collection. This is the expected state, not an acceptance failure.

## I. Futures issue reproduction

The archived failing run at `2026-10-16T06:51Z` resolved five underlyings but received a Dhan rate-limit error for the batched quote request. Canonical contracts were present; all five candidates lacked quote evidence. The old generic message failed to distinguish provider failure from insufficient sample history.

The new output gives a deterministic primary reason and ordered additional reasons. Provider failures are distinct from missing response entries, stale quotes and insufficient percentile cohorts. No provider retry storm or extra per-row request was introduced.

## J. Futures evidence pipeline

Exact FUTSTK/FUTIDX resolution → one futures/spot quote batch → quote freshness → active metric availability → current-scan percentile population → same-contract OI comparison when needed → spot direction/basis when needed → explicit predicates → archived outcome/reasons.

Freshness uses provider source time against receipt: a quote more than 30 minutes old during ordinary weekday 09:15–15:30 IST hours is stale. Outside that window the last available quote can be used for up to seven days, with its source time retained. Missing source time or an implausibly future source timestamp is invalid. Stale futures samples cannot populate other candidates' percentile cohorts; stale spot quotes cannot create a direction value.

Basis retains the existing stricter policy: futures and spot source times within five minutes of each other and each at most 15 minutes behind receipt. Missing optional basis cannot block unrelated predicates. After hours, price/volume/OI may remain usable while basis or OI comparison is unavailable.

The quote model distinguishes valid zero volume/OI from missing fields. Zero is usable for a Futures numeric comparison; it is deliberately excluded from completed-session liquidity ranking. Invalid/negative/nonfinite provider metrics are rejected by the existing quote parser. A partial parser rejection currently appears as an absent quote ID rather than exposing raw provider internals.

## K. Required versus optional evidence

| Active predicate | Required evidence |
| --- | --- |
| Price / price change | Exact fresh futures quote; previous close additionally for change |
| Volume / OI | Corresponding observed value, including legitimate zero |
| Volume percentile / OI percentile | Corresponding metric and at least five fresh comparable current-scan contracts |
| ΔOI / ΔOI % | Current OI and valid same-contract archived comparison within 30 minutes with advancing provider time |
| Spot direction | Fresh exact underlying spot quote and valid prior close; unchanged ±0.1% rule |
| Basis | Fresh exact futures and spot evidence meeting the existing timestamp policy |
| Interpretation | Existing same-window futures price/OI comparison inputs |
| DTE | Resolved expiry; existing global exact-quote availability rule remains |

The Futures percentile population is **five current-scan contracts**, not the F&O universe's three completed sessions. These independent requirements must not be conflated. IV is not a Futures evaluation prerequisite.

Required evidence takes precedence over predicate failure: if any active prerequisite is missing, the candidate remains NOT_EVALUATED even if another condition is already known false. Only complete required evidence permits MATCH/NON_MATCH. This corrects the previous short-circuit classification to the task’s explicit evaluation contract. Display-only missing fields remain optional. Missing the globally required exact fresh futures quote is always NOT_EVALUATED. No scoring or predicate threshold was changed.

## L. NOT_EVALUATED taxonomy

Ordered quote/metric/context reasons include:

- `PROVIDER_UNAVAILABLE` with bounded provider error category, including `RATE_LIMITED`/`TIMEOUT`.
- `FUTURES_QUOTE_UNAVAILABLE`, `FUTURES_QUOTE_STALE`, `DATA_INVALID`.
- `VOLUME_UNAVAILABLE`, `OI_UNAVAILABLE`.
- `VOLUME_HISTORY_INSUFFICIENT`, `OI_HISTORY_INSUFFICIENT` (current-scan minimum population).
- `OI_COMPARISON_UNAVAILABLE` (same-contract time comparison).
- `SPOT_QUOTE_UNAVAILABLE`, `SPOT_QUOTE_STALE`, `SPOT_DIRECTION_UNAVAILABLE`.
- `TIMESTAMP_MISMATCH` for unavailable required basis.

Unresolved candidates preserve the canonical resolver's specific failure code (for example `NO_MASTER_MATCH`, `FUTURES_IDENTITY_UNAVAILABLE`) in underlying diagnostics and grouped counts. These have no fabricated contract row. Primary reasons are deterministic by pipeline order; reason text contains no stack trace or credential.

## M. Row-level diagnostics

Additive row fields `evaluation_reason` and `evaluation_reasons` explain NOT_EVALUATED. Enabling “Show non-matches / not evaluated” adds the evaluation/reason column. Why? retains predicates for evaluated outcomes and displays evidence failures for NOT_EVALUATED. The existing interpretation field remains domain evidence, not a container for infrastructure errors.

Underlying diagnostics show exact contract ID, outcome and stage statuses for contract, quote, volume, OI, percentile cohorts, spot, direction and basis. Stale quote/spot stages say STALE; absent values say MISSING. Existing history remains readable when new fields are absent.

## N. Grouped diagnostics and counts

The expandable “Not evaluated: N · view reasons” section lists primary reason counts. Grouping uses already-fetched/archived evidence and does not make extra provider calls.

Counts retain the existing explicit unresolved terminal classification:

- `requested >= resolved`.
- `evaluated + resolved_not_evaluated = resolved`.
- Displayed `not_evaluated` also includes unresolved underlyings, so `evaluated + displayed_not_evaluated = requested` for the bounded one-contract-per-underlying run.
- `matches <= evaluated`; grouped primary reasons sum to displayed NOT_EVALUATED count.

## O. Live Dhan evidence

Provider endpoint category: Dhan `/marketfeed/quote`; futures native IDs listed below. Live field presence was verified for price, volume, OI and source time. Requests were bounded; no orders were placed. Sanitized records were retained privately in `/tmp/twf-readiness-live-evidence.json` and the durable Scanner run history. That file contains market evidence, not credentials.

Official source contracts consulted: [Dhan market quote](https://dhanhq.co/docs/v2/market-quote/) and [instrument master](https://dhanhq.co/docs/v2/instruments/). The detailed master provides structured identities; batched quotes avoid one request per row.

## P. Live Futures result

Run `c7b89570-f493-4d83-8560-f3e77be0cafa`, 16 October 2026 at 13:06:35 IST. Custom underlyings: ABB, ADANIPOWER, BHEL, ADANIGREEN, RELIANCE. Nearest expiry, volume percentile ≥40, OI percentile ≥40, spot direction Up.

**Requested 5 · Resolved 5 · Evaluated 5 · Not evaluated 0 · Matches 2.** All resolved expiries: **27 October 2026**.

| Symbol | Exact Dhan futures | Quote | Volume | OI | Vol cohort | OI cohort | Spot | Direction | Basis ₹ | Outcome | Reason |
| --- | --- | ---: | ---: | ---: | --- | --- | --- | --- | ---: | --- | --- |
| ABB | NSE_FNO:48707 | 6,857 | 250,625 | 1,679,750 | 5; P20 | 5; P20 | PASS | Up | 26 | NON_MATCH | Both percentile predicates fail |
| ADANIPOWER | NSE_FNO:48720 | 197.46 | 6,049,200 | 227,427,200 | 5; P60 | 5; P100 | PASS | Up | 0.33 | MATCH | 3/3 predicates pass |
| BHEL | NSE_FNO:48764 | 435.85 | 7,833,000 | 79,096,500 | 5; P80 | 5; P60 | PASS | Sideways | 1.25 | NON_MATCH | Up predicate fails |
| ADANIGREEN | NSE_FNO:48712 | 1,315.90 | 571,800 | 22,474,200 | 5; P40 | 5; P40 | PASS | Up | 4.50 | MATCH | 3/3 predicates pass |
| RELIANCE | NSE_FNO:48987 | 1,211 | 12,188,000 | 144,049,000 | 5; P100 | 5; P80 | PASS | Down | 2.70 | NON_MATCH | Up predicate fails |

Source trade timestamps span 13:04:23–13:06:34 IST, same day. OI *percentile* evidence was available for all five. Same-contract OI *change* was absent for four and present for RELIANCE; it was optional and did not block the scan.

Deliberate insufficient-evidence run `c075d536-15cd-4bad-8a60-2eb32ff62712`, 13:07:06 IST: ABB alone, volume percentile ≥40. Counts **1 requested / 1 resolved / 0 evaluated / 1 not evaluated / 0 matches**. Exact reason: `VOLUME_HISTORY_INSUFFICIENT` — “Volume percentile requires 5 current-scan comparable contracts; 1 available”. The quote, spot and basis were present. No zero or invented percentile was substituted.

## Q. Regression coverage

Focused tests cover eligibility, expiry rollover, deterministic nested ranking, 0/1/2/3-session readiness, partial retry, duplicate-date protection, persisted restart, weekend/open-session exclusion, prior-session timestamp rejection, positive-metric rules, provider failure and last-good retention. Futures tests cover typed failures, optional evidence, fresh/stale cohorts, stale required versus optional spot, mixed MATCH/NON_MATCH/NOT_EVALUATED counts, exact identity and canonical index resolution.

The archived dynamic-universe test now seeds three valid observation dates through collection persistence instead of bypassing readiness with an empty-history ranking. Its compact derivative underlying fields are blank, while detailed identities remain populated, matching the live failure. Removing a detailed active-option identity excludes that symbol from current detail without changing archived membership. Its original historical-membership assertion is preserved. An additional direct probe verifies four-session coverage, duplicate-date rank stability and eight-day last-good expiration.

Options/Equity/Watchlists are covered by the full backend/frontend suites and browser workflows. No broker execution test was used to place an actual order; browser previews use isolated fixtures.

## R. Gates

The final complete backend gates ran sequentially on the final source. Neither suite had a failed test.

| Gate | Result |
| --- | --- |
| Full PostgreSQL backend | 1556 passed, 1 skipped, 4 warnings in 623.73s (0:10:23) |
| Full SQLite backend | 1,482 passed, 75 PostgreSQL-specific skips, 4 existing warnings; 542.08s |
| Frontend unit suite | 296 passed, 33 files (`npm test -- --maxWorkers=2`) |
| Production frontend build | PASS |
| PostgreSQL-backed Chromium 390 / 1440 | 19 passed, 1 existing skip; final truthful missing-volume fixture recheck 2/2 passed |
| TypeScript / ESLint / Prettier | PASS |
| Ruff / Ruff format | PASS; 237 files formatted |
| compileall / pip check | PASS |
| Changed-file mypy | PASS, 10 files |
| Repository mypy | PRE_EXISTING_UNRELATED: 15 errors in three unchanged tests |
| git diff --check | PASS |

Commands: `tools/test-postgres.sh -q`; `PYTHONPATH=src .venv/bin/pytest --db-backend=sqlite -q`; `npm test -- --maxWorkers=2`; frontend `type-check`, `lint`, `format:check`, `build`; PostgreSQL browser runner with `scanner-v2`, `derivatives-scanner`, `futures-scanner`, `futures-ux-parity`, `scanner-watchlist-unification` at both required Chromium widths.

The unrestricted frontend run exhausted the unchanged 5-second timeout of the existing serial watchlist-hydration test. All 296 tests passed with two workers, without increasing timeouts or changing hydration behavior. Initial backend gates found an obsolete test helper removed by the cache merge implementation; the fixture was corrected, not production readiness weakened. Initial browser assertions expected the old readiness wording and assumed Equity could not share the derivative chip CSS class; tests now assert the actual mode boundary and current label.

An intermediate PostgreSQL full run had one unrelated MCP wall-clock bound failure: TIMEOUT returned after 1.058 seconds against a 0.52-second assertion, before the test reached its durable-state checks. All 18 delayed-finalization cases passed on immediate focused recheck, including durability. No MCP code, deadline or assertion was changed. An earlier full SQLite run passed 1,481 tests (75 backend-specific skips). Runs whose source had been loaded before final eligibility/classification/last-good corrections were superseded; incomplete superseded runs were stopped. Full gates run sequentially on the final source; acceptance uses those full results, not the focused retry alone.

Existing mypy debt: `test_option_chain.py` (method assignment), `test_derivative_relative_volume.py` (annotations/optional Decimal), `test_derivative_templates.py` (test app typing). No changes to those files. The browser skip is the pre-existing mobile skip of a catalog-error case tested at desktop width.

## S. Exact files changed

- `apps/api/src/twf/discovery/dhan_futures.py`
- `apps/api/src/twf/discovery/market_data.py`
- `apps/api/src/twf/main.py`
- `apps/api/src/twf/scanner_v2/futures.py`
- `apps/api/src/twf/watchlists/fno_liquidity.py`
- `apps/api/src/twf/watchlists/system.py`
- `apps/api/tests/test_dhan_futures_resolution.py`
- `apps/api/tests/test_fno_liquidity.py`
- `apps/api/tests/test_futures_scanner.py`
- `apps/api/tests/test_scanner_v2.py`
- `apps/web/src/components/scanner/futures-scanner.tsx`
- `apps/web/src/lib/watchlists.ts`
- `apps/web/src/styles/scanner.css`
- `apps/web/tests/browser/derivatives-scanner.spec.ts`
- `apps/web/tests/browser/futures-scanner.spec.ts`
- `apps/web/tests/browser/futures-ux-parity.spec.ts`
- `apps/web/tests/browser/scanner-watchlist-unification.spec.ts`
- `apps/web/tests/scanner-watchlist-selector.test.tsx`
- `apps/web/tests/watchlists.test.tsx`
- `docs/TWF_SCANNER_V2_ARCHITECTURE.md`
- `docs/TWF_WATCHLIST_ARCHITECTURE.md`
- `docs/TWF_SCANNER_DATA_READINESS_HARDENING_REPORT.md`

The generated `next-env.d.ts` change is restored before completion. No runtime data migration or change to frozen OE lifecycle/authority boundaries is included.

## T. Documentation

Updated `TWF_WATCHLIST_ARCHITECTURE.md` for detailed-master collection, background lifecycle, safe retries, truthful states and persistence. Updated `TWF_SCANNER_V2_ARCHITECTURE.md` for active-predicate evidence, freshness and diagnostic UI. This report preserves the historical limitations: prospective collection, three sessions, five-contract Futures percentile population and optional same-contract comparison.

## U. Scorecard

```text
SCANNER_DATA_READINESS_STATUS = PASS
FNO_SESSION_COLLECTION_TRACED = PASS
FNO_SESSION_COUNT_TRUTHFUL = PASS
FNO_DUPLICATE_SESSION_BLOCKED = PASS
FNO_HOLIDAY_HANDLING = PASS
FNO_ROLLOVER_HANDLING = PASS
FNO_READINESS_STATE_MODEL = PASS
FNO_READY_AUTO_ENABLE = PASS
FNO_LAST_GOOD_POLICY = PASS
FNO_50_NESTED = PASS
FNO_100_NESTED = PASS
FNO_200_READY_IF_EVIDENCE_SUFFICIENT = PASS
FUTURES_CONTRACT_RESOLUTION = PASS
FUTURES_QUOTE_EVIDENCE = PASS
FUTURES_VOLUME_EVIDENCE = PASS
FUTURES_OI_EVIDENCE = PASS
FUTURES_VOLUME_HISTORY = PASS
FUTURES_OI_HISTORY = PASS
FUTURES_SPOT_EVIDENCE = PASS
FUTURES_DIRECTION_EVIDENCE = PASS
FUTURES_BASIS_POLICY = PASS
REQUIRED_OPTIONAL_EVIDENCE_SEPARATED = PASS
NOT_EVALUATED_TYPED_REASONS = PASS
NOT_EVALUATED_ROW_DIAGNOSTICS = PASS
NOT_EVALUATED_GROUPED_SUMMARY = PASS
EVALUATED_NON_MATCH_SEMANTICS = PASS
MATCH_SEMANTICS = PASS
SUMMARY_COUNT_INVARIANTS = PASS
LIVE_DHAN_VALIDATION = PASS
LIVE_FNO_READINESS_TRUTHFUL = PASS
LIVE_FUTURES_REASONS_EXPLICIT = PASS
OPTIONS_SCANNER_REGRESSION = PASS
EQUITY_SCANNER_REGRESSION = PASS
WATCHLIST_REGRESSION = PASS
FULL_BACKEND_POSTGRES = PASS
FULL_BACKEND_SQLITE = PASS
FRONTEND = PASS
BROWSER_POSTGRES = PASS
CHANGED_FILE_MYPY = PASS
REPO_MYPY = PRE_EXISTING_UNRELATED
RUFF = PASS
FORMAT = PASS
COMPILE = PASS
PIP_CHECK = PASS
TYPESCRIPT = PASS
ESLINT = PASS
PRETTIER = PASS
GIT_DIFF_CHECK = PASS
READY_FOR_USER_VALIDATION = YES
```

Holiday coverage is the conservative same-session evidence policy described above, not a newly introduced exchange calendar. Live F&O availability remains 0/3; auto-enable and nesting passed with controlled sufficient-history data. No live history was fabricated.

## V. Final status

**READY_FOR_USER_VALIDATION.** No commit/tag/push. No OE-4 work or broker submission. Refresh the Scanner to see the compact readiness progress and explicit Futures reasons. Keep the API running through completed-session collection windows; the liquidity universes enable automatically when each ranked underlying has at least three valid sessions.

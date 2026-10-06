# Watchlists — Implementation Report

2026-10-06 · **READY_FOR_USER_VALIDATION** · not accepted/frozen.

## Current refinement — selected-instrument production UX

2026-10-06, approximately 21:52 IST live validation. **READY_FOR_USER_VALIDATION**.
This frontend presentation pass supersedes the always-visible Overview provenance
and redundant Chart tab described in older sections; it preserves data semantics.

### A. Preflight

Branch `main`, HEAD `41667f8d096bc6e6b94f4dd186838904c77ef0fe`. The preceding
12-file uncommitted Watchlists semantics change was present and preserved. No
backend normalization/provider contract was changed in this pass. No commit,
tag, push, scan or live order was made.

### B–G. Panel, formatting and disclosure

- Removed the Chart tab; retained the reusable chart renderer in Overview.
  Overview / Option Chain / News have tablist/tab/tabpanel relationships and
  ArrowLeft/ArrowRight/Home/End navigation. Existing timeframe behavior is retained.
- Kept symbol, LTP and labeled, color-coded selected-period return prominent.
  Chart precedes timeframe controls, then Price / market data, Reference /
  fundamentals, Data details and unchanged Quick Trade.
- Volume formatting: 999 → `999`, 1500 → `1.50 K`, 8252213 → `82.52 L`,
  18003127 → `1.80 Cr`. Zero stays `0`; missing/nonfinite/negative volume stays `—`.
  This is display rounding only; underlying counts remain unchanged.
- Market Cap uses the existing **normalized INR** contract. 85400000000 INR →
  `₹8,540 Cr`, 1240000000000 INR → `₹1.24 L Cr`, and 16482632200000 INR →
  `₹16.48 L Cr`. No second provider-crore conversion occurs. The existing backend
  provider-unit normalization test was rerun successfully; backend code was unchanged.
- Fundamentals groups Market Cap/PE; Price reference groups 52W High/Low.
  PE is an unsuffixed ratio. All market prices reuse `numberText`'s Indian grouping
  and up-to-two-decimal convention without ₹; Market Cap includes ₹ explicitly.
- Native Data details is collapsed by default, with a visible disclosure indicator,
  keyboard support and synchronized `aria-expanded`. It preserves market/reference
  provider, source/tool, source and receipt timestamps, freshness/limitations and
  exact period comparison basis. Primary Overview no longer exposes tool names or
  provider/debug blocks. Missing data remains a dash, not an invented value.
- News contents/provenance and Option Chain placeholder are unchanged. Broker
  selection, type controls, quantity, order type, Buy/Sell and preview/confirmation
  remain on the existing Broker V2 path.

### H. Exact files changed in this pass

1. `apps/web/src/components/watchlists/watchlists-workspace.tsx`
2. `apps/web/src/lib/watchlists.ts`
3. `apps/web/src/styles/watchlists.css`
4. `apps/web/tests/watchlists.test.tsx`
5. `apps/web/tests/browser/watchlists.spec.ts`
6. `docs/TWF_WATCHLIST_ARCHITECTURE.md`
7. `docs/TWF_WATCHLIST_IMPLEMENTATION_REPORT.md`

Other dirty files listed in the preceding remediation inventory predate this pass.

### I. Validation

- Focused frontend Watchlists/proxy: **36 passed** (2 files).
- Full frontend unit suite: **200 passed** (19 files, serial workers).
- TypeScript, ESLint, Prettier and production build: **PASS**.
- Existing backend reference normalization test: **1 passed / 13 deselected**.
  Ruff/strict mypy were not rerun for this frontend-only pass; no new backend
  normalization changes require them. Prior full-mypy limitations remain recorded below.
- Focused Chromium Watchlists: **6 passed** at 390, 768, 1024, 1440, 1920 and 2560.
  Tests cover chart preservation/all periods, compact units, absent Chart tab,
  hidden provenance, keyboard disclosure expansion/collapse, keyboard tab navigation,
  unchanged News/Option Chain, and Quick Trade preview with zero dispatches.
  These tests use isolated API/database plus mocked market overlays.
- `git diff --check`: **PASS**.

### J. Live validation

Authenticated, unmocked My Core checks at 1920px passed; no JavaScript errors.

| Symbol   | Volume  | Average volume (20d) | Market Cap  | PE    | 52W High / Low    | 1M return |
| -------- | ------- | -------------------- | ----------- | ----- | ----------------- | --------- |
| RELIANCE | 1.80 Cr | 1.26 Cr              | ₹16.48 L Cr | 22.06 | 1,611.8 / 1,160.8 | -9.65%    |
| HDFCBANK | 2.66 Cr | 3.17 Cr              | ₹10.97 L Cr | 13.85 | 1,020.5 / 681.9   | +0.57%    |
| NIFTY    | 0       | 30.55 Cr             | —           | —     | — / —             | -5.68%    |

NIFTY zero volume and historical mean are existing provider values, not filled-in
reference metrics. All three Overview charts rendered; Chart tab was absent.
Disclosure began collapsed, hid provenance, and exposed retained Dhan/TapTide
source/receipt metadata with keyboard Enter. NIFTY reference availability remained
NOT AVAILABLE. Live requests: one quote batch, four existing row 1M history reads,
and three selected reference endpoints; dev Strict Mode duplicated the first
local reference GET, with the existing backend cache retaining provider deduplication.
No market-provider capabilities or request loops were added by this UI pass.

### K. Screenshots / visual acceptance

Live collapsed/expanded captures:
`/tmp/twf-panel-live-RELIANCE.png`, `/tmp/twf-panel-live-RELIANCE-details.png`,
`/tmp/twf-panel-live-HDFCBANK.png`, `/tmp/twf-panel-live-HDFCBANK-details.png`,
`/tmp/twf-panel-live-NIFTY.png`, `/tmp/twf-panel-live-NIFTY-details.png`.

Light/dark six-width browser captures:
`apps/web/test-results/watchlists-persistent-Watc-bff0e-rchive-and-responsive-shell-chromium-{width}/watchlists-{light|dark}-detail.png`.
The desktop inspector and smaller scrollable modal retain the approved layout;
compact units fit, tabs/chart align, and Quick Trade remains usable. Technical
metadata no longer dominates Overview. Existing compact-table responsive rules
and scanner/broker content are unchanged.

### L–M. Scorecard and status

```text
WATCHLIST_CHART_TAB_REMOVED = PASS
WATCHLIST_OVERVIEW_CHART_PRESERVED = PASS
WATCHLIST_VOLUME_INDIAN_UNITS = PASS
WATCHLIST_AVG_VOLUME_INDIAN_UNITS = PASS
WATCHLIST_MARKET_CAP_INDIAN_UNITS = PASS
WATCHLIST_PE_FORMAT_CORRECT = PASS
WATCHLIST_52W_PRICE_FORMAT_CORRECT = PASS
WATCHLIST_PROVIDER_DEBUG_HIDDEN = PASS
WATCHLIST_DATA_DETAILS_DISCLOSURE = PASS
WATCHLIST_PROVENANCE_PRESERVED = PASS
WATCHLIST_QUICK_TRADE_REGRESSION_FREE = PASS
WATCHLIST_NEWS_REGRESSION_FREE = PASS
WATCHLIST_OPTION_CHAIN_REGRESSION_FREE = PASS
RESPONSIVE_VALIDATION = PASS
ACCESSIBILITY_VALIDATION = PASS
WATCHLIST_PRODUCTION_UX_STATUS = READY_FOR_USER_VALIDATION
```

---

## Previous remediation — explicit time bases and reference metrics

2026-10-06, 21:24–21:27 IST live validation. **READY_FOR_USER_VALIDATION**.
This section supersedes earlier missing-reference and unlabeled-detail observations.

### A. Preflight

Branch `main`; HEAD `41667f8d096bc6e6b94f4dd186838904c77ef0fe`; clean worktree at
start. Existing accepted Watchlists work was preserved. No commit/tag/push, scan,
live order or execution-policy change was made. TapTide remained generation 3,
CONNECTED/AVAILABLE after validation; all 105 recorded operations were COMPLETE,
with reconciliation_required false and no active operations.

### B–D. Time-basis diagnosis and implementation

The row calculation already used session-change semantics, but its old label was
ambiguous. It is now **1D %**, retaining normalized-provider percentage priority,
then previous-close comparison; valid zero stays 0.00% and missing stays “—”.
Positive/negative values retain green/red, including the period-aware detail value.

The existing row series is 22 completed Dhan daily bars, now explicitly labeled
**Quick Chart (1M)** with a concise tooltip. Selection cannot replace the row series.

Previously the detail header reused the row's one-day return for every chart range.
It now displays `1D/1W/1M/3M/1Y` beside the return and its actual comparison dates
and prices. 1D compares latest quote to previous session close. Longer periods use
first/last close of the displayed 5/22/66/252 completed daily bars, approximately
one week/month/quarter/year. Their end price may differ from current LTP; the basis
is visible. Insufficient/invalid history returns a dash. India-session chart-axis
dates agree with the comparison labels. No scanner indicator/threshold changed.

### E–G. Provider capability, normalization, provenance and caching

Live discovered schemas identify `get_stock_quote` and `get_company_profile` as
company reference capabilities. One diagnostic RELIANCE quote, one company profile,
and one `read_me` call inspected actual response/unit semantics through the existing
MCP manager. A rejected profile admission made no provider dispatch; the existing
local recovery protocol cleared a diagnostic completion receipt before the bounded
profile call. Final durable state is clean as recorded above.

Production reference reads use only `get_stock_quote`, exact NSE equity symbol,
existing credentials and server tool policy. Typed `ReferenceSnapshot` contains
Market Cap in INR, PE, direct 52W High/Low, provider/tool, source time, received time,
freshness and availability. No raw response keys/payload reach the UI. `updated_at`
was verified live and mapped explicitly; its timestamp describes the provider
snapshot, not separately verified filing dates for each fundamental.

Market cap units are corroborated by TapTide's published
[Marketcap (₹Cr) leaderboard](https://tapetide.com/score/leaderboard?sort=market_cap)
and the live profile's share/price metadata. The raw quote has no explicit unit
field: this is an evidence-backed adapter interpretation. Only unit conversion is
performed; capitalization/PE are not inferred from incomplete fundamentals.

Reference cache: owner + connection + generation + instrument; max 128 entries per
API process, 15-minute successful/partial/not-available TTL, 60-second failed-result
TTL, concurrent deduplication and 25-second total budget. Browser cache: 50 entries,
same TTLs. Existing daily/intraday history cache remains five minutes, 256 API/100
browser entries, and the existing one-at-a-time provider pacing remains unchanged.
No new HTTP client or distributed cache was introduced.

NIFTY/index, derivative and BSE reference values stay unavailable in this bounded
NSE company-reference integration. No extra annual-history derivation was added.
Prices/volume remain Dhan-backed and reference metrics are visibly separate.

### H. Exact changed files

- `apps/api/src/twf/api/watchlists.py`
- `apps/api/src/twf/main.py`
- `apps/api/src/twf/watchlists/reference.py` (new)
- `apps/api/tests/test_watchlists.py`
- `apps/web/src/app/api/v1/watchlists/[[...path]]/route.ts`
- `apps/web/src/components/watchlists/market-chart.tsx`
- `apps/web/src/components/watchlists/watchlists-workspace.tsx`
- `apps/web/src/lib/watchlists.ts`
- `apps/web/tests/browser/watchlists.spec.ts`
- `apps/web/tests/watchlists.test.tsx`
- `docs/TWF_WATCHLIST_ARCHITECTURE.md`
- `docs/TWF_WATCHLIST_IMPLEMENTATION_REPORT.md`

### I. Validation

- Backend focused Watchlists + market data: **32 passed**.
- Frontend full suite, serial execution: **186 passed / 19 files**. Two earlier
  concurrent runs hit an unchanged Discovery test's immediate assertion while its
  asynchronous drawer was still loading (185 passed/1 failed). Baseline extracted
  at HEAD also passed in isolation and full-suite checks; no Discovery source/test
  was changed. Final serial suite passed, but the concurrency-sensitive test remains
  a suite limitation, not a claimed Watchlists fix.
- TypeScript, ESLint, Prettier and production build: **PASS**.
- Chromium Watchlists: **6 passed**, widths 390/768/1024/1440/1920/2560. Market
  overlays are mocked here; collection CRUD, CSV, notes, routing, archive/restore,
  broker ticket preview and persistence use the isolated real test API/database.
  The new assertions verify all periods, unchanged row values, cached 1M reuse,
  reference display and one reference API request. No order confirmation occurs.
- Ruff lint + format: **PASS**, 146 Python files formatted.
- Strict mypy on all source + focused tests: **PASS**, 87 files. Full strict mypy
  retains two unchanged errors: `tests/test_discovery_product.py:1321` fake provider
  protocol mismatch and `tests/test_dhan_credentials.py:126` Any return. These are
  outside this bounded change; the full check is **not** claimed clean.
- `git diff --check`: **PASS**.

### J. Live validation

Authenticated My Core, no response mocks, four canonical instruments. Dhan supplied
75 completed 5-minute bars for each 1D chart and 5/22/66/252 daily bars for the other
periods. All 20 chart responses succeeded. The table's four daily percentages and
22-bar sparklines remained unchanged throughout all detail switches.

| Symbol   |      LTP | Table / detail 1D | Detail 1W | Detail 1M | Detail 3M | Detail 1Y |
| -------- | -------: | ----------------: | --------: | --------: | --------: | --------: |
| RELIANCE |    1,218 |            +2.66% |    -0.94% |    -9.65% |    -8.98% |   -13.88% |
| INFY     | 1,013.85 |            -0.65% |    +1.72% |   -10.48% |    -1.96% |   -29.57% |
| HDFCBANK |   711.45 |            +0.94% |    -1.98% |    +0.57% |   -11.45% |   -25.42% |
| NIFTY    | 22,776.1 |            +0.98% |    -0.99% |    -5.68% |    -6.70% |    -8.51% |

These are observed provider snapshots, not claims of continuously current prices.
For example RELIANCE 1M used Sep 2 close 1,313.1 to Oct 5 close 1,186.4; its 1D
used Oct 5 close 1,186.4 versus Oct 6 quote 1,218.

| Symbol   | Market Cap (₹Cr) |    PE | 52W High | 52W Low |
| -------- | ---------------: | ----: | -------: | ------: |
| RELIANCE |     16,48,263.22 | 22.06 |  1,611.8 | 1,160.8 |
| INFY     |      4,11,443.90 | 13.65 |    1,728 |   980.4 |
| HDFCBANK |     10,96,821.13 | 13.85 |  1,020.5 |   681.9 |
| NIFTY    |                — |     — |        — |       — |

All three equity reference snapshots retained TapTide / get_stock_quote provenance,
source Oct 6 15:59 IST, received approximately 21:27 IST, CURRENT within the reference
freshness policy. NIFTY is explicitly NOT_AVAILABLE. No browser JavaScript errors.

### K–L. Screenshots and request observations

Local live captures (not Git artifacts):
`/tmp/twf-semantics-live-reference-RELIANCE.png`,
`/tmp/twf-semantics-live-reference-INFY.png`,
`/tmp/twf-semantics-live-reference-HDFCBANK.png`,
`/tmp/twf-semantics-live-reference-NIFTY.png`.

Six-width light/dark browser captures are under
`apps/web/test-results/watchlists-persistent-Watc-bff0e-rchive-and-responsive-shell-chromium-{width}/`
(`watchlists-light-detail.png`, `watchlists-dark-detail.png`, list/reload captures).
The existing 390px compact table hides optional columns, including daily percent
and sparkline; semantics remain explicit in the column controls/footer and selected
detail. No horizontal page overflow; detail is a scrollable modal below 1200px.

Cold live traversal: one quote batch, four row 1M API reads, then four additional
period API reads per symbol (20 total historical ranges). Each period requested
once; cached 1M selection/reselection did not fetch again. Three TapTide reference
calls served the three equities; NIFTY made no provider reference call. React dev
mode sent two concurrent first-reference API reads, deduplicated to one provider
operation. Reselecting RELIANCE added **zero** requests. The source-timestamp mapping
correction reset the API cache; a separate confirmation pass made three additional
reference calls, then retained all source timestamps. No aggressive retries.

### M–N. Scorecard and status

```text
WATCHLIST_TABLE_1D_PERCENT_LABEL = PASS
WATCHLIST_TABLE_1D_PERCENT_CORRECT = PASS
WATCHLIST_TABLE_MISSING_CHANGE_IS_DASH = PASS
WATCHLIST_QUICK_CHART_1M_LABEL = PASS
WATCHLIST_QUICK_CHART_1M_DATA = PASS
WATCHLIST_DETAIL_PERIOD_CHANGE = PASS
WATCHLIST_DETAIL_PERIOD_LABEL = PASS
WATCHLIST_DETAIL_PERIOD_SYNC = PASS
WATCHLIST_MARKET_CAP = PASS
WATCHLIST_PE = PASS
WATCHLIST_52W_HIGH = PASS
WATCHLIST_52W_LOW = PASS
WATCHLIST_REFERENCE_PROVENANCE = PASS
NO_PROVIDER_CALL_EXPLOSION = PASS
WATCHLIST_CORE_REGRESSION_FREE = PASS
RESPONSIVE_VALIDATION = PASS
WATCHLIST_DATA_SEMANTICS_STATUS = READY_FOR_USER_VALIDATION
```

Reference-metric PASS means supported equities; NIFTY remains truthfully unavailable.
No acceptance/freeze or repository publication is claimed.

---

## Previous remediation — live rows, Change %, and news semantics

2026-10-06, approximately 20:31 IST. This section supersedes the earlier live-data
limitations and selection-dependent row behavior recorded below. Branch/HEAD
remain `main` / `2cdd1d765bd1614741c47f288c66b7e0f62b96f8`; the existing dirty
workspace was preserved. No commit/tag/push, scan, or order was performed.

### Proven root causes

- Row RSI/trend/sparkline state was populated only by selected-detail requests.
- The quote adapter mapped `ohlc.close` to previous close. Dhan defines that field
  as the day's closing price and `net_change` as absolute change from previous
  close ([official quote contract](https://dhanhq.co/docs/v2/market-quote/)).
- Live generation-3 READY Dhan snapshots returned **zero net_change** and close
  equal to LTP for all four rows. Thus substituting net_change alone would still
  leave this live defect unresolved. Normalized history supplied October 5's
  completed close; source quote timestamps identified October 6's session.
- Corporate-event claims and even metadata-only records were being presented in
  the company-news section. They are now separate, and empty metadata isn't a story.

### Implemented behavior and request budget

Visible-page lazy hydration (option B) uses 22 normalized Dhan daily bars. The
accepted Wilder RSI(14), close versus SMA(20), and volume calculations are reused.
Longer/shorter detail ranges don't replace the row series. An unchanged visible
page needs no selection to hydrate. Switching page stops scheduling its old rows.

Quotes: one batch per list refresh, existing 15-second cache. History: at most one
cold request per visible row (default ten; page choices ten/25/50), serially loaded.
Backend concurrency is one per application process, at least one second between
provider starts. Shared owner/generation/instrument/range cache: five-minute success
TTL, 30-second failure TTL, 256-entry bound; rate limiting starts a 30-second
cooldown. Total history wait plus provider I/O is bounded at 12 seconds. Browser
in-flight deduplication/cache prevents repeat 1M detail requests. No distributed
rate coordinator is claimed. Hard reload does issue new local API reads, but valid
backend cache entries reuse the provider series.

Change prefers a normalized provider percentage if present, then valid normalized
previous close. Ambiguous zero quotes instead use the latest completed daily close
strictly before the source quote's India session date (maximum seven-day age).
Missing source time or baseline stays unavailable. Zero is displayed only when
established by valid data. Neither today's open nor today's closing bar is used.

Company news requires a symbol-scoped NEWS_SENTIMENT headline. Corporate events
require a symbol-scoped CORPORATE_EVENT with an event type. Empty record metadata
isn't shown as a card. Sector context requires explicit sector scope, never an
inferred company-sector assignment. Market context appears last. Provider, tool,
scope, source time, receipt time and freshness remain visible without raw JSON.

### Live verification

Existing My Core list `50546d15-c90d-40f5-ad3e-7065f38b1a37` was read, not recreated.
No row was selected before the hard-reload assertions and screenshot.

| Symbol   |      LTP | Prior-session close | Change | RSI(14) | Trend | Sparkline |
| -------- | -------: | ------------------: | -----: | ------: | ----- | --------- |
| RELIANCE |  1218.00 |             1186.40 | +2.66% |   30.13 | Down  | 22 bars   |
| INFY     |  1013.85 |             1020.50 | -0.65% |   34.44 | Down  | 22 bars   |
| HDFCBANK |   711.45 |              704.80 | +0.94% |   47.96 | Down  | 22 bars   |
| NIFTY    | 22776.10 |            22555.75 | +0.98% |   25.37 | Down  | 22 bars   |

Selecting RELIANCE and HDFCBANK made **zero additional history API requests**.
No browser page errors occurred. Quote source times and received times remained
separate. The table and detail agreed on percentage and previous close.

The bounded RELIANCE news read returned **PARTIAL**: market news was available;
corporate events were unavailable in this invocation. Company news correctly said
“No recent RELIANCE-specific news.” The Shiva Granito headline remained exclusively
under Market-wide context. No company headline or sector mapping was invented.
Provider failure was not retried. Live corporate-event success is not claimed.

### Validation

- Focused backend Watchlists/market-data tests: **29 passed**.
- Frontend Watchlists tests: **13 passed**; full frontend: **179 passed**.
- TypeScript, ESLint, Prettier, production build: **PASS**.
- Chromium Watchlists workflows: **6 passed**, widths 390/768/1024/1440/1920/2560,
  including hard reload with unselected rows, cache reuse, and existing workflows.
- Ruff lint and format: **PASS**, 126 Python files checked for formatting.
- Strict mypy runtime source plus changed tests: **PASS**, 86 files.
- Full strict mypy: **not clean**, the same two unchanged test errors at
  `tests/test_discovery_product.py:1321` and `tests/test_dhan_credentials.py:126`.
  They were already recorded in the earlier validation below; no unrelated test
  or Scanner code was altered to conceal them.
- One initial parallel frontend run hit an existing timing-sensitive Discovery
  assertion. The final full serial run passed; no Discovery source/test was edited.
- `git diff --check`: **PASS**.

### Exact files changed in this remediation

- `apps/api/src/twf/discovery/market_data.py`
- `apps/api/src/twf/watchlists/market.py`
- `apps/api/src/twf/api/watchlists.py`
- `apps/api/src/twf/main.py`
- `apps/api/tests/test_market_data.py`
- `apps/api/tests/test_watchlists.py`
- `apps/web/src/lib/watchlists.ts`
- `apps/web/src/components/watchlists/watchlists-workspace.tsx`
- `apps/web/tests/watchlists.test.tsx`
- `apps/web/tests/browser/watchlists.spec.ts`
- `docs/TWF_WATCHLIST_ARCHITECTURE.md`
- `docs/TWF_WATCHLIST_IMPLEMENTATION_REPORT.md`
- Five screenshot files linked below under `docs/evidence/watchlists-row-hydration/`.

### Screenshot evidence

- [Live hard reload, no selection](evidence/watchlists-row-hydration/live-hard-reload.png)
- [Live HDFCBANK detail](evidence/watchlists-row-hydration/live-hdfcbank-detail.png)
- [Live RELIANCE news, partial provider result](evidence/watchlists-row-hydration/live-reliance-news.png)
- [390px hard reload, isolated test data](evidence/watchlists-row-hydration/chromium-390-reload.png)
- [1440px hard reload, isolated test data](evidence/watchlists-row-hydration/chromium-1440-reload.png)

### Required scorecard

```text
WATCHLIST_ROWS_HYDRATE_ON_LOAD = PASS
WATCHLIST_RSI_WITHOUT_SELECTION = PASS
WATCHLIST_TREND_WITHOUT_SELECTION = PASS
WATCHLIST_SPARKLINE_WITHOUT_SELECTION = PASS
WATCHLIST_CHANGE_PERCENT_REAL = PASS
WATCHLIST_CHANGE_PERCENT_MISSING_NOT_ZERO = PASS
WATCHLIST_COMPANY_NEWS = PASS
WATCHLIST_CORPORATE_EVENTS = PASS
WATCHLIST_SECTOR_CONTEXT = PASS
WATCHLIST_MARKET_CONTEXT_SEPARATED = PASS
WATCHLIST_NO_N_PLUS_ONE_STORM = PASS
WATCHLIST_CACHE_REUSE = PASS
DHAN_LIVE_VALIDATION = PASS
TAPTIDE_LIVE_VALIDATION = PARTIAL
WATCHLIST_FIX_STATUS = READY_FOR_USER_VALIDATION
```

News/event/sector PASS means classification, empty/unavailable behavior, provenance
and automated coverage; it does not claim the live provider supplied missing items.

---

## A. Preflight

Branch: `main`. Start and finish HEAD:
`2cdd1d765bd1614741c47f288c66b7e0f62b96f8`.
The worktree was **not clean**: the application-shell redesign and Brokers navigation
restoration were already uncommitted. Those changes were preserved. No commit, tag,
push, reset or rebase was performed. No real order was placed.

## B–D. Architecture, persistence and API

The [architecture](TWF_WATCHLIST_ARCHITECTURE.md) records the domain, four tables,
owner checks, bounds, exact identities and complete API surface. Watchlists belongs
to the TWF user, not a selected broker. It persists independently of Dhan/TapTide
availability. Membership is resolved server-side and duplicates are both checked in
serialized transactions and constrained in the database. Archive is reversible.

The `/watchlists` route and secure same-origin proxy are enabled. There is no new
execution endpoint. Short database transactions precede/follow provider I/O.

## E–G. Navigator, table and instrument panel

Implemented multiple lists, search, create, rename/description, favorite, Trash and
restore. The central table supports canonical Equity/Index/Future/Option rows, dynamic
type chips, search, LTP/change/volume filters, column visibility, type grouping,
pagination and bulk remove/move/copy. Stable membership order survives display filters.

Quote refresh batches a list and preserves rows on provider failures. Sparklines use
received quote observations. The detail panel includes Overview/Chart/Option Chain/
News, bounded Dhan periods and unavailable fields. Daily charts lazily populate RSI,
trend and mean daily volume. No synthetic replacement data enters the production path.
The native detail modal replaces the desktop inspector on narrower screens.

## H. Quick Trade / Broker integration

Connected, trading-eligible broker accounts are displayed explicitly. One eligible
account is the visible default; multiple accounts require selection. Equity resolution
uses exact native symbols/exchanges; derivatives use the Dhan catalog underlying
identity plus expiry/right/strike and exchange. Ambiguous mappings fail closed.
Indices cannot be directly traded.

Buy/Sell opens the existing Broker V2 ticket with exact broker instrument, side,
quantity/lots and order type. Existing capability, Preview, OrderIntent, confirmation
and reconciliation controls remain. Browser validation reached Preview with quantity
2 and asserted no submission request from Watchlists. Existing Broker V2 browser
regressions also passed with the test-only transport.

## I–J. CSV, activity and notes

Import accepts up to 100 canonical-symbol rows and reports added, duplicate and
unresolved rows. Export emits canonical symbol, exchange, instrument type and trading
symbol without credentials. Recent activity records collection changes, not market
polling. Notes are owner-scoped and bounded. Bulk transfers preserve source metadata
and stable insertion order at the destination.

## K–L. Universe snapshots and inbound contracts

`UniverseSnapshot` freezes list ID/revision/capture time and canonical instrument
values. A future scanner must persist it in its run. Later list edits do not mutate
that returned snapshot. `POST /{id}/items` accepts canonical IDs plus optional
scanner/discovery run/candidate provenance. No Scanner/Discovery state is copied;
no Watchlist-side pull buttons or Scanner/Discovery send UI were added.

## M. Responsive behavior and accessibility

Chromium validation covers 390, 768, 1024, 1440, 1920 and 2560 pixels. Every width
passed collection CRUD, multi-list copy, filters, detail/chart, CSV, notes, reload,
archive/restore and broker-preview handoff. The tests check page overflow. Dialogs
provide an explicit Tab/Shift-Tab loop, Escape handling and focus restoration.
Controls have accessible names; trend uses text rather than color alone.

Existing shell keyboard/mobile tests passed. This is focused functional and visual
accessibility validation, not a comprehensive assistive-technology certification.

## N. Exact files changed by this task

The list below includes new files and integrations changed for Watchlists. Other
already-dirty shell files shown by `git status` belong to the pre-existing shell task.
Shared README/shell/test-harness files retain their earlier changes.

```text
README.md
apps/api/alembic/env.py
apps/api/alembic/versions/0017_watchlists.py
apps/api/src/twf/api/watchlists.py
apps/api/src/twf/infrastructure/watchlists.py
apps/api/src/twf/main.py
apps/api/src/twf/watchlists/__init__.py
apps/api/src/twf/watchlists/catalog.py
apps/api/src/twf/watchlists/contracts.py
apps/api/src/twf/watchlists/market.py
apps/api/src/twf/watchlists/service.py
apps/api/tests/test_backend_shell.py
apps/api/tests/test_database_foundation.py
apps/api/tests/test_foundation.py
apps/api/tests/test_watchlists.py
apps/web/src/app/(protected)/watchlists/page.tsx
apps/web/src/app/api/v1/watchlists/[[...path]]/route.ts
apps/web/src/app/globals.css
apps/web/src/components/brokers/order-ticket.tsx
apps/web/src/components/shell/app-shell.tsx
apps/web/src/components/shell/navigation.ts
apps/web/src/components/watchlists/dialog.tsx
apps/web/src/components/watchlists/market-chart.tsx
apps/web/src/components/watchlists/watchlists-workspace.tsx
apps/web/src/lib/watchlists.ts
apps/web/src/styles/watchlists.css
apps/web/tests/browser/auth-test-server.mjs
apps/web/tests/browser/service_fixture_api.py
apps/web/tests/browser/watchlists.spec.ts
apps/web/tests/watchlists.test.tsx
apps/web/tests/watchlists-proxy.test.tsx
docs/TWF_DETAILED_ROADMAP.md
docs/TWF_DOCUMENTATION_INDEX.md
docs/TWF_WATCHLIST_ARCHITECTURE.md
docs/TWF_WATCHLIST_IMPLEMENTATION_REPORT.md
docs/evidence/watchlists/1440-light-detail.png
docs/evidence/watchlists/1920-light-detail.png
docs/evidence/watchlists/390-light-list.png
docs/evidence/watchlists/390-light-detail.png
docs/evidence/watchlists/1440-dark-detail.png
docs/evidence/watchlists/390-dark-list.png
docs/evidence/watchlists/390-dark-detail.png
```

## O. Migrations

Added `0017_watchlists`. The local development SQLite database was upgraded to this
head without changing existing broker/discovery records. Fresh and existing-layout
PostgreSQL 16 and disposable SQLite databases passed upgrade/downgrade/upgrade,
Alembic metadata comparison, existing-user preservation and concurrent duplicate adds.
Four concurrent callers added five unique items once and reported 15 duplicates.

An existing PostgreSQL incompatibility in the 33-character revision 0016 ID was fixed
by widening migration metadata to 128 characters, preserving published IDs. Validation
also exercised an existing 32-character column and executed generated offline SQL
against a fresh PostgreSQL database successfully. No existing application database
was downgraded. The disposable test container was removed after validation.

## P. Tests and checks

| Check                                                                                | Result                                                                               |
| ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| Full backend `pytest -q`                                                             | **984 passed**, 234.48 seconds                                                       |
| Final focused Watchlists + migration tests after exact derivative-mapping refinement | **26 passed**; includes 9 Watchlists tests                                           |
| Frontend unit tests                                                                  | **169 passed**, 19 files                                                             |
| Shell + Watchlists browser suite, six Chromium widths                                | **42 passed**                                                                        |
| Final expanded Watchlists browser suite, six widths                                  | **6 passed**; multi-list copy, keyboard focus and repeated-period selection included |
| Broker V2 + Discovery browser regressions at 390/1440                                | **6 passed**                                                                         |
| TypeScript, ESLint, Prettier, production build                                       | PASS                                                                                 |
| Ruff and Python formatting                                                           | PASS, 145 files formatted                                                            |
| Focused strict mypy, Watchlists source/API/tests                                     | PASS, 7 files                                                                        |
| Full strict mypy                                                                     | **2 existing failures**, below                                                       |
| Python compilation / OpenAPI construction                                            | PASS; 74 OpenAPI paths                                                               |
| `pip check` / offline backend wheel                                                  | PASS                                                                                 |
| SQLite and PostgreSQL migration/data/concurrency probes                              | PASS                                                                                 |
| Executable offline PostgreSQL migration SQL                                          | PASS                                                                                 |
| Documentation links / formatting / `git diff --check`                                | PASS                                                                                 |

The full strict-mypy failures are outside this task and remain unchanged:
`tests/test_discovery_product.py:1321` passes a test double that does not implement
the full `MarketDataProvider` protocol; `tests/test_dhan_credentials.py:126` returns
`Any` from a typed helper. Full typing is **not claimed clean**.

Browser market prices/history use explicit test overlays; collections, accounts,
canonical mapping and preview go through the real API/test database. Browser
screenshots prove layout and workflow, not live quote availability. No production
fixture prices or demo watchlists were seeded.

## Q. Live validation

Created the requested **My Core** list in the existing owner's development database:
`50546d15-c90d-40f5-ad3e-7065f38b1a37`.

| Symbol   | Canonical Dhan native identity | Result    |
| -------- | ------------------------------ | --------- |
| RELIANCE | `NSE_EQ:2885`                  | Persisted |
| INFY     | `NSE_EQ:1594`                  | Persisted |
| HDFCBANK | `NSE_EQ:1333`                  | Persisted |
| NIFTY    | `IDX_I:13`                     | Persisted |

Four additions, zero duplicates, four exported CSV rows. Exactly one bounded quote
batch and one RELIANCE daily-chart request were attempted. Both returned
`AUTH_REQUIRED`, despite saved Dhan state READY/generation 2. No retry loop was run.
Zerodha Primary's stored state was connected/generation 17, but its effective public
state is **reauth_required**. Live broker preview was therefore not attempted.
No secrets were printed, no credential configuration was changed, and no live order
was placed. Live quote/chart/preview acceptance remains blocked on reauthorization.

To finish: update/test Dhan credentials in Settings → Integrations, reconnect Zerodha
in Brokers, then open Watchlists → My Core. Refresh quotes, inspect RELIANCE and open
Buy → Preview. Stop before Confirm. Automated behavior passes; live credentials must
be valid for those provider-dependent checks.

## R. Screenshot evidence

The captured account and market overlays are test-only. The 1440 light image was
compared with the supplied reference for the three-column hierarchy, compact controls,
table, right inspector, Quick Trade and activity/notes. These are implementation
screenshots, not AI-generated mockups.

- [1440 light, selected instrument](evidence/watchlists/1440-light-detail.png)
- [1920 light, selected instrument](evidence/watchlists/1920-light-detail.png)
- [390 light, list](evidence/watchlists/390-light-list.png)
- [390 light, selected instrument](evidence/watchlists/390-light-detail.png)
- [1440 dark](evidence/watchlists/1440-dark-detail.png)
- [390 dark, list](evidence/watchlists/390-dark-list.png)
- [390 dark, detail](evidence/watchlists/390-dark-detail.png)

## S. Deliberate deviations and limits

- 15-second refresh minimum, default off, rather than the illustrative 5 seconds.
- No fabricated quote, RSI, trend, sparkline or fundamental values. Indicators load
  only with sufficient daily history. PE/market cap/52-week ranges remain unavailable.
- Option Chain is a visible, truthful future-capability placeholder.
- TapTide provides a normalized bounded market headline/corporate-event summary, not
  a comprehensive symbol-news terminal; provider absence is harmless to Watchlists.
- Broker execution stays inside the existing staged ticket, not a one-click trade.
  Unsupported/ambiguous mappings and indices cannot bypass it.
- Dates/rows/chart levels reflect actual data or explicitly isolated test fixtures,
  rather than copying reference screenshot values.
- PostgreSQL version-column widening was necessary to validate the existing migration
  chain; it does not rename revisions or alter scanner/broker behavior.
- Live Dhan quote/chart and broker-preview checks remain pending renewed credentials.

## T. Required scorecard

PASS below means implemented and covered by the stated automated/visual checks.
It does **not** claim successful live quote/chart/preview reads while credentials are
expired; the live limitation in Q remains outstanding.

```text
WATCHLIST_DOMAIN_IMPLEMENTED = PASS
MULTIPLE_WATCHLISTS = PASS
OWNER_ISOLATION = PASS
EQUITY_ITEMS = PASS
INDEX_ITEMS = PASS
FUTURE_ITEMS = PASS
OPTION_ITEMS = PASS
ADD_SYMBOLS = PASS
REMOVE_ITEMS = PASS
DUPLICATE_PREVENTION = PASS
WATCHLIST_SEARCH_FILTER = PASS
TYPE_CHIPS = PASS
QUOTE_REFRESH = PASS
SPARKLINES = PASS
INSTRUMENT_DETAIL_PANEL = PASS
QUICK_TRADE_UI = PASS
BROKER_SELECTION = PASS
BROKER_V2_PREVIEW_REUSED = PASS
NO_EXECUTION_BYPASS = PASS
CSV_IMPORT = PASS
CSV_EXPORT = PASS
RECENT_ACTIVITY = PASS
NOTES = PASS
WATCHLIST_UNIVERSE_SOURCE_READY = PASS
SCANNER_TO_WATCHLIST_API_READY = PASS
DISCOVERY_TO_WATCHLIST_API_READY = PASS
NO_ADD_FROM_SCANNER_BUTTON_IN_WATCHLIST = PASS
NO_ADD_FROM_DISCOVERY_BUTTON_IN_WATCHLIST = PASS
RESPONSIVE_VALIDATION = PASS
ACCESSIBILITY_VALIDATION = PASS
BROKER_REGRESSION_FREE = PASS
SCANNER_REGRESSION_FREE = PASS
SHELL_REGRESSION_FREE = PASS
REFERENCE_VISUAL_MATCH = PASS
WATCHLIST_STATUS = READY_FOR_USER_VALIDATION
```

## U. Final status

Implementation and automated validation are complete. Watchlists is ready for user
validation at `/watchlists`; live provider-dependent validation requires renewed
Dhan and broker authorization. It is not accepted/frozen. No commit/tag/push.

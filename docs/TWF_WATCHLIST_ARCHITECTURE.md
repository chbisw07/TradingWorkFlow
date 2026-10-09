# TWF Watchlists — Architecture and Implementation

Status: **IMPLEMENTED / READY FOR USER VALIDATION**, 2026-10-06. Not accepted or frozen.

The approved Watchlists reference is the visual target. This is a TWF-owned
collection workspace at `/watchlists`, independent of broker watchlists and of
Scan & Discover candidate lifecycle. It uses the existing application shell.

## Built-in system universes and custom lists

Watchlists now has two explicit ownership classes. `USER` lists are the existing
owner-scoped, editable database collections. `SYSTEM` lists are application-owned
`SystemUniverseDefinition` records with deterministic stable IDs, display metadata,
source references and a read-only policy. System membership is resolved centrally;
it is not copied into every owner's database. This extension adds no database table
or migration.

The enabled built-ins are Nifty 500, Nifty Smallcap 250, Nifty Pharma, Nifty
Energy, Nifty Midcap 100, Nifty Bank, Nifty Metal and Nifty Realty. Their
constituent files come from the official NSE Archives static CSV resources,
with the corresponding NSE Indices page retained as human-readable provenance.
Runtime fetches read the published CSV resource directly and never scrape an HTML page. Downloads are bounded to 512 KiB
and 600 unique canonical symbols, use an eight-second timeout, reject redirects
and invalid schemas, and are single-flight per universe. Successful membership is
cached for 24 hours. If refresh fails, the last successful membership may be used
for at most seven days and is labeled `STALE`; without an eligible cache the read
fails truthfully. Source reference, receipt time, freshness and unresolved count are
returned to the UI.

Membership symbols are resolved through the current owner's Dhan security master
to exact NSE equity identities. Missing or ambiguous identities are omitted and the
list is marked `PARTIAL`; membership is never fabricated. F&O 100 and F&O 50 are
visible disabled TWF system-universe definitions marked **Definition pending**. No
accepted repository/provider eligibility source exists, so they have no invented
constituents and are not presented as official indices.

The navigator separates **My Watchlists** from **Built-in Watchlists**. Built-ins
show a lock/Built-in badge plus chips derived from actual member types. Official
index constituent lists contain equities and therefore show `EQ`, not `IDX`. The
cyan/blue family identifies `EQ` and `IDX`; magenta/purple identifies `FUT` and
`OPT`, with text retained for accessibility. Built-ins permit inspection, search,
charts, export, existing Broker V2 preview handoff, and copying selected/all members
to a custom list. Rename, description edits, direct add/remove/import, notes,
archive, Trash and permanent deletion return `READ_ONLY_SYSTEM_WATCHLIST` at the
API boundary. Copy is one bounded bulk request (maximum 500 selected identities or 600 for an all-constituent system copy), targets
custom lists only, preserves existing contents, reports duplicates, and records
optional source-list provenance; copied members become ordinary editable custom
items.

## Ownership and persistence

Migration `0017_watchlists` follows `0016_dhan_market_data_credentials` and adds:

| Table                | Purpose                                                                      |
| -------------------- | ---------------------------------------------------------------------------- |
| `watchlists`         | Owner, name, description, favorite, archived, revision, ordering, timestamps |
| `watchlist_items`    | Canonical instrument snapshot, source metadata, insertion order, added time  |
| `watchlist_notes`    | Bounded owner-scoped notes and creation time                                 |
| `watchlist_activity` | Collection actions; never quote refresh events                               |

Every public operation derives its owner from the authenticated session. Item,
notes, activity, export, market overlay and broker-resolution reads first check
ownership of the parent list. Parent-row updates serialize competing mutations;
transfers lock the two parents in stable ID order. A database unique constraint on
`(watchlist_id, instrument_id)` also prevents duplicate membership. Provider calls
run after authorization transactions have closed. No database lock spans I/O.

Bounds: 100 lists per owner including Trash, 600 items per list, 100 instruments per
add/import/transfer, 32 KiB CSV, 80-character names, 240-character descriptions,
200 notes per list, 2,000 characters per note. Detail reads return the latest 50
notes and 30 activity events. Names need not be unique. Favorites precede stable
list ordering. Display filtering/grouping does not rewrite item order.

Trash is reversible archive, not hard deletion. Archived lists preserve membership,
notes and export but reject item mutations and universe/market operations. Migration
downgrade removes the four Watchlists tables, including their data; it is an operator
schema rollback, not a user Trash operation. Other domain tables are preserved.

PostgreSQL migration validation exposed a pre-existing issue: the published `0016`
revision identifier exceeds Alembic's default `VARCHAR(32)`. The migration environment
now uses a 128-character version column for new PostgreSQL databases and widens
existing columns. Revision IDs remain unchanged. Online and offline SQL are supported.

## Canonical identity

The searchable catalog reuses the existing cached Dhan scrip master. It filters
supported raw rows before building immutable `InstrumentIdentity` objects. Exact
symbols rank before prefixes/contains matches. NSE and BSE equities, indices,
futures and options retain exchange, segment, Dhan security ID, canonical UUID,
expiry, right and strike where applicable. Expired or incomplete derivative
contracts are excluded from new additions. Existing members are never silently
removed when provider data becomes unavailable.

No unresolved free text is stored. Add/import re-resolve submitted identifiers in
the server catalog. CSV requires `canonical_symbol`, for example `NSE:RELIANCE`.
Ambiguous/unrecognized entries are reported by row; duplicates are counted and
no-op. Export includes canonical symbol, exchange, type and trading symbol and
neutralizes spreadsheet-formula prefixes.

## Market overlays and chart rendering

Quotes are separate from durable membership. One Dhan batch request covers the
selected list. An application-owned cache is bounded to 128 entries, keyed by
owner, credential generation and exact instrument IDs, with a 15-second TTL.
In-flight calls are serialized within that application process. There is no new
cross-worker global rate-limit coordinator; existing Dhan transport limits still
apply. Cache errors are typed, and no synthetic provider is a fallback.

Auto-refresh defaults off, with 15/30/60-second intervals and hidden-tab suppression.
The reference's illustrative 5-second default is deliberately not used. Visible rows
hydrate serially from one cached 260-session normalized completed-daily history on
load, independently of selection. That same bounded series supplies RSI, trend,
ATR(14), 52-week metrics and the final 22 bars used by each one-month sparkline.
No off-page row history is eagerly fetched. Missing data remains a compact dash.

A shared history cache keys owner, credential generation, canonical instrument,
interval and count. It retains at most 256 results for five minutes (failures for
30 seconds). One historical provider request runs at a time per API process, with
at least one second between starts. A rate-limit response pauses cold reads for
30 seconds; lock-wait plus provider I/O is bounded to 12 seconds. No DB lock is
held. Concurrent identical row/detail reads recheck the cache after admission.
The browser deduplicates in-flight requests and caches up to 100 results using the
same TTLs. Its row loader stops scheduling obsolete pages; already started bounded
reads may finish. There is no cross-worker global history-rate coordinator.

The selected-instrument chart lazily reads normalized Dhan OHLCV: 1D uses up to 75
completed 5-minute bars; daily periods reuse the cached 260-session acquisition and
display its final 5/22/66/252 bars for 1W/1M/3M/1Y.
These are bounded trading-bar windows, not exact calendar-window promises. Provider
availability and derivative history limitations remain visible. Nothing requests
TradingView data. The `MarketChart` renderer takes only normalized bars and serves
both the compact sparkline and detail chart; it is independent of provider schema.
The existing scan Evidence Chart remains unchanged.

Daily history of at least 20 bars supplies RSI(14), close-versus-SMA(20) trend,
mean volume over the last 20 completed daily bars and canonical Wilder ATR(14).
ATR percent is `ATR(14) / latest completed close * 100`; live LTP is never its
denominator. The completed-session 52-week range uses at most 252 bars and requires
at least 200. Shorter histories expose dashes rather than relabelling a short window.
Distances use the current Dhan LTP against those completed-session extremes and may
be negative above the prior high or below the prior low. Existing pure indicator
functions are reused; scanner thresholds/conditions are unchanged. Table tooltips
state the basis and source bar time. Selecting 1M detail reuses the row series;
other detail windows cannot overwrite the row's indicator/sparkline basis.

Dhan `ohlc.close` is the day's close, not previous session close. A nonzero absolute
`net_change` can establish previous close as LTP minus change. The live closing
snapshots tested on October 6 reset `net_change` to zero, so zero alone is ambiguous.
Watchlists then compares LTP against the latest normalized daily bar strictly before
the quote's trading date in Asia/Kolkata. Source time is required; bars older than
seven days are rejected as an unavailable baseline. The quote day's own close and
open are never substituted. A normalized percentage takes priority if supplied;
missing price/baseline yields a dash, and verified unchanged price yields 0.00%.
This changes quote normalization, not Scanner OHLCV acquisition or indicators.

The table labels its session return **1D %** and its fixed 22-bar daily sparkline
**Quick Chart (1M)**. The row basis never follows selected-detail period changes.
Detail 1D compares the latest quote with previous session close. Other detail
periods compare the first and last valid closes of the displayed 5/22/66/252-bar
window; the label, actual India-session start/end dates and prices change together.
The quote above the chart remains LTP, while the explicitly labeled longer-period
return ends at the last completed daily close, which can precede that quote.
Missing/invalid history gives a dash. No calendar sessions are fabricated.

Open/high/low/previous close/volume remain normalized Dhan quote/history values.
A separate **Reference / fundamentals** group uses a typed `ReferenceSnapshot`
from the existing TapTide MCP connection's `get_stock_quote` capability. It maps
market cap to INR, PE, and direct 52W high/low after exact NSE company-symbol
verification. TapTide's market-cap value is INR crore, corroborated by its published
[market-cap leaderboard](https://tapetide.com/score/leaderboard?sort=market_cap)
and live profile share/price metadata; normalization converts units, not fundamentals.
Missing individual values remain null. Index, derivative and BSE references are
unsupported by this bounded company-symbol integration and remain unavailable.
No historical 52W fallback is implemented; incomplete history is never annualized.

Reference metrics retain provider, tool, source `updated_at`, received time and
freshness (source unavailable, future, older than seven days, or current within
that reference TTL). A quote update timestamp does not establish independent
filing dates for PE or market cap. Raw provider payloads never enter the UI DTO.
The cache is bounded to 128 owner/connection/generation/instrument entries per API
process, with 15-minute successful/partial/not-available TTL and 60-second failure
TTL. A local lock deduplicates concurrent reads and total wait/I/O is bounded to
25 seconds; no DB transaction spans MCP I/O. Durable MCP admission and completion
receipts remain owned by the existing connection manager. The browser caches up
to 50 selected-symbol results for the same TTL. No distributed cache or global
rate-coordination guarantee is claimed. Disconnect/generation changes fence new
backend reads; already displayed snapshots keep their source/received timestamps.
Option Chain explicitly says “Option chain coming later.” News uses only existing
bounded TapTide market-news and selected-symbol corporate-event tools, with normalized
claims, scope and freshness. Market-wide headlines are labeled as market-wide;
TapTide absence never prevents list management or Dhan reads.

## Broker execution boundary

The user selects an eligible connected broker. A sole eligible account is selected
and named visibly. Index rows cannot execute directly. Buy/Sell first resolve a
unique executable contract from that account's current broker catalog using exact
symbol/exchange for equities and catalog-derived underlying identity plus exact
exchange, kind, expiry and strike for derivatives. No fuzzy first-match routing
is allowed; ambiguous/unavailable native mappings fail closed and direct the user
to Brokers. The resolved broker reference and token are passed to the existing
Broker V2 `OrderTicket`, including side, quantity/lots and supported order type.

There is no Watchlists submit endpoint. Broker capability checks, Preview,
OrderIntent, explicit confirmation, idempotency and reconciliation stay in the
existing Broker V2 path. Preview is not an authorization to submit an order.
The existing ticket's launch contract now accepts optional quantity/order-type
prefill; prior launch defaults remain unchanged.

## API surface

All routes are under `/api/v1/watchlists` and use existing session and mutation-origin
protection. The Next.js proxy forwards only the selected session cookie, origin
and content type, allowlists paths/methods, bounds request size, and disables caching.

| Method      | Path                                            | Purpose                                                 |
| ----------- | ----------------------------------------------- | ------------------------------------------------------- |
| GET / POST  | root                                            | List / create                                           |
| GET         | `/instruments`                                  | Bounded catalog search                                  |
| GET / PATCH | `/{id}`                                         | Detail / rename, description, favorite, archive/restore |
| POST        | `/{id}/items`                                   | Canonical IDs and optional source metadata; custom only |
| DELETE      | `/{id}/items/{instrument_id}`                   | Remove one                                              |
| POST        | `/{id}/remove`, `/{id}/transfer`                | Bounded bulk remove or atomic move/copy                 |
| POST        | `/{id}/copy`                                    | Copy selected/all system members into a custom list     |
| POST        | `/{id}/notes`, `/{id}/import`                   | Note / CSV import with summary; custom only             |
| GET         | `/{id}/export`, `/{id}/universe`                | CSV / immutable universe snapshot                       |
| GET         | `/{id}/quotes`                                  | Batched market overlay                                  |
| GET         | `/{id}/items/{instrument_id}/chart`             | Cached Dhan history and shared row/detail metrics       |
| GET         | `/{id}/items/{instrument_id}/reference`         | Optional normalized company reference metrics           |
| GET         | `/{id}/items/{instrument_id}/news`              | Optional bounded normalized intelligence                |
| GET         | `/{id}/items/{instrument_id}/broker-instrument` | Exact selected-account execution mapping                |

## Scanner and Discovery contracts

`POST /{id}/items` accepts `instrument_ids` and `source_metadata` with `source`
(`manual`, `import`, `scanner`, `discovery`, `built_in_watchlist`), optional `run_id`,
`candidate_id`, and source-system-list identity. These references are collection
provenance, not imported candidate state. Custom-list copy/move preserves metadata.

Scanner V2 consumes custom and system lists through the same provider-neutral
`WATCHLIST` universe source. Disabled definitions are excluded. Because Scanner V2
has a 20-instrument execution bound, a large built-in opens with a visible first-20
selection that the user can refine. Execution resolves current membership and
persists the complete `UniverseSnapshot` (name, ownership class, system code,
revision, source reference/time and immutable canonical identities) with the run;
the selected IDs in the scan configuration identify the exact evaluated subset.
Future constituent refreshes cannot rewrite historical run truth. Scanner result
handoff accepts custom destinations only, and the API independently rejects a
system target. Discovery's existing inbound provenance remains unchanged.

## Selected-instrument production presentation

Overview is the sole embedded chart view; the redundant Chart tab is removed.
The reusable normalized `MarketChart` remains available for a future richer chart
workspace. Overview / Option Chain / News use an accessible tablist with arrow,
Home/End navigation, selected-state semantics and an associated panel. News
semantics, the Option Chain placeholder and Quick Trade behavior are unchanged.

Chart/timeframes remain in Overview. LTP and period-aware return remain visible.
Detailed return comparison dates/prices and all Overview provenance now live in a
collapsed native **Data details** disclosure. Keyboard Enter/Space expands it and
`aria-expanded` follows the native open state. The disclosure retains Dhan source
and receipt times, snapshot limitations, chart interval and TapTide provider/tool,
source/receipt times, freshness, availability and reference limitations. A quote
snapshot is not relabeled as a continuous live feed. News retains its existing
per-claim provenance because that view is outside this presentation refinement.

Selected-panel volume/average volume format normalized counts as K/L/Cr with two
scaled decimal places; counts below 1,000 remain ordinary integers. `market_cap_inr`
is already normalized to INR: the presentation formatter divides by 10^7 for Cr
or 10^12 for L Cr. No raw provider unit is accepted or converted twice. Reference
metrics are grouped as Fundamentals (Market Cap/PE) and Price reference (52W range).
PE stays a ratio. LTP/Open/High/Low/Prev Close/52W values share the existing Indian
grouping price formatter, with up to two fractional digits and no currency prefix;
Market Cap explicitly carries ₹. Missing values stay “—”. Raw numeric values and
all provider contracts/caches remain unchanged.

## UX and validation boundary

Desktop uses navigator, main table and selected-instrument panel. Below 1200px the
panel becomes a native modal; mobile uses a compact table and horizontal list selector.
Native dialogs provide focus containment, Escape handling and focus restoration.
Inputs and row actions have accessible labels, and missing values use explicit
unavailable text. Watchlists retains the shell's light/dark tokens and visible focus.

Validation, exact file inventory, screenshots, live restrictions and the requested
scorecard are recorded in [the implementation report](TWF_WATCHLIST_IMPLEMENTATION_REPORT.md).
Current live validation on October 6 at approximately 21:24–21:27 IST passed all
four My Core Dhan rows and all five detail periods. TapTide reference metrics were
available for the three equities; NIFTY reference metrics remained unavailable. The report's latest remediation section supersedes
its earlier expired-credential observations. No live broker order was attempted.

## Instrument metadata presentation — 2026-10-09

Custom and built-in Watchlists enrich rows from the same system-global
`InstrumentMetadataService` used by Scanner V2. Each detail response performs at
most one bounded bulk lookup after any provider I/O. Sector is visible by default;
stored Market Cap Category and readable INR Market Cap are also default-visible
table columns. Industry, stored TWF analytical tier,
and analytical context benchmark appear in the selected-instrument panel. Equity
lookups use exact exchange/symbol identity. Futures and options inherit metadata only
from an unambiguous canonical underlying and are labelled accordingly; indices and
unknown instruments remain unavailable. Stale last-known values are explicit. No
Watchlist request calls Yahoo, NSE, or the metadata harvester.

The Columns control also exposes ATR %, 52W High Distance and 52W Low Distance.
Column state is component-local, as it was before this extension; no saved preference
contract exists to migrate. At narrow widths the existing responsive table keeps
Symbol, Type, LTP, 1D % and Actions visible while lower-priority metrics remain
available in the selected-instrument detail. CSV export intentionally remains the
canonical membership/identity interchange format; it does not serialize transient
quotes, metadata snapshots or technical metrics.

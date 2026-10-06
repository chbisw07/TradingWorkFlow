# TWF Watchlists — Architecture and Implementation

Status: **IMPLEMENTED / READY FOR USER VALIDATION**, 2026-10-06. Not accepted or frozen.

The approved Watchlists reference is the visual target. This is a TWF-owned
collection workspace at `/watchlists`, independent of broker watchlists and of
Scan & Discover candidate lifecycle. It uses the existing application shell.

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

Bounds: 100 lists per owner including Trash, 500 items per list, 100 instruments per
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
hydrate serially from 22 normalized completed daily bars on load, independently
of selection. That same bounded series supplies RSI, trend and each sparkline.
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
completed 5-minute bars; 1W/1M/3M/1Y use up to 5/22/66/252 completed daily bars.
These are bounded trading-bar windows, not exact calendar-window promises. Provider
availability and derivative history limitations remain visible. Nothing requests
TradingView data. The `MarketChart` renderer takes only normalized bars and serves
both the compact sparkline and detail chart; it is independent of provider schema.
The existing scan Evidence Chart remains unchanged.

Daily history of at least 20 bars also supplies RSI(14), close-versus-SMA(20)
trend and mean volume over the last 20 completed daily bars. Existing pure indicator
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

Open/high/low/previous close/volume use normalized quotes. Market cap, PE and 52-week
extremes remain unavailable because the current quote contract does not supply them.
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
| POST        | `/{id}/items`                                   | Canonical IDs and optional source metadata              |
| DELETE      | `/{id}/items/{instrument_id}`                   | Remove one                                              |
| POST        | `/{id}/remove`, `/{id}/transfer`                | Bounded bulk remove or atomic move/copy                 |
| POST        | `/{id}/notes`, `/{id}/import`                   | Note / CSV import with summary                          |
| GET         | `/{id}/export`, `/{id}/universe`                | CSV / immutable universe snapshot                       |
| GET         | `/{id}/quotes`                                  | Batched market overlay                                  |
| GET         | `/{id}/items/{instrument_id}/chart`             | Cached Dhan history and shared row/detail metrics       |
| GET         | `/{id}/items/{instrument_id}/news`              | Optional bounded normalized intelligence                |
| GET         | `/{id}/items/{instrument_id}/broker-instrument` | Exact selected-account execution mapping                |

## Future Scanner and Discovery contracts

`POST /{id}/items` accepts `instrument_ids` and `source_metadata` with `source`
(`manual`, `import`, `scanner`, `discovery`), optional `run_id` and `candidate_id`.
These references are collection provenance, not imported candidate state. Copy/move
preserves the original metadata. Watchlists contains no “Add from Scanner” or
“Add from Discovery” controls and does not query those modules.

`WatchlistService.snapshot()` / `GET /{id}/universe` returns a frozen
`UniverseSnapshot` containing list ID, revision, capture time and resolved immutable
instrument identities. A future scanner caller must persist that snapshot in its
run, never reconstruct historical universe truth from the subsequently edited list.
No scanner send action or new scanner universe option is wired in this task.

## UX and validation boundary

Desktop uses navigator, main table and selected-instrument panel. Below 1200px the
panel becomes a native modal; mobile uses a compact table and horizontal list selector.
Native dialogs provide focus containment, Escape handling and focus restoration.
Inputs and row actions have accessible labels, and missing values use explicit
unavailable text. Watchlists retains the shell's light/dark tokens and visible focus.

Validation, exact file inventory, screenshots, live restrictions and the requested
scorecard are recorded in [the implementation report](TWF_WATCHLIST_IMPLEMENTATION_REPORT.md).
Current live validation on October 6 at approximately 20:31 IST passed all four
My Core Dhan rows after a hard reload. TapTide returned market news with partial
corporate-event availability. The report's latest remediation section supersedes
its earlier expired-credential observations. No live broker order was attempted.

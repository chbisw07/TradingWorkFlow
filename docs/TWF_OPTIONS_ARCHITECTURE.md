# TradingWorkFlow Options Architecture

Status: **O1 IMPLEMENTED / USER VALIDATION; O2 ACTIVE DEVELOPMENT**
Scope: provider-neutral option identity and governed Broker V2 single-leg execution  
Primary execution adapter: Zerodha NSE/NFO

## Purpose and authority

The Options program makes listed options first-class TWF instruments without creating a
second execution system. Broker V2 remains the only order authority:

```text
listed broker instrument master
  → provider-neutral OptionContract
  → exact broker mapping
  → existing Broker V2 preview
  → option, product, quantity and price validation
  → explicit user confirmation
  → existing one-attempt broker dispatch
  → existing order/position reconciliation
```

O1 supports one NSE/NFO option contract per manual order. It does not implement an
option-chain product, Derivatives Scanner, strategies, multi-leg orders, payoff graphs,
Greeks/IV analytics, option ranking, or automated order placement.

## Canonical option contract

`twf.options.OptionContract` is immutable and provider-neutral. Its structural identity is:

```text
exchange : underlying_symbol : expiry : exact_strike : CE|PE
```

The contract records exchange, segment, underlying symbol and type, expiry, exact decimal
strike, typed CE/PE, lot size, display symbol, tick size, currency, active state, and last
trading date. Freeze quantity and contract multiplier remain nullable because the current
Zerodha master does not always provide them.

`OptionType` uses `CE` and `PE` internally. `CALL` and `PUT` are accepted only as boundary
aliases. Broker symbols and tokens never form the canonical identity. Different expiries,
strikes, or option types therefore remain different contracts even if a provider display
name is ambiguous.

Underlying type can be `INDEX`, `EQUITY`, or `UNKNOWN`. O1 preserves a verified type when a
canonical source supplies it and otherwise remains `UNKNOWN`; it does not infer equity or
index identity from a broker trading-symbol string.

## Exact resolution and instrument-master strategy

O1 reuses Broker V2's bounded Zerodha instrument-master cache and dependent selector. The
picker queries only the relevant slice and follows:

```text
Options → underlying → listed expiry → CE/PE → listed numeric strike → exact contract
```

Expiries and strikes come from listed master rows. TWF does not synthesize calendars,
strike ladders, counterpart contracts, or broker symbols. The resolver compares the
master's structured exchange, underlying, expiry, strike, and type fields. An absent or
ambiguous match fails with `OPTION_CONTRACT_NOT_FOUND` or
`BROKER_INSTRUMENT_UNAVAILABLE`.

`BrokerOptionMapping` is deliberately separate from `OptionContract`. It holds the
Zerodha execution exchange, trading symbol, native token/reference, lot and tick size,
resolution time, and optional master version. A Dhan identifier is never used as a Zerodha
execution identifier. Dhan remains the market-data authority for Scanner and Watchlists;
it is not the O1 order-mapping source.

The current cache refreshes at most daily through the existing Broker V2 pattern. Every
preview and confirmation re-resolves the exact identity and rechecks expiry in
Asia/Kolkata. Same-day exchange availability and RMS remain broker truth; O1 does not
invent separate session rules or promise acceptance after market close.

## Broker capabilities and supported matrix

The generic Broker V2 capability response now states equity, futures, and options support,
option BUY/SELL support, and intraday/overnight product support. Capability flags are
adapter truth, not assumptions made by the UI.

The implemented real execution adapter is Zerodha:

| Instrument     | Products  | MARKET  | LIMIT   | SL  |
| -------------- | --------- | ------- | ------- | --- |
| NSE/BSE equity | CNC, MIS  | No      | DAY/IOC | DAY |
| NFO future     | NRML, MIS | No      | DAY/IOC | DAY |
| NFO CE/PE      | NRML, MIS | DAY/IOC | DAY/IOC | No  |

Other broker execution adapters are not implemented in O1 and must not claim option
support. Unsupported products and order types fail during preview before any broker write.

## Quantity, expiry, strike, and price semantics

Options use lot entry in the UI. The server computes and validates:

```text
quantity = lots × current broker-master lot_size
```

Quantity and lots must be positive integers and match exactly. O1 never rounds quantity or
strike. A known freeze quantity is enforced. Expired, malformed, unmapped, missing-lot,
missing-tick, invalid-product, unsupported-order-type, and non-tick-aligned LIMIT requests
fail closed.

MARKET has no submitted price. Its preview may use an independently fetched exact-contract
LTP for an indicative value, but that quote is never converted into a limit price. LIMIT
requires a positive price aligned to the contract tick.

The API accepts one `OrderDraft` and forbids extra fields, so a multi-leg request cannot be
smuggled into the single-leg contract. Future multi-leg work requires a separate governed
design rather than repeated O1 submissions presented as atomic.

## Preview, risk, and confirmation

The existing Broker V2 sequence remains mandatory:

```text
select exact contract → ticket → preview → explicit Confirm Buy/Sell → result
```

The option preview identifies the instrument as Option and shows the underlying, expiry,
strike/type, lots, lot size, total quantity, product, order type, price or Market,
reference option LTP, indicative order value, optional premium outlay, optional broker
margin estimate, available cash, and warnings.

For BUY, `premium_outlay` is an indicative `effective price × quantity`; it is not labelled
as guaranteed execution cost or final realized maximum loss. For SELL, O1 does not infer
whether the user is closing a long or opening a short. It preserves the side and displays:

> Short option positions may have substantial or theoretically unbounded risk, depending
> on the contract and underlying.

Zerodha's existing margin endpoint is reused. A returned estimate is shown as available.
A missing or failed optional margin/quote read is displayed as unavailable and does not
invent a value. Broker RMS, funds, permissions, market state, and exchange rules remain
final authorities.

No UI control dispatches directly. Preview persistence does not authorize execution;
confirmation is a distinct user action.

## Persistence, security, and reconciliation

O1 extends the existing `OrderIntent` JSON contracts; it introduces no parallel order
table or migration. The persisted instrument includes the canonical contract ID,
underlying, expiry, strike, CE/PE, lot/tick metadata, Zerodha symbol/reference and native
token. The order record preserves side, lots/quantity, product, type, optional price,
status, and broker order ID. Secrets are not present in these records or responses.

Preview and confirmation retain Broker V2's owner/session checks, current connection
generation, five-minute preview expiry, immutable terms, durable pre-dispatch claim,
single provider write, no transport retry, sanitized failures, and reconciliation by
broker ID or exact tag plus exact terms. A frontend retry cannot create a second provider
order from the same intent.

Broker-discovered option positions are read through the existing position endpoint. When
current master metadata is available, their structural option identity is reconstructed.
They are explicitly `BROKER_EXTERNAL` and `managed=false`; O1 never silently adopts or
manages them. Historical positions remain visible even if current master metadata is no
longer complete.

## Broker workspace and Watchlist interoperability

The existing compact Broker V2 selector already provides Equity, Futures, and Options.
Options use dependent underlying, expiry, CE/PE, and strike controls, then show the exact
resolved contract before ticket entry. The same responsive modal, Buy/Sell controls,
preview, confirmation, result, recent intents, and Orders truth are reused. No option-chain
surface is added.

Watchlist `OPT` rows already resolve their canonical derivative identity against the
current Zerodha execution master before opening the same Broker V2 `OrderTicket`. Missing
mapping remains unavailable. Watchlists neither place nor authorize orders.

## Validation boundary

Automated O1 validation uses only deterministic broker transports. It covers index/equity
CE/PE identity, exact resolver failures, expiry and lot rejection, absent broker mapping,
capability denial, CE/PE BUY/SELL across MARKET/LIMIT, optional quote/margin behavior,
persistence, broker rejection/timeout, duplicate confirmation, generation fencing,
reconciliation, external positions, frontend preview, and responsive Broker journeys.

Live contract resolution and live Zerodha preview are separate user-authorized checks. O1
does not place a live order during automated validation.

## Program roadmap

This roadmap describes intent and does not commit later implementation details:

1. **O1 — Domain + Broker single-leg trading:** canonical contracts, exact mapping, Broker
   V2 preview/confirmation, MARKET/LIMIT options, and reconciliation.
2. **O2 — Canonical option-chain service:** bounded chain reads and contract discovery.
3. **O3 — Option Chain workspace:** O2 market data, responsive chain view and exact Broker V2 preview handoff.
4. **O4 — Derivatives Scanner V1:** deterministic derivative scan contracts and engine.
5. **O5 — Explainable option ranking:** evidence-led deterministic ranking.
6. **O6 — Option Watchlists:** deeper option-specific list workflows.
7. **O7 — Options Analytics:** Greeks, IV, liquidity, and risk views with explicit sources.
8. **O8 — Strategy Builder:** user-authored multi-leg strategy modelling.
9. **O9 — Advanced execution / multi-leg governance:** atomicity, margin, and execution
   controls designed before implementation.
10. **O10 — Discovery / optional LLM synthesis:** evidence-bound interpretation without
    granting trading authority.


## O2 — Canonical option chain service

O2 adds one read-only `OptionChainService` for future Broker, Scanner, Analytics,
Watchlist, Strategy Builder and Discovery consumers. It reuses the O1 `OptionContract`
and structural identity; it does not create another execution path. O3 supplies the
chain workspace described below; Derivatives Scanner remains planned. Shared frontend types live in
`apps/web/src/lib/options.ts` and reuse the O1 contract type. The existing Broker picker
continues to discover directly executable broker contracts, so Dhan outages cannot
prevent manual Broker V2 contract discovery.

### Public API and broker handoff

Authenticated API endpoints:

- `GET /api/v1/options/underlyings?query=NIF&limit=50` (maximum 100 names).
- `GET /api/v1/options/expiries?underlying=NIFTY` (active listed expiry dates).
- `GET /api/v1/options/chain?underlying=NIFTY&expiry=YYYY-MM-DD&around_atm=10`.
- Optional chain filters: `strike_min`, `strike_max`, `side=CE|PE`.
- `POST /api/v1/brokers/accounts/{account_id}/order-entry/option-preview` accepts
  `{contract: {exchange, underlying_symbol, expiry, strike, option_type}, order:
  {side, product, order_type, quantity, lots, price, trigger_price, validity}}`.

The handoff accepts canonical identity, resolves it against the current owned broker
catalog, and passes the exact native mapping into the existing `OrderService.preview`.
Callers do not supply Dhan tokens, guessed broker symbols, or execution IDs. Broker V2
still requires a separate explicit confirmation of the resulting durable preview.
Missing or ambiguous mappings reject; there is no fuzzy search. The chain endpoint is
read-only and does not change provider health or broker connection state.

### Models and derivations

`OptionChainRequest`, `OptionChainSnapshot`, `OptionChainRow`, `OptionLegSnapshot`,
`OptionMarketSnapshot`, and `OptionChainProvenance` provide the shared API contract.
Decimals serialize as strings. Provider response keys and native security IDs remain
inside the adapter. Each leg contains the original O1 canonical option contract.

Rows are sorted by exact numeric strike. Only listed CE/PE legs exist; absent legs are
null. ATM is the nearest actual strike, with the lower strike winning a tie. CE below
spot is ITM and above spot OTM; PE reverses that rule. Both sides at the selected ATM
strike are ATM. Distance is signed `strike - spot`; percent divides by positive spot.
DTE is integer calendar days using the Asia/Kolkata date, including zero on expiry day.
Expired and unavailable expiry requests reject. Without spot, ATM, moneyness and distance
are null; the first bounded ascending slice remains available with `spot_unavailable`.

Spread uses positive non-crossed bid/ask: ask minus bid, divided by their midpoint for
percentage. Zero bid, missing ask and crossed quotes produce null spread. OI remains
provider contract quantity, never divided by lot size or inferred from volume. OI change
uses a direct provider value if supplied, otherwise current minus previous OI. IV is in
percentage points; no IV or Greeks are calculated by TWF. Provider zero IV is unavailable,
and associated placeholder Greeks are omitted. Unsupported fields remain null. Missing
required quote fields produce partial leg availability while valid fields are retained.

### Dhan source boundary and capability evidence

Dhan provides the authoritative market source. The public detailed master supplies
structured underlying, expiry, strike, option type, lot and tick metadata. NSE derivatives
map to O1 exchange `NFO` and segment `NFO-OPT`. Master tick sizes are converted from paise
to INR. Underlying spot lookup reuses the existing Dhan resolver; derivative master
underlying IDs are not assumed to be the spot endpoint's IDs. Quote legs are accepted
only when both structural identity and the master security ID agree.

For index options, the Dhan adapter resolves the exact NSE `INDEX`/`IDX_I`
underlying through the same compact-master resolver used by the global market
summary. It reads `QuoteSnapshot.last_price` through the shared owner/generation
Dhan quote cache (`/marketfeed/quote`) once per chain snapshot. That canonical
quote is the sole index spot for O2, ATM and moneyness. The option-chain payload's
`last_price` is only a diagnostic comparison: a discrepancy greater than 1% adds
`underlying_spot_mismatch`, while the canonical quote still wins. If the quote is
unavailable, O2 preserves listed option quotes but leaves spot, ATM and dependent
moneyness unavailable with `underlying_spot_unavailable`/`spot_unavailable`.
An incorrect instrument type, NSE segment, native segment, or non-exact symbol
is rejected before an option-chain or quote call; neither futures nor similarly
named indices can supply spot. Explicit aliases use the existing Dhan benchmark
resolver. Equity options retain their previous option-chain `last_price` behavior.
The backend O2 snapshot remains the only source for O3 spot, ATM and moneyness;
no Dhan security ID enters the neutral contract or frontend identity.

On 10 October 2026 the public Dhan detailed master listed these index-option
families. The compact master supplied exact NSE `I`/`INDEX` rows as shown. The
five resolvable families are deterministic adapter-tested; authenticated live
quote and chain support require a signed-in Dhan READY session and were not
validated in this remediation.

| Option underlying | Compact-master index | Segment | Quote support | Chain support | Spot resolution |
| --- | --- | --- | --- | --- | --- |
| NIFTY | NIFTY | IDX_I | canonical path; live untested | listed; live untested | exact index |
| BANKNIFTY | BANKNIFTY | IDX_I | canonical path; live untested | listed; live untested | exact index |
| FINNIFTY | FINNIFTY | IDX_I | canonical path; live untested | listed; live untested | exact index |
| MIDCPNIFTY | MIDCPNIFTY | IDX_I | canonical path; live untested | listed; live untested | exact index |
| NIFTYNXT50 | NIFTYNXT50 | IDX_I | canonical path; live untested | listed; live untested | exact index |
| NIFTYFPI | no exact index row | unavailable | unresolved; no substitution | listed, but chain call blocked | unavailable |

The deterministic reproduction used canonical NIFTY 22,520 and chain payload
23,122: O2 now selects listed ATM 22,500, not the strike nearest 23,122. A
BANKNIFTY fixture similarly uses canonical 48,040 despite a conflicting chain
payload of 49,050. The prior divergence began at the Dhan adapter's use of the
option-chain `data.last_price`; the nearest-listed-strike algorithm was already
correct and remains unchanged.

Primary provider contracts consulted:
[Dhan option-chain API](https://dhanhq.co/docs/v2/option-chain/) and
[Dhan instrument master](https://dhanhq.co/docs/v2/instruments/).

| Capability | Dhan O2 adapter | Zerodha existing O1 adapter |
| --- | --- | --- |
| Contracts | SUPPORTED; public master parsed live | SUPPORTED; existing broker master |
| Quotes | SUPPORTED; deterministic transport verified | PARTIAL; preview LTP, no O2 chain adapter |
| Bid/ask | SUPPORTED; deterministic transport verified | UNSUPPORTED by O2 adapter |
| Volume | SUPPORTED; deterministic transport verified | UNSUPPORTED by O2 adapter |
| OI | SUPPORTED; deterministic transport verified | UNSUPPORTED by O2 adapter |
| OI change | SUPPORTED; reliable previous OI required | UNSUPPORTED by O2 adapter |
| IV | PARTIAL; provider positive value only | UNSUPPORTED by O2 adapter |
| Greeks | PARTIAL; provider values with available IV | UNSUPPORTED by O2 adapter |

This matrix describes implemented adapter support, not proof of authenticated live quote
availability or a statement that the upstream Zerodha API lacks these capabilities.
On 10 October 2026 IST the Dhan public master parsed 83,657 active option contracts in
6.651 seconds including download. Nearest listed expiries were NIFTY 13 October (239
strikes, 478 legs, lot 65), BANKNIFTY 27 October (370 strikes, 740 legs, lot 30), and
HDFCBANK 27 October (55 strikes, 110 legs, lot 650). All had CE/PE and INR 0.05 ticks.
Authenticated live enrichment was NOT RUN: local owner generation 5 was stored READY,
but the existing credential capture returned `SECRET_STORE_UNAVAILABLE`. No credentials,
headers or secrets were logged, no connection state was modified, and no order was sent.

### Bounds, caching and failure isolation

The default response window is 10 listed strikes on either side of ATM plus ATM (at most
21 rows). `around_atm` is 0–25; all responses are capped at 51 rows and 102 legs. A strike
range and side filter further restrict output. Empty ranges reject. Unknown parameters,
inverted ranges and oversized limits fail validation. Unknown underlyings, absent
contracts/expiries, provider failures, unavailable spot/quotes, partial chains and
unsupported capabilities use typed codes rather than raw provider error messages.

Dhan's upstream endpoint has no strike-window parameter: it returns one whole expiry
batch, never one request per option. That unavoidable upstream batch is capped at 8 MB
and 5,000 strike entries; only requested bounded rows leave the domain service. The
master download is capped at 40 MB and 250,000 rows. Contracts are parsed once per master
refresh (default six hours, existing Dhan setting); active expiry checks run on every
request so a cached expiry cannot remain active indefinitely. Market snapshots have a
separate five-second cache, with up to 32 underlying/expiry keys. Concurrent requests
share a lock and cache; uncached provider calls are spaced by at least 3.1 seconds with
no retries. Cache entries are scoped to current owner/generation; a new generation drops
that owner's older entries. The application registry is bounded to 64 owner/generation
sources. No chain snapshot history or database migration is introduced.

`received_at` is retained on cache hits, never refreshed to disguise stale data. Source
time is separate; index spot now inherits the canonical quote's provider source time when
supplied, while equity chain responses without source time remain
`SOURCE_TIME_UNAVAILABLE`. The service does not call data fresh/live solely because it
was just received; the existing source-time freshness rule still applies. Missing quote
legs retain their canonical contract and null market values. Full quote failure still
returns bounded contract structure as PARTIAL. Chain failures do not write Dhan health,
Broker connection state, Watchlist data, Scanner results, or Instrument Metadata.

### O3+ consumers

Future Derivatives Scanner can consume raw volume/OI/OI-change/IV/spread/DTE/moneyness
without inventing unavailable fields. Analytics, Watchlists, Strategy Builder and
Discovery should use this same service and canonical leg identity. Ranking, option-chain
UI, Greeks calculations, historical snapshots, multi-leg execution and strategy authority
remain outside O2. Existing O1 order governance remains the authority for any later trade.


## O3 — Options Analytics chain workspace

Status: **IMPLEMENTED / USER VALIDATION PENDING**. O2 is implemented; O1 remains the
existing governed single-leg execution foundation. Authenticated live O3 acceptance
is separate from fixture/browser verification and remains pending.

### Product surface and canonical data

The existing Tools → Options Analytics entry is active at `/options-analytics`.
The page uses the full shell width, with a canonical underlying search, nearest listed
expiry, ±5/10/15/20 strike window (default ±10), explicit Refresh, compact source/spot/
expiry/DTE/ATM summary, symmetrical Calls/Strike/Puts table and selected-contract panel.
O2 supplies all structural identity, ATM, moneyness, spot and derivations; the browser
only formats fields. Strike ordering remains the O2 ascending order. Missing legs are
absent, missing values use an em dash, and unsupported IV/Greeks are never manufactured.
Greeks appear in expandable contract details with up to six decimal places.

Same-origin read-only proxies expose O2 `underlyings`, `expiries` and `chain`, forward
only the TWF session/allowed headers and retain no-store semantics. Requests are
abortable and scope-checked. A late response cannot replace a different underlying,
expiry or window. Refresh preserves the current setup and selected canonical leg,
respects the O2 cache, and does not start an automatic polling loop. A failed refresh
retains the previous retrieved timestamp, labels that snapshot explicitly, and disables
trade launch until refresh succeeds. Provider/partial errors use product messages,
not raw provider exceptions.

### Exact Broker V2 handoff

A selected CE/PE leg carries the O1 contract directly. Only connected, enabled brokers
that declare options support are offered. One eligible broker is selected automatically;
multiple eligible brokers require explicit selection. Buy/Sell support is respected per
broker. Market data provenance remains Dhan; the execution account/provider is separate.

The existing `OrderTicket` accepts an optional canonical launch. A backward-compatible
endpoint, `POST /api/v1/brokers/accounts/{account_id}/order-entry/option-capabilities`,
accepts O1 `OptionContractRequest`, performs exact owned-catalog resolution, and returns
the existing lot-aware capability model. It requires authentication and allowed Origin.
No caller-supplied native token or fuzzy symbol search is used. Invalid/missing exact
contracts reject. The ticket retains its existing quantity/product/order-type/price
controls and sends the same canonical identity to O2's `option-preview` endpoint.
The existing durable preview, confirmation, submission and reconciliation remain the
only order execution path. O3 automated validation stops at preview and blocks confirm.
The existing equity/futures/manual option picker remains available independently.

### Responsive and accessible behavior

Wide desktop shows the symmetrical chain beside contract detail. Medium widths place
detail below the table; tablets can scroll the table within its own labeled region.
Below 768 px, a Calls/Puts toggle selects a compact Strike/LTP/OI/Volume/IV table.
Both views retain exact contract selection. ATM has explicit text, moneyness is textual,
leg buttons expose pressed state, headers are semantic, and loading/errors are announced.
Keyboard users can select a leg and use the existing modal ticket/focus restoration.
Light and dark styles follow the shell tokens and navy summary strip.

### Freshness, live acceptance and capability truth

The workspace is explicitly an on-demand snapshot, including outside market hours.
It shows `Retrieved … IST`; source time is separately unavailable when O2 reports
`SOURCE_TIME_UNAVAILABLE`. The page does not infer a market session or claim that a
just-retrieved response is continuously live. Partial quotes retain listed contracts.
The O2 adapter support matrix remains unchanged: public-master validation is live,
quote/OI-change/IV/Greek normalization is fixture-verified, and authenticated provider
field availability is not yet verified for O3. No omitted live field is called supported
on the strength of a fixture alone.

During O3 development the running local API was reachable but unauthenticated options
reads returned HTTP 401. The computer-use inventory exposed no signed-in browser.
No credential changes, token extraction or session fabrication were used. NIFTY,
BANKNIFTY, HDFCBANK authenticated chain reads and live Broker preview therefore remain
NOT_RUN unless a signed-in application session becomes available. This is an access
limitation, not evidence that Dhan is unavailable to the user's running application.

### Scope and validation

Unit coverage exercises underlying/expiry/window selection, canonical CE/PE launches,
optional fields, partial/error states, refresh retention and stale-response protection.
Browser coverage uses deterministic normalized chain fixtures with the real isolated
TWF Broker mapping/preview API and its test transport, across 390/768/1024/1440/1920/2560
widths. Fixture timings measure UI/preview behavior, not authenticated Dhan latency.

Add to Watchlist is explicitly deferred: the existing Watchlist identity requires a
provider-native instrument reference that the public canonical chain intentionally does
not expose. O3 does not invent an ID or add a second resolver. Auto-refresh, a columns
editor, ranking, Derivatives Scanner, strategy/P&L/payoff tools, multi-leg execution,
computed IV/Greeks and historical chain persistence remain outside this phase.

O3 automated validation completed with 1,208 backend tests and 247 frontend tests
passing. Strict mypy checked 187 files; Ruff, compile, dependency checks, TypeScript,
ESLint, Prettier, production build and OpenAPI 3.1.0 validation (99 paths) passed.
All six Chromium chain journeys and all six existing Broker journeys passed. Stable
light/dark screenshots and fixture timings were saved outside Git in
`/tmp/twf-o3-evidence`. Representative screenshots were visually inspected at mobile
and desktop widths. Median fixture timings across the six widths: initial chain
503 ms, expiry switch 132 ms, refresh 177 ms, Buy preview 654 ms, Sell preview 646 ms.
These are isolated fixture timings, not live Dhan latency. The running development
API also exposes the new capability endpoint after reload; authenticated live checks
still require an accessible signed-in browser session. No live order was placed.

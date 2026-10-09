# TradingWorkFlow Options Architecture

Status: **O1 ACTIVE DEVELOPMENT / READY FOR USER VALIDATION AFTER VALIDATION PASSES**  
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
3. **O3 — Real option-data provider integration:** quotes and approved option evidence.
4. **O4 — Derivatives Scanner V1:** deterministic derivative scan contracts and engine.
5. **O5 — Explainable option ranking:** evidence-led deterministic ranking.
6. **O6 — Option Watchlists:** deeper option-specific list workflows.
7. **O7 — Options Analytics:** Greeks, IV, liquidity, and risk views with explicit sources.
8. **O8 — Strategy Builder:** user-authored multi-leg strategy modelling.
9. **O9 — Advanced execution / multi-leg governance:** atomicity, margin, and execution
   controls designed before implementation.
10. **O10 — Discovery / optional LLM synthesis:** evidence-bound interpretation without
    granting trading authority.

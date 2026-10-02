# TWF Market Data Provider Architecture

Status: **IMPLEMENTED / READY FOR USER VALIDATION**
Date: 2026-10-02

## Decision

TWF uses a provider-neutral `MarketDataProvider` boundary for authoritative technical market data. Dhan is the first active implementation. Zerodha is the next intended interchangeable implementation. TradingView is decommissioned from the active market-data runtime; its historical records and provenance remain immutable.

```text
Dhan (active) ─┐
               ├─ MarketDataProvider ─ Normalized MarketSeries ─ Internal Scanner V0
Zerodha (next) ┘                                                │
                                                                ├─ ScanMatch/evidence
Fixture provider ─ same contract ────────────────────────────────┘
                                                                │
                                                                └─ retained exact series ─ Evidence Chart
```

The invariant is strict: **the normalized series evaluated by the scanner is the series archived for that scan's As Scanned Evidence Chart**. Current Chart is a separate on-demand read and never rewrites historical evidence.

## Contract

`MarketDataProvider` supports:

- bounded capability and health reporting;
- deterministic canonical instrument resolution;
- bounded batch quote normalization;
- bounded OHLCV retrieval;
- the existing `MarketSeriesSource.read` shape used by Internal Scanner V0.

Provider-native payloads stop at the adapter. The domain receives `InstrumentIdentity`, `QuoteSnapshot`, `Bar`, `MarketSeries`, and typed failures.

### Instrument identity

The normalized identity retains the TWF instrument ID, symbol, exchange, segment, instrument type, provider namespace/native ID, provider symbol, and future derivative fields for expiry, strike, and right. Dhan identities use the compact instrument master security ID and exchange segment; scans do not perform fuzzy provider lookup.

### Quote and series truth

`QuoteSnapshot` records only fields returned by Dhan: last price, optional OHLC/previous close, volume, open interest, receipt time, and provider. It does not invent a provider timestamp.

`MarketSeries` records the canonical instrument, provider provenance, interval, requested count, received time, completeness, completed-bar finality, live-bar exclusion, adjustment/session revisions, and normalized OHLCV/OI bars. Response sizes, total wall-clock time, supported intervals, bar count, and dates are bounded.

## Dhan implementation

The Dhan adapter uses documented DhanHQ v2 endpoints:

- compact instrument master for canonical security IDs;
- `/marketfeed/quote` for batch quotes;
- `/charts/historical` for daily bars;
- `/charts/intraday` for 1, 5, 15, and 60 minute bars.

TWF exposes `1m`, `5m`, `15m`, `1h`, and `1d`. Daily and intraday requests include a bounded warm-up range and return at most the requested TWF bar cap. The current/incomplete bar is excluded using a conservative exchange-session/interval availability cutoff. The adapter reports the exclusion and does not claim provider-supplied finality metadata.

The compact master is cached for six hours. Quote requests use one Dhan batch for up to 1,000 instruments. Real scanning resolves a maximum of 64 requested instruments and performs at most one OHLCV request for each successfully resolved instrument, sequentially, with no automatic retry.

Typed Dhan outcomes include `AUTH_REQUIRED`, `RATE_LIMITED`, `INSTRUMENT_NOT_FOUND`, `AMBIGUOUS_INSTRUMENT`, `DATA_UNAVAILABLE`, `PARTIAL_RESPONSE`, `TIMEOUT`, `PROVIDER_ERROR`, `INVALID_RESPONSE`, and `UNSUPPORTED_INTERVAL`.

## Scanner and temporal behavior

Real mode means Dhan. Synthetic mode uses `FixtureMarketDataProvider`. Both flow through the same normalized `MarketSeries` and `InternalScannerV0` profile evaluator. There is no active TradingView verification phase.

Per instrument:

- evaluated and matched produces `PRESENT`;
- evaluated and not matched produces `ABSENT`;
- resolution, authentication, rate-limit, timeout, malformed response, or data failure produces `NOT_EVALUATED`.

A partial run preserves successful instruments and explicitly records failed ones. Provider failure cannot close an active episode as an evaluated absence. Relevance continues to use accepted normalized scan evidence and deterministic relevance v2; it is not probability of profit.

## Evidence Chart

For a Dhan match, TWF stores the bounded normalized series used by the scanner together with profile and computation revisions. As Scanned reconstructs only that archive and verifies its metrics. Current Chart asks Dhan for a new bounded series and labels provider, interval, receipt/source time where available, completeness, and finality truthfully.

The renderer remains a TWF component. It knows normalized bars, indicators, thresholds, markers, predicates, and provenance; it has no Dhan transport or authentication logic.

Older TradingView-backed runs keep their original provider, metrics, observations, and provenance. If their source bars were never retained, As Scanned remains truthfully retention-restricted and Current Chart remains unavailable. No Dhan refetch is presented as the historical TradingView series.

## Configuration

Dhan market-data credentials are owner-scoped and configured through **Settings → Data providers → Dhan market data**. TWF encrypts the client ID and access token in a separate secret row, returns only sanitized status metadata, generation-fences replacement/disconnect, and removes local credential authority on disconnect. Saving produces `CONFIGURED`; a bounded one-symbol quote test must succeed before the owner reaches `READY` and can run real S&D.

`TWF_DHAN_MARKET_DATA` remains an optional development/bootstrap fallback:

```dotenv
TWF_DHAN_MARKET_DATA='{"enabled":true,"client_id":"<DHAN_CLIENT_ID>","access_token":"<CURRENT_DHAN_ACCESS_TOKEN>"}'
```

The access token must be current. Stored values are never returned to the browser, URLs, logs, or screenshots. Settings and S&D expose `NOT_CONFIGURED`, `CONFIGURED`, `READY`, `AUTH_FAILED`, `RATE_LIMITED`, `PROVIDER_ERROR`, and `DISABLED` without exposing credential material.

## Retention and licensing

The current implementation retains only the bounded normalized evidence window needed to explain an internal personal-development scan. It does not grant redistribution or commercial data rights. Before production, sharing, or commercial use, the operator must confirm the applicable Dhan plan and licensing terms; if retention is not permitted, TWF must retain derived evidence/provenance and show the chart limitation rather than fabricate equivalence.

## Zerodha compatibility

A future Zerodha market-data adapter must implement this contract and preserve broker-native instrument identity. The scanner, evidence, temporal, relevance, and chart domain objects do not change. Provider selection remains an operator capability decision until Zerodha market-data behavior and licensing are independently validated.

## Active boundaries

This architecture does not add watchlists, Opportunity, LOB, Trade Construction, autonomous execution, order authority, or broker-position truth. Dhan is authoritative only for the technical market-data inputs described here. Market Intelligence is a separate optional layer.

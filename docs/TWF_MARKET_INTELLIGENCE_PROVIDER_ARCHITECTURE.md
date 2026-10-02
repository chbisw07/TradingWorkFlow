# TWF Market Intelligence Provider Architecture

Status: **IMPLEMENTED / PARTIAL — LIVE AUTHORIZATION AND VALIDATION NOT RUN**
Date: 2026-10-02

## Decision

TWF uses a provider-neutral `MarketIntelligenceProvider` boundary. TapTide is the first bounded implementation. Market Intelligence (MI) enriches context; it never owns technical market truth, scan predicates, execution price, broker state, or trading authority.

```text
0..N MI providers
  ├─ TapTide MCP (first)
  ├─ future licensed news/research
  ├─ exchange/public sources
  └─ search providers
          │
          └─ normalized intelligence claims ─ MarketContext/evidence ─ bounded relevance context

Dhan MarketSeries ─ Internal Scanner V0 ─ technical match (independent of MI availability)
```

## Normalized contract

`MarketIntelligenceProvider` reports readiness and returns a bounded `MarketIntelligenceBatch`. Each `IntelligenceClaim` includes:

- a provider-neutral claim kind;
- subject and scope;
- a small allowlisted normalized value vocabulary;
- provider and provider tool;
- source time when supplied;
- TWF receipt time;
- explicit freshness;
- a bounded source reference.

Raw TapTide keys and payloads do not cross the adapter boundary. No confidence or reliability field is invented when the provider does not justify one.

Typed states are `AVAILABLE`, `PARTIAL`, `STALE`, `AUTH_REQUIRED`, `RATE_LIMITED`, `UNAVAILABLE`, and `PROVIDER_ERROR`. Claim freshness is `CURRENT`, `STALE`, `FUTURE_SOURCE_TIME`, or `SOURCE_TIME_UNAVAILABLE`.

## TapTide bounded capability set

The adapter allows only these read-only tools:

| Provider tool           | Normalized purpose                    |
| ----------------------- | ------------------------------------- |
| `get_market_pulse`      | broad market pulse                    |
| `get_india_vix`         | market volatility                     |
| `get_fii_dii_detail`    | institutional market flow             |
| `get_fpi_sectors`       | sector flow                           |
| `get_index_performance` | index/sector strength context         |
| `get_market_news`       | news/sentiment context                |
| `get_stock_events`      | important instrument corporate events |

The server-side allowlist is fixed; the frontend cannot select an arbitrary tool. A cold context observation makes at most seven sequential tool calls with no automatic retry. Successful complete/stale batches are cached for five minutes, capped at 128 entries, and fenced by owner, connection, credential generation, selected tools, and the relevant instrument. Cached batches retain their original source and receipt times.

Deep options analytics, exhaustive fundamentals, analyst forecasts, portfolio/watchlist modification, delivery/deal datasets, and full company research remain deferred.

## Generic MCP reuse

TapTide uses the existing generic MCP foundation: owner isolation, ProviderConfig registration, OAuth 2.1/PKCE, encrypted secret references, generation fencing, durable operation permits, draining disconnect, hard deadlines, response limits, server-controlled tool allowlists, and sanitized failures.

The official remote endpoint is `https://mcp.tapetide.com/mcp`. TWF can use either:

- a verified OAuth ProviderConfig with pre-registered public-client metadata; or
- `API_KEY` mode with a TapTide personal bearer token entered through Settings.

A minimal personal-token provider registration is operator configuration:

```dotenv
TWF_MCP_PROVIDERS='[{"provider_id":"tapetide","display_name":"TapTide","endpoint":"https://mcp.tapetide.com/mcp","auth_mode":"API_KEY","timeout_seconds":10,"max_response_bytes":262144,"max_tools":64,"max_pages":4}]'
```

After restart, a signed-in owner opens **Settings → Provider connections**, creates a TapTide connection, supplies the personal token to Connect, and tests the connection. The token is encrypted through the existing secret store and never returned to the page. Do not put it in Git.

Generic OAuth and `/settings/mcp/callback` remain provider-neutral. Existing TradingView connection rows are not deleted, but the product UI filters the decommissioned TradingView provider from active connection choices.

## Failure isolation

TapTide is never a boot or scan dependency. If it is absent, stale, rate limited, malformed, or fails unexpectedly:

- Dhan resolution/OHLCV and Internal Scanner V0 continue;
- technical `PRESENT`/`ABSENT`/`NOT_EVALUATED` semantics remain governed by Dhan evaluation;
- MI dimensions are marked unavailable/degraded with sanitized typed reasons;
- no synthetic MI is substituted;
- no raw provider payload or diagnostic escapes.

MI may contribute only through existing market-context/evidence concepts. It does not silently redefine profile predicates. Any later relevance effect must remain bounded, deterministic, explainable, and versioned.

## Provenance and freshness

Every surfaced TapTide claim identifies TapTide, the tool, the context kind, source time when available, receipt time, and freshness. A missing timestamp remains explicit. A timestamp more than seven days old is stale; a timestamp more than five minutes in the future is flagged rather than treated as current.

Provider data is for internal informational use under the operator's TapTide plan. TWF does not redistribute raw responses. Production/commercial use requires a separate licensing review.

## Active boundaries

This implementation adds no watchlist operation, portfolio mutation, trade recommendation, Opportunity, LOB, Trade Construction, order action, or autonomous workflow. Future providers fit beside TapTide through the same normalized claim contract.

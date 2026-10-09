# TWF Market Intelligence Provider Architecture

## Runtime health and operation accounting (2026-10-09)

Connection state, provider health and operation authority are independent.
`CONNECTED` retains owner/generation-bound credentials; it does not promise that
every tool works. An MCP `isError` reply is `TOOL_FAILED`, not a transport outage.
One tool failure degrades health and leaves other allowlisted capabilities callable.
Three consecutive transport, session-contract or timeout failures mark the provider
unavailable (`OUTAGE_THRESHOLD` in `integrations/mcp/health.py`). A tool-error reply
resets that transport streak because transport responded. Authentication failures
still invalidate authority immediately. No automatic retries were added.

Normal successful calls recover health after the caller-delivery receipt, without
requiring Test connection. Missing registered required tools still mean degraded.
Health provenance records transition time, last failure category/time and bounded
transport-failure count. Durable operations record tool name and an idempotent
health observation; logs contain IDs, family, generation, duration and category,
never credentials or provider error text. Full per-capability health history is
not introduced; failure isolation occurs at the tool boundary.

`operations_pending` now means current-generation RUNNING work with no terminal
outcome and an unexpired deadline. `unresolved_cleanup_count` reports other
outstanding permits/receipts separately. Timed-out and expired foreign-worker work
is never displayed indefinitely as active. This read-time classification works
after restart, without pretending the old worker stopped. Explicit local recovery
can acknowledge proven committed delivery receipts; other expired work remains
UNRESOLVED. Admission and disconnect still fence on **all** outstanding authority.
Test connection cannot bypass unresolved teardown or erase it. Thus an unsafe
test is rejected until recovery, rather than returning a fictitious success.

Caller timeout remains final; owned teardown may continue and late results never
become caller success. Stale generations cannot change current health. No DB
transaction spans provider I/O. The provider-configured 10-second TapTide budget
(maximum 30 seconds) is unchanged and includes setup, tool work and transport
teardown; the Watchlist reference envelope is 25 seconds including cache-lock
waiting. Receipt handoff and shutdown drain are separately bounded to one second.
Failed/unconfirmed teardown remains visible and fenced, even after those bounds.

Watchlist reference failures produce a temporary-unavailable message, independent
of Dhan quotes/charts and imported instrument metadata. Connected degraded or
unavailable providers are eligible for bounded normal requests; the manager still
checks authentication, generation and durable permits. The existing owner,
generation and instrument-scoped cache uses 900 seconds for reference responses
and 60 seconds for failure responses. It never substitutes expired last-known-good
values or invents missing fundamentals. Schema migration `0020_mcp_health` is
additive and contains no credential changes.

Status: **IMPLEMENTED / READY FOR OWNER AUTHORIZATION — LIVE VALIDATION NOT RUN**
Date: 2026-10-03

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

The official [TapTide MCP documentation](https://mcp.tapetide.com/) identifies the remote endpoint as `https://mcp.tapetide.com/mcp` over Streamable HTTP. It documents OAuth 2.1 with PKCE and dynamic client registration, plus personal bearer tokens. The current TWF OAuth contract intentionally accepts only operator-verified, preregistered public clients; it does not perform dynamic client registration. TapTide therefore uses the already-supported generic `API_KEY` mode for this bounded integration. OAuth DCR is deferred rather than approximated.

The operator registration is metadata only:

```dotenv
TWF_MCP_PROVIDERS='[{"schema_version":"mcp.connection.v1","provider_id":"tapetide","display_name":"TapTide","category":"MARKET_INTELLIGENCE","endpoint":"https://mcp.tapetide.com/mcp","auth_mode":"API_KEY","timeout_seconds":10,"max_response_bytes":262144,"max_tools":64,"max_pages":4,"required_tools":["get_market_pulse","get_india_vix","get_fii_dii_detail","get_fpi_sectors","get_index_performance","get_market_news","get_stock_events"],"retry_count":0,"refresh_policy":"EXPLICIT","health_policy":"INITIALIZE_AND_LIST_TOOLS"}]'
```

After API restart, a signed-in owner opens **Settings → Data providers → Market intelligence connections**, adds TapTide, enters a personal bearer token, selects **Connect TapTide**, and then **Test connection**. Connect stores the token through the existing encrypted owner-scoped secret lifecycle. Test performs MCP initialization and tool discovery. The connection is **Ready** only when all seven bounded capabilities are present; a missing required capability is **Degraded**. Tokens are never returned to the page or written to Git.

A public `tools/list` probe on 2026-10-03 returned 55 tools and all seven required tools above. Their provider annotations were read-only, non-destructive, idempotent, and closed-world. TWF does not treat annotations as authority and does not expose the remaining catalog: business calls retain the fixed seven-tool server allowlist. The live schema uses a bounded one-completed-month sector ranking (`category=sectoral`, `granularity=month`, `periods=1`, `limit=10`), and news/events remain capped at 10/5 results. The published free tier currently permits 50 successful calls per day and 1,000 per month, with separate burst controls; provider limits remain authoritative and can yield a typed rate-limited state.

Generic OAuth/PKCE and `/settings/mcp/callback` remain provider-neutral for providers whose verified metadata fits the existing contract. Existing TradingView connection rows are not deleted, but the product UI filters the decommissioned TradingView provider from active connection choices.

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

# S2-3 — TradingView MCP ScanProvider implementation

Date: 2026-09-30. Status: **ACCEPTED / FROZEN WITH DEFERRED HARDENING**.
Sprint 2 remains ACTIVE. S2-1/S2-2/S2-3 and Broker V2 are ACCEPTED / FROZEN.
S2-3A durability is integrated into S2-3. S2-4 is NEXT. The S2-3 Git checkpoint
is prepared but is not committed or tagged by this documentation task.

Read the [bounded acceptance record](TWF_S2_3_ACCEPTANCE_REVIEW.md) and
[hardening register](TWF_S2_3_DEFERRED_ISSUES_AND_HARDENING_REGISTER.md).

## Scope and boundary

The TradingView adapter uses the accepted generic MCP connection manager and
normalizes provider observations through the existing `ScanProvider`,
`ProviderAccess`, `ScanRun`, `ScanMatch`, evidence and lineage contracts.
It adds no TradingView-specific secret store, broker call, trade operation, LLM,
market-intelligence engine, frontend or later Sprint-2 feature.

The production scan API accepts an explicit TWF instrument universe. That path
always uses exact batch retrieval; it never substitutes an India-wide scan for
requested symbols. A separate internal provider-screener planner/parser retains
the verified broad `run_screener` contract for truthful provider-defined broad
universes.

## Verified provider contract

Official sources:

- [TradingView MCP documentation](https://www.tradingview.com/mcp/docs).
- [TradingView MCP public-beta announcement](https://www.tradingview.com/blog/en/tradingview-mcp-server-public-beta-60864/).
- [TradingView OAuth issuer metadata](https://www.tradingview.com/.well-known/oauth-authorization-server).

The endpoint is `https://mcp.tradingview.com/mcp` over Streamable HTTP with
OAuth 2.1/PKCE. Prior live verification discovered 35 tools, verified India
screener support, fetched the column catalogue and returned real India/NSE rows
through `mcp-tv-run-screener`.

The three server-allowed read tools are:

- `mcp-tv-get-screener-columns`;
- `mcp-tv-get-symbol-data-batch`;
- `mcp-tv-run-screener`.

Write tools remain denied by the server-controlled TWF allowlist. The production
API accepts no arbitrary destination or tool name.

A direct `run_screener.symbolset` request containing arbitrary
`NSE:RELIANCE`/`NSE:TCS` identities returned an empty set. TradingView's
symbol-set vocabulary is therefore not used as an exact ticker array. This live
finding is preserved rather than approximated away.

## Execution strategies

### Exact explicit universe

`TradingViewAdapter.arguments()` validates 1–64 canonical NSE/BSE equity
identities whose native ID is exactly `EXCHANGE:TICKER`. Duplicate, ambiguous,
non-equity or provider-mismatched identities fail before provider I/O.

It derives the minimum requested column set from the scan criteria plus the
configured sort column, validates those columns against a fresh bounded
`get_screener_columns` response, and partitions the request deterministically
into chunks of at most 50 symbols. Each chunk calls
`mcp-tv-get-symbol-data-batch`.

Every requested identity must appear exactly once either as a returned row or in
the provider's `missing` list. Unexpected identities, duplicates, returned-and-
missing overlap, silent omissions, missing metrics, non-finite values or malformed
envelopes fail the operation. A failed chunk fails the whole call; prior chunks
are never presented as successful partial scan output.

Resolved rows are aggregated and evaluated locally with the accepted Internal
Scanner comparator for every existing `Comparison` value (LT, LTE, EQ, GTE and
GT) and the existing ALL/ANY combination semantics. No second expression language
or unavailable historical structure is invented. Results are sorted and bounded
only after exact local evaluation. Unresolved symbols are explicit in execution
lineage and make the normalized batch PARTIAL.

### Broad provider screener

`broad_arguments()` and `broad_screener_rows()` retain the verified
`mcp-tv-run-screener` request/result contract for provider-defined broad
universes. The plan never places arbitrary tickers into `symbolset`. Its live
India/NSE evidence remains the earlier bounded result containing `NSE:IDEA`
and `NSE:PCJEWELLER` from 7,908 provider results.

The current HTTP scan endpoint requires an explicit universe and therefore selects
the exact strategy. A later broad product surface would require its own bounded API
contract rather than encoding "broad" as an empty exact universe.

## Response binding and rate limits

Column discovery requires a bounded grouped schema with unique column names and
the required fields. Exact-batch binding accepts the documented result rows plus
an explicit `missing` list, including the supported nested form. Broad binding
accepts `success/data/{rows,totalCount}`.

TradingView may report a provider HTTP 429 inside structured tool content while
the MCP envelope has `isError=false`. The adapter inspects the provider
`success`/error payload and maps 429 to typed TWF `RATE_LIMITED`; it never
normalizes that payload as scanner data. The 2026-09-30 live exact-batch attempt
reproduced this structure:

```json
{
  "success": false,
  "error": "provider returned HTTP 429"
}
```

The fixture is sanitized; no OAuth code, token, authorization header, cookie or
private authorization URL is stored in the repository.

## Time, freshness and lineage

TradingView's response does not provide an authoritative provider source timestamp
or bar-finality field. TWF records its own observed/received time, leaves
`source_data_time` null, reports UNKNOWN freshness and includes
`source-time-unavailable` and `bar-completion-unverified` limitations.
`LIVE_SNAPSHOT` means an on-demand remote observation; it is not a claim of
exchange real-time data or a completed candle.

Every exact execution records:

- provider `tradingview`;
- strategy `EXACT_BATCH`;
- remote tool `mcp-tv-get-symbol-data-batch`;
- requested universe and minimal columns;
- deterministic chunk count and unresolved symbols;
- schema hash, generation, start and completion times;
- the original immutable `ScanDefinition`;
- local transformation `tradingview-exact-batch-local-filter` version 1;
- dependence group `tradingview-exact-batch`.

Matches retain the original canonical `InstrumentIdentity`, owner, run, profile,
definition revision and configuration fingerprint. The public result contains no
raw token or transport payload.

## Timeout and failure policy

The default exact-operation budget remains 8 seconds. Operators may configure a
bounded total up to 60 seconds because an exact capture performs two separately
bounded MCP sessions (column discovery and batch retrieval); the generic MCP
descriptor independently caps each provider session at 30 seconds. The outer
deadline surrounds both calls, parsing, local evaluation and normalization, and
a final monotonic deadline check prevents late success.

Failures distinguish authentication, authorization, stale generation/provenance,
timeout, rate limit, unsupported capability, malformed response and provider
unavailability. There is no automatic fallback to the Internal Scanner and no
automatic retry that could disguise rate-limit or partial-chunk behavior.

## Configuration and API

The safe default remains disabled and unverified:

```sh
export TWF_TRADINGVIEW_SCAN='{"enabled":false,"response_contract_verified":false,"max_items":20,"timeout_seconds":8,"snapshot_ttl_seconds":60,"sort_by":"volume","sort_order":"desc"}'
```

Do not set `response_contract_verified=true` merely to bypass the runtime guard.
The current endpoints are:

- `GET /api/v1/scan-providers/tradingview/{identity}/status`;
- `POST /api/v1/scan-providers/tradingview/{identity}/scan`;
- the accepted owner-scoped generic MCP connection/OAuth/recovery endpoints.

Status truthfully keeps `last_successful_scan=null` because durable scan history
belongs to S2-7. Run-specific timing and lineage remain in each `Execution`.

## Integrated MCP durability

The accepted S2-3A generation-bound permit, draining disconnect, hard caller
deadline, late-result quarantine and durable reconciliation semantics remain
unchanged. No database transaction or lock spans provider I/O. Lost/ambiguous work
stays unresolved; permit expiry does not prove completion. Migration 0011 and the
historical independent S2-3A reviews remain authoritative.

Run `alembic upgrade head` before deployment; application startup does not migrate.

## Validation and live status

Deterministic coverage includes exact universes at and above 50 symbols,
deterministic multi-chunk aggregation, unresolved and duplicate identities, empty
matches, all existing comparisons, ALL/ANY, unsupported definitions, minimal
columns, structured/transport rate limits, malformed responses, failed later
chunks, missing timestamps/bar finality, exact lineage, ScanRun/ScanMatch
compatibility and retained broad-screener parsing.

On 2026-09-30 fresh OAuth/PKCE callbacks succeeded in the signed-in Chromium
profile. A one-symbol `NSE:RELIANCE` exact request reached
`mcp-tv-get-symbol-data-batch` with only `close` requested. The provider returned
the structured 429 above. TWF emitted typed `RATE_LIMITED`; no row was normalized.
The live real-row requirement is therefore still open.

A later final bounded probe on the same date made exactly one new authorization
attempt and opened the private consent URL in the normal Chromium profile. The
loopback callback did not arrive within five minutes, so the attempt expired
without acquiring credentials and without issuing a TradingView tool call. The
temporary connection disconnected cleanly with no local cleanup pending. This is
recorded as an incomplete interactive authorization attempt, not a new provider or
adapter defect.

The subsequent final authorization retry started the loopback listener before
browser handoff, received the fresh OAuth callback and issued exactly one remote
`mcp-tv-get-symbol-data-batch` call for `NSE:RELIANCE` with `columns=["close"]`.
TradingView again returned the structured provider HTTP 429 condition. TWF emitted
typed `RATE_LIMITED`; no other tool was called, no retry occurred and no row was
normalized. This confirms the callback path and rate-limit normalization while
leaving the real-row gate open.

The explicitly authorized one final retry reproduced the same result with a fresh
OAuth callback and exactly one identical exact-batch request. The provider exposed
no retry-after, reset, quota or limit metadata in the structured response, so the
scope of throttling remains unknown; the evidence does not support classifying it
as per-minute, daily/quota, tool-specific or account/plan-specific.

Disconnect moved each temporary connection to DISCONNECTED and denied further use.
Remote revocation cleanup remained explicitly pending after bounded retries, so
encrypted revoked material was quarantined rather than deleted or misreported as
clean. Because the connection is DISCONNECTED, local authority is revoked and new
admission is disabled, the remote obligation is accepted only as explicit Sprint-2
hardening; it is not described as complete.

```ini
TRADINGVIEW_EXACT_IMPLEMENTATION = COMPLETE
TRADINGVIEW_LIVE_EXACT_REQUEST_REACHED_PROVIDER = YES
TRADINGVIEW_LIVE_EXACT_REAL_ROW_NORMALIZED = NO
TRADINGVIEW_LIVE_RESULT = RATE_LIMITED
TRADINGVIEW_FINAL_PROBE_AUTH = PASS
TRADINGVIEW_FINAL_PROBE_CALLBACK = PASS
TRADINGVIEW_FINAL_PROBE_PROVIDER_CALL = RATE_LIMITED
TRADINGVIEW_FINAL_PROBE_REMOTE_TOOLS = mcp-tv-get-symbol-data-batch
TRADINGVIEW_FINAL_PROBE_CLEANUP_PENDING = YES
TRADINGVIEW_FINAL_PROBE_RATE_LIMIT_SCOPE = UNKNOWN
S2_3_STATUS = ACCEPTED_FROZEN_WITH_DEFERRED_HARDENING
```

## Final verification disposition

Real-provider evidence verifies:

- OAuth 2.1 / PKCE and loopback callback;
- authenticated MCP session and 35-tool discovery;
- TradingView column and broad-screener response schemas;
- a bounded real India screener result;
- exact-batch tool invocation for `NSE:RELIANCE` and `columns=["close"]`;
- typed normalization of structured provider HTTP 429.

Real-provider evidence does **not** yet verify a successful exact-batch row or
live ScanRun, ScanMatch and EXACT_BATCH lineage derived from such a row. Repeated
minimal exact requests were externally rate-limited and exposed no retry/reset/quota
metadata; `RATE_LIMIT_SCOPE=UNKNOWN`.

Synthetic deterministic verification covers successful exact rows, 50-symbol
chunking, local filtering, every supported comparison, ALL/ANY semantics, ScanRun,
ScanMatch, exact lineage, missing symbols, malformed responses, failed chunks and
429 handling. This is why implementation acceptance is distinct from the mandatory
successful-live-row hardening item.

```ini
REAL_PROVIDER_OAUTH_PKCE = PASS
REAL_PROVIDER_CALLBACK = PASS
REAL_PROVIDER_TOOL_DISCOVERY = PASS
REAL_PROVIDER_COLUMN_SCHEMA = PASS
REAL_PROVIDER_BROAD_SCHEMA_AND_DATA = PASS
REAL_PROVIDER_EXACT_BATCH_INVOCATION = PASS
REAL_PROVIDER_EXACT_ROW_NORMALIZATION = DEFERRED_EXTERNAL_RATE_LIMIT
SYNTHETIC_EXACT_BATCH_NORMALIZATION = PASS
SYNTHETIC_EXACT_BATCH_LINEAGE = PASS
RATE_LIMIT_SCOPE = UNKNOWN
REMOTE_REVOCATION_CLEANUP = DEFERRED_PENDING
S2_3_STATUS = ACCEPTED_FROZEN_WITH_DEFERRED_HARDENING
```

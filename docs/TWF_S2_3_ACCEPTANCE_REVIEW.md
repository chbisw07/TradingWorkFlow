# S2-3 — Final exact-universe correction acceptance record

Date: 2026-09-30. **Decision: ACCEPT_S2_3_WITH_DEFERRED_HARDENING.**

This is the implementing-agent's bounded validation record, not an independent
review. Historical S2-3A independent reviews remain unchanged. S2-1, S2-2 and
Broker V2 remain accepted/frozen; S2-4 is not started.

## Result

The exact-universe implementation is complete and deterministic:

- explicit TWF universes use `mcp-tv-get-symbol-data-batch`;
- arbitrary tickers are never placed in `run_screener.symbolset`;
- deterministic chunks contain at most 50 identities;
- required columns are derived from criteria and sort;
- rows are evaluated locally with the accepted comparator and ALL/ANY semantics;
- missing identities remain explicit and any failed chunk fails the call;
- normalized matches preserve exact identity, ScanRun/ScanMatch contracts and
  exact-strategy lineage;
- source timestamp and bar finality remain explicitly unavailable;
- provider 429 inside a successful MCP envelope becomes typed `RATE_LIMITED`;
- the provider-wide broad screener planner/parser and prior live broad proof remain.

The live acceptance gate did not close. The one final exact-batch retry on
2026-09-30 started the loopback listener before browser handoff, completed fresh
OAuth/PKCE approval and received the callback. It then issued exactly one remote
tool call: `mcp-tv-get-symbol-data-batch` for `NSE:RELIANCE` with only `close`.
TradingView again returned its structured provider HTTP 429 condition, which TWF
normalized to typed `RATE_LIMITED`. No retry, broad screener or unrelated tool call
occurred, and no real row entered ScanRun/ScanMatch normalization. No retry-after,
reset, quota or limit metadata was supplied, so rate-limit scope is unknown.

The temporary connection reached DISCONNECTED, rejects new admission and has no
active local credential authority. Remote revocation cleanup remains explicitly
pending after bounded attempts; encrypted token material is locally revoked and
quarantined rather than deleted or reported as clean.

Successful live exact-row normalization remains unproven and is registered as
mandatory Sprint-2 hardening evidence. The implementation is nevertheless accepted:
controlled real attempts repeatedly proved OAuth, callback, authenticated MCP access
and exact-tool reachability; each minimal exact request was externally rate-limited;
and no TWF correctness or response-contract defect was reproduced. TWF failed closed,
normalized 429 truthfully and made no automatic retry. S2-3 is therefore ACCEPTED /
FROZEN WITH DEFERRED HARDENING and is ready for its Git checkpoint. S2-4 is NEXT;
Sprint 2 remains ACTIVE.

## Validation evidence

Final validation established:

- 33 focused TradingView tests passed;
- 901 full backend tests passed;
- Ruff lint and format passed; strict mypy passed for 70 source files;
- Python compilation, OpenAPI construction (42 paths / 87 schemas), `pip check`,
  Docker Compose validation, Markdown formatting/link checks and `git diff --check`
  passed;
- offline sdist/wheel build passed with the frontend dependency check explicitly
  skipped because the local venv has setuptools 84 while the declared build range is
  `>=75,<83`; the pre-existing package-local README warning remains.

Earlier validation of the same uncommitted S2-3 worktree also established 202 focused
MCP durability/Internal Scanner/TradingView passes before the added timeout-boundary
case, 30 PostgreSQL remediation passes, and SQLite/PostgreSQL migration round trips.

Dependency audit status remains **NONBLOCKING_WITH_EVIDENCE**: seven records
represent the same four accepted `cryptography==47.0.0` advisories. The audit is
not clean, and no new dependency was added by the exact-universe correction.

## Historical findings preserved

The earlier S2-3 integrated review proved generic MCP durability and the live broad
TradingView contract, but held because exact arbitrary ticker semantics had not been
implemented. That architecture finding is resolved in code by exact batch retrieval.
The remaining evidence gap is narrower: provider throttling prevented a real exact
row, and temporary remote revocation remains pending. Existing deferred MCP diagnostic,
unknown-work support, scan-history and time/finality limitations remain in the
hardening register.

## Historical pre-disposition scorecard

```ini
TRADINGVIEW_BROAD_SCREENER = PASS
TRADINGVIEW_EXACT_BATCH_FETCH = PASS
TRADINGVIEW_EXACT_UNIVERSE_PRESERVED = PASS
TRADINGVIEW_BATCH_CHUNKING = PASS
TRADINGVIEW_LOCAL_FILTER_EVALUATION = PASS
TRADINGVIEW_UNRESOLVED_SYMBOL_HANDLING = PASS
TRADINGVIEW_429_NORMALIZATION = PASS
TRADINGVIEW_TIMESTAMP_LIMITATION_TRUTHFUL = PASS
TRADINGVIEW_BAR_FINALITY_LIMITATION_TRUTHFUL = PASS

TRADINGVIEW_REAL_RESULT_NORMALIZED = FAIL
TRADINGVIEW_LINEAGE_VERIFIED = PASS
LIVE_EXACT_UNIVERSE_SMOKE = FAIL

MCP_DURABILITY_REGRESSION_FREE = PASS
INTERNAL_SCANNER_REGRESSION_FREE = PASS
S2_1_S2_2_REGRESSION_FREE = PASS
BROKER_V2_REGRESSION_FREE = PASS
FULL_TESTS_PASS = PASS

DEPENDENCY_AUDIT_STATUS = NONBLOCKING_WITH_EVIDENCE

S2_3_FINAL_DECISION = HOLD_S2_3
READY_FOR_S2_3_GIT_CHECKPOINT = NO
```

## Historical one-final-retry evidence

```ini
TRADINGVIEW_LIVE_AUTH = PASS
AUTHORIZATION_CALLBACK_RECEIVED = PASS
REAL_EXACT_ROW_RECEIVED = RATE_LIMITED
REAL_SCANRUN_VERIFIED = NOT_RUN
REAL_SCANMATCH_VERIFIED = NOT_RUN
REAL_EXACT_BATCH_LINEAGE = NOT_RUN

LIVE_DISCONNECT = PASS
CLEANUP_PENDING_FALSE = FAIL
PRIVATE_TEMP_ARTIFACTS_REMOVED = PASS

RATE_LIMIT_SCOPE = UNKNOWN
SOURCE_CHANGED_DURING_PROBE = NO
FULL_TESTS_PASS = PREVIOUS_901_TEST_REGRESSION_STILL_APPLICABLE
DEPENDENCY_AUDIT_STATUS = NONBLOCKING_WITH_EVIDENCE

S2_3_FINAL_DECISION = HOLD_S2_3
READY_FOR_S2_3_GIT_CHECKPOINT = NO
```

The listener was active at `127.0.0.1:8765` before the browser opened. Approval and
callback completed within the five-minute window. The only remote MCP tool call was
`mcp-tv-get-symbol-data-batch` for `NSE:RELIANCE` with only `close`. TradingView
again returned HTTP 429. It supplied no retry-after, reset, quota or limit metadata,
so the limit scope remains UNKNOWN. The typed outcome and pending remote cleanup
are reported without retrying or weakening exact-universe semantics.

## Final disposition

Implementation acceptance is distinct from successful-live-row evidence. Real
provider verification covers OAuth/PKCE, callback, authenticated MCP sessions,
35-tool discovery, column and broad-screener contracts, broad real data, exact-batch
tool invocation and 429 normalization. Deterministic synthetic validation covers the
successful exact-row path through local filtering, ScanRun, ScanMatch and
EXACT_BATCH lineage.

A successful real exact-batch row has not been received. Accordingly, live ScanRun,
live ScanMatch and live EXACT_BATCH lineage remain NOT_PROVEN. Repeated provider
HTTP 429 responses supply no evidence of a TWF implementation defect: every probe
used one symbol, one column, no automatic retry and no unrelated remote tool; the
provider supplied no retry-after, reset, quota or limit metadata. The scope remains
UNKNOWN. This evidence gap and remote revocation cleanup are mandatory, explicit
Sprint-2 hardening items.

```ini
TRADINGVIEW_REAL_OAUTH = PASS
TRADINGVIEW_REAL_TOOL_DISCOVERY = PASS
TRADINGVIEW_REAL_SCHEMA_VERIFICATION = PASS
TRADINGVIEW_REAL_BROAD_SCREENER = PASS
TRADINGVIEW_REAL_EXACT_BATCH_TOOL_REACHED = PASS
TRADINGVIEW_REAL_EXACT_ROW = DEFERRED_EXTERNAL_RATE_LIMIT
TRADINGVIEW_REAL_EXACT_SCANRUN = NOT_PROVEN
TRADINGVIEW_REAL_EXACT_SCANMATCH = NOT_PROVEN
TRADINGVIEW_REAL_EXACT_LINEAGE = NOT_PROVEN
TRADINGVIEW_SYNTHETIC_EXACT_BATCH = PASS
TRADINGVIEW_429_NORMALIZATION = PASS
LOCAL_DISCONNECT_FAIL_CLOSED = PASS
REMOTE_REVOCATION_CLEANUP = DEFERRED_PENDING
FULL_TESTS_PASS = PREVIOUS_901_TEST_REGRESSION_APPLICABLE
DEPENDENCY_AUDIT_STATUS = NONBLOCKING_WITH_EVIDENCE
DEFERRED_HARDENING_REGISTER_COMPLETE = PASS
S2_3_FINAL_DECISION = ACCEPT_S2_3_WITH_DEFERRED_HARDENING
READY_FOR_S2_3_GIT_CHECKPOINT = YES
```

## Mandatory deferred live proof

During consolidated Sprint-2 Hardening:

1. use an appropriate later provider window for one minimal authorized exact-batch
   request;
2. if a real row is returned, pass it through production ScanRun/ScanMatch
   normalization and verify EXACT_BATCH lineage;
3. reconcile remote revocation until `cleanup_pending=false` without weakening the
   fail-closed local boundary;
4. preserve the provider 429 envelope, time/finality and dependency items in the
   hardening register.

No source change is expected unless a successful provider response proves an actual
contract discrepancy. This obligation does not block the accepted S2-3 checkpoint.

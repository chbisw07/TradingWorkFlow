# S2-3 — Deferred issues and Sprint-2 hardening register

> **2026-10-02 decommission disposition:** this register remains the historical S2-3/TradingView hardening record. TradingView broad-screener, OHLCV-retention, bar-finality, delayed/realtime, exact-batch, and successful-live-row items are no longer active runtime blockers because TradingView is decommissioned from S&D. They are closed as **DECOMMISSIONED / HISTORICAL**, not retroactively proven. Generic MCP revocation, OAuth lifecycle, provider health, dependency advisories, generation fencing, durable permits, and cleanup/recovery items remain applicable to TapTide and future MCP providers.

Date: 2026-09-30. S2-3 is **ACCEPTED / FROZEN WITH DEFERRED HARDENING**.
Sprint 2 remains ACTIVE. This register is mandatory input to consolidated
Sprint-2 Hardening after S2-4 through S2-8, internal validation, user testing and
adversarial review. Acceptance does not erase the evidence gaps or operational
obligations below.

## S2H-TV-EXACT-LIVE-01 — Successful real exact-batch normalization proof

- **Severity/status:** NONBLOCKING ACCEPTANCE EVIDENCE GAP / OPEN.
- **Scenario:** An authorized call to `mcp-tv-get-symbol-data-batch` for
  `NSE:RELIANCE` with `columns=["close"]`.
- **Context/reproduction:** Multiple controlled live attempts completed OAuth/PKCE,
  callback and authenticated MCP admission. Each issued one exact symbol/one column,
  used no automatic retry and called no unrelated remote tool. TradingView repeatedly
  returned structured provider HTTP 429, including when the MCP envelope itself had
  `isError=false`. One intervening attempt timed out before callback and made no tool
  call; that separate operational event is preserved in the acceptance record.
- **Already proven:** Real OAuth/callback, 35-tool discovery, column and broad
  screener schemas, broad real screener data, exact tool reachability and typed 429
  normalization. Deterministic tests prove successful exact-batch parsing, chunking,
  local ALL/ANY evaluation, every supported comparison, missing-symbol behavior,
  ScanRun, ScanMatch, lineage and malformed/rate-limited responses.
- **Not yet proven:** A successful real exact row, live ScanRun/ScanMatch
  normalization or live EXACT_BATCH lineage derived from that row.
- **Runtime impact:** Real exact-provider success has not been observed in the local
  acceptance environment. Real scanning remains disabled and contract-unverified by
  default unless explicitly configured.
- **Containment:** Exact-universe semantics fail closed; a 429 becomes
  `RATE_LIMITED`, never data or partial success. Source time and bar finality are not
  fabricated.
- **Why nonblocking:** Repeated requests reached the authenticated exact tool and
  produced the same external 429 without a reproduced TWF correctness defect. The
  provider supplied no retry-after, reset, quota or limit metadata, so
  `RATE_LIMIT_SCOPE=UNKNOWN` and no cause is inferred.
- **Future action:** During Sprint-2 Hardening, use one appropriate later provider
  window for a minimal authorized exact-batch call. If it succeeds, pass the actual
  row through production `TradingViewScanProvider` and record ScanRun, ScanMatch and
  EXACT_BATCH lineage. Modify source only if that response proves a contract defect.
- **Target:** Sprint-2 Hardening. Do not lose or silently close this item.

## S2H-TV-REMOTE-REVOCATION-01 — Remote revocation reconciliation

- **Severity/status:** NONBLOCKING SECURITY OPERATIONS / OPEN.
- **Scenario:** Live-probe disconnect reaches DISCONNECTED, rejects new admission and
  removes local credential authority, while provider-side revocation remains
  `cleanup_pending=true` after bounded attempts.
- **Context/reproduction:** The final authorized rate-limited exact-batch probes
  reproduced this state. Remote cleanup was attempted through the normal provider
  contract; it was never reported complete without acknowledgment.
- **Runtime impact:** The provider may retain remote grant material until its
  revocation endpoint accepts reconciliation.
- **Containment:** The encrypted local record is revoked and quarantined, the
  connection is DISCONNECTED, no active secret reference remains and new admission
  is disabled. Expiry is never treated as revocation proof.
- **Why nonblocking:** The enforceable local security boundary is fail-closed and
  cannot authorize further work. The remaining obligation is explicit, durable and
  retryable rather than hidden or misreported.
- **Future action:** Reconcile with the existing bounded cleanup path, retain audit
  evidence and confirm `cleanup_pending=false`. Never delete the encrypted record
  manually.
- **Target:** Sprint-2 Hardening / provider operations.

## S2H-TV-429-ENVELOPE-01 — Provider 429 inside successful MCP envelope

- **Severity/status:** LOW OPERATIONAL HARDENING / OPEN.
- **Scenario:** TradingView may return `success=false` and HTTP 429 text in structured
  tool content while the MCP envelope reports `isError=false`.
- **Context/reproduction:** Repeated live exact-batch calls reproduced this shape.
- **Runtime impact:** A transport-envelope-only client could mistake throttling for a
  successful tool response.
- **Containment:** TWF inspects the provider payload and maps the condition to typed
  `RATE_LIMITED`; no row normalization occurs.
- **Why nonblocking:** Current behavior is deterministic, fail-closed and covered by
  tests plus live evidence.
- **Future action:** Recheck provider documentation/metadata and preserve sanitized
  fixtures if the beta contract changes.
- **Target:** Sprint-2 Hardening / provider contract monitoring.

## S2H-DEP-CRYPTO-01 — Existing cryptography advisory baseline

- **Severity/status:** MEDIUM HARDENING / NONBLOCKING_WITH_EVIDENCE.
- **Scenario:** Runtime and development audits report seven records representing the
  same four advisories against `cryptography==47.0.0`.
- **Context/reproduction:** No dependency changed in the exact-universe correction.
- **Runtime impact:** The advisories affect specific X.509, PKCS#7 and ASN.1 paths.
- **Containment:** Current credential storage uses Fernet and does not call those
  affected paths. This is reachability evidence, not a clean audit.
- **Why nonblocking:** The vulnerable paths are not reachable in the accepted S2-3
  implementation.
- **Future action:** Perform bounded dependency/encryption compatibility work and
  reassess immediately if affected APIs become reachable.
- **Target:** Sprint-2 Hardening.

## S2H-MCP-CLOSE-FIDELITY-01 — Remote session-close error fidelity

- **Severity/status:** LOW / OPEN.
- **Scenario:** Exceptional MCP teardown may retain a generic session/availability
  label instead of the most specific remote close cause.
- **Context/reproduction:** Recorded as the earlier S23A-05 diagnostic limitation.
- **Runtime impact:** Operator diagnostics may be less specific; authorization or
  completion truth does not change.
- **Containment:** Hard deadlines, tracked cleanup, redaction and unresolved permits
  prevent false success.
- **Why nonblocking:** It is error-label fidelity, not a bypass, data corruption or
  success-promotion path.
- **Future action:** Refine bounded exception mapping without weakening teardown.
- **Target:** Sprint-2 Hardening.

## S2H-MCP-UNKNOWN-WORK-01 — Operator reconciliation of ambiguous work

- **Severity/status:** MEDIUM HARDENING / CONTAINED.
- **Scenario:** Worker loss or storage failure can leave a durable permit whose caller
  outcome is unknowable.
- **Context/reproduction:** The accepted S2-3A durability tests cover lost workers,
  close failures and reconciliation state.
- **Runtime impact:** A connection may remain blocked pending operator evidence.
- **Containment:** The permit remains UNRESOLVED; expiry is never completion proof and
  provider work is never replayed automatically.
- **Why nonblocking:** The safety model chooses explicit unavailability rather than
  false success or unsafe disconnect.
- **Future action:** Add evidence-based operator reconciliation workflows.
- **Target:** Sprint-2 Hardening / platform operations.

## S2H-SCAN-HISTORY-01 — Durable scan-status history

- **Severity/status:** LOW / DEFERRED.
- **Scenario:** Provider status returns `last_successful_scan=null`; execution timing
  and lineage are returned per run but are not persisted as product history.
- **Runtime impact:** No durable last-success display is available.
- **Containment:** The API reports null rather than inventing history.
- **Why nonblocking:** Durable product history is outside S2-3 provider integration.
- **Future action:** Persist owner-scoped run history and settings under the accepted
  product contract.
- **Target:** S2-7.

## S2H-TV-SOURCE-TIME-01 — Source time and bar finality

- **Severity/status:** DEFERRED RESEARCH / OPEN.
- **Scenario:** Current TradingView responses provide no authoritative source
  timestamp or bar-finality guarantee.
- **Runtime impact:** Exchange-time freshness and completed-bar claims cannot be made.
- **Containment:** Only `provider-current` is advertised; `source_data_time` remains
  null, freshness is UNKNOWN and bar completion is unverified.
- **Why nonblocking:** S2-3 truthfully exposes the available snapshot without making
  historical or completed-bar guarantees.
- **Future action:** Verify vendor semantics before any historical/completed-bar
  expansion.
- **Target:** Sprint-2 Hardening / later market-data architecture.

## 2026-10-02 real-evidence integration reconciliation

The later empirical diagnostic established that exact-batch data and historical OHLCV can return successfully through the authenticated TradingView MCP connection. `S2H-TV-EXACT-LIVE-01` is therefore **RESOLVED AS A PROVIDER CAPABILITY PROOF**; controlled product-flow validation for the new real-evidence bridge remains pending and must not be confused with the earlier capability proof.

The following items remain open and are carried into user validation:

- **Broad screener unreliable:** the new flow does not call or depend on it. Internal Scanner owns discovery breadth.
- **Bar finality unavailable:** provider `t` is retained, but no completed-bar claim is made; finality is `PROVIDER_UNSPECIFIED`.
- **Realtime/delayed semantics unresolved:** UI says TradingView market data and makes no realtime claim.
- **Retention rights unknown:** real provider bars are not stored durably; As Scanned retains numerical evidence and reports `RETENTION_RESTRICTED`.
- **Remote revocation cleanup pending:** local authority is removed through the accepted MCP lifecycle; provider reconciliation remains explicit.
- **Cryptography advisory disposition unchanged:** retain the evidence-based nonblocking disposition; this integration adds no dependency.
- **WebKit host/runtime issue unchanged:** Chromium remains the practical browser-validation surface until the known environment issue is resolved.

No new provider hardening item was discovered by the implementation-only phase. The 2026-10-02 controlled-run preflight was `NOT_RUN`: the active local profile had TradingView scanning and response-contract verification disabled and registered no MCP provider, so the safe runtime guard prevented remote dispatch. A later operator-configured, owner-authorized product run may add evidence or a concrete new item, but may not silently close these limitations.

## Active Dhan/TapTide hardening register — 2026-10-02

- **Dhan live validation:** run the bounded four-symbol workflow when credentials are available; zero legitimate matches is acceptable.
- **Dhan licensing:** confirm production/commercial retention and redistribution rights before any deployment beyond bounded internal evidence retention.
- **Dhan token lifecycle:** individual access tokens are owner-configured through encrypted Settings storage (with optional operator bootstrap) and expire; show `AUTH_REQUIRED` truthfully and do not invent refresh support.
- **Zerodha contract proof:** implement and independently validate a second adapter before presenting provider interchangeability as operational.
- **TapTide live validation:** authorize one bounded owner-scoped connection, validate the initial capability set and timestamps, and retain `NOT_RUN` while unconfigured.
- **TapTide plan limits/licensing:** provider-enforced plan limits and downstream data rights require operator review; cold calls are capped and successful results use a short fenced cache.
- **Generic MCP:** remote revocation cleanup, cryptography disposition, provider health, stale-generation safety, durable operation permits, hard deadlines, and disconnect recovery retain their existing dispositions.
- **Generic MCP full-suite timing stability:** three 960-test runs each produced one different deadline/cleanup-sensitive MCP failure under accumulated suite load, while the affected finalization/recovery/remediation set passed 44/44 when rerun together. Treat the backend full-regression gate as open until the timing flake is reproduced and stabilized without weakening the hard-deadline contract.

## S2H-TAPTIDE-OAUTH-DCR-01 — TapTide OAuth dynamic client registration

- **Severity/status:** LOW / DEFERRED.
- **Scenario:** TapTide's official OAuth 2.1 path uses dynamic client registration, while the accepted TWF generic OAuth contract requires explicit operator-verified endpoints and a preregistered public client.
- **Runtime impact:** TWF uses TapTide's officially supported personal bearer-token path through generic encrypted `API_KEY` storage.
- **Containment:** No endpoint, scope, client ID, secret, or callback metadata is guessed; the server-controlled seven-tool allowlist and all generic MCP safety properties remain in force.
- **Future action:** Add provider-neutral OAuth protected-resource discovery and DCR only after a separate security design and acceptance review.
- **Target:** Generic MCP hardening; not a blocker for bounded TapTide personal-token validation.

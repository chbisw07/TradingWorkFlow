# Sprint 2 Scan & Discover — consolidated hardening register

**Date:** 2026-09-30  
**Program state:** IMPLEMENTED / READY FOR USER VALIDATION  
**Purpose:** mandatory input to post-validation adversarial review and consolidated hardening

This register does not hide blockers. No known blocking invariant is open at implementation handoff. Items below preserve accepted S2-3 evidence gaps and bounded limitations discovered during S2-4 through S2-8.

## S2H-TV-EXACT-LIVE-01 — successful real exact-batch row proof

- **Component:** TradingView MCP ScanProvider.
- **Severity:** HIGH_HARDENING / open evidence gap.
- **Scenario:** Authorized `mcp-tv-get-symbol-data-batch` for one exact India symbol and one column.
- **Reproduction/context:** Repeated authorized probes reached the exact tool but TradingView returned structured HTTP 429, including an MCP envelope with `isError=false`.
- **Runtime reachability:** Real TradingView mode only; deterministic synthetic path is unaffected.
- **Impact:** A successful live exact row, production normalization, and live EXACT_BATCH lineage have not been observed locally.
- **Containment:** Real scanning remains disabled/contract-unverified by default; rate limits fail closed and never become data.
- **Why nonblocking current implementation:** OAuth, tool discovery, schemas, broad data, exact tool reachability, rate-limit normalization, and deterministic exact-batch success parsing are already proven; no TWF correctness defect was reproduced.
- **Recommended hardening:** At an appropriate provider window, run one minimal authorized exact call and pass a real successful row through the production provider.
- **Target timing:** consolidated Sprint-2 hardening.

## S2H-TV-REMOTE-REVOCATION-01 — remote revocation reconciliation

- **Component:** MCP connection lifecycle and credential operations.
- **Severity:** HIGH_HARDENING / security operations.
- **Scenario:** Local disconnect completes while provider-side cleanup remains pending.
- **Reproduction/context:** Accepted S2-3 probes left `cleanup_pending=true` after bounded remote attempts.
- **Runtime reachability:** Real connected provider accounts.
- **Impact:** Provider-side grant material may remain until remote reconciliation succeeds.
- **Containment:** Local encrypted authority is revoked/quarantined, connection is disconnected, active secret references are removed, and new admission is rejected.
- **Why nonblocking current implementation:** The enforceable local boundary is fail-closed and the outstanding operation is durable and truthful.
- **Recommended hardening:** Reconcile through the bounded cleanup endpoint until acknowledged; retain audit evidence and never delete the encrypted row manually.
- **Target timing:** consolidated Sprint-2 hardening/provider operations.

## S2H-TV-429-ENVELOPE-01 — provider 429 in a successful MCP envelope

- **Component:** TradingView MCP response normalization.
- **Severity:** LOW.
- **Scenario:** Provider content says `success=false`/HTTP 429 while MCP has `isError=false`.
- **Reproduction/context:** Reproduced in repeated live exact-batch probes.
- **Runtime reachability:** Real TradingView calls under provider throttling.
- **Impact:** A transport-only client could mistake throttling for success.
- **Containment:** TWF inspects provider content and returns typed `RATE_LIMITED`; it emits no row or partial success.
- **Why nonblocking current implementation:** Current parsing is deterministic, fail-closed, and covered by tests plus live evidence.
- **Recommended hardening:** Monitor provider contract changes and retain sanitized fixtures.
- **Target timing:** consolidated Sprint-2 hardening/contract monitoring.

## S2H-DEP-CRYPTO-01 — accepted cryptography advisory baseline

- **Component:** Python dependency baseline.
- **Severity:** MEDIUM_HARDENING / NONBLOCKING_WITH_EVIDENCE.
- **Scenario:** Audits report duplicate records for four advisories affecting `cryptography==47.0.0`.
- **Reproduction/context:** Accepted S2-3 audit; S2-4 through S2-8 add no dependency.
- **Runtime reachability:** Affected X.509, PKCS#7, and ASN.1 paths are not used by current Fernet credential storage.
- **Impact:** The dependency audit is not clean even though affected paths are currently unreachable.
- **Containment:** Current encrypted credential path does not call the affected APIs; reachability must be reassessed if usage changes.
- **Why nonblocking current implementation:** Existing accepted disposition is evidence-based and unchanged.
- **Recommended hardening:** Perform bounded upgrade/compatibility work and rerun vulnerability plus encryption tests.
- **Target timing:** consolidated Sprint-2 hardening.

## S2H-MCP-CLOSE-FIDELITY-01 — S23A-05 remote close error fidelity

- **Component:** MCP teardown diagnostics.
- **Severity:** LOW.
- **Scenario:** Exceptional remote session close may retain a generic session/availability label.
- **Reproduction/context:** Earlier S23A-05 diagnostic finding.
- **Runtime reachability:** Exceptional MCP teardown.
- **Impact:** Operator diagnosis may be less specific; authorization and completion truth do not change.
- **Containment:** Hard deadlines, tracked cleanup, redaction, and unresolved permits prevent false success.
- **Why nonblocking current implementation:** It affects error-label fidelity, not authority, data integrity, or success promotion.
- **Recommended hardening:** Refine bounded close exception mapping without weakening teardown ownership.
- **Target timing:** consolidated Sprint-2 hardening.

## S2H-MCP-UNKNOWN-WORK-01 — ambiguous provider operation recovery

- **Component:** durable MCP permits and recovery.
- **Severity:** MEDIUM_HARDENING.
- **Scenario:** Worker loss or persistence failure leaves caller/provider outcome unknowable.
- **Reproduction/context:** Accepted S2-3A lost-worker and close-failure scenarios.
- **Runtime reachability:** Process loss or storage error during an admitted provider operation.
- **Impact:** Connection can remain unavailable pending operator evidence.
- **Containment:** Permit remains `UNRESOLVED`; expiry is not completion proof and work is not replayed automatically.
- **Why nonblocking current implementation:** Explicit unavailability preserves safety and truth.
- **Recommended hardening:** Add evidence-based operator reconciliation workflows.
- **Target timing:** consolidated Sprint-2 hardening/platform operations.

## S2H-TV-SOURCE-TIME-01 — provider source timestamp and bar finality

- **Component:** TradingView market-data provenance.
- **Severity:** DEFERRED_RESEARCH.
- **Scenario:** Current provider responses lack an authoritative exchange source timestamp and completed-bar guarantee.
- **Reproduction/context:** Accepted S2-3 live/schema evidence.
- **Runtime reachability:** Real TradingView scan results.
- **Impact:** TWF cannot claim exchange-time freshness or completed bars.
- **Containment:** `source_data_time` stays null, freshness is unknown, and bar finality is not advertised.
- **Why nonblocking current implementation:** The product exposes the limitation and does not fabricate timing facts.
- **Recommended hardening:** Verify vendor semantics before historical/completed-bar expansion.
- **Target timing:** consolidated Sprint-2 hardening/later market-data architecture.

## S2H-S2-PRODUCERS-01 — deterministic context and internal-series boundary

- **Component:** Internal Scanner V0 and bounded Market Context.
- **Severity:** MEDIUM_HARDENING.
- **Scenario:** Product validation uses deterministic local series and context rather than a production independent market-data feed.
- **Reproduction/context:** Select Internal Scanner or any context validation condition in the S&D UI.
- **Runtime reachability:** Current implementation path; clearly labelled validation data.
- **Impact:** The product proves workflow, rules, persistence, and UX, but not live market usefulness.
- **Containment:** UI and provenance say deterministic/local validation; no live or neutral-value claim is made.
- **Why nonblocking current implementation:** Sprint-2 implementation explicitly permits deterministic producers and requires user validation before acceptance.
- **Recommended hardening:** Bind an independently accepted data source behind the existing provider/context contracts and repeat relevance/freshness validation.
- **Target timing:** post-user-validation hardening or later approved data-provider gate.

## S2H-S2-LLM-REMOTE-01 — remote Level-0 providers are inactive seams

- **Component:** optional LLM explanation.
- **Severity:** MEDIUM_HARDENING.
- **Scenario:** OpenAI, Anthropic, or Google may be selected in settings but no remote adapter is activated.
- **Reproduction/context:** Enable LLM and select a non-synthetic provider, then request an explanation.
- **Runtime reachability:** Explicit non-synthetic LLM configuration only.
- **Impact:** Explanation returns typed unavailable while core discovery remains functional.
- **Containment:** No silent synthetic substitution, no fabricated live facts, and no LLM authority.
- **Why nonblocking current implementation:** Level-0 is optional; the controlled provider proves grounding/provenance and disabled/unavailable behavior.
- **Recommended hardening:** Add one separately reviewed remote contributor with egress, redaction, prompt bounds, and provider-contract tests.
- **Target timing:** optional post-validation hardening.

## S2H-S2-WEBKIT-01 — WebKit host runtime validation gap

- **Component:** responsive browser validation.
- **Severity:** LOW / environment uncertainty.
- **Scenario:** Playwright WebKit aborts at navigation with an internal browser error on the current Linux host.
- **Reproduction/context:** Run the discovery browser test under the configured WebKit projects.
- **Runtime reachability:** Test host only; no application exception is reached.
- **Impact:** Safari/WebKit runtime compatibility is not independently executed in this environment.
- **Containment:** Chromium passes at 390, 768, 1024, 1440, 1920, and 2560; source uses standards-based browser APIs and CSS.
- **Why nonblocking current implementation:** This is an unchanged host/runtime limitation and user validation still precedes acceptance.
- **Recommended hardening:** Run the same suite on a supported WebKit/macOS host before final freeze.
- **Target timing:** user validation/adversarial Sprint-2 review.

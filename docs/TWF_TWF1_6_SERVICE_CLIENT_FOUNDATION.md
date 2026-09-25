# TradingWorkFlow (TWF) — TWF-1.6 Service Client Foundation

## Status and authority

Implemented and bounded remediation completed on 2026-09-25;
**pending independent acceptance re-review**. This record
does not assert acceptance or freeze. No commit, tag or push was performed.

Preflight: `main`, starting HEAD `664d4cf577c71a7319e54f566b2a4a9b5a82d0ec`, clean
working tree, no pre-existing changes. TWF-1.5 was accepted and committed at that
HEAD; no tag pointed at HEAD. Its historical implementation record is preserved.

Remediation preflight: the same branch and HEAD, with the existing uncommitted
TWF-1.6 implementation (30 files) and generated `next-env.d.ts` development type
paths already present. Those generated paths were preserved. No unrelated source
changes were found. Remediation changes only the findings, tests and this record;
README, roadmap and index milestone statuses remain accurate and unchanged.

Scope derives from [the detailed roadmap](TWF_DETAILED_ROADMAP.md#twf-16-service-client-foundation),
[service contracts](TWF_SERVICE_CONTRACT_ARCHITECTURE.md),
[service integration](TWF_SERVICE_INTEGRATION_ARCHITECTURE.md),
[configuration v0.6](TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md),
the accepted [backend](TWF_TWF1_2_BACKEND_SHELL.md),
[settings](TWF_TWF1_5_SETTINGS_FOUNDATION.md), and
[UX buckets](TWF_UX_BUCKET_ROADMAP.md). Existing TI/TM contract documents remain
the authority for their future domain integrations.

## Bounded implementation contract

| Requirement | Artifact | Evidence |
|---|---|---|
| Versioned logical service boundary | `integrations/contracts.py`: identity, request context, health, errors, protocol | Equivalent local, remote and synthetic contract tests |
| Explicit deployment form | LOCAL callable, REMOTE HTTP, SYNTHETIC adapters | Registry identity/mode validation; shared consumer |
| Four deterministic families | SyntheticScannerService, SyntheticTIService, SyntheticTMService, SyntheticLLMService | Eight typed scenarios per family, injected aware reference time, preserved synthetic provenance |
| Finite operator configuration | Validated descriptors, origin allowlist, timeout bounds and capability policy | Unsafe URL, TLS, production synthetic, unknown capability tests |
| Failure isolation | Authenticated service status, released auth read transaction, independent readiness | Failure/transaction/API tests and real loopback transport checks |
| Minimal UX-B1 surface | On-demand Service connections panel | Component, proxy and six-width browser tests |

The only operation/capability is `foundation.health`; its contract version is
`foundation.health.v1`. Provider/service version is separate. Service kinds are
SCANNER, TI, TM and LLM. No domain methods or provider SDKs exist. All four fixture
families implement the same protocol without pretending to produce live trading data.

## Layers and ownership

- `integrations/contracts.py` has no HTTP, configuration, database or provider import.
- `integrations/config.py` owns immutable operator descriptors and endpoint policy.
- `integrations/adapters.py` owns local invocation, deterministic fixtures and HTTP.
- `integrations/registry.py` consumes `ServiceClient`, applies policy and isolates
  each optional failure. Its constructor is the composition boundary for adapters.
- `api/services.py` exposes authenticated `GET /api/v1/services`. It captures the
  accepted user UUID and rolls back the authentication read transaction before
  awaiting any client. No database work occurs after that await.
- The web route proxies only to the operator-configured TWF API; the browser does
  not receive endpoints or call satellites directly.

The application factory creates descriptors/clients without network calls. HTTP
clients are owned per operation and closed on success, timeout or error, so there
is no shared cookie jar or shutdown resource. The injected local callable must be
cooperative async code; blocking synchronous work must not be put on this boundary.
The registry also bounds local/synthetic operations. Readiness remains exactly
application-initialization-only, independent of optional service health and the DB.

No persistence models, migrations, personal settings keys or profile semantics were
changed. Configuration is process/operator-owned, not user-editable Setup. No tenant
membership or commercial entitlement is inferred. A replaceable policy receives the
authenticated user UUID, registered service ID and finite capability; default grants
permit only registered health. Unknown service/capability fails closed. Later policy
can deny a check without deleting configuration.

## Operator configuration

Defaults: no configured services, no allowed remote origins, no background checks.
`TWF_SERVICE_CLIENTS` and `TWF_SERVICE_ALLOWED_ORIGINS` are JSON arrays interpreted by
the existing environment-settings loader. Descriptors include identity, explicit
mode, enabled flag, optional remote origin and bounded timeout. Changes require an
operator restart; no profile activation/rebind administration was added.

Example development fixture (no secret material):

```bash
export TWF_SERVICE_CLIENTS='[{"identity":{"service_id":"synthetic-ti","service_kind":"TI","provider":"twf-fixture","service_version":"1"},"mode":"SYNTHETIC","enabled":true}]'
```

Remote foundation test endpoint example (requires a server implementing the wire
contract below; this is not a real TI/TM endpoint):

```bash
export TWF_SERVICE_ALLOWED_ORIGINS='["https://satellite.example"]'
export TWF_SERVICE_CLIENTS='[{"identity":{"service_id":"test-ti","service_kind":"TI","provider":"test-provider","service_version":"1"},"mode":"REMOTE","enabled":true,"endpoint":"https://satellite.example","timeout_seconds":2}]'
```

Descriptors default to disabled. At most 16 unique IDs are accepted, with 0.1–10
second timeouts (default 2). Checks execute concurrently with bounded per-operation
deadlines; no retry or polling loop exists. Disabled clients are not called. LOCAL
descriptors require an explicit injected callable/client binding in the application
composition; without one they remain inactive. SYNTHETIC mode is rejected in
production. Fixture provenance also survives through LOCAL/REMOTE test adapters.

## Remote foundation wire contract

The generic remote adapter sends `GET <origin>/health` with `Accept: application/json`,
`X-Request-ID`, and `X-TWF-Contract-Version: foundation.health.v1`. HTTP transport adds
its ordinary protocol headers; no browser headers are copied. A 200 JSON response
contains exactly the typed `HealthResult`: matching identity, matching request ID,
aware UTC/offset timestamp `as_of`, health enum and boolean `synthetic`. Example:

```json
{
  "identity": {
    "service_id": "test-ti",
    "service_kind": "TI",
    "provider": "test-provider",
    "service_version": "1",
    "contract_version": "foundation.health.v1",
    "capabilities": ["foundation.health"]
  },
  "request_id": "check-1",
  "health": "AVAILABLE",
  "as_of": "2026-01-01T00:00:00Z",
  "synthetic": true
}
```

This protocol proves the foundation, not satellite API compatibility. Future
service-specific adapters must translate their public contracts into logical
results; they must not assume real TI/TM services expose this exact `/health` body.
Contract mismatches are distinct from malformed data. HTTP 401/403/503 map to typed
authentication/authorization/unavailable failures; other non-200 responses (including
redirects) map to REMOTE_ERROR. Connection failures and timeouts are distinct. JSON
content type, a 16 KiB decoded-body limit, strict field types, no extra fields,
identity and correlation checks bound response acceptance. Raw response bodies and
transport exception messages never enter public failures.

## Health and UX semantics

`configured` means a validated descriptor exists. `enabled` is the operator flag.
`active` means an enabled adapter is bound and permitted to execute, not that it is
healthy. `health` is AVAILABLE, DEGRADED, UNAVAILABLE or UNKNOWN. Disabled, unbound
and policy-denied entries have no observation and remain UNKNOWN. Failure returns
UNAVAILABLE with a typed error code; it does not fail sibling checks or readiness.

The authenticated API returns a no-store snapshot. Individual downstream failures
are typed status data inside a successful aggregate, not failures of the TWF API.
Authentication/HTTP failures still use the accepted common error envelope; the web
proxy's own unavailable error contains the complete canonical envelope:
`error.code`, `error.message`, `error.request_id`, and `error.details: null`.
Forwarded backend envelopes are unchanged.

The existing Service connections panel now checks on explicit user action, explains
that results have no trading authority/live market data, and distinguishes unchecked,
empty, disabled, inactive, unknown, available, degraded and unavailable states.
Synthetic observations are always labeled. A refresh removes the old observation
while loading or on failure. Status is a last-check snapshot, not continuous monitoring.
The frontend preserves `identity.provider` and `observation.as_of`, displays the
provider and absolute UTC observation time using a semantic `time` element, and
presents health and freshness separately (for example, **Available · stale**).
The governing documents specify no numerical freshness threshold. The bounded
TWF-1.6 presentation rule is: age from zero through five minutes inclusive is
fresh; older observations are stale. Future, invalid or timezone-less timestamps
have unknown freshness; missing observations display no valid observation time.
This is a presentation baseline, not a permanent service SLA or a second health
engine. It never changes the backend health enum. A one-shot local expiry timer
ages a displayed fresh snapshot to stale, with clock refresh on focus/visibility
changes; it adds no network polling. Text conveys freshness without relying on color.

All styles reuse accepted theme tokens. No full Setup, TI/TM workspace or UX-B2/B3
workflow is introduced; UX-B1 remains partial.

## Finite synthetic scenarios and shared semantics

`SyntheticScenario` is a finite enum selected only through typed test/development
construction (`scenario=`, `reference_time=`), not request input, environment
configuration or an administration UI. Each of the four named families accepts the
same options. Reference times must be timezone-aware and are normalized to UTC.
The deterministic default remains `2026-01-01T00:00:00Z`; it is visibly stale today.
No current-time lookup, sleep, network, retry, credential or domain payload is used.

| Scenario | Logical result | Observation |
|---|---|---|
| AVAILABLE | AVAILABLE | Reference time, synthetic |
| DEGRADED | DEGRADED | Reference time, synthetic |
| UNAVAILABLE | SERVICE_UNAVAILABLE failure | None |
| TIMEOUT | TIMEOUT failure | None |
| DENIED | AUTHORIZATION_FAILED failure | None |
| INCOMPATIBLE | CONTRACT_MISMATCH failure | None |
| STALE | AVAILABLE | Reference time minus ten minutes, synthetic |
| EMPTY | UNKNOWN | Reference time, synthetic; no domain content |

The registry converts logical failures into UNAVAILABLE status with the typed error
and no observation. Synthetic mode and identity remain visible even for failures.
Success results preserve identity, provider, aware timestamp, correlation and fixture
provenance. Shared tests also assert operation-log correlation and outcome on both
success and failure paths. The error model itself is unchanged.

`test_service_scenarios.py` independently asserts the same expected logical outcomes
for all eight scenarios across LOCAL, REMOTE and SYNTHETIC (24 cases). Local handlers
return a logical result or raise `ServiceFailure`; they do not fake HTTP. Controlled
remote responses exercise 403/503, a transport timeout and incompatible wire version.
Synthetic scenarios directly generate the corresponding result/failure. Transport
mechanisms intentionally differ. Existing real-loopback, malformed-response, 401,
header isolation and deadline tests remain. Another 32 cases check all eight
scenarios for all four families, across two correlation IDs; two cases verify
aware-time construction and sibling/readiness isolation.

Browser tests inject a test-only application factory with an explicit UTC reference:
one fresh, one stale, one unavailable and one unknown synthetic family. The browser
clock is fixed to that same reference. No runtime entry point or operator setting
was changed to make tests pass.

## Security and observability

Endpoints must be explicit HTTP(S) origins, independently included in an operator
allowlist. Paths, queries, fragments, URL credentials, control characters, wildcard,
percent/backslash ambiguity and literal link-local/multicast/unspecified IPs are
rejected. Production remote endpoints require HTTPS with normal certificate
verification. Local HTTP is available for development. Redirects are not followed;
environment HTTP proxies are ignored. Configuration does not come from request URLs.

This is an SSRF baseline, not a DNS-rebinding firewall. Operators must own DNS,
allowlist changes and network egress restrictions, including metadata access rules.
Private service-discovery destinations can be explicitly allowed. No user endpoint
editing is exposed. Remote credentials are not supported by this milestone; future
authentication must resolve the accepted secret-reference boundary server-side.

Browser cookies are allowlisted only across the web-to-TWF-API boundary; production
session cookie wins, duplicates fail closed. Neither cookies, Authorization, user
IDs, tenant IDs nor arbitrary browser headers reach a satellite. Safe request IDs
follow the accepted 64-character grammar or are generated. Logs include service ID,
operation, duration, outcome and operation correlation, never endpoints, bodies,
raw exceptions, credentials or secrets.

## Dependencies

Existing development dependency `httpx==0.28.1` is promoted to runtime for async,
bounded, testable HTTP transport. Locked `httpcore==1.0.9` and `certifi==2026.7.22`
move into the runtime closure; versions already present in the dev lock remain
unchanged. Both lockfiles were regenerated. No frontend dependency was added.

## Validation

| Check | Result |
|---|---|
| Backend pytest | 188 passed (86 accepted baseline + 44 foundation + 58 remediation cases) |
| Ruff lint / format | Passed; 47 API Python files formatted; browser API fixture also checked with API configuration |
| Strict mypy | Passed, 46 source files |
| Python compilation / pip check | Passed / no broken requirements |
| OpenAPI construction | Passed, 15 paths including the protected service-status route |
| Frontend Vitest | 71 passed across 10 files |
| TypeScript / ESLint / Prettier | Passed |
| Production Next.js build | Passed |
| Chromium Playwright | 48 passed across 390, 768, 1024, 1440, 1920 and 2560 widths |
| Docker Compose / API build / web build | Passed |
| API + web container smoke | Passed: non-root startup, explicit migration, health/ready/status, login/settings/logout, correlated errors and service status |
| Container service checks | Four labeled stale synthetic families plus one intentionally unreachable remote service; six widths and both themes |
| Documentation checks | 30 Markdown files, 163 local links/anchors, no index omissions |
| Git whitespace check | `git diff --check` passed |

Real loopback HTTP tests supplement MockTransport tests. Coverage includes shared
adapter semantics, strict wire validation, contract/correlation mismatch, endpoint
policy, finite deadlines, connection/HTTP errors, cookie isolation, authorization,
transaction release, deterministic fixtures and sanitized logs. Frontend tests cover
empty/error recovery, provider/UTC timestamp rendering, fresh/stale/unknown semantics,
exact five-minute and timezone boundaries, local expiry without polling, and the
complete proxy error envelope and header isolation. Browser checks
assert both page-level and status-panel-level horizontal containment. Screenshot
inspection found and corrected inherited mobile button overflow; final mobile and
desktop panels were visually inspected in both themes.

The original WebKit-1440 check exited before reaching the application because
`libmanette-0.2.so.0` is missing. The remediation host check still found no library;
WebKit was therefore not reattempted. This matches the known host
limitation; Safari is not verified. New browser code uses standard fetch, React,
flex layout and existing tokens; no Chromium-only API was introduced. The existing
Starlette TestClient/httpx deprecation warning remains; no unrelated dependency
migration was made.

Persistence checks are limited to the accepted disposable test database required
for authenticated smoke tests; no schema change required another PostgreSQL
migration exercise. Docker smoke resources were removed after execution. Builds,
test results and screenshots are ignored artifacts, not committed sources.

## Deliberate deferrals

Real provider connections, domain payloads, TI/TM internals, scanners, LLM inference,
broker/orders, notifications, external credential resolution, saved integration
profiles, full System/Integration Setup, billing/APS/ACS, dynamic plugins, discovery,
retries/circuit breakers, caches, background workers and event infrastructure remain
deferred. Operation-specific retries and SSE/WebSocket event contracts can be added
separately without putting streaming into the health protocol.

## Exact file inventory

Created (16), including four files added during remediation:

```text
apps/api/src/twf/api/services.py
apps/api/src/twf/integrations/adapters.py
apps/api/src/twf/integrations/config.py
apps/api/src/twf/integrations/contracts.py
apps/api/src/twf/integrations/registry.py
apps/api/tests/test_service_clients.py
apps/api/tests/test_service_scenarios.py
apps/web/src/app/api/v1/services/route.ts
apps/web/src/components/shell/service-status.tsx
apps/web/src/lib/service-freshness.ts
apps/web/tests/browser/service_fixture_api.py
apps/web/tests/browser/services.spec.ts
apps/web/tests/service-status.test.tsx
apps/web/tests/service-freshness.test.tsx
apps/web/tests/services-proxy.test.tsx
docs/TWF_TWF1_6_SERVICE_CLIENT_FOUNDATION.md
```

Modified (18):

```text
README.md
apps/api/pyproject.toml
apps/api/requirements-dev.lock
apps/api/requirements.lock
apps/api/src/twf/config/settings.py
apps/api/src/twf/integrations/__init__.py
apps/api/src/twf/main.py
apps/api/src/twf/observability.py
apps/api/tests/test_backend_shell.py
apps/web/src/components/shell/context-panel.tsx
apps/web/src/components/shell/top-bar.tsx
apps/web/src/styles/shell.css
apps/web/tests/browser/auth-test-server.mjs
apps/web/tests/browser/shell.spec.ts
apps/web/tests/shell.test.tsx
docs/TWF_DETAILED_ROADMAP.md
docs/TWF_DOCUMENTATION_INDEX.md
docs/TWF_UX_BUCKET_ROADMAP.md
```

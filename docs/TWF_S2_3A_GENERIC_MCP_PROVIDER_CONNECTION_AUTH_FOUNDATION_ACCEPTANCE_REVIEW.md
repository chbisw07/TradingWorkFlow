# S2-3A — Independent Acceptance Review

Review date: **2026-09-29**. Decision: **HOLD_S2_3A**.

Starting branch: `main`. Starting HEAD:
`e22e17ffb2ce492e2a560193a8558c15b7836018`.
Reviewed the uncommitted Generic MCP Provider Connection & Authentication
Foundation, including untracked implementation files, rather than accepting the
implementation report as proof. This review changes no runtime source or tests.

## A. Preflight

Branch, HEAD, status, complete tracked diff, untracked source/tests, diff inventory
and recent history were inspected. Changes belong to S2-3A; no unrelated work was
found. S2-2 remains frozen at the starting HEAD/tag
`twf-s2-2-internal-scanner-v0`; Broker V2 remains frozen at `69a643e` /
`twf-broker-v2`. S2-1 remains frozen at `caadc9d` /
`twf-s2-1-discovery-foundation`.

README correctly leaves S2-3 blocked pending S2-3A acceptance. S2-3A was not
prematurely marked accepted. No Git mutation was performed.

## B. Inventory and governing sources

New implementation: `integrations/mcp/{contracts,http,oauth,client,connection}.py`
and package initializer; `infrastructure/mcp.py`; `api/mcp.py`; Alembic
`0007_mcp_connections`; three MCP test modules and `mcp_support.py`; the
implementation document. Existing settings, app composition, logging, migration
imports, package declarations/locks, three inventory tests, README and three
roadmap/index documents are modified. There are 14 modified files and 14 new files
before this review record. Frontend and broker implementation are untouched.

Governing sources inspected:

- [Implementation record](TWF_S2_3A_GENERIC_MCP_PROVIDER_CONNECTION_AUTH_FOUNDATION.md).
- [Scan & Discover architecture](TWF_SCAN_AND_DISCOVER_ARCHITECTURE.md) and
  [Sprint 2 plan](TWF_SPRINT2_SCAN_DISCOVER_DELIVERY_PLAN.md).
- [Security](TWF_SECURITY_AUTH_ARCHITECTURE.md),
  [service contracts](TWF_SERVICE_CONTRACT_ARCHITECTURE.md),
  [service integration](TWF_SERVICE_INTEGRATION_ARCHITECTURE.md),
  [configuration/ownership](TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md)
  and [data architecture](TWF_DATA_ARCHITECTURE.md).
- Existing broker credential encryption, owner/session checks, generation fencing
  and cleanup behavior, plus the accepted milestones and current status documents.

Scope remains provider-neutral and backend-only. There is no TradingView business
adapter, scanning semantics, LLM, broker execution, or additional settings engine.
Personal USER ownership is implemented; unsupported shared/workspace ownership is
rejected. This is an explicit scope limit, not proof of a shared-workspace feature.

## C–G. Security, OAuth, credentials and transport

The foundation has useful boundaries: registered operator-controlled destinations,
public-address pinning with original TLS SNI/Host, HTTPS-only exact URLs, no proxy
inheritance or redirects, encrypted owner-bound references, explicit generation
checks, authenticated same-origin writes, safe errors, bounded response/schema
sizes, and no public arbitrary tool invocation route.

OAuth state uses 256-bit randomness; stored state is hashed and the S256 verifier
is encrypted and bound to the connection/owner/session/generation. Callback claim
clears the verifier and is committed before provider I/O. Owner changes, expired
or revoked sessions, wrong/missing/replayed state, stale generations and competing
callbacks are rejected. A separate reviewer probe changed the encrypted verifier
while preserving its other bindings; the synthetic authorization server rejected
the mismatched challenge, yielding `AUTHENTICATION_FAILED` with no token attached.

The OAuth surface is explicitly a preregistered public-client foundation with
operator-verified metadata. The same-origin POST callback conduit still needs its
future browser landing page. Confidential-client grants, dynamic registration and
shared ownership are not claimed or required for this bounded acceptance.

Credentials use the existing Fernet cipher and deployment key. Plaintext token
values do not enter status/settings contracts. Reference owner, provider,
connection, generation and revocation bindings are checked. This storage design
passes, but lifecycle behavior around already-known credentials does not; see
S23A-02 and S23A-03.

Discovery does not grant authority. Exact server-owned `ToolPolicy` names are
required, unknown/write-like tools are denied, and argument/schema checks run
before invocation. Actual SDK tests prove discovery of `read_demo` and
`write_demo`, successful allowed reads, and denial without dispatch for a
write-like tool. These authority gates pass.

The manager's explicit-operation and result fences reject stale attachments and
results. They do **not** fence every SDK-generated HTTP request. The actual SDK
starts a GET stream after initialization and can reconnect it with the captured
Authorization header. Likewise, SDK context teardown defeats the claimed total
operation deadline in a reproduced case. These are bounded remediation issues,
not a need to replace the overall architecture.

### Exact additional probes and observed results

All probes used the installed official SDK, in-memory `httpx2.MockTransport`,
synthetic credentials and disposable databases. No external provider or broker
was contacted. Temporary reproductions and outputs are under
`/tmp/twf-s23a-review/`; these are review-session evidence, not repository tests.

1. **Disconnect during failed refresh** (`probes.py`): connect OAuth G1; pause the
   refresh token endpoint after the G2 claim; disconnect G2; then return HTTP 400
   from the refresh endpoint. Observed zero revocation calls, zero remaining secret
   rows, `cleanup_pending=false`, DISCONNECTED, and `AUTHENTICATION_FAILED` from
   refresh. The old credentials were known locally before the request; this is
   distinct from an unknowable token whose response was lost.
2. **Second-manager recovery** (`extra.py`): the same pause/disconnect sequence
   through a newly constructed manager also produced zero revocations and no
   cleanup pending. Durable state does not preserve the cleanup obligation.
   This models manager restart/recovery against the same DB, not an OS crash test.
3. **Provider retains token values on reauthorization** (`extra.py`): authorize G1,
   reauthorize G2 with the same provider-issued token values, prove tools work,
   then clean up G1. Two remote revocations occur while G2 still reports CONNECTED.
   A fixture that honors revocation returns `AUTH_REQUIRED` on the next tool check.
4. **SDK reconnect after disconnect** (`transport_probes.py`): API-key connection;
   pause `tools/list`; return an SSE GET response with an event ID and `retry: 10`,
   then EOF; disconnect; wait 70 ms before releasing the list response. Repeated
   runs observed six/seven authenticated GET requests starting after disconnect.
   The caller eventually receives `STALE_GENERATION`, so stale result attachment
   is blocked, but outbound stale credential use has already happened. This probe
   does not claim a write-tool replay was observed.
5. **Slow termination after timeout** (`transport_probes.py`, `deadline.py`): set
   an 80 ms operation timeout; delay `tools/list` 300 ms; stream a DELETE response
   in small delayed chunks. Returns after approximately 310–315 ms with
   `SERVICE_UNAVAILABLE`, rather than timely `TIMEOUT`. Instrumentation shows
   DELETE starts around 83 ms. This demonstrates a deadline escape during SDK
   unwinding. A control with an immediate DELETE response returned TIMEOUT in
   88 ms. It does not claim that every timeout or teardown is unbounded.
6. **Remote session closure** (`probes.py`): after initialize establishes a session,
   return HTTP 404 for `tools/list`. Actual result is `INVALID_RESPONSE`, rather
   than distinguishing a closed remote session with `CONNECTION_CLOSED`.
7. **Wrong PKCE and redaction** (`extra.py`): corrupted verifier rejected; DEBUG
   enabled for MCP/HTTP library logger namespaces; TWF structured logging captured
   two operation records. Synthetic access/refresh tokens, original/replaced
   verifier, state and authorization-code sentinels are absent. Source review
   also confirms suppression of raw SDK payload logging and metadata-only TWF
   logging. No confidential-client secret flow exists in this slice.

## H. Dependency advisory assessment

Independent audit is **not clean**: seven records collapse to four distinct
advisories for installed/locked `cryptography==47.0.0`. No advisory was reported
for the added MCP packages. Existing provenance alone does not waive a finding.
The table assesses actual runtime reachability, not package-level safety.

| Advisory                                                                                                                             | Affected / fixed                                                     | Vulnerable functionality and prerequisites                                                                                                                      | TWF reachability / classification                                                                                                                                                                                                                                                                                                | Severity and remediation                                                                                                                                                    |
| ------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [GHSA-m2h6-j472-rp4c](https://github.com/pyca/cryptography/security/advisories/GHSA-m2h6-j472-rp4c), CVE-2026-69248, PYSEC-2026-3554 | Through 48.0.0; fixed 49.0.0                                         | Cryptography X.509 verification accepts a wildcard certificate outside permitted DNS name constraints; requires a crafted chain processed by that verifier.     | TWF does not call the cryptography X.509 verification API. MCP TLS uses Python `ssl`, not this verifier. **NOT_APPLICABLE** to the reviewed S2-3A path.                                                                                                                                                                          | Upstream Low. Upgrade before introducing this certificate-verification functionality; include in the bounded baseline upgrade.                                              |
| [GHSA-jwv3-5hgf-82ww](https://github.com/pyca/cryptography/security/advisories/GHSA-jwv3-5hgf-82ww), CVE-2026-69249, PYSEC-2026-3553 | Through 48.0.0; fixed 49.0.0                                         | Exponential X.509 path construction with crafted duplicate self-signed intermediate certificates; requires untrusted chains reaching the cryptography verifier. | No such certificate-chain verification path in TWF's MCP client. **NOT_APPLICABLE** to this path.                                                                                                                                                                                                                                | Upstream Low, availability impact. Include in baseline upgrade; do not add a vulnerable verifier path.                                                                      |
| [GHSA-g6cj-pr64-35w5](https://github.com/pyca/cryptography/security/advisories/GHSA-g6cj-pr64-35w5), CVE-2026-69247, PYSEC-2026-3552 | Introduced 44.0.0; affected before 50.0.0; fixed 50.0.0              | RSA PKCS#1 v1.5 oracle in PKCS#7 envelope decryption APIs, requiring attacker-controlled encrypted envelopes and repeated observable decryptions.               | TWF uses Fernet AES/HMAC, not `pkcs7_decrypt_der/pem/smime`. Fernet's block padding is not this RSA envelope API, and its HMAC is verified before decryption. **NOT_APPLICABLE** to this path.                                                                                                                                   | Upstream Moderate. A complete upgrade covering all four requires 50.0.0 or a later compatible patched release.                                                              |
| [GHSA-537c-gmf6-5ccf](https://github.com/pyca/cryptography/security/advisories/GHSA-537c-gmf6-5ccf), CVE-2026-34180                  | Affected binary wheels from 0.5 to before 48.0.1; fixed wheel 48.0.1 | Bundled OpenSSL ASN.1 decoder heap over-read on 64-bit Unix; requires an ASN.1 primitive exceeding 2 GB passed to affected `d2i_*` decoders.                    | Installed cryptography links affected OpenSSL 4.0.0, but the Fernet path does not decode ASN.1. MCP consumes bounded JSON, not these envelopes/certificates. Python TLS separately links OpenSSL 3.0.13; it does not use the wheel's library. No qualifying S2-3A decoder input path was found. **NOT_APPLICABLE** to this path. | GitHub Moderate; OpenSSL rates the underlying issue Low. Patch the wheel in baseline maintenance. Separate system OpenSSL maintenance is not solved by upgrading the wheel. |

The [OpenSSL primary advisory](https://openssl-library.org/news/secadv/20260609.txt)
confirms the large-input prerequisite and affected decoder family. Runtime library
versions were independently inspected. Repository searches found cryptography
usage in the existing Fernet credential cipher, with no PKCS#7 decryption or
cryptography `PolicyBuilder` use. The SDK's installed JWT/server dependencies are
not an application JWT or certificate-verification path in this client composition.

These are code-reachability assessments, not exploits or a blanket certification
of the environment. **CRYPTOGRAPHY_ADVISORIES_STATUS = NONBLOCKING_WITH_EVIDENCE**.
A bounded, separately reviewed upgrade to at least 50.0.0 is recommended, including
the current `<48` constraint, both locks, Fernet backwards-decryption checks and
full regression. A safe drop-in upgrade has not been proven during this review;
no dependency was changed. Based on current reachability, that upgrade is not a
prerequisite for this S2-3A acceptance decision. Reassess before expanding crypto
usage and retain the implementation document's production-maintenance caveat.

## I. Scorecard

```ini
S2_3A_SCOPE_DISCIPLINE = PASS
OWNER_SCOPED_CONNECTION_IDENTITY = PASS
AUTH_STRATEGY_ABSTRACTION = PASS
OAUTH_STATE_PKCE = PASS
CALLBACK_OWNER_BINDING = PASS
GENERATION_FENCING = FAIL
SECURE_TOKEN_STORAGE = PASS
TOKEN_REFRESH_MODEL = FAIL
REVOCATION_DISCONNECT = FAIL
CLEANUP_PENDING_MODEL = FAIL
MCP_TRANSPORT_BOUNDARY = FAIL
DISCOVERY_AUTHORITY_SEPARATION = PASS
TOOL_ALLOWLIST = PASS
MCP_TYPED_FAILURES = FAIL
MCP_HEALTH_MODEL = PASS
MCP_SETTINGS_ALIGNMENT = PASS
SERVICE_CLIENT_REUSE = PASS
SYNTHETIC_MCP_PROOF = PASS
MCP_RESTART_RECOVERY = PASS
MCP_PERSISTENCE_CONCURRENCY = FAIL
MCP_SECRET_REDACTION = PASS
SECURITY_REGRESSION_FREE = PASS
S2_3A_TEST_QUALITY = FAIL
REGRESSION_FREE = PASS
S2_3A_DOCUMENTATION_ACCURATE = FAIL
CRYPTOGRAPHY_ADVISORIES_STATUS = NONBLOCKING_WITH_EVIDENCE
```

Restart PASS means revoked/stale local bindings do not become active after manager
recreation; interrupted-refresh cleanup fails under its separate gates.
Persistence/concurrency FAIL concerns the refresh/disconnect/cleanup interleaving,
not a failure of PostgreSQL callback locking or SQLite claim serialization.
Regression PASS means the existing 722-test baseline remains green; it does not
mean new S2-3A behavior is defect-free. Health remains an explicit last-check model,
not a guarantee that a remote token is currently valid.

The 53 new cases exercise meaningful negative paths and the actual SDK. However,
they do not cover SDK reconnection after disconnect, retained-token reauthorization
cleanup, failed-refresh/disconnect interleaving, or slow teardown after deadline.
Counting mock revocation calls without making the fixture invalidate credentials
misses the current-token revocation defect. Test quality is insufficient for this
security-sensitive acceptance until these cases are added.

## J. Findings

| ID      | Severity | Timing               | Area/File                                                          | Finding                                                                                                                                                                                                                                        | Required Action                                                                                                                                                                                                                                                                                                                       |
| ------- | -------- | -------------------- | ------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| S23A-01 | HIGH     | MUST FIX BEFORE S2-3 | `integrations/mcp/client.py:91`, `http.py:52`, `connection.py:616` | SDK GET reconnects dispatch captured credentials after durable disconnect. Manager fences reject the eventual result but do not prevent those requests. `retry_count=0` does not control SDK reconnection.                                     | Fence each credential-bearing dispatch, account for SDK background/reconnect traffic and cancel or retire superseded sessions. Specify any permitted terminal cleanup separately. Prove no new authenticated GET/POST dispatch after disconnect/session revocation or generation replacement. Do not introduce automatic tool replay. |
| S23A-02 | HIGH     | MUST FIX BEFORE S2-3 | `connection.py:515`, `connection.py:557`                           | Refresh retires old credentials with `revoke_pending=False` before the result is known. Concurrent disconnect/cleanup deletes them without remote revocation; the later failed refresh cannot restore cleanup because its generation is stale. | Persist an explicit in-flight-refresh cleanup obligation. Disconnect must preserve/revoke all relevant known credentials; cleanup cannot discard them merely because refresh started. Cover failed/cancelled refresh, independent-manager recovery and SQLite/PostgreSQL interleavings.                                               |
| S23A-03 | MEDIUM   | MUST FIX BEFORE S2-3 | `connection.py:255`, `connection.py:557`, `oauth.py:148`           | Reauthorization can return the same token material as the previous generation. Cleaning up the previous reference remotely revokes the active generation's token.                                                                              | Make retirement/revocation aware of credentials still backing an active or pending generation, including concurrency. Use a revocation-enforcing fixture for both retained and rotated token cases. Avoid replacing this with unconditional deletion that loses remote cleanup.                                                       |
| S23A-04 | HIGH     | MUST FIX BEFORE S2-3 | `client.py:91`, `client.py:94`, `http.py:129`, `connection.py:645` | SDK context cleanup escapes the 80 ms total deadline and masks timeout as `SERVICE_UNAVAILABLE` in the slow-termination reproduction.                                                                                                          | Bound initialization, streaming and teardown within a defined total budget; preserve cancellation and typed TIMEOUT. Add elapsed-time tests for slow response/termination and regression tests for normal closure.                                                                                                                    |
| S23A-05 | LOW      | SAFE TO DEFER        | `http.py:137`                                                      | Remote MCP session HTTP 404 becomes INVALID_RESPONSE through SDK error -32600 rather than a distinct closed-session outcome.                                                                                                                   | Normalize remote closure without exposing provider text; add a real-SDK session-404 test. This alone does not hold acceptance.                                                                                                                                                                                                        |
| S23A-06 | NOTE     | SAFE TO DEFER        | `pyproject.toml`, `requirements*.lock`                             | Four package advisories remain, with no reachable vulnerable functionality identified in this MCP path.                                                                                                                                        | Track a bounded cryptography baseline upgrade and retest persisted ciphertext compatibility; reassess if cryptography use expands.                                                                                                                                                                                                    |

Correct the implementation document's no-retry, deadline and cleanup claims when
remediating S23A-01 through S23A-04. Do not resolve documentation inaccuracies by
weakening the security requirements. No cosmetic issue is used to hold acceptance.

## K. Independent validation

| Check                           | Result                                                                                                                                                                                                                                                                                                                                |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Full pytest                     | **775 passed in 105.43 seconds**, no warnings; includes existing Broker/auth/settings/service-client/S2-1/S2-2 suites and 53 new MCP cases.                                                                                                                                                                                           |
| Ruff lint / format              | PASS; 106 Python files already formatted.                                                                                                                                                                                                                                                                                             |
| Strict mypy                     | PASS; 105 checked files.                                                                                                                                                                                                                                                                                                              |
| Compilation / imports / OpenAPI | PASS; 39 paths, 63 component schemas.                                                                                                                                                                                                                                                                                                 |
| Dependency consistency          | `pip check` PASS.                                                                                                                                                                                                                                                                                                                     |
| Dependency audit                | NOT CLEAN; seven records, four distinct advisories assessed above.                                                                                                                                                                                                                                                                    |
| Offline package build           | PASS, sdist and wheel, with repository-compatible build tooling in a temporary environment. Existing API venv setuptools 84 does not satisfy the declared `<83` build requirement.                                                                                                                                                    |
| SQLite                          | Migration/lifecycle and five repeated four-way callback race cases pass in the full suite; additional adversarial lifecycle probes fail as recorded.                                                                                                                                                                                  |
| PostgreSQL 16                   | Disposable container: upgrade, repeat upgrade, downgrade to 0006, re-upgrade and Alembic metadata check PASS. Five four-way callback races each yield one success/three STALE; five two-way refresh races each yield one success/one STALE. Successful restart/discovery/disconnect lifecycle checks PASS. Provider I/O is synthetic. |
| Security probes                 | Positive owner/state/tool/redaction checks pass; four blocking lifecycle/transport findings reproduced independently.                                                                                                                                                                                                                 |
| Documentation                   | All six changed/new Markdown files pass formatting; 160 local link targets resolve, including the review record. Content accuracy fails as described.                                                                                                                                                                                 |
| Whitespace                      | `git diff --check` PASS.                                                                                                                                                                                                                                                                                                              |
| Frontend                        | Untouched; frontend/browser tests not applicable.                                                                                                                                                                                                                                                                                     |

Migrations and concurrency used disposable databases only. No real provider, broker
call, financial action, or developer database access was required. Synthetic tests
do not certify real-provider registration/browser OAuth behavior. Review scripts,
logs, audit JSON, package artifacts and source snapshot are under `/tmp`; they are
not committed deliverables.

## L–N. Reviewer changes

Created exactly:

`docs/TWF_S2_3A_GENERIC_MCP_PROVIDER_CONNECTION_AUTH_FOUNDATION_ACCEPTANCE_REVIEW.md`

Existing repository files modified by reviewer: **NONE**.
Runtime source changed by reviewer: **NO**.
Dependencies/tests modified by reviewer: **NO**.
No commit, tag, push, merge, rebase, cherry-pick or reset was performed.
The pre-review SHA-256 manifest comparison confirms every original repository
file is unchanged; the only added file is this review record. No status document is promoted on a HOLD decision.

## O–Q. Decision, authorization and Git recommendation

**HOLD_S2_3A**.

Can TradingView now be integrated as the first real authenticated MCP provider
without provider-specific authentication infrastructure or weakening TWF security?
**Not yet.** The generic architecture is suitable, but the four bounded transport
and credential-lifecycle defects must be fixed and independently re-reviewed.

S2-3 remains **BLOCKED / PENDING S2-3A ACCEPTANCE**. This review authorizes no
TradingView integration, other provider work, Market Intelligence, LLM, TI, TM,
LOB, broker execution from S&D, autonomous trading or production ML.

Recommended Git action: do not freeze/tag S2-3A as accepted or unblock S2-3 now.
After remediation and a passing focused review, the user may authorize committing
the implementation plus review documentation and optionally an S2-3A freeze tag.
No Git action is performed by this review.

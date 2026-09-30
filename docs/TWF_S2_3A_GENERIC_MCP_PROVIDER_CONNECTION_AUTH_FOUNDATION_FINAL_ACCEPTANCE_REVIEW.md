# S2-3A final independent acceptance re-review

## Decision

**HOLD_S2_3A**. Two reproduced persistence failure paths prevent acceptance. S2-3 remains **BLOCKED**. The approved durable-permit/draining architecture remains appropriate; bounded failure-handling remediation is required.

The central acceptance question is answered **NO**: ordinary draining, public deadlines, and successful durable finalization work, but auth-fence write failure and lost completion reconciliation do not remain truthful across workers/restarts.

## Preflight and review boundary

- Review date: 2026-09-29.
- Branch: `main`.
- `REVIEW_START_HEAD = e22e17ffb2ce492e2a560193a8558c15b7836018`.
- HEAD matches the S2-2 baseline and `twf-s2-2-internal-scanner-v0` tag.
- Preflight commands: branch, HEAD, short status, diff stat, diff name-status, and ten-entry decorated log.
- Initial inventory: **37 paths**, comprising 14 tracked modifications and 23 untracked files. These are the S2-3A implementation, remediation, and documentation; no unrelated changes were identified.
- Source, tests, manifests, locks, existing documentation, and historical reviews were not edited. No commit, tag, push, merge, rebase, cherry-pick, or reset was performed.
- Independent probes used disposable SQLite databases and an isolated PostgreSQL 16 container. No normal development database was migrated. No real MCP provider or broker calls were made.

The [initial acceptance review](TWF_S2_3A_GENERIC_MCP_PROVIDER_CONNECTION_AUTH_FOUNDATION_ACCEPTANCE_REVIEW.md) and [focused re-review](TWF_S2_3A_GENERIC_MCP_PROVIDER_CONNECTION_AUTH_FOUNDATION_REREVIEW.md) preserve the earlier HOLD history: dispatch/generation fencing, deadline truth, and later durable-finalization concerns. Neither historical record is rewritten by this review. The [implementation record](TWF_S2_3A_GENERIC_MCP_PROVIDER_CONNECTION_AUTH_FOUNDATION.md) supplies the corrected contract, but its reported tests are not treated as independent acceptance evidence.

Governing boundaries were checked against the security/auth, service-contract, service-integration, and data architecture documents. Provider I/O must remain outside database transactions; permits and credentials remain owner/connection/generation scoped; MCP discovery does not confer execution authority.

## Findings

| ID            | Severity | Timing               | Area/File                                          | Finding                                                                                                                                                                                                                              | Required Action                                                                                                                                                                                                                  |
| ------------- | -------- | -------------------- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| S23A-FINAL-01 | BLOCKING | MUST FIX BEFORE S2-3 | `connection.py:1002–1027`, completion at `777–790` | Failure to persist the auth fence is swallowed. Finalization can close the permit while the connection remains CONNECTED/enabled, permitting new authenticated work.                                                                 | Make auth invalidation durable before releasing its admission-blocking evidence; retain explicit unresolved/fenced recovery when invalidation cannot be committed. Cover a transient auth-fence write failure on both databases. |
| S23A-FINAL-02 | BLOCKING | MUST FIX BEFORE S2-3 | `connection.py:777–827`; `lifecycle.py:120–172`    | COMPLETE/SUCCESS can commit before caller decision reconciliation. Lost acknowledgment plus failed repair, or process loss after caller timeout/cancellation, leaves a clean-looking SUCCESS with no recoverable outstanding permit. | Durably represent pending/ambiguous final-decision reconciliation and recover it without replaying provider work. Add post-commit acknowledgment-loss/repair-failure and real-worker-loss tests on both databases.               |

### S23A-FINAL-01: failed auth fence reopens ordinary authority

Independent probe: API-key G1 connection; real MCP SDK path against a synthetic HTTP 401 provider. Inject exactly one typed storage failure in the transaction containing `fail.save`; allow subsequent transactions to succeed.

Observed in **three repetitions per database, six total**:

1. Caller receives `AUTH_REQUIRED`.
2. Connection remains `CONNECTED`, `enabled=true`, generation 1.
3. Its operation is `COMPLETE / AUTH_REQUIRED`; pending operations are zero and recovery is false.
4. A recreated manager admits another operation with the same generation and retained credential. With the synthetic provider returning 200, it physically sends `initialize`, `notifications/initialized`, and `tools/list`, and returns SUCCESS.

`fail()` catches `Failure` without retaining a durable fence. Completion records unavailable health/error but does not itself close new admission. The authoritative admission predicate still accepts CONNECTED/enabled. This is one transient invalidation-write failure, not an assumption of permanent database unavailability.

Smallest bounded remediation: do not release the failed operation's durable admission-blocking evidence until the required auth transition is committed or explicitly recoverable. An auth-aware finalization transaction or equivalent durable recovery fence must prevent a new worker from admitting work. A process-local flag is insufficient.

### S23A-FINAL-02: final commit can outrun durable caller truth

`settle.decide` marks the permit COMPLETE and records SUCCESS at commit. A later negative caller outcome is repaired only after commit delivery to the owning task. That task is tracked in memory, but a committed COMPLETE permit no longer exposes pending reconciliation durably.

Two independent variants reproduced this gap:

- **Lost acknowledgment plus failed recovery write: six cases**, three per database. Let the actual settle transaction commit, then inject a typed storage failure in place of its acknowledgment and fail the fallback unresolved write. Caller receives `SECRET_STORE_UNAVAILABLE`; DB remains `COMPLETE / SUCCESS`, provider outcome SUCCESS, pending zero, recovery false. A recreated manager can disconnect instead of observing an unresolved final decision. The disconnect response's own cleanup permit is separate from the already-COMPLETE failed invocation.
- **Actual child-process loss: twelve cases**, three per TIMEOUT/CANCELLED outcome per database. Pause the worker after the real settle commit, before acknowledgment delivery. Let the caller reach its final TIMEOUT or cancellation, then exit the child process before reconciliation runs. The parent reads `COMPLETE / SUCCESS`, provider outcome SUCCESS, CONNECTED, and zero pending permits. No SUCCEEDED audit was emitted. TIMEOUT returned at **400.81–402.61 ms** for a 400 ms budget; this probe targets persistence, not the separate 80 ms deadline test.

The fallback comment that prior RUNNING/FINALIZING evidence remains fail-closed is incorrect once settle has already committed. An UNRESOLVED log alone does not make the permit discoverable by restart recovery.

Smallest bounded remediation: preserve a durable, recoverable representation of an unacknowledged or unreconciled final decision. Where worker loss makes the precise caller outcome unknowable, retain a truthful unresolved state rather than claiming clean SUCCESS. This does not require impossible atomicity between a database and the HTTP caller, exactly-once audit delivery, or a database lock across provider I/O. It does require that restart recovery can distinguish ambiguity from confirmed completion, without replaying the provider operation.

## Corrected draining contract and independent controls

Admission grants authority to drain under the admitted generation. Already-admitted G1 work may physically send during REAUTH_DRAINING. The zero-send assertion applies after final retirement, while new admission must close when draining begins.

| Independent probe                      |                                                   Cases | Evidence                                                                                                                                                                                                                                                                                                                                                                                                                   |
| -------------------------------------- | ------------------------------------------------------: | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Paused-before-send auth drain          |                        10: five SQLite, five PostgreSQL | A paused after the final authority check committed. B received actual synthetic HTTP 401. New C was rejected in REAUTH_DRAINING. A sent under retained G1 while draining; its result did not restore success. Final retirement advanced generation, removed the active secret, and rejected old-G1 sends.                                                                                                                  |
| Multiple admitted operations           |                                   6: three per database | Two operations remained accounted for. First completion left one pending permit and retained G1/secret; only the final completion allowed retirement. No old-generation send after final invalidation.                                                                                                                                                                                                                     |
| Lost worker during auth drain          | 4: before dispatch and during dispatch on each database | Real process exit left the admitted permit visible. Simulated elapsed deadline did not prove completion; REAUTH_DRAINING/recovery remained explicit and new work was rejected.                                                                                                                                                                                                                                             |
| 80 ms caller deadline / owned teardown |                                                      20 | Four repetitions each of fast provider with slow shielded close, slow provider, near-deadline provider error, error during close, and cancellation during shielded close. Actual HTTPcore2 pool teardown was delayed. Sixteen TIMEOUT samples: minimum 80.434 ms, median 81.019 ms, maximum 82.276 ms. Four cancellations returned promptly. Cleanup remained owned at return and later completed. No late caller SUCCESS. |

Equivalent authority locks were acquired from independent database sessions while provider work was blocked, including PostgreSQL. No admission row lock or transaction intentionally spans provider I/O.

These positive controls establish the normal committed-drain contract. They do not excuse S23A-FINAL-01, where the required fence never commits, or S23A-FINAL-02, where terminal bookkeeping loses durable reconciliation ownership.

## Durable outcomes, audits, and test quality

The provider-outcome column is separate from the authoritative outcome. Once a negative outcome is actually durable, the locked permit predicate prevents later provider success from replacing it. Auth invalidation that commits before completion remains authoritative. Late provider results are quarantined, and public timeout is final.

Completion failure returns a sanitized typed failure, not caller SUCCESS. SUCCEEDED audit occurs after durable completion and the final deadline check. The independent timeout, cancellation, auth invalidation, and storage-failure probes did not emit an ordinary success audit. Audit delivery is not an exactly-once transactional outbox; that is not required.

The 33 new finalization cases use meaningful SDK paths, commit barriers, cancellation, auth-drain, persistence-failure, and audit assertions. Their SQLite/PostgreSQL runs pass. They omit the transient auth-fence write failure, successful commit with lost acknowledgment and failed repair, and worker death after final commit before negative reconciliation reproduced here. Consequently, test quality is insufficient for final security/concurrency acceptance despite the green regression suite.

Ordinary lost RUNNING/FINALIZING permits remain safe across restart. The restart failure in the scorecard concerns the clean-looking COMPLETE record in S23A-FINAL-02. Likewise, durable-negative monotonicity passing does not mean every negative caller result was durably recorded.

## Migration and schema review

Migration `0010_mcp_provider_outcome` correctly follows `0009_mcp_operation_permits` and adds a nullable `String(40)` provider-outcome column. Existing rows are not backfilled with fabricated provider success. Migration 0008's cleanup claim remains bounded bookkeeping, not provider authority across I/O.

Fresh disposable SQLite and PostgreSQL 16 checks passed:

- Populate migration 0009 with an existing user, connection at generation 17, opaque secret reference, and COMPLETE/TIMEOUT permit.
- Upgrade to 0010; preserve connection identity/generation/secret reference and negative outcome; provider outcome remains NULL for the old row.
- Reject downgrade for RUNNING, FINALIZING, UNRESOLVED permits and REAUTH_DRAINING connections.
- Perform supported 0010 → 0009 → 0010 round trip and repeat upgrade.
- Run Alembic metadata comparison: no new upgrade operations detected on either backend.

The supported downgrade drops the added provider diagnostic column; it does not rewrite an existing negative authoritative outcome to success. No development database was used.

## Validation executed independently

| Check                                   | Result                                                                                                                   |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Full backend pytest                     | **846 passed**, 118.83 seconds; no warnings                                                                              |
| SQLite/PostgreSQL focused matrix        | **128 passed**, 33.61 seconds: 66 executions of the 33 new finalization cases plus 62 prior permit/refresh/cleanup cases |
| Independent probes                      | 64 cases: 24 reproduced failure cases and 40 positive controls; not added to the repository test suite                   |
| Ruff lint                               | PASS                                                                                                                     |
| Ruff format check                       | PASS, 113 files                                                                                                          |
| Strict mypy                             | PASS, 112 source files                                                                                                   |
| Python compilation/import               | PASS for source, tests, and Alembic; application import/OpenAPI construction passed                                      |
| OpenAPI                                 | PASS, 39 paths and 63 schemas; MCP routes and REAUTH_DRAINING schema present                                             |
| pip check                               | PASS, no broken requirements                                                                                             |
| Offline package build                   | PASS, wheel and sdist, no-isolation build in the available build environment                                             |
| SQLite/PostgreSQL migration lifecycle   | PASS, including data preservation and downgrade guards above                                                             |
| Refreshed runtime/dev dependency audits | Completed; known cryptography findings remain, detailed below                                                            |
| Documentation formatting/local targets  | PASS, eight Markdown files formatted; 172 local link targets exist (external URLs and fragment anchors not validated)    |
| git diff --check                        | PASS at review completion                                                                                                |

Existing S2-1/S2-2, Broker V2, MCP refresh/cleanup, owner isolation, PKCE/state/replay, callback binding, encrypted secret storage, redaction, server tool allowlist, and discovery/authority separation regressions pass. No broker or real-provider runtime verification is claimed. No Docker API build was required or claimed in this review.

Temporary reproducer scripts and logs are retained locally under `/tmp/s23a-final-review/`: `auth-drain`, `multi`, `lost-auth-worker`, `deadlines`, `faults`, `crash`, and `migrations`, plus suite/audit/build logs. These are review artifacts, not committed tests or permanent repository evidence.

## Dependency disposition

Both advisory feeds refreshed successfully. Runtime lock audit inspected 44 packages; dev lock audit inspected 55. Each reports **seven advisory records representing four distinct advisories**, all for `cryptography==47.0.0`. Duplicate PYSEC/GHSA alias records must not be counted as separate vulnerabilities. The audit exit status is nonzero because vulnerabilities are reported, not because refreshing failed.

Distinct advisories: `GHSA-m2h6-j472-rp4c`, `GHSA-g6cj-pr64-35w5`, `GHSA-jwv3-5hgf-82ww`, and `GHSA-537c-gmf6-5ccf`. No additional vulnerable package was reported. Dependency manifests and lockfiles match the corrected-remediation preflight baseline; this review changed none.

Retain **NONBLOCKING_WITH_EVIDENCE**, not CLEAN. The accepted historical reachability disposition remains: the integration uses the existing Fernet encrypted-store path rather than the affected certificate/PKCS7 paths; no new reachability evidence was found. Local evidence identifies Python TLS OpenSSL 3.0.13 and cryptography's bundled OpenSSL 4.0.0 separately. This review does not broaden the accepted exception or recommend suppressing the audit.

S23A-05 remote-session-close error fidelity remains **LOW / SAFE TO DEFER**: a remote closed-session 404 can be mapped to INVALID_RESPONSE rather than CONNECTION_CLOSED; this does not confer provider authority or bypass a tool allowlist.

## Documentation accuracy and authorization

README, both roadmaps, and the documentation index correctly keep S2-3A unaccepted and S2-3 blocked. The implementation record explains REAUTH_DRAINING, generation retention, provider/final-outcome separation, migration 0010, owned teardown, and the non-clean dependency disposition.

Its finalization/recovery assurance is too strong: around lines 855–863 it says failed fallback persistence retains RUNNING/FINALIZING evidence, but S23A-FINAL-02 leaves COMPLETE/SUCCESS. Its universal auth-fence claims also omit S23A-FINAL-01. The corrected implementation evidence must be updated with bounded remediation; historical review records should remain intact.

S2-3 receives **no authorization** from this review. TradingView MCP integration, other scan providers, market/event intelligence, LLM/TI/TM/LOB work, broker execution from Scan & Discover, autonomous trading, and production ML remain outside this review. Defer an acceptance/freeze commit or tag until the two blockers are remediated and independently re-reviewed. No Git mutation was performed.

## Required scorecard

```ini
S23A_AUTH_FAILURE_USES_DRAINING = FAIL
S23A_AUTH_FAILURE_CLOSES_NEW_ADMISSION = FAIL
S23A_AUTH_FAILURE_EXISTING_PERMITS_DRAIN = PASS
S23A_AUTH_FAILURE_LATE_SUCCESS_NOT_PROMOTED = PASS
S23A_AUTH_FAILURE_FINAL_RETIREMENT_AFTER_DRAIN = PASS
S23A_NO_AUTH_DISPATCH_AFTER_FINAL_INVALIDATION = PASS
S23A_MULTI_OPERATION_AUTH_DRAIN = PASS
S23A_LOST_WORKER_AUTH_DRAIN_SAFE = PASS

S23A_PROVIDER_RESULT_FINAL_OUTCOME_SEPARATED = PASS
S23A_FINAL_OUTCOME_MONOTONIC = PASS
S23A_TIMEOUT_DURABLE_OUTCOME_TRUTHFUL = FAIL
S23A_CANCELLATION_DURABLE_OUTCOME_TRUTHFUL = FAIL
S23A_AUTH_INVALIDATION_DURABLE_OUTCOME_TRUTHFUL = PASS
S23A_LATE_RESULT_QUARANTINED = PASS

S23A_COMPLETION_PERSISTENCE_FAILURE_TYPED = PASS
S23A_COMPLETION_PERSISTENCE_FAILURE_NOT_SUCCESS = PASS
S23A_UNRESOLVED_PERMIT_RECOVERABLE = FAIL

S23A_SUCCESS_AUDIT_AFTER_DURABLE_COMMIT = PASS
S23A_NO_SUCCESS_AUDIT_ON_TIMEOUT = PASS
S23A_NO_SUCCESS_AUDIT_ON_CANCEL = PASS
S23A_NO_SUCCESS_AUDIT_ON_AUTH_INVALIDATION = PASS
S23A_SUCCESS_AFTER_DEADLINE_BLOCKED = PASS

NO_DB_LOCK_ACROSS_PROVIDER_IO = PASS

MCP_0010_SCHEMA_ACCEPTED = PASS
MCP_0010_SQLITE_MIGRATION = PASS
MCP_0010_POSTGRES_MIGRATION = PASS

S23A_02_REGRESSION_FREE = PASS
S23A_03_REGRESSION_FREE = PASS
S23A_04_REGRESSION_FREE = PASS

OWNER_SCOPED_CONNECTION_IDENTITY = PASS
OAUTH_STATE_PKCE = PASS
CALLBACK_OWNER_BINDING = PASS
SECURE_TOKEN_STORAGE = PASS
MCP_SECRET_REDACTION = PASS
TOOL_ALLOWLIST = PASS
DISCOVERY_AUTHORITY_SEPARATION = PASS
MCP_RESTART_RECOVERY = FAIL

S23A_05_STILL_NONBLOCKING = PASS

CRYPTOGRAPHY_ADVISORIES_STATUS = NONBLOCKING_WITH_EVIDENCE

S2_3A_FINAL_TEST_QUALITY = FAIL
REGRESSION_FREE = PASS
S2_3A_DOCUMENTATION_ACCURATE = FAIL
```

Interpretation: auth-drain PASS entries assume the fence successfully committed, with entry/admission failures captured separately. Completion-persistence NOT_SUCCESS describes the caller result; the failed durable recovery is separately marked FAIL. Late-result quarantine describes late provider results, whereas the post-commit ambiguity concerns a provider result obtained before the public deadline. `REGRESSION_FREE` records the executed existing suites, not overall acceptance.

## Reviewer changes

Only this new file was created:

`docs/TWF_S2_3A_GENERIC_MCP_PROVIDER_CONNECTION_AUTH_FOUNDATION_FINAL_ACCEPTANCE_REVIEW.md`

`RUNTIME_SOURCE_CHANGED_BY_REVIEWER = NO`

No existing status document or historical review was updated. All pre-existing file hashes matched the review-start inventory at completion. The only new nonignored path is this record; HEAD remains unchanged.

## Exact starting worktree inventory

```text
 M README.md
 M apps/api/alembic/env.py
 M apps/api/pyproject.toml
 M apps/api/requirements-dev.lock
 M apps/api/requirements.lock
 M apps/api/src/twf/config/settings.py
 M apps/api/src/twf/main.py
 M apps/api/src/twf/observability.py
 M apps/api/tests/test_backend_shell.py
 M apps/api/tests/test_database_foundation.py
 M apps/api/tests/test_foundation.py
 M docs/TWF_DETAILED_ROADMAP.md
 M docs/TWF_DOCUMENTATION_INDEX.md
 M docs/TWF_UX_BUCKET_ROADMAP.md
?? apps/api/alembic/versions/0007_mcp_connections.py
?? apps/api/alembic/versions/0008_mcp_cleanup_claim.py
?? apps/api/alembic/versions/0009_mcp_operation_permits.py
?? apps/api/alembic/versions/0010_mcp_provider_outcome.py
?? apps/api/src/twf/api/mcp.py
?? apps/api/src/twf/infrastructure/mcp.py
?? apps/api/src/twf/integrations/mcp/__init__.py
?? apps/api/src/twf/integrations/mcp/client.py
?? apps/api/src/twf/integrations/mcp/connection.py
?? apps/api/src/twf/integrations/mcp/contracts.py
?? apps/api/src/twf/integrations/mcp/http.py
?? apps/api/src/twf/integrations/mcp/lifecycle.py
?? apps/api/src/twf/integrations/mcp/oauth.py
?? apps/api/tests/mcp_support.py
?? apps/api/tests/test_mcp_connections.py
?? apps/api/tests/test_mcp_finalization.py
?? apps/api/tests/test_mcp_permits.py
?? apps/api/tests/test_mcp_recovery.py
?? apps/api/tests/test_mcp_remediation.py
?? apps/api/tests/test_mcp_security.py
?? docs/TWF_S2_3A_GENERIC_MCP_PROVIDER_CONNECTION_AUTH_FOUNDATION.md
?? docs/TWF_S2_3A_GENERIC_MCP_PROVIDER_CONNECTION_AUTH_FOUNDATION_ACCEPTANCE_REVIEW.md
?? docs/TWF_S2_3A_GENERIC_MCP_PROVIDER_CONNECTION_AUTH_FOUNDATION_REREVIEW.md
```

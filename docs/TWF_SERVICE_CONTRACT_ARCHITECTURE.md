# TradingWorkFlow (TWF) — Service Contract Architecture

## Status
**TWF-0 accepted service-contract baseline, with configuration clarification dated 2026-09-25 and Broker Workspace clarification dated 2026-09-26**

## 1. Purpose
Define how TWF consumes scanner, TI, TM, LLM, broker-facing, notification, and future services through stable logical contracts while remaining independent of physical deployment.

## 2. Service Architecture Principle
```text
TWF application code depends on logical service contracts.
Transport adapters depend on deployment.
Satellite internals remain outside TWF.
```

## 3. Logical Service Families
Initial service families:
- ScannerService
- TIService
- TMService
- LLMService
- NotificationService
- BrokerClient for the separately versioned Broker Workspace contract
- future IFLService

A service family represents semantics, not transport.

## 4. Common Service Envelope
Every service should expose or be adapted to common concepts:
```text
ServiceIdentity
ContractVersion
Capabilities
Health
TypedRequest
TypedResponse
TypedError
CorrelationContext
Provenance
```

## 5. ServiceIdentity
Conceptual fields:
- logical_service_name
- service_version
- contract_version(s)
- deployment_instance_id optional
- capability set
- provider identity where applicable

Deployment endpoint is not the same as semantic identity.

## 6. Capability Discovery
TWF should discover explicit capabilities rather than assume them from configuration.
Examples:
- SCAN
- ANALYZE
- SYNTHESIZE
- ASSESS_RISK
- AUTHORIZE
- MONITOR
- NOTIFY

Capability discovery must not grant authority by itself.

## 7. Local / Remote Adapter Pattern
```text
Domain / Workflow
      ↓
Logical Client
   ├── LocalAdapter
   └── RemoteAdapter
```
Local and remote adapters must be semantically equivalent for the same service contract.

## 8. Request Context
Cross-service requests should preserve:
- request_id
- workflow_id
- candidate_id when applicable
- user/workspace context reference
- trace/correlation ID
- as-of timestamp
- contract version

Sensitive secrets must not be embedded in generic context.

## 9. Response Envelope
A common response envelope may include:
- service identity
- response ID
- request ID
- created_at
- freshness/as_of
- payload
- warnings
- provenance
- contract version

Business payload remains service-specific and strongly typed.

## 10. Typed Error Taxonomy
Common categories:
- INVALID_REQUEST
- UNSUPPORTED_CAPABILITY
- UNAVAILABLE
- TIMEOUT
- AUTHENTICATION_FAILED
- AUTHORIZATION_FAILED
- VERSION_MISMATCH
- INVALID_RESPONSE
- STALE_STATE
- PROVENANCE_MISMATCH
- BUSINESS_REJECTED
- INTERNAL_ERROR

Service-specific errors may refine these.

## 11. HTTP / Realtime Split
Recommended initial policy:
```text
HTTP/REST
  commands
  queries
  explicit state reads

WebSocket / SSE
  live updates
  progress
  console streams
  order/position events
  alerts
  health changes
```
No requirement for gRPC initially.

## 12. Idempotency
Authority-changing or duplicate-sensitive requests must support explicit idempotency semantics.
Examples:
- TM candidate handoff
- approval submission
- adoption request
- execution request

Read-only analysis may use request identity/caching without authority semantics.

## 13. Versioning
Separate:
- TWF client version
- service implementation version
- API/contract version
- model version
- policy version
- prompt/orchestration version

Do not conflate these.

## 14. Service Registry
TWF should maintain lightweight configured service instances linked to the APS-owned capability catalog. Capability definitions, tenant profiles and runtime health are separate; instance descriptors include:
- logical service key
- service family
- enabled state
- adapter type
- endpoint/reference
- supported contract version
- health state
- capabilities
- user/workspace visibility

Do not build a dynamic plugin marketplace in the miniature.

## 15. Scanner Contract Boundary
Scanner owns discovery logic.
TWF consumes candidates with:
- candidate/source identity
- instrument
- timestamp
- ranking/score where defined
- scanner provenance
- optional horizon/context

TWF must not reconstruct scanner internals.

## 16. TI Contract Boundary
TI owns intelligence semantics.
TWF consumes typed IntelligenceResponse including:
- primary/secondary claims
- horizon
- evidence
- explanation
- producer/model provenance
- optional trade expression

TI advice is not execution authority.

## 17. TM Contract Boundary
For TM-managed workflows/accounts, TM owns:
- risk
- authority
- broker reconciliation
- position ownership/adoption
- execution supervision
- monitoring

TWF presents and orchestrates but does not duplicate TM authority. Direct manual Broker Workspace commands apply only to explicitly unmanaged accounts under the separate contract in section 25. Read-only broker observations do not grant command ownership.

## 18. LLM Contract Boundary
LLM is consumed through provider-neutral logical service.
Normal runtime uses one active primary LLM configuration.
The actual provider/model/version/configuration must remain explicit in provenance.

## 19. Browser Boundary
Browser should normally call TWF APIs, not satellite services directly.
Reasons:
- centralized auth
- secret isolation
- stable frontend contract
- audit/correlation
- service replacement
- uniform error handling

## 20. Contract Testing
Every integration should have:
- synthetic adapter
- contract test suite
- local/remote semantic equivalence tests
- error/version mismatch tests
- correlation/provenance tests
- degraded-service tests

## 21. Compatibility Policy
Breaking service-contract changes require:
- new version
- explicit adapter/migration strategy
- test updates
- compatibility note

TWF must not silently coerce unknown incompatible responses.

## 22. Service Security
Remote services eventually require:
- authenticated service identity
- TLS
- authorization
- secret management
- request/audit correlation

Authority-changing TM calls require stricter controls than read-only scanner/TI calls.

## 23. Architectural Invariants
1. Workflow code depends on logical contracts, not transports.
2. Browser does not own satellite secrets.
3. Local/remote deployment preserves semantics.
4. Capabilities are explicit.
5. Errors are typed.
6. Correlation is preserved end-to-end.
7. Satellite authority boundaries remain intact.
8. Synthetic adapters are clearly marked.
9. Contract versions are explicit.
10. Service replacement must not require workflow-domain redesign.

## 24. Capability and Configuration Contracts

The [configuration architecture v0.6](TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md) governs registration, dependencies, rollout, entitlements and profile revisions. A service identity/capability response verifies deployed support; it cannot register arbitrary code, confer customer entitlement or bypass authorization. Stable capability IDs link to provider/implementation, contract/schema versions, required/optional/conflicting capabilities, mutability and safe health/test operations. Health is an observation, not a plan grant.

Before use, resolve an authorized profile revision and secret reference under the caller's account/user context. Contract requests preserve correlation, actual producer identity and relevant configuration revisions without secret values. Changing providers or restoring an entitlement requires revalidation; retries cannot silently switch producer. Running-work behavior on revocation must follow the operation's safety contract, especially TM-governed exposure.

SyntheticScannerService, SyntheticTIService, SyntheticTMService and SyntheticLLMService are explicit test/development adapters behind the same versioned logical contracts as real adapters. Deterministic fixtures cover success, empty, failure, timeout, stale, denied, incompatible and degraded states; preserve source/as-of/correlation/provenance and mark synthetic mode. They never contact live brokers or grant real authority. Real TM contracts still require committed public-surface reconciliation before integration freeze.

## 25. Broker Workspace Contract Clarification — 2026-09-26

[Broker Workspace v0.3](TWF_BROKER_WORKSPACE_ARCHITECTURE.md) governs BrokerClient, typed provider capabilities, account-scoped observations/commands and the adapter registry. Application/UI code consumes these contracts, never vendor SDK types. Synthetic adapters must use the same contract and visibly synthetic provenance. Provider/account identity, dataset timestamps, completeness, configuration/contract revisions and safe correlation survive normalization; provider details are sanitized and typed.

TWF-1.6 actually implements `foundation.health.v1` for SCANNER, TI, TM and LLM only. Its process-scoped descriptors, health timeout/failure model and 16-descriptor bound are not a BrokerAccount registry, broker quota or trading contract. Preserve that accepted surface. Introduce separately versioned broker contracts under the same layering principles; reuse safe transport/correlation mechanisms only where semantics match.

Read failures are distinct from uncertain command outcomes: a timeout after possible dispatch means `SUBMISSION_UNKNOWN`, not a retryable rejection. Durable request identity, exact confirmed payload, fenced dispatch, scoped broker IDs and restart reconciliation are mandatory before live commands. Provider client tags alone do not promise idempotency. Contract-level tests cover two synthetic providers and multiple accounts before a real provider; no real provider support is asserted by this architecture.

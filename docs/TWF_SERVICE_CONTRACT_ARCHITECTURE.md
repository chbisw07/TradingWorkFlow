# TradingWorkFlow (TWF) — Service Contract Architecture

## Status
**TWF-0 normative service-contract architecture — proposed for acceptance**

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
- future BrokerMetadataService where needed
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
TWF should maintain a lightweight configured-service catalog containing:
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
TM owns:
- risk
- authority
- broker reconciliation
- position ownership/adoption
- execution supervision
- monitoring

TWF presents and orchestrates but does not duplicate TM authority.

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

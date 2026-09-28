# TradingWorkFlow (TWF) — Service Contract Architecture

> **2026-09-29 S&D architecture acceptance:** The dated S&D extension below is **ACCEPTED / IMPLEMENTATION AUTHORIZED** within the [Sprint-2 delivery plan](TWF_SPRINT2_SCAN_DISCOVER_DELIVERY_PLAN.md). The [independent acceptance record](TWF_SCAN_DISCOVER_ARCHITECTURE_ACCEPTANCE_REVIEW.md) supersedes its 2026-09-28 proposal status. Sprint 2 is **ACTIVE / NEXT; implementation not started**. Earlier acceptance history and separate TI/TM/provider/security gates remain unchanged; proposal wording in the dated extension records its origin, not the current review status.

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
Historical TWF-0 wording: “Scanner owns discovery logic.” For proposed S&D,
section 26 refines this into provider-owned scan criteria/native outputs and
TWF-owned discovery evaluation. This older generic candidate payload inventory
is historical, not the new DiscoveryCandidate contract:

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


## 26. Scan and discovery contracts — 2026-09-28

The historical section 15 shorthand is refined: a ScanProvider owns declared
criteria execution and native results; TWF S&D owns cross-source normalization,
intent/context evaluation and DiscoveryCandidate lifecycle. TWF does not reconstruct
an external scanner's internals. A provider-native ranking is retained as source
evidence, not relabelled as TWF Discovery Relevance or TI confidence.

Proposed families are UniverseProvider, CandidateSource, ScanProvider,
MarketIntelligenceProvider, CandidateIntelligenceProvider and LLMService. Define
separately versioned `sd.*.v1` domain contracts at implementation; preserve the
accepted `foundation.health.v1` surface and existing Broker V2 contracts. A healthy
service is not proof of scan support, data rights, entitlement or execution authority.

Every request/result carries schema/provider/capability/configuration identity,
correlation, owner scope, exact native subject/listing references, observation/source
mode, source/available/received times, completeness and safe typed errors. Unknown
and partial cannot collapse into successful empty. Bound total time, body/pages,
work size and retries; cancellation/restart fencing rejects obsolete results.
Local, remote and synthetic adapters retain identical semantics and actual provenance.

TradingView MCP tools/transport are adapter details, not core DTOs. Select and verify
the actual service, schemas/auth/capabilities/data rights before implementing it.
MCP is not a promise of official TradingView support. Internal V0 and synthetic
adapters prove an independent path. No LLM is required for scans/discovery; optional
Level-0 returns server-validated grounding/citation metadata and has no authority.

See [S&D provider contracts](TWF_SCAN_AND_DISCOVER_ARCHITECTURE.md) and the
[shared domain](TWF_OPPORTUNITY_DOMAIN_ARCHITECTURE.md). TI analysis and TM management
still require their own public-contract gates; no later API is invented by this
proposal. The service-contract DOCX needs regeneration after acceptance.

### Revision history addition

| Revision | Date | Status | Role / change |
| --- | --- | --- | --- |
| S&D reconciliation 1 | 2026-09-28 | PROPOSED / RECONCILED / READY FOR REVIEW | Normative design/planning extension: Scan and discovery contracts; prior history and acceptance preserved |
| S&D acceptance 1 | 2026-09-29 | ACCEPTED / IMPLEMENTATION AUTHORIZED | Independent S&D architecture acceptance; staged Sprint-2 scope only, no runtime delivery or prior milestone change; see [review](TWF_SCAN_DISCOVER_ARCHITECTURE_ACCEPTANCE_REVIEW.md) |

# TradingWorkFlow (TWF) — Service Integration Architecture

## Status

**Accepted TWF-0 integration baseline, clarified for configuration and UX planning on 2026-09-25**

---

# 1. Purpose

Define the common integration pattern TWF uses for TI, TM, scanners, LLMs, brokers, notifications, and future satellite services.

---

# 2. Core Model

```text
                     TWF Web
                        │
                        ▼
                     TWF API
                        │
                        ▼
                 Workflow/Application
                        │
        ┌───────────────┼────────────────┐
        ▼               ▼                ▼
     TIClient         TMClient      ScannerClient
        │               │                │
   Local/Remote     Local/Remote      Local/Remote
        │               │                │
        ▼               ▼                ▼
       TI              TM             Scanner
```

The browser should normally communicate with TWF backend, not directly with satellite services.

---

# 3. Why TWF Backend Is the Integration Hub

Benefits:

- centralized authentication;
- secret isolation;
- consistent service contracts;
- correlation IDs;
- auditability;
- timeout/error policy;
- retries/idempotency where appropriate;
- stable browser API;
- service replacement without frontend rewrite.

---

# 4. Common Logical Service Requirements

Every satellite service should expose or be adapted to:

```text
ServiceIdentity
Capabilities
ContractVersion
Health
Typed Requests
Typed Responses
Typed Errors
Correlation
Provenance
```

Not every service needs the same business methods.

---

# 5. Local / Remote Adapter Pattern

```text
LogicalClient
├── LocalAdapter
└── RemoteAdapter
```

Local and remote adapters must preserve semantic equivalence.

Transport metadata is not business identity.

---

# 6. HTTP / Realtime Split

Initial recommendation:

```text
HTTP/REST
    commands
    queries
    explicit state requests

WebSocket / SSE
    live updates
    progress
    console events
    position/order events
    alerts
    service health
```

No need for gRPC initially unless later justified.

---

# 7. Service Registry

TWF needs lightweight configured service instances linked to the platform capability catalog. Follow the separate definition, profile, eligibility and health model in [configuration architecture v0.6](TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md).

Possible fields:

```text
service key
logical service type
enabled
adapter type
endpoint
contract version
health status
capabilities
user/workspace visibility
```

Secrets should be referenced securely, not stored as ordinary service metadata.

---

# 8. Error Handling

Common envelope should distinguish:

```text
transport failure
service unavailable
timeout
authentication
authorization
contract mismatch
invalid request
invalid response
business rejection
stale state
```

Business rejections must not be flattened into generic HTTP errors.

---

# 9. Correlation

TWF should assign:

```text
request_id
workflow_id
candidate_id where relevant
```

Satellite responses should retain service-specific IDs.

Traceability should survive asynchronous/realtime updates.

---

# 10. Compatibility

Client adapters should support explicit contract compatibility.

Avoid:

- guessing capability from response fields;
- silent schema coercion;
- ignoring unknown breaking versions.

---

# 11. Security

Remote integration eventually requires:

- TLS;
- service authentication;
- authorization;
- secret management;
- audit;
- rate limits where appropriate.

Authority-changing TM calls deserve stricter controls than read-only scanner queries.

---

# 12. Testing

Every service integration should have:

- synthetic adapter;
- contract tests;
- local/remote semantic equivalence tests;
- degraded-service tests;
- version mismatch tests;
- timeout tests;
- provenance/correlation tests.

---

# 13. Initial Integration Order

Recommended:

```text
1. Two synthetic broker providers / three isolated account rooms (BW-1)
2. One verified real broker read-only (BW-2)
3. Native watchlists and order draft/preview (BW-3)
4. Synthetic durable command/recovery proof (BW-4)
5. Controlled manual live orders after safety/security gates (BW-5)
6. Second real broker contract/UI proof (BW-6)
7. TM integration after committed public-contract reconciliation
8. Scanner, then TI; realtime when justified by its own gate
```

This 2026-09-26 priority supersedes the original Scanner-first/TM-only broker sequence. It preserves existing milestone IDs and TM authority for managed accounts. Manual accounts use the dedicated TWF BrokerClient boundary; TM-managed accounts never bypass TM. See the [current delivery overlay](TWF_DETAILED_ROADMAP.md#18-broker-workspace-delivery-overlay) and [Broker Workspace v0.3](TWF_BROKER_WORKSPACE_ARCHITECTURE.md). Each later live gate needs its own acceptance; BW-1 does not authorize real credentials or submission.

---

# 14. Architectural Invariants

1. Browser depends on TWF API, not satellite internals.
2. TWF workflow code depends on logical clients.
3. Local/remote adapters are interchangeable semantically.
4. Service capabilities are explicit.
5. Correlation is preserved.
6. Errors are typed.
7. Broker credentials do not traverse generic workflow payloads.
8. TM authority is not weakened by generic service abstraction.
9. Provider/model identities remain visible where scientifically meaningful.
10. Synthetic services are clearly marked.

# 15. Profile Application and Synthetic Adapters

An integration adapter receives validated effective configuration and authorized secret references from TWF's configuration boundary. It does not interpret commercial plan names or own settings authorization. Reconnect/rebind is a WARM operation with explicit applied revision, bounded connection test, failure/rollback reporting and correlation. Unknown/incompatible schemas and missing required capabilities fail explicitly. Provider/schema upgrades cannot silently replace provenance or TM authority.

SyntheticScannerService, SyntheticTIService, SyntheticTMService and SyntheticLLMService support the [UX bucket workstream](TWF_UX_BUCKET_ROADMAP.md). Use deterministic contract fixtures and the same typed errors/identity/provenance as real adapters, while clearly marking synthetic operation and isolating credentials/network access. TWF-1.6 establishes foundations; functional payloads mature under TWF-3/4/5. Neither synthetic UI completion nor capability registration authorizes a live integration.

# 16. Broker Adapter Boundary — 2026-09-26

Broker domain/application → versioned BrokerClient → broker adapter registry → provider adapter. This is a sibling integration boundary, not new methods silently added to `foundation.health.v1`. Keep provider credentials/headers, endpoint trust policy, parsing and SDKs inside the server-side adapter. Share transport utilities only when they preserve account ownership, typed operation outcomes, bounded per-provider/account concurrency, pagination and rate budgets.

A read endpoint being healthy does not prove order submission is available. A cancelled UI request does not cancel a broker order. A possibly sent command must be reconciled, not retried by generic timeout middleware. No automatic broker switch or credential reuse across account rooms is permitted. Connection generations prevent late callbacks/refreshes from resurrecting disabled sessions. Initial TM integration requires one durable command owner per broker account and an audited handoff with outstanding commands resolved; see Broker Workspace sections 18–19.

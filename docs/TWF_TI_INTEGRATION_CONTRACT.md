# TradingWorkFlow (TWF) — TI Integration Contract

## Status

**Architecture-stage integration contract — proposed, not yet implementation-frozen**

This document defines how TradingWorkFlow (TWF) should consume TradingIntelligence (TI) as an external logical service.

TWF must not depend on TI internal model, agent, forecaster, or repository implementation details.

---

# 1. Purpose

Define a stable, versioned integration boundary between:

```text
TradingWorkFlow (TWF)
        ↓
TIService logical contract
        ↓
TradingIntelligence (TI)
```

The contract must support:

- local/in-process integration;
- remote/network integration;
- provider/model evolution inside TI;
- deterministic provenance;
- typed intelligence claims;
- future realtime/event integration;
- backward-compatible evolution.

---

# 2. Responsibility Boundary

## TWF owns

- user/session/workspace context;
- trader-facing workflow;
- candidate selection context;
- orchestration;
- display/presentation;
- workflow correlation;
- persistence of TWF-owned workflow references;
- service-health presentation.

## TI owns

- intelligence generation;
- claims;
- forecast/analysis semantics;
- horizon;
- evidence;
- explanation;
- producer/model identity;
- synthesizer/contributor provenance;
- optional trade-expression advisory output;
- TI-specific Ground Truth / Evaluation semantics;
- TI internal agents/models/services.

## TWF must NOT

- recompute TI model outputs;
- reinterpret model identity;
- mutate TI claims;
- silently change horizon/target semantics;
- convert TI advice into execution authority;
- claim scientific authority over TI results.

---

# 3. Logical Service Contract

Conceptual contract:

```text
TIService
    identity()
    capabilities()
    health()
    analyze(request) -> IntelligenceResponse
    get_analysis(id)          optional
    subscribe_events(...)     future
```

Exact method names may differ in implementation.

The semantic contract matters more than transport syntax.

---

# 4. Deployment Model

TWF should support:

```text
TIService
├── LocalTIAdapter
└── RemoteTIAdapter
```

## LocalTIAdapter

Used when TWF and TI are co-located or TI is directly importable.

## RemoteTIAdapter

Used when TI runs:

- in another process;
- container;
- host;
- cloud environment.

TWF domain/workflow code must not know which adapter is active.

---

# 5. Request Contract

Conceptual `TIAnalysisRequest`:

```text
request_id
workflow_id
user_id / workspace_id
instrument
instrument_type
exchange / market
as_of timestamp
query / intent
requested horizon
expiry              optional
position context     optional
scanner context      optional
trade context        optional
requested capabilities
correlation metadata
contract_version
```

Do not include broker credentials.

Do not embed arbitrary opaque provider-specific payloads into the core contract.

---

# 6. Instrument Identity

TWF and TI must agree on a canonical instrument reference.

At minimum support future identification for:

```text
cash equity
future
option
index
```

Potential fields:

```text
market
exchange
symbol
instrument_type
expiry
strike
option_type
contract identifier
underlying identifier
```

Exact identity should ultimately reuse an accepted shared contract or explicit adapter mapping.

---

# 7. IntelligenceResponse

TWF should consume TI's typed intelligence response rather than a raw prose-only answer.

Conceptual structure:

```text
IntelligenceResponse
├── response_id
├── request_id
├── created_at
├── producer/service identity
├── synthesizer identity        optional
├── contributor provenance[]
├── primary claim
├── secondary claims[]
├── horizon / resolution semantics
├── evidence references
├── explanation
├── recommendations             advisory only
├── trade-expression proposal   optional
├── warnings / limitations
└── contract/schema version
```

TWF should render this structure without erasing provenance.

---

# 8. Claims

TWF should support TI claim types already established in the IFL foundation:

```text
BINARY
NUMERIC
CATEGORICAL
ORDINAL
RANKING
INTERVAL
EVENT_TIME
```

TWF should not assume every TI output is probabilistic.

---

# 9. Primary / Secondary Claims

A forecast-bearing response should support:

```text
PrimaryClaim
SecondaryClaims[]
```

TWF should visually distinguish the primary claim from supporting claims.

The primary claim should remain immutable in historical workflow records.

---

# 10. Horizon

TWF should display TI horizon semantics exactly.

Examples:

```text
5 trading days
15 trading days
calendar duration
specific expiry
event-time horizon
```

TWF must not silently convert horizon into:

- mandatory position holding period;
- order validity;
- TM execution deadline.

---

# 11. Active LLM

TI may use an active primary LLM.

TWF should receive sufficient provenance to display or audit:

```text
provider
model
configuration version
prompt/template version
tool configuration version
orchestration version
```

TWF should not depend on OpenAI/Anthropic/Google-specific semantics.

---

# 12. Trade Expression

TI/A6 may provide a trade-expression proposal.

TWF should treat it as:

```text
ADVISORY
```

not:

```text
AUTHORIZED ORDER
```

The UI should clearly separate:

```text
intelligence
forecast
trade expression
trader decision
TM authority
execution
```

---

# 13. Error Contract

Recommended typed categories:

```text
INVALID_REQUEST
UNSUPPORTED_CAPABILITY
STALE_REQUEST
SERVICE_UNAVAILABLE
TIMEOUT
VERSION_MISMATCH
INVALID_RESPONSE
PROVENANCE_ERROR
AUTHENTICATION_ERROR
AUTHORIZATION_ERROR
INTERNAL_ERROR
```

TWF should display degraded/unavailable state honestly.

No silent replacement of one producer/model with another without identity change.

---

# 14. Timeout Policy

Initial architecture recommendation:

- short health/capability calls;
- bounded analysis timeout;
- asynchronous workflow option for long-running analysis later.

Do not freeze numeric timeout values until implementation/performance testing.

---

# 15. Idempotency

`request_id` should support safe retry semantics.

The same logical request should not accidentally create unrelated duplicate workflow records.

TI may still generate a new response identity when a legitimate re-analysis occurs.

---

# 16. Correlation

Preserve:

```text
TWF workflow_id
TWF candidate_id
TI request_id
TI response_id
TI primary_claim_id
```

This lineage becomes important for:

- TM handoff;
- history;
- future IFL;
- audit;
- trader review.

---

# 17. Contract Versioning

Separate:

```text
TI service version
TI response schema version
producer/model version
LLM version/config
TWF client version
```

Do not conflate these.

Breaking schema changes require explicit version negotiation or adapter support.

---

# 18. Health / Capability Discovery

TWF should be able to determine:

- TI service available/unavailable;
- service version;
- supported capabilities;
- contract versions;
- optional feature availability.

Do not infer capability from UI configuration alone.

---

# 19. Realtime / Events

Initial `analyze()` may be request/response.

Future event types may include:

```text
analysis_started
analysis_progress
analysis_completed
analysis_failed
intelligence_updated
service_health_changed
```

Recommended transport:

- HTTP for commands/queries;
- SSE/WebSocket for progress/events as needed.

Do not require realtime transport in first implementation.

---

# 20. Security

Remote TI integration should eventually require:

- authenticated service identity;
- encrypted transport;
- authorization policy;
- no secrets in normal request payloads;
- correlation/audit.

Initial local development may use trusted local adapters.

---

# 21. Persistence Boundary

TWF may persist:

- TI response reference;
- immutable snapshot needed for workflow/history;
- correlation metadata;
- selected display fields.

TWF should not become the authoritative TI artifact registry.

Where long-term reproducibility requires exact TI capture, use explicit immutable capture/reference semantics.

---

# 22. Offline / Mock Adapter

TWF should implement a deterministic mock/synthetic TI adapter before real integration.

This enables:

- UI development;
- E2E workflow tests;
- degraded-mode testing;
- contract validation.

Synthetic responses must be clearly identified as synthetic.

---

# 23. Initial TWF TI Integration Acceptance

Minimum acceptance should prove:

```text
candidate
  ↓
TI request
  ↓
typed IntelligenceResponse
  ↓
TWF candidate workspace
  ↓
claim / horizon / evidence / provenance rendered
```

No TM or execution required for the first TI integration target.

---

# 24. Open Items

Before implementation freeze:

1. exact TI public API surface;
2. instrument identity reuse;
3. schema-generation strategy;
4. analysis timeout policy;
5. capture/reference policy;
6. streaming/progress requirement;
7. local adapter packaging;
8. remote authentication;
9. TI endpoint discovery;
10. exact trade-expression schema mapping.

---

# 25. Architectural Invariants

1. TWF consumes TI through a logical service contract.
2. Local/remote deployment does not change semantics.
3. TI internal models remain opaque to TWF.
4. TI claims retain producer/model provenance.
5. TWF does not grant execution authority.
6. Trade expression remains advisory.
7. Contract versioning is explicit.
8. Synthetic/mock TI remains distinguishable from actual TI.
9. TWF preserves correlation lineage.
10. TI remains independently deployable and replaceable.

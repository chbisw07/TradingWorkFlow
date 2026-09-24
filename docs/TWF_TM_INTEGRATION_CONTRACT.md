# TradingWorkFlow (TWF) — TradeMonitor Integration Contract

## Status

**Architecture-stage integration contract — provisional pending committed TradeMonitor public-surface reconciliation**

This document defines the intended boundary between TradingWorkFlow (TWF) and TradeMonitor (TM).

Before implementation freeze, this contract MUST be reconciled against the current committed TM repository/public contracts.

TWF must not design around uncommitted TM internals without explicit review.

---

# 1. Purpose

Define a stable integration boundary:

```text
TradingWorkFlow
      ↓
TMService logical contract
      ↓
TradeMonitor
      ↓
Broker
```

TM remains the authoritative governance/risk/execution-supervision layer.

Broker remains execution truth.

---

# 2. Responsibility Boundary

## TWF owns

- trader interaction;
- workflow presentation;
- candidate/workflow correlation;
- manual approval UX;
- display of TM state;
- TWF audit of workflow actions;
- service status presentation.

## TM owns

- broker reconciliation;
- position truth within TM semantics;
- risk;
- authority;
- execution supervision;
- adoption of external positions;
- monitoring state;
- order/position lifecycle;
- broker-facing coordination.

## Broker owns

- actual execution truth;
- fills;
- orders;
- broker position state;
- balances/margins as broker reports them.

## TWF must NOT

- create independent risk truth;
- mark a position owned without TM;
- silently adopt external positions;
- mutate TM position state directly;
- treat TI recommendations as TM approval;
- duplicate broker reconciliation logic.

---

# 3. Logical Service Contract

Conceptual:

```text
TMService
    identity()
    capabilities()
    health()

    assess_candidate(...)
    get_positions(...)
    get_position(...)
    get_authority_state(...)
    get_risk_state(...)

    adopt_position(...)       governed
    submit_intent(...)        governed
    approve_intent(...)       depending ownership model
    cancel_intent(...)
    monitor(...)
```

This is conceptual only.

The exact API MUST be reconciled against actual TM public contracts before implementation.

---

# 4. Deployment Model

Support:

```text
TMService
├── LocalTMAdapter
└── RemoteTMAdapter
```

TWF workflow/domain logic must not know transport.

---

# 5. Candidate Assessment Request

Conceptual `TMCandidateAssessmentRequest`:

```text
request_id
workflow_id
candidate_id
instrument identity
direction / trade expression
TI response reference
TI claim reference
horizon
proposed entry context
proposed invalidation / SL
proposed target
proposed quantity / sizing context   optional
trader identity
workspace/account context
correlation metadata
contract_version
```

TI provenance should be referenced, not flattened into TM authority semantics.

---

# 6. Assessment Response

Conceptual response:

```text
assessment_id
candidate_id
TM service identity
broker-state timestamp
risk status
authority status
position context
existing exposure
blocking reasons
warnings
allowed next actions
expiry/staleness metadata
contract_version
```

TWF should display this as authoritative TM state.

---

# 7. Authority Model

Initial miniature:

```text
TI advises
TWF presents/orchestrates
TM assesses/governs
Trader manually approves
TM coordinates execution/adoption
Broker executes
```

Manual trader approval should remain mandatory initially.

No autonomous execution in the first miniature.

---

# 8. Existing / External Broker Positions

TM's existing philosophy must be preserved.

Conceptually:

```text
broker position exists
        ↓
TM discovers it
        ↓
BROKER_EXTERNAL / UNMANAGED
        ↓
explicit ADOPT if trader/TM policy permits
```

TWF should show:

- external/unmanaged state;
- adoption eligibility;
- managed state only after authoritative TM transition.

TWF must never silently adopt.

---

# 9. Existing Managed Position

When TM already owns/monitors a position and TI produces new intelligence:

```text
TI intelligence update
        ↓
TWF workflow context
        ↓
TM-managed position remains authoritative
```

TWF may present:

- new TI thesis;
- updated claim;
- risk context;
- TM monitoring state.

TI/TWF must not mutate position state.

---

# 10. Position Contract

TWF should consume a stable TM position view.

Conceptual fields:

```text
tm_position_id
instrument identity
broker position reference
ownership/adoption state
side
quantity
average price
current price
P&L
risk state
authority state
monitoring state
SL/target state where TM owns them
opened_at
updated_at
broker_sync timestamp
contract version
```

Exact fields require TM reconciliation.

---

# 11. Orders / Execution

TWF should not talk directly to broker execution APIs when TM owns the workflow.

Preferred:

```text
TWF
  ↓
TM
  ↓
Broker
```

TWF may display:

- intent;
- order state;
- fills;
- errors;
- broker truth.

---

# 12. Idempotency

Every action capable of creating/changing TM workflow must have an idempotency/correlation identity.

Examples:

```text
candidate handoff
intent submission
adoption request
manual approval
cancel request
```

Retry must not accidentally create duplicate broker actions.

---

# 13. Staleness

TM responses should include enough time/version context for TWF to detect stale state.

Examples:

- broker snapshot timestamp;
- TM assessment timestamp;
- position reconciliation version;
- assessment expiry if applicable.

A valid TI analysis does not imply the TM risk assessment remains current.

---

# 14. Reassessment

Before execution, TM may need to reassess:

- price;
- exposure;
- broker funds;
- margin;
- existing position;
- risk limits;
- market state relevant to TM policy.

TWF should not assume a previous approval remains indefinitely valid.

---

# 15. Error Contract

Recommended categories:

```text
INVALID_REQUEST
UNSUPPORTED_CAPABILITY
SERVICE_UNAVAILABLE
TIMEOUT
VERSION_MISMATCH
STALE_STATE
RISK_REJECTED
AUTHORITY_REJECTED
POSITION_CONFLICT
DUPLICATE_ACTION
BROKER_UNAVAILABLE
BROKER_REJECTED
PARTIAL_EXECUTION
AUTHENTICATION_ERROR
AUTHORIZATION_ERROR
INTERNAL_ERROR
```

Exact mapping should reuse TM's actual error semantics where possible.

---

# 16. Realtime Events

Likely TM → TWF events:

```text
position_discovered
position_updated
position_adopted
risk_state_changed
authority_state_changed
intent_updated
order_submitted
order_updated
fill_received
execution_failed
position_closed
broker_sync_changed
service_health_changed
```

Recommended initial model:

- HTTP for commands/queries;
- WebSocket/SSE for updates.

Do not freeze event names before TM reconciliation.

---

# 17. Correlation

Preserve lineage:

```text
TWF workflow_id
TWF candidate_id
TI response_id
TI primary_claim_id
TM assessment_id
TM intent_id
TM position_id
broker order id
broker position reference
```

Not every ID exists at every stage.

Upstream IDs should remain immutable references.

---

# 18. Security

Remote TM integration requires stronger trust than ordinary read-only analysis.

Eventually require:

- service authentication;
- TLS;
- authorization;
- request signing/idempotency policy where justified;
- secret isolation;
- audit of authority-changing actions.

Broker secrets remain inside TM/broker integration boundary.

TWF should not receive raw broker credentials.

---

# 19. Local Development

TWF should support:

```text
SyntheticTMAdapter
```

and later:

```text
LocalTMAdapter
RemoteTMAdapter
```

A synthetic adapter should simulate:

- risk accept/reject;
- authority states;
- external position;
- adopted position;
- execution state;
- broker failure.

This allows TWF workflow development before live TM wiring.

---

# 20. TM Public Contract Reconciliation Gate

Before coding the real TM adapter:

1. TM repo must be clean/committed.
2. Inspect public contracts/APIs.
3. Identify current:
   - position identity;
   - authority state;
   - risk state;
   - adoption;
   - reconciliation;
   - intent/order model;
   - cockpit/public interface.
4. Map this document to actual TM types.
5. Prefer adapters over TM rewrites.
6. Create a versioned TM integration contract.
7. Add contract tests.

Do not design against uncommitted/stale snapshots.

---

# 21. Initial TM Integration Acceptance

Minimum acceptance should prove:

```text
TWF analyzed candidate
        ↓
TM assessment request
        ↓
risk / authority response
        ↓
manual trader approval
        ↓
synthetic/local execution/adoption
        ↓
position monitoring state displayed
```

Use synthetic/local adapter before live broker action.

---

# 22. Relationship to TI

TWF should preserve separation:

```text
TI claim
    = intelligence truth candidate

TM assessment
    = trading governance decision

Broker state
    = execution truth
```

A wrong TI forecast and a failed trade are not automatically the same failure class.

This separation is important for future IFL.

---

# 23. Relationship to Future IFL

TWF should preserve references so later learning can distinguish:

```text
intelligence quality
trade-expression quality
TM risk/authority decision
execution quality
broker outcome
```

Do not implement IFL in the TM adapter.

Only preserve correlation/provenance.

---

# 24. Contract Versioning

Separate:

```text
TM service version
TM API/schema version
TM policy version
broker adapter version
TWF client version
```

A policy change is not necessarily an API schema change.

---

# 25. Open Items

1. exact committed TM public API;
2. current cockpit/public command boundary;
3. intent model;
4. manual approval ownership;
5. TM vs Workflow App responsibility for approval state;
6. order-request API;
7. adoption API;
8. event stream;
9. assessment staleness;
10. broker-state timestamps;
11. error mapping;
12. service authentication;
13. remote endpoint design;
14. version negotiation.

---

# 26. Architectural Invariants

1. TWF consumes TM through a logical service contract.
2. TM remains risk/authority owner.
3. Broker remains execution truth.
4. TWF does not silently adopt positions.
5. TWF does not duplicate broker reconciliation.
6. Manual approval is mandatory initially.
7. TI advice never equals TM authorization.
8. Remote/local transport does not change semantics.
9. Authority-changing calls are auditable/idempotent.
10. Actual TM public contracts must be reconciled before implementation freeze.

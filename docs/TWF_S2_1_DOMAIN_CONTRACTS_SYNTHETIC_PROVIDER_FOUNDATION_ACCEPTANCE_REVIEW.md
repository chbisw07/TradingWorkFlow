# S2-1 — Independent Acceptance Review

**Review date: 2026-09-29. Decision: HOLD_S2_1.**

The bounded synthetic foundation is implemented and its existing tests pass, but
three implementation findings prevent acceptance. S2-2 is **not authorized**.
These findings need bounded remediation, not redesign of the accepted architecture.
No runtime source or tests were changed during this review.

## A. Preflight and current status

- Branch: `main`.
- Starting and final HEAD: `7704261c6387c9de420ccf7c564e952bce6a72c4`.
- Architecture baseline: `twf-scan-discover-architecture-v0.2` → `6db608c`.
- Broker V2: accepted/frozen, `twf-broker-v2` → `69a643e`.
- Incoming tracked changes: `README.md` and `docs/TWF_DOCUMENTATION_INDEX.md`
  (20 additions, 15 deletions collectively).
- Incoming untracked implementation: seven source modules, four test/support files
  and one implementation record, listed below. No unrelated changes or staged files.
- Review-start SHA-256 inventory covers 238 tracked/unignored files. Final comparison
  confirms every incoming file is unchanged; this review adds only this record.

The README's later user-approved S2-0…S2-8 hierarchy is preserved. S2-1 was reported
IMPLEMENTED / READY FOR REVIEW, not accepted/frozen; S2-2…S2-8 remain pending.
Sprint 2 remains ACTIVE. Earlier TWF-0/TWF-1/Broker acceptance is not reopened.
The older delivery plan's broader slice grouping is explicitly cross-referenced in
the implementation record; that numbering refinement is not a blocker here.

## B. Sources and implementation inventory

Reviewed [README](../README.md), the complete tracked documentation diff, all new
source/test files, and these governing records:

- [S&D architecture](TWF_SCAN_AND_DISCOVER_ARCHITECTURE.md).
- [Opportunity domain](TWF_OPPORTUNITY_DOMAIN_ARCHITECTURE.md).
- [Sprint-2 delivery plan](TWF_SPRINT2_SCAN_DISCOVER_DELIVERY_PLAN.md).
- [Architecture acceptance](TWF_SCAN_DISCOVER_ARCHITECTURE_ACCEPTANCE_REVIEW.md).
- [S2-1 implementation report](TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION.md), treated as claims to verify.

Relevant ownership, S&D extensions and engineering gates were cross-checked in
[product/system](TWF_PRODUCT_VISION_AND_SYSTEM_ARCHITECTURE.md),
[data](TWF_DATA_ARCHITECTURE.md),
[service contracts](TWF_SERVICE_CONTRACT_ARCHITECTURE.md),
[integration](TWF_SERVICE_INTEGRATION_ARCHITECTURE.md),
[configuration](TWF_CONFIGURATION_SETUP_CAPABILITY_ENTITLEMENT_PLUGGABILITY_ARCHITECTURE.md),
[security](TWF_SECURITY_AUTH_ARCHITECTURE.md),
[technology decisions](TWF_TECHNOLOGY_DECISION_RECORD.md) and
[engineering standards](TWF_REPOSITORY_AND_ENGINEERING_STANDARDS.md).
Actual reuse was verified in [service-client contracts](../apps/api/src/twf/integrations/contracts.py)
and [settings contracts](../apps/api/src/twf/settings_contracts.py), including the
finite `foundation.health.v1` identity and the `CapabilityPolicy` protocol.

Exact incoming source inventory, all under `apps/api/src/twf/discovery/`:

| File           | Reviewed responsibility                                                             |
| -------------- | ----------------------------------------------------------------------------------- |
| `__init__.py`  | Package marker                                                                      |
| `domain.py`    | Identity, horizon, evidence, relevance, scan, tolerance, episode/snapshot/candidate |
| `lifecycle.py` | Pure state guards and transition event                                              |
| `memory.py`    | Owner-scoped non-durable history, head CAS and observation counting                 |
| `providers.py` | Provider protocols, manifest/batch/errors and operation validation                  |
| `synthetic.py` | Five deterministic fixture adapters                                                 |
| `service.py`   | Direct-call synthetic orchestration and optional enrichment                         |

Exact incoming test/support inventory, all under `apps/api/tests/`:

- `discovery_support.py`
- `test_discovery_domain.py`
- `test_discovery_providers.py`
- `test_discovery_flows.py`

The incoming new document is
`docs/TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION.md`.
No existing runtime, dependency, migration, API, configuration or frontend file is
modified by the implementation. Tests use fixtures/fake transports, not broker calls.

## C. Findings

| ID     | Severity | Timing                          | Area/File                                                           | Finding                                                                                                                                                                                                                                                                                                    | Required Action                                                                                                                                                                                                                                                                                                                                                                                                      |
| ------ | -------- | ------------------------------- | ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| S21-01 | HIGH     | MUST FIX BEFORE S2-2            | `providers.py:177`, `providers.py:197`; `service.py:91`             | Result validation trusts the returned model class instead of the operation's expected item schema. A matching-envelope `ProviderBatch[str]` passes the universe/scan boundary; the scan flow then leaks `AttributeError`. A SYNTHETIC batch can also contain LIVE_SNAPSHOT item/evidence provenance.       | Validate against a caller-owned expected response schema for each operation; reject incompatible item shapes and unsupported/contradictory provenance modes with safe typed errors before application use. Add negative adapter tests, including complete orchestration. Do not prohibit legitimate upstream producers merely because their identity differs from the adapter; define compatible lineage explicitly. |
| S21-02 | HIGH     | MUST FIX BEFORE S2-2            | `memory.py:35`, `memory.py:155`, `memory.py:194`; `domain.py:493`   | Comparability checks only outer producer/normalization and category/basis/unit signatures. Nested evidence producer/normalization changes are counted as comparable and promote NEW to CURRENT. Separately, unchanged underlying evidence can be counted twice by changing snapshot-level source time/key. | Base comparison on validated source-evidence identity, version, mode and observation basis/times. Establish consistency between snapshot summary and authoritative evidence; reject/quarantine incompatible or replayed input without promotion. Add nested-provenance, envelope-only replay and unchanged-history negative regressions.                                                                             |
| S21-03 | MEDIUM   | ARCHITECTURAL HOOK REQUIRED NOW | `service.py:52`, `service.py:210`; `domain.py:373`, `domain.py:475` | Scan-to-discovery lineage is discarded. `CandidateInput.scan_match_id` is not captured, and run/profile/definition revisions do not survive into episode/snapshot history. Different scan configurations produce byte-identical snapshots.                                                                 | Preserve typed, owner-scoped input/source lineage and relevant immutable run/profile/definition references through normalization and capture. An in-memory reference/capture suffices now; no SQL schema or production coordinator is requested. Prove scan and non-scan inputs remain attributable after the original call returns.                                                                                 |
| S21-04 | LOW      | SAFE TO DEFER                   | Documentation index                                                 | Whole-file Prettier warning exists in committed HEAD as well as the incoming worktree.                                                                                                                                                                                                                     | Handle formatting in a separate bounded cleanup; it is not a reason for HOLD.                                                                                                                                                                                                                                                                                                                                        |
| S21-05 | NOTE     | SAFE TO DEFER                   | In-memory repository and fixture orchestration                      | Process-local storage, separate append/promotion operations, cooperative async deadlines and fixed synthetic scoring are openly documented.                                                                                                                                                                | Before production persistence/adapters, prove atomic capture/evaluation/event/head transactions, restart behavior, transport bounds and production policy evaluation. Those later features are not requested as S2-1 fixes.                                                                                                                                                                                          |

S21-01 through S21-03 block S2-2. No CRITICAL finding or architectural contradiction
was found. In particular, no snapshot mutation, broker-authority expansion or
external-provider dependence was found.

### Independently reproduced failures

Read-only probes used the checked-in fixed-clock builders and normally validated
Pydantic models. They did not modify source/tests, use `model_construct`, mutate
frozen objects, or contact any service. Temporary probe programs were created under
`/tmp`, outside the repository.

**S21-01:** Obtain a valid universe envelope, retain its identity/owner/request/time
and source mode, but return `ProviderBatch[str]` with `items=("not-an-instrument",)`.
`ProviderAccess.call(..., "sd.universe", "sd.universe.v1", operation)` returns it
successfully. The implementation invokes `type(result).model_validate(...)`, which
revalidates the provider-selected string schema rather than the universe schema.
Repeat with a scanner adapter declaring the normal typed signature and returning
that wrong specialization: `SyntheticFoundationProof.scan_only` raises
`AttributeError: 'str' object has no attribute 'owner_id'` outside the error wrapper.
Static protocol annotations do not validate a runtime adapter response.

A separate candidate-source response retains a SYNTHETIC outer envelope but changes
the item's and its evidence's provenance mode to LIVE_SNAPSHOT. The same boundary
accepts it. `discover` has a later synthetic-only check, but that does not repair
normalization or typed failure behavior for all provider consumers.

**S21-02:** Create S1 using `SyntheticCandidateSource` at fixture time zero. At
+60 seconds, retain the candidate-input producer but change the nested evidence's
producer version and transformation revision to `2`. Discovery accepts S2,
`comparable_observations` returns `2`, and lifecycle becomes CURRENT. This can
arise when a stable adapter changes an upstream feed/transformation; the outer
adapter identity alone is not sufficient comparability evidence.

In a separate history instance, retain S1's entire evidence tuple byte-for-byte,
create a valid S2 sequence/predecessor, and change only snapshot-level observation
key and source/observed/evaluation/recording times. `append` accepts it and the
count becomes `2`, although `S1.evidence == S2.evidence`. Source observation
identity must not be manufactured by an envelope timestamp. S1 itself remains
immutable; the defect is false temporal comparison, not historical mutation.

**S21-03:** Run the synthetic scan twice at the same cutoff, changing run ID,
profile ID/applied revision and definition ID/revision, while retaining equivalent
criteria. Normalize a match and capture it in separate clean history instances with
the same episode/intent. The snapshots are byte-identical; neither contains input
ID, match ID, run ID, profile ID or definition ID. The repository retains no other
input/run registry from which to recover those references. A derivable UUID or a
producer name is not retained source-run/configuration lineage. The same loss of
input identity applies to non-scan `CandidateInput` ingestion.

This violates the accepted S&D §§6–7 and domain §3 snapshot/profile/run provenance
requirements. Deferring durable storage does not justify discarding the reference
contract now, before S2-2 consumes these types.

## D. Scorecard

PASS is assessed within the bounded S2-1 scope, not a claim of production readiness.
The three basic composability flows do execute; their PASS does not override the
negative-path failures in normalization, lineage and lifecycle. Provider protocol
signatures are neutral and reusable, so that gate passes while their runtime
validation/error gates fail.

```ini
S2_1_SCOPE_DISCIPLINE = PASS
S2_1_DOMAIN_MODEL = FAIL
DISCOVERY_EPISODE_IDENTITY = PASS
TIME_HORIZON_CONTRACT = PASS
SNAPSHOT_IMMUTABILITY = PASS
DISCOVERY_EVIDENCE_CONTRACT = PASS
DISCOVERY_LIFECYCLE_CONTRACT = FAIL
REJECTION_REASON_PRESERVED = PASS
DISCOVERY_RELEVANCE_CONTRACT = PASS
GROUNDING_CONTRACT = PASS
TOLERANCE_ENVELOPE_CONTRACT = PASS
PROVIDER_CONTRACTS = PASS
PROVIDER_CAPABILITY_MODEL = PASS
SND_TYPED_ERRORS = FAIL
SYNTHETIC_PROVIDERS = PASS
SCAN_ONLY_FLOW = PASS
SCAN_DISCOVERY_FLOW = PASS
DISCOVERY_WITHOUT_SCAN = PASS
NORMALIZATION_BOUNDARY = FAIL
S2_1_MEMORY_FOUNDATION = FAIL
S2_1_APPLICATION_SERVICE = FAIL
FOUNDATION_REUSE = PASS
SECURITY_AUTHORITY_PRESERVED = PASS
S2_1_TEST_QUALITY = FAIL
REGRESSION_FREE = PASS
S2_1_DOCUMENTATION_ACCURATE = FAIL
```

Domain-model failure is the missing capture lineage hook (S21-03), not rejection of
the identity/horizon/evidence value-object design. Lifecycle/memory failure is the
false comparable-observation promotion (S21-02), not the documented STALE projection
or legal transition matrix. The report's broad provenance/comparability/typed-error
claims are stronger than the implementation, so documentation accuracy fails too.

The 95 new tests have useful boundary and negative coverage: quantized scores,
custom/session horizons, ownership/CAS, immutable nested objects, terminal closure,
fixed expiry, provider revocation, timeout and optional-provider loss. They are not
merely count padding. However, malformed-envelope tests retain the correct generic
item type, comparability tests alter outer provenance only, and scan/discovery tests
assert producer identity but not run/profile/definition lineage. These gaps explain
why all 489 tests pass despite the reproduced failures. Add regressions for the
findings rather than replacing the useful existing suite.

## E. Independent validation

Commands were run from `apps/api` with its `.venv`, unless noted otherwise:

| Check                                                                                                         | Result                                                                                                                                           |
| ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `.venv/bin/pytest -q`                                                                                         | **489 passed in 100.45s**, no warnings; includes 95 S2-1 cases and 394 existing cases, including Broker V2                                       |
| `.venv/bin/ruff check src tests alembic`                                                                      | PASS                                                                                                                                             |
| `.venv/bin/ruff format --check src tests alembic`                                                             | PASS, 82 files already formatted                                                                                                                 |
| `.venv/bin/mypy`                                                                                              | PASS, strict configuration, 81 source files                                                                                                      |
| `.venv/bin/python -m compileall -q src tests`                                                                 | PASS                                                                                                                                             |
| `.venv/bin/python -m pip check`                                                                               | PASS, no broken requirements                                                                                                                     |
| `.venv/bin/python -m pip wheel --no-build-isolation --no-deps --no-index . -w /tmp/twf-s21-independent-wheel` | PASS, offline API wheel; all seven discovery module bytes match source                                                                           |
| Import probe                                                                                                  | All six functional discovery modules import with network disabled; no broker, app or database module imported                                    |
| Independent negative probes                                                                                   | Reproduced S21-01, S21-02 and S21-03 as described above; these are observed defects, not passing regression tests                                |
| Secret/dependency/scope review                                                                                | No added dependency or credential; only fabricated redaction-test strings match token/secret patterns; no new authority, API or frontend changes |
| README and implementation-record Prettier                                                                     | PASS                                                                                                                                             |
| Documentation index Prettier                                                                                  | Existing warning independently reproduced both from HEAD and worktree; unchanged by reviewer                                                     |
| Review-record Prettier, Markdown parsing and local links                                                      | PASS after creating this record                                                                                                                  |
| `git diff --check` and new-record whitespace                                                                  | PASS                                                                                                                                             |
| Review-start/final file fingerprints                                                                          | All 238 incoming files unchanged; only this review record added                                                                                  |

No live provider, MCP, LLM or broker request was made. There were no dependency
changes requiring a new network audit. Frontend suites were not rerun because the
frontend is unchanged. No schema or durable persistence was added, so separate
migration/PostgreSQL checks were not required. Container configuration is unchanged;
the offline package build and full backend suite were rerun, not Docker smoke.

## F. Reviewer changes

Exactly one repository file created:

- `docs/TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION_ACCEPTANCE_REVIEW.md`

**Existing files modified during review: NONE.**
**Runtime source changed by reviewer: NO.**

The two incoming README/index changes and twelve incoming untracked implementation
files are not review edits. The implementation report remains the author's original
claim; this record supplies the independent decision. GO-only milestone promotion
and index/status reconciliation were not performed under HOLD. No S2-2 work began.

## G. Decision, remediation boundary and deferred work

**HOLD_S2_1.** Resolve S21-01 and S21-02, add the S21-03 lineage hook, add focused
regression tests and correct the associated implementation claims. Then perform a
focused independent rereview before any S2-1 acceptance/freeze or S2-2 authorization.
The accepted architecture remains coherent; architectural rework is unnecessary.

Do not expand remediation into production discovery, persistence, a scanner engine,
a provider framework or product UX. In-memory reference contracts and guarded
synthetic proofs are sufficient to fix these findings.

Still separately gated: TradingView MCP, Tapetide/other real providers, independent
real data rights/calendars, production market intelligence, production Discovery
Engine, LLM integration, TI, TM, LOB, broker execution from S&D, production ML and
autonomous trading. Production persistence/retention, settings and product UX remain
later slices. The fixture score, TTL and cooldown are not approved market policies.

**Recommended Git action:** retain the worktree for bounded remediation and
rereview. After an eventual GO, commit the reviewed S2-1 implementation plus its
acceptance documentation and optionally create an S2-1 freeze tag. Do not label
this HOLD as acceptance. No commit, tag, push, merge, rebase, cherry-pick or reset
was performed.

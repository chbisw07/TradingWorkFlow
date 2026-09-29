# S2-1 — Focused Independent Re-review

**Review date: 2026-09-29. Decision: GO_S2_2.**

No blocking findings. S21-01, S21-02 and S21-03 are closed. S2-1 is
**ACCEPTED / FROZEN** as a reviewed milestone. Only **S2-2 Internal Scanner V0**
is authorized as the next bounded implementation slice; it was not implemented
in this review. Sprint 2 remains ACTIVE; S2-3 through S2-8 remain PENDING.
No Git commit, tag, push or branch/history mutation was performed.

## Preflight and scope

- Branch: `main`.
- Starting HEAD: `7704261c6387c9de420ccf7c564e952bce6a72c4`; unchanged at completion.
- Accepted architecture: `twf-scan-discover-architecture-v0.2` → `6db608c`.
- Broker V2: accepted/frozen, `twf-broker-v2` → `69a643e`; unchanged.
- Incoming tracked modifications: README and documentation index, 21 additions
  and 15 deletions collectively. No staged changes or unrelated runtime changes.
- Incoming untracked files: seven `apps/api/src/twf/discovery/` modules;
  `discovery_support.py`, `test_discovery_domain.py`, `test_discovery_providers.py`,
  `test_discovery_flows.py`, `test_discovery_remediation.py` under `apps/api/tests/`;
  the S2-1 implementation record and historical acceptance review.
- A SHA-256 inventory captured all 240 incoming tracked/unignored files. Review
  changes are restricted to the five status documents and new record listed below.
  All source, tests, dependencies, historical reviews and other files are unchanged.

The [prior HOLD review](TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION_ACCEPTANCE_REVIEW.md)
is preserved byte-for-byte. This focused review examines the actual remediated
source, original tests and 29 new regression cases, rather than accepting the
[remediation report](TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION.md)
on its assertions alone. It does not reopen unrelated accepted architecture.

Authority was checked against [README](../README.md), the
[S&D architecture](TWF_SCAN_AND_DISCOVER_ARCHITECTURE.md),
[opportunity domain](TWF_OPPORTUNITY_DOMAIN_ARCHITECTURE.md),
[delivery plan](TWF_SPRINT2_SCAN_DISCOVER_DELIVERY_PLAN.md) and
[architecture acceptance](TWF_SCAN_DISCOVER_ARCHITECTURE_ACCEPTANCE_REVIEW.md).
The later user-approved S2-0…S2-8 status hierarchy remains the current tracking
breakdown; older planning groupings and dated acceptance records retain their history.

## Findings closed and exact behavior verified

| Prior finding                                           | Disposition | Verified remediation                                                                                                                                                                                                                                                                                                                   |
| ------------------------------------------------------- | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| S21-01 — operation validation/provenance/typed failures | CLOSED      | `ProviderAccess` chooses `ProviderBatch[InstrumentIdentity]`, `[ScanMatch]`, `[CandidateInput]` or `[DiscoveryEvidence]` from the expected operation, not the returned generic class. Invalid payloads fail before downstream field access. Typed errors retain provider, operation and request context.                               |
| S21-02 — nested comparability and replay                | CLOSED      | History pins S1 evidence bases and scan configuration context. Nested source/producer/normalization changes cannot silently replace required bases. Every original basis must have a new source time and observation key to count; capture time alone cannot supply S2. Snapshot time summaries are validated against nested evidence. |
| S21-03 — retained immutable lineage                     | CLOSED      | Scan run/match/definition/profile/configuration references survive normalization and immutable snapshot capture. Non-scan input/source lineage is also retained. Same-cutoff runs/configurations produce distinguishable captures.                                                                                                     |

Source reviewed: `domain.py`, `memory.py`, `providers.py`, `service.py`,
`synthetic.py`, plus the unchanged lifecycle/contracts and all S2-1 test files.

Provenance rules distinguish result authorship from nested upstream contributions:
batch/result producers must match the declared adapter; same-producer evidence
must use the same mode; synthetic and real modes cannot mix. Distinct upstream
producers may retain their own real-data freshness mode. The two valid-upstream
regressions cover both synthetic contributions and an EOD result containing
DELAYED upstream evidence. These are local test values, not live-data integrations.

Comparability uses subject, category, observation basis, nested producer/version,
source/revision, source mode, normalization/version, dependence group and measurement
names/units. It excludes changing measurement values and observation/capture IDs.
The outer source/producer/normalization and definition/profile/configuration remain
pinned. Run and match IDs remain auditable but are excluded from the configuration
comparison key, allowing later runs of the same definition/profile.

Additional independent evidence remains representable. It cannot replace a required
S1 basis or manufacture a second observation of that cohort. Replayed captures
remain immutable audit records, with no count increment or NEW → CURRENT promotion.
Unknown source times do not confirm evolution. The policy is a conservative fixture
foundation, not a production multi-source fusion or correction engine.

## Independent adversarial probes

A temporary program at `/tmp/twf_s21_rereview_probes.py` exercised **18 probe groups**
using normal validated models and fixed clocks. Socket connections were disabled.
It did not modify repository tests, use `model_construct`, mutate frozen objects
through bypasses, access credentials, or contact a provider.

1. Scan matches in a universe response → typed `INVALID_RESPONSE`.
2. Universe instruments in a scan response → typed `INVALID_RESPONSE`.
3. Universe instruments in a candidate-source response → typed `INVALID_RESPONSE`.
4. Candidate inputs in a market-context response → typed `INVALID_RESPONSE`.
5. Universe instruments in a candidate-intelligence response → typed `INVALID_RESPONSE`.
6. All five valid operation results still succeed.
7. A synthetic provider's live-mode result is rejected.
8. Mismatched result producer identity is rejected.
9. Missing required item producer produces typed `INVALID_RESPONSE`.
10. Live-mode evidence within a synthetic candidate-source result is rejected.
11. An adapter `KeyError` containing private text becomes a safe, correlated
    `ProviderFailure(INVALID_RESPONSE)`; raw text does not escape.
12. S1 serialized to JSON and restored into a fresh in-memory history, followed by
    identical evidence/lineage with later capture times, retains two snapshots but
    counts one observation and remains NEW. S1 bytes remain unchanged.
13. The prior forged snapshot summary timestamp is rejected by validation.
14. A nested producer-version change rejects continuation without modifying history.
15. A genuine later source observation promotes NEW to CURRENT.
16. Five same-cutoff scan captures differing only in run, definition, profile or
    criteria retain distinct serialized lineage. Run-only changes remain comparable;
    definition/profile/criteria changes have distinct comparison keys.
17. Mutation of a captured profile revision is rejected; non-scan source/input
    identity remains present without fabricated scan lineage.
18. With two required S1 sources, advancing only one keeps NEW/count 1; advancing
    both permits CURRENT/count 2.

All 18 groups passed. Probe 12 verifies serializable contract/history behavior,
not production restart recovery or durable persistence.

The 29 new remediation test cases are meaningful regressions:
they vary wrong generic specializations across all five operations, test complete
scan orchestration, assert exact typed codes, exercise contradictory and legitimate
upstream provenance, capture-only replay, reissued IDs/keys, nested incompatibility,
additional independent evidence and full immutable lineage. They supplement rather
than weaken the original 95 S2-1 cases. Independent probes additionally cover the
same-cutoff lineage failure, missing producer, JSON history reconstruction and
partial advancement of a multi-source S1 cohort.

## Scorecard

PASS applies to the bounded S2-1 contract/synthetic scope.

```ini
S21_01_OPERATION_SCHEMA_VALIDATION = PASS
S21_01_PROVENANCE_CONSISTENCY = PASS
S21_01_TYPED_FAILURES = PASS

S21_02_EVIDENCE_COMPARABILITY = PASS
S21_02_REPLAY_DETECTION = PASS
S21_02_NESTED_PROVENANCE = PASS
S21_02_FALSE_SECOND_OBSERVATION_BLOCKED = PASS

S21_03_TYPED_LINEAGE = PASS
S21_03_SCAN_RUN_LINEAGE = PASS
S21_03_SCAN_MATCH_LINEAGE = PASS
S21_03_SCAN_DEFINITION_LINEAGE = PASS
S21_03_SCAN_PROFILE_LINEAGE = PASS
S21_03_EXTERNAL_CANDIDATE_LINEAGE = PASS
S21_03_LINEAGE_IMMUTABLE = PASS

S2_1_EXISTING_PROOFS_REGRESSION_FREE = PASS
S2_1_REMEDIATION_TEST_QUALITY = PASS
REGRESSION_FREE = PASS
S2_1_DOCUMENTATION_ACCURATE = PASS
```

“External candidate lineage” is proven through the synthetic non-scan candidate
source. It does not claim a real external provider was integrated.

## Remaining findings

**No blocking findings.** No new MUST FIX BEFORE S2-2 issue or architectural
contradiction was found. Existing bounded follow-ups remain:

| ID     | Severity | Timing        | Area/File                                 | Finding                                                                                                                                    | Required Action                                                                                             |
| ------ | -------- | ------------- | ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------- |
| S21-04 | LOW      | SAFE TO DEFER | Documentation index                       | Pre-existing whole-file Prettier warning; also present in HEAD. Existing roadmap formatting similarly predates this status update.         | Separate formatting cleanup; preserve focused status changes here.                                          |
| S21-05 | NOTE     | SAFE TO DEFER | In-memory history / fixture orchestration | Process-local storage, separate append/promotion operations, cooperative deadlines and fabricated fixed scoring remain explicitly bounded. | Prove durable atomicity/restart, transport limits and production policies in their separately gated slices. |

The two roadmaps had stale current-status notices saying Sprint 2 implementation
had not started. Following GO, these notices were reconciled without changing
normative semantics, historical acceptance rows or milestone numbering.

## Validation evidence

Backend commands ran from `apps/api` using its existing virtual environment:

| Command / check                                                                                            | Result                                                                                              |
| ---------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `.venv/bin/pytest -q`                                                                                      | **518 passed in 102.07s**, no warnings: 394 prior backend + 95 original S2-1 + 29 remediation cases |
| `.venv/bin/ruff check src tests alembic`                                                                   | PASS                                                                                                |
| `.venv/bin/ruff format --check src tests alembic`                                                          | PASS; 83 files                                                                                      |
| `.venv/bin/mypy`                                                                                           | PASS; strict configuration, 82 source files                                                         |
| `.venv/bin/python -m compileall -q src tests`                                                              | PASS                                                                                                |
| `.venv/bin/python -m pip check`                                                                            | PASS; no broken requirements                                                                        |
| `.venv/bin/python -m pip wheel --no-build-isolation --no-deps --no-index . -w /tmp/twf-s21-rereview-wheel` | PASS; offline API wheel                                                                             |
| Packaged-source comparison                                                                                 | All seven discovery module bytes match source                                                       |
| Import probe                                                                                               | All six functional modules import with sockets blocked; no broker/database/app composition import   |
| `PYTHONPATH=src:tests .venv/bin/python /tmp/twf_s21_rereview_probes.py`                                    | PASS; 18 independent probe groups                                                                   |

Root documentation checks use the installed local Prettier executable, without
`npx` downloads. README, the implementation record and this new review record pass
`node apps/web/node_modules/prettier/bin/prettier.cjs --check` with their explicit
paths. Whole-file index/roadmap formatting warnings are checked against HEAD and
left as bounded follow-up. Local Markdown parsing/link/anchor validation, current
status searches and `git diff --check` pass after the status edits. Final link
validation covers **seven Markdown documents and 175 local links/anchors**.
The review-start inventory confirms exactly five existing status documents changed;
all **235 other incoming files**, including runtime/tests and the historical HOLD
record, remain byte-identical. This record is the only new repository file.

No frontend, dependency, database schema, container or broker code changed.
Additional frontend/browser/Docker checks were not necessary for this focused
backend review. Existing backend regression uses fake transports. No external
network calls, broker calls or live trading smoke were performed.

## Documentation changes made by this review

Created exactly:

- [TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION_REREVIEW.md](TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION_REREVIEW.md).

Modified exactly, relative to the incoming worktree:

- [README.md](../README.md): S2-1 accepted/frozen, S2-2 active/next, later slices pending; links acceptance.
- [TWF_DOCUMENTATION_INDEX.md](TWF_DOCUMENTATION_INDEX.md): current status and review registration.
- [TWF_DETAILED_ROADMAP.md](TWF_DETAILED_ROADMAP.md): current status/next gate; preserves history and provider gates.
- [TWF_UX_BUCKET_ROADMAP.md](TWF_UX_BUCKET_ROADMAP.md): removes stale current implementation notice; no UX/bucket completion claim.
- [S2-1 implementation record](TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION.md): adds current independent-acceptance notice while preserving its earlier implementation/remediation account.

**Runtime source changed by reviewer: NO.** Tests and the historical HOLD review
remain byte-identical. No DOCX or normative architecture document was modified.

## Decision, authorization and Git recommendation

**GO_S2_2.** S2-2 Internal Scanner V0 can now be implemented against the accepted
S2-1 core domain/provider/lineage semantics. Its new scanner-specific behavior
still requires a bounded implementation prompt, deterministic tests and independent
acceptance. This decision does not begin S2-2 implementation.

The authorization does **not** include TradingView MCP, Tapetide, real market
providers, production market intelligence or Discovery Engine, LLM Level-0, TI,
TM, LOB, broker execution from S&D, production ML or autonomous trading. Existing
source/data/security/policy gates remain mandatory; synthetic acceptance is not
live-data acceptance. Sprint 2 and the broader UX buckets are not complete.

Recommended Git action only: review and commit the S2-1 implementation/remediation
and acceptance/re-review/status documents, then optionally create an explicit S2-1
freeze tag on that reviewed commit. Neither action was performed here. The frozen
milestone label records acceptance; no new Git freeze/tag is claimed.

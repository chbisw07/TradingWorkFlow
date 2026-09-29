# S2-2 — Focused Independent Re-review

**Review date: 2026-09-29. Decision: GO_S2_3.**

**No blocking findings.** S22-01 is closed. S2-2 Internal Scanner V0 is
**ACCEPTED / FROZEN** as a reviewed milestone. Only **S2-3 Real Scan Provider
Integration (TradingView MCP first)** is authorized as the next bounded slice,
subject to its exact provider, data-rights and security gates. No S2-3 implementation
was performed. Sprint 2 remains ACTIVE; S2-4 through S2-8 remain PENDING.

## Preflight and review scope

- Branch: `main`.
- Starting HEAD: `caadc9d2a8bead840b5b0621d83d006bb2c5dde8`; unchanged at completion.
- Accepted S2-1 baseline: `twf-s2-1-discovery-foundation`, peeled to that HEAD.
- Broker V2 remains accepted/frozen at `twf-broker-v2` (`69a643e`).
- Incoming tracked modifications: README, documentation index, detailed roadmap and
  UX bucket roadmap; 18 additions and 16 deletions. No staged or unrelated changes.
- Incoming untracked files: six modules under
  `apps/api/src/twf/discovery/internal_scanner/`; four test/support files
  (`internal_scanner_support.py`, `test_internal_scanner_indicators.py`,
  `test_internal_scanner_provider.py`, `test_internal_scanner_numeric.py`);
  the S2-2 implementation record and historical HOLD review.
- Review-start SHA-256 inventory captured 253 tracked/unignored files.

Preflight ran branch, HEAD, status, diff stat/name-status and ten-entry log checks.
The incoming documents correctly kept S2-2 ready for re-review and S2-3 pending.

The [historical HOLD review](TWF_S2_2_INTERNAL_SCANNER_V0_ACCEPTANCE_REVIEW.md) is
preserved byte-for-byte. The [implementation/remediation record](TWF_S2_2_INTERNAL_SCANNER_V0.md)
was checked against actual source and tests. This is a focused review of S22-01,
not a reopening of accepted unrelated architecture or permission to implement fixes.
The prior review's indicator, cutoff, lineage and provider conclusions were checked
for regression through source comparison, independent probes and the full suite.

## Remediation reviewed and S22-01 disposition

Only `indicators.py` and `conditions.py` changed in the remediation's runtime scope.
The prior reviewed wheel and remediation-start hashes provide comparison evidence.
The original 129 scanner cases, S2-1 core, scanner orchestration, profiles, market
series, broker runtime, frontend and dependencies are unchanged.

The shared `require_finite` helper rejects NaN and both infinities with existing
`DataUnavailable(MALFORMED_SERIES)`. The central `measure` boundary validates a
calculated metric before the scanner constructs any comparison flags. Direct
`compare` validates its value and converted threshold. Both crossover functions
validate all four operands before short-circuit relations. Breakout validates its
resistance operand before a boolean conversion could hide invalid arithmetic.
Paired inclusive comparisons provide BETWEEN; no new core operator is introduced.

The existing scanner wrapper converts data failures into
`ScannerDataFailure(INVALID_RESPONSE)` with instrument ID and safe reason. The
common provider guard preserves provider ID, operation and request correlation.
The existing public error contract does not include a metric field; that remains
an intentional diagnostic limit, not raw exception leakage or a new schema change.
Whole-batch rejection remains intact even after a previous subject has matched.

Arithmetic helpers are not clamped or silently normalized. Ten arithmetic function
ASTs are identical to the original reviewed implementation: SMA, EMA, RSI, ATR,
average volume, relative volume, ROC, momentum and both rolling ranges. Crossover
relations and breakout relation are unchanged except for preceding validation.
The arithmetic-only relative-volume/ROC helpers can still produce infinity for
extreme inputs; the condition-evaluation boundary rejects it. This separation is
consistent with the required invariant and does not allow an invalid decision.

## Independent adversarial probes

A fresh temporary program, `/tmp/twf_s22_rereview_probes.py`, passed **106 assertions**.
It used fabricated schema-valid fixtures, blocked socket connections and changed no
repository source or test files. Fault injections were temporary in-process patches
restored on exit, used to examine currently uncommon NaN/negative-infinity paths.

1. Reproduced the exact volume input `[1e-310] * 20 + [100]`; independently asserted
   the arithmetic helper produces infinity. A separate valid OHLC fixture with the
   N-bars-ago close equal to `1e-310` also produces ROC overflow.
2. Exercised each of GT/GTE/LT/LTE/EQ for both real overflow fixtures, through both
   direct scanner and ProviderAccess. Every case returned typed INVALID_RESPONSE.
   A comparison spy recorded **zero calls**, proving rejection precedes comparison,
   not merely evidence serialization. Former matching and nonmatching paths agree.
3. Directly passed NaN/+inf/−inf through every scalar operator and each of the four
   operands of both crossover functions. All raised the existing typed data failure.
4. Injected each non-finite sign into breakout resistance and SMA operands used by
   cross-above/cross-below. Complete direct and guarded scanner calls rejected all
   cases; boolean conversion did not turn them into normal true/false results.
5. Injected OverflowError, ZeroDivisionError, ValueError, AssertionError and
   AttributeError from a calculation. None escaped the provider boundary; each
   became the existing safe correlated INVALID_RESPONSE.
6. Tested a matching subject followed by an overflowing subject under paired
   BETWEEN. The complete run failed; a subsequent valid-only run still matched.
   ALL/ANY with an otherwise matching or nonmatching first condition could not hide
   the invalid second condition.
7. Finite range values below, at, inside and above inclusive boundaries retained
   expected results. True crossings, an already-above noncrossing, equality at the
   breakout threshold and a genuine breakout retained their expected decisions.
8. Future extreme bars left those crossover/breakout results unchanged at the
   original cutoff.

The original independent review program `/tmp/twf_s22_review_probes.py` was also
rerun: **102 assertions passed**, including exact-rational reference arithmetic,
all 23 metrics' fixed-cutoff reports, moving-average/RSI/relative-volume paths,
availability boundaries and multi-instrument isolation. Its formerly inconsistent
LT/GT overflow observations now both produce typed MALFORMED_SERIES failures.
Together, the independent probes passed **208 assertions**.

The 75 new repository cases have meaningful oracles: actual finite-input overflow,
matching/nonmatching operators, all three non-finite signs, operand positions,
profile evaluation, error code/context, whole-batch behavior and finite boundaries.
They supplement the original 129 cases rather than modifying or weakening them.
The independent boolean-provider probes additionally cover the full scanner path
behind the tests' focused operand/indicator checks.

## Scorecard

```ini
S22_01_FINITE_VALUE_GUARD = PASS
S22_01_ORIGINAL_REPRODUCTION_FIXED = PASS
S22_01_OPERATOR_CONSISTENCY = PASS
S22_01_NAN_BLOCKED = PASS
S22_01_POS_INF_BLOCKED = PASS
S22_01_NEG_INF_BLOCKED = PASS
S22_01_TYPED_FAILURE = PASS
S22_01_WHOLE_BATCH_POLICY_PRESERVED = PASS

FINITE_VALUE_REGRESSION_FREE = PASS
FORMULA_SEMANTICS_UNCHANGED = PASS
LOOKAHEAD_BIAS_STILL_BLOCKED = PASS
S2_2_EXISTING_PROOFS_REGRESSION_FREE = PASS
S22_01_REMEDIATION_TEST_QUALITY = PASS
REGRESSION_FREE = PASS

S22_02_STILL_NONBLOCKING = PASS
S22_03_STILL_NONBLOCKING = PASS
S2_2_DOCUMENTATION_ACCURATE = PASS
```

The full suite preserves all five profiles, scan-only, native scan→Discovery,
capability rejection, ScanRun/ScanMatch lineage, data validation, determinism,
S2-1 contracts and Broker V2 regressions. The earlier three FAIL entries in the
historical HOLD review are resolved by this focused decision; that historical
scorecard is intentionally not rewritten.

## Findings and deferred items

**No blocking findings.** No new MUST FIX BEFORE S2-3 or architectural-hook finding
was identified. S22-01 is closed; the two previous follow-ups remain nonblocking.

| ID     | Severity | Timing        | Area/File                              | Finding                                                                                                                                                                                                                                     | Required Action                                                                   |
| ------ | -------- | ------------- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| S22-02 | LOW      | SAFE TO DEFER | `apps/api/tests/test_broker_v1.py:233` | Existing broker race test relies on coordinator/provider sleep timing. It passed this full run; its unchanged source and prior controlled baseline reproduction remain evidence of test scheduling sensitivity, unrelated to scanner state. | Separate event-synchronization test follow-up; no broker change made here.        |
| S22-03 | LOW      | SAFE TO DEFER | Documentation index and both roadmaps  | Whole-file Prettier warnings were independently reproduced both in the worktree and fresh exports of HEAD.                                                                                                                                  | Separate formatting cleanup; focused status edits preserve historical formatting. |

A single successful run does not prove S22-02 can never recur. Neither deferred
finding is treated as fixed, and neither justifies reopening unrelated broker or
document formatting work in this review.

## Full validation evidence

Commands ran from the repository root unless another directory is specified.

| Command / check                                                                                                              | Result                                                                                                                     |
| ---------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `apps/api/.venv/bin/pytest -q apps/api/tests`                                                                                | **722 passed in 114.87s**, no warnings; 518 baseline + 129 original scanner + 75 remediation cases                         |
| `apps/api/.venv/bin/ruff check apps/api/src apps/api/tests apps/api/alembic`                                                 | PASS                                                                                                                       |
| `apps/api/.venv/bin/ruff format --check apps/api/src apps/api/tests apps/api/alembic`                                        | PASS; 93 files                                                                                                             |
| `.venv/bin/mypy` from `apps/api`                                                                                             | PASS; strict configuration, 92 source files                                                                                |
| `apps/api/.venv/bin/python -m compileall -q apps/api/src apps/api/tests`                                                     | PASS                                                                                                                       |
| `apps/api/.venv/bin/python -m pip check`                                                                                     | PASS; no broken requirements                                                                                               |
| `apps/api/.venv/bin/python -m pip wheel --no-build-isolation --no-deps --no-index ./apps/api -w /tmp/twf-s22-rereview-wheel` | PASS; offline build                                                                                                        |
| Wheel/source comparison                                                                                                      | All 13 discovery modules byte-identical to packaged source                                                                 |
| Original/remediated arithmetic AST comparison                                                                                | All ten arithmetic functions unchanged                                                                                     |
| Import check with socket connect/create_connection blocked                                                                   | Five functional modules import; no broker/database/app composition imports                                                 |
| `PYTHONPATH=apps/api/src:apps/api/tests apps/api/.venv/bin/python /tmp/twf_s22_rereview_probes.py`                           | PASS; 106 fresh independent assertions                                                                                     |
| Same invocation of `/tmp/twf_s22_review_probes.py`                                                                           | PASS; 102 arithmetic/cutoff/isolation assertions                                                                           |
| Local Prettier check of README, implementation and re-review records                                                         | PASS after status updates                                                                                                  |
| Local Prettier check of index/roadmaps and fresh HEAD exports                                                                | Same three pre-existing warnings; S22-03 retained                                                                          |
| Local Markdown parsing/link/anchor checks                                                                                    | PASS after status updates                                                                                                  |
| Current milestone terminology search                                                                                         | S2-2 accepted/frozen; S2-3 active/next; S2-4…S2-8 pending; Sprint 2 active                                                 |
| `git diff --check` and new-record whitespace checks                                                                          | PASS                                                                                                                       |
| Review-start hash comparison                                                                                                 | Only five authorized status documents changed; all 248 other incoming files unchanged; this re-review is the sole new file |

There were no external network or broker calls. Backend regression uses fake
transports and disposable local storage. Frontend, broker runtime and dependencies
are unchanged, so no frontend build/browser test or deployment change was needed.
No runtime source or repository test was edited by the reviewer. Final local-link
validation parsed seven Markdown documents and resolved 177 local links/anchors.

## Exact documentation changes

Created:

- [TWF_S2_2_INTERNAL_SCANNER_V0_REREVIEW.md](TWF_S2_2_INTERNAL_SCANNER_V0_REREVIEW.md).

Modified, relative to the incoming worktree:

- [README.md](../README.md): S2-2 acceptance and S2-3 next-slice status; links re-review.
- [TWF_DOCUMENTATION_INDEX.md](TWF_DOCUMENTATION_INDEX.md): current hierarchy and re-review registration.
- [TWF_DETAILED_ROADMAP.md](TWF_DETAILED_ROADMAP.md): current status and gated next slice.
- [TWF_UX_BUCKET_ROADMAP.md](TWF_UX_BUCKET_ROADMAP.md): current milestone notice; no product UX/bucket completion claim.
- [TWF_S2_2_INTERNAL_SCANNER_V0.md](TWF_S2_2_INTERNAL_SCANNER_V0.md): current acceptance notice above the preserved implementation/remediation history.

**Runtime source changed by reviewer: NO.** Historical HOLD review changed: **NO**.
Tests changed: **NO**. No DOCX, frontend, broker, dependency or unrelated file changed.
No commit, tag, push, merge, rebase, cherry-pick, reset or branch change occurred.

## Decision, authorization and Git recommendation

**GO_S2_3.** The central acceptance question is answered **YES**: TradingView MCP
can be integrated as another ScanProvider without changing accepted Internal Scanner,
ScanProvider, ScanMatch, cutoff or lineage semantics. S22-01 is fully remediated
within the existing scanner validation and failure boundaries.

This authorizes only the next bounded **S2-3 Real Scan Provider Integration,
TradingView MCP first** slice. Exact server/version/tools/authentication/schema,
capabilities/limits, data licensing/retention and security gates still apply before
their dependent integration work. This review neither selects an unverified server
nor grants credential use, live access or a broader product implementation.

It does not authorize Tapetide, production Market Intelligence, production Discovery
Engine, LLM Level-0, TI, TM, LOB, trading from S&D, production ML, event-trigger
subsystems or autonomous trading. S2-4 through S2-8 remain pending. Synthetic scanner
acceptance does not claim real-data calendars/licensing or enable the Scanners UI.

Recommended Git action only: review and commit the S2-2 implementation/remediation,
tests and implementation/acceptance/re-review/status documents together; optionally
create an S2-2 freeze tag on that accepted commit. These actions were not performed.
The accepted/frozen label records milestone acceptance, not a newly created Git tag.

# S2-2 — Independent Internal Scanner V0 Acceptance Review

**Review date: 2026-09-29. Decision: HOLD_S2_2.**

One bounded numeric-validation defect prevents acceptance. Indicator formulas,
completed-bar selection, look-ahead protection, lineage and S2-1 interoperability
pass. The full existing suite passes, but does not cover finite inputs whose
calculated ratio overflows. No core architecture redesign is required.

S2-1 and Broker V2 remain ACCEPTED / FROZEN. S2-2 is implemented but is not
accepted/frozen. S2-3 remains PENDING and is not authorized by this review.
Sprint 2 remains ACTIVE. No runtime or test file was changed during review.

## Preflight, authority and incoming inventory

- Branch: `main`.
- Starting and finishing HEAD: `caadc9d2a8bead840b5b0621d83d006bb2c5dde8`.
- Accepted S2-1 baseline: `twf-s2-1-discovery-foundation`, resolving to HEAD.
- Architecture checkpoint: `twf-scan-discover-architecture-v0.2` → `6db608c`.
- Broker V2 checkpoint: `twf-broker-v2` → `69a643e`; accepted/frozen and unchanged.
- Incoming tracked changes: README, documentation index, detailed roadmap and UX
  bucket roadmap; 18 additions and 16 deletions. No staged or unrelated changes.
- Incoming untracked implementation: six scanner modules, three test/support
  files and the S2-2 implementation record, enumerated below.
- Review-start SHA-256 inventory: 251 tracked/unignored files. All remain
  byte-identical at completion; this acceptance record is the sole new file.

Preflight ran `git branch --show-current`, `git rev-parse HEAD`,
`git status --short`, `git diff --stat`, `git diff --name-status`,
`git log --oneline --decorate -10` and tag listing. Incoming status documents
correctly label S2-2 IMPLEMENTED / READY FOR REVIEW and S2-3 pending.

Governing sources: [README](../README.md),
[S&D architecture](TWF_SCAN_AND_DISCOVER_ARCHITECTURE.md),
[opportunity domain](TWF_OPPORTUNITY_DOMAIN_ARCHITECTURE.md),
[delivery plan](TWF_SPRINT2_SCAN_DISCOVER_DELIVERY_PLAN.md),
[architecture acceptance](TWF_SCAN_DISCOVER_ARCHITECTURE_ACCEPTANCE_REVIEW.md),
[S2-1 implementation](TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION.md),
[original S2-1 review](TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION_ACCEPTANCE_REVIEW.md),
[accepted S2-1 re-review](TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION_REREVIEW.md)
and [S2-2 implementation record](TWF_S2_2_INTERNAL_SCANNER_V0.md).
The current S2-0…S2-8 hierarchy supersedes the older planning grouping; prior
acceptance records remain historical evidence, not current status overrides.

| Incoming new file                                              | Reviewed responsibility                                                  |
| -------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `apps/api/src/twf/discovery/internal_scanner/__init__.py`      | Package boundary                                                         |
| `apps/api/src/twf/discovery/internal_scanner/market_series.py` | Immutable bounded bars, series, availability and injected fixture reader |
| `apps/api/src/twf/discovery/internal_scanner/indicators.py`    | Arithmetic, seeds and warm-up                                            |
| `apps/api/src/twf/discovery/internal_scanner/conditions.py`    | 23 metrics, operators and comparisons                                    |
| `apps/api/src/twf/discovery/internal_scanner/profiles.py`      | Five explicit definition recipes                                         |
| `apps/api/src/twf/discovery/internal_scanner/scanner.py`       | Provider, execution report, typed failure and normalized lineage         |
| `apps/api/tests/internal_scanner_support.py`                   | Fabricated OHLCV fixtures                                                |
| `apps/api/tests/test_internal_scanner_indicators.py`           | 74 indicator/condition cases                                             |
| `apps/api/tests/test_internal_scanner_provider.py`             | 55 provider/profile/flow cases                                           |
| `docs/TWF_S2_2_INTERNAL_SCANNER_V0.md`                         | Implementation evidence and limits                                       |

The six source modules total 750 lines. Existing discovery contracts, provider
guard, history, lifecycle, orchestration and their tests were inspected alongside
the additions. None changed in S2-2. No frontend, dependency, migration, application
composition, broker, transport, credential or deployment file changed.

## Formula, condition and profile review

Independent probes use exact rational arithmetic (`fractions.Fraction`) for
reference calculations, separately from implementation float arithmetic. A fixed
random seed supplies seven periods (1, 2, 3, 14, 20, 50, 252), each with additional
smoothing history. Assertions compare numerical results, not just match counts.

| Measure         | Independently verified semantics                                                                                          |
| --------------- | ------------------------------------------------------------------------------------------------------------------------- |
| SMA             | Mean of the last N completed closes; N bars required                                                                      |
| EMA             | Mean of first N supplied closes seeds the recurrence; alpha 2/(N+1); subsequent supplied history is used                  |
| RSI             | First N changes seed mean gains/losses; Wilder recurrence thereafter; N+1 bars; all-up 100, all-down 0, flat 50           |
| ATR             | True range uses previous close, including upward/downward gaps; first N true ranges seed Wilder smoothing; N+1 bars       |
| Relative volume | Current volume divided by the mean of preceding N volumes, excluding current; explicit missing/zero-baseline failures     |
| Momentum / ROC  | Current minus N-bars-ago close; percentage ratio against that same close                                                  |
| Rolling range   | Maximum/minimum preceding N highs/lows, excluding the tested bar                                                          |
| Crossing        | Previous equality is eligible; current relation must strictly cross; an already-above/below state is not another crossing |
| Breakout        | Current close strictly exceeds prior-20-bar high; equality is not a breakout                                              |

Normal representable formula results pass. This does not excuse the non-finite
intermediate defect in S22-01 below. Zero-range/flat bars, missing warm-up,
zero-volume baselines, NaN/inf input rejection and tolerance boundaries are covered
by source inspection, existing cases and independent probes.

The condition language remains the accepted five comparison operators with flat
ALL/ANY. BETWEEN is a pair of inclusive comparisons in ALL; crossovers are named
boolean metrics with EQ 0/1. There is no eval/exec or provider expression leakage.
Unknown core operator strings fail schema validation; unsupported but valid metric,
interval, unit, boolean/operator pairing or recipe produces typed
UNSUPPORTED_CAPABILITY before input reads. These are two deliberate validation
boundaries, not silent approximation.

All five recipes match their documented definitions and have meaningful positive,
near-miss, negative and insufficient-history cases. Trend continuation checks
SMA50/SMA200 alignment and bounded RSI. Breakout additionally requires relative
volume. Pullback requires an uptrend, price above SMA50, price within the SMA20
zone and a negative one-bar return. Momentum combines positive ROC10 and RSI;
relative volume tests its configured threshold. The pullback rule is explicit,
not subjective pattern recognition or a profitability claim.

## Independent cutoff, isolation and contract evidence

`/tmp/twf_s22_review_probes.py` passed **102 assertions** beyond the repository
suite, then reproduced the numeric defect. It blocked socket connections and used
validated immutable fixtures; no model-construction bypass or real data was used.

- All 23 advertised metrics were scanned at fixed cutoff T, then rescanned at T
  after appending extreme future closes of 10^10 and 1. Entire fixed-clock reports,
  normalized batches and input digests remained equal.
- Separate true cross-above, cross-below and breakout fixtures remained matches
  after future data was appended. This extends the repository's five-profile
  look-ahead tests to EMA and crossover paths explicitly.
- Bars exactly at T are included; later completions are excluded. Equivalent
  Asia/Kolkata and UTC instants give identical reports. Availability one microsecond
  after cutoff produces SERIES_UNAVAILABLE instead of using an older window.
- A four-subject fixture set contains a match, a nonmatch, insufficient history and
  a malformed interval gap. The two defective subjects were exercised separately
  with the valid pair so each reason could be observed under fail-fast behavior.
  Both cause safe, subject-specific whole-batch rejection; a subsequent valid-only
  run returns exactly the matching subject with no state contamination.
- The suite also verifies all five intervals, input bounds, ordering/duplicates,
  invalid OHLC, negative/missing volume, naive timestamps and sanitized reader errors.
  Daily bars use the documented continuous 24-hour fixture clock. No actual exchange
  calendar support or live-data acceptance is inferred.

Provider output passes the existing operation-specific schema/ownership/mode guard.
Health denotes local implementation availability only. Cancellation propagates;
cooperative checkpoints and bounded CPU work are appropriate for this offline slice.
Runtime is bounded by instruments × criteria × bars (64 × 16 × 1,024), with small
repeated scans/copies and no shared cache. No blocking complexity issue was found.

Each match retains exact subject, run, definition/revision, applied profile,
configuration digest, calculated-provider identity and upstream source evidence.
Timeframe is retained in evidence basis; cutoff is retained in batch/report/run and
receipt time; actual source time remains the last eligible bar. The execution report
composes the existing run with exact universe/fingerprint, captures, timing and count.
It does not replace ScanRun or claim durable failed-run recovery.

Native scan-only uses the existing universe/orchestration path. Native matches
enter unchanged Discovery through the existing normalization function. The fixture
S1 → repeat-poll → new-source-bar sequence remains NEW → NEW → CURRENT; lineage
survives, and changed adjustment/configuration cannot silently continue an episode.
There is no scanner-specific branch or provider class in core Discovery.

## Findings

| ID     | Severity | Timing               | Area/File                                                                                            | Finding                                                                                                                                                                                                                                                                                                                                             | Required Action                                                                                                                                                                                                                                                                                                                                                                               |
| ------ | -------- | -------------------- | ---------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| S22-01 | MEDIUM   | MUST FIX BEFORE S2-3 | `indicators.py:72`, `scanner.py:163`, `scanner.py:189`; implementation record failure-policy section | Finite schema-valid inputs can overflow a derived ratio to infinity. The scanner compares it before checking finiteness; a nonmatching branch returns COMPLETE empty, while a matching branch fails during evidence validation. Failure semantics therefore depend on the chosen operator, and the documented blanket rejection policy is not true. | Reject every non-finite calculated value before comparison/ALL/ANY decisions, using a safe typed whole-batch failure. Add finite-input overflow regressions covering matching and nonmatching operators, ALL/ANY and the generic provider guard; include analogous ROC behavior. Reconcile the failure-policy evidence after remediation. No core contract or dependency expansion is needed. |
| S22-02 | LOW      | SAFE TO DEFER        | `apps/api/tests/test_broker_v1.py:233`                                                               | Pre-existing concurrency test assumes a 50 ms coordinator sleep reliably overlaps a 150 ms mock read. Scheduling can invalidate that assumption and make the 409 assertion incorrect for the actual event order.                                                                                                                                    | Separate broker-test follow-up: synchronize the read/disconnect race with explicit events. Do not alter broker code in this scanner review.                                                                                                                                                                                                                                                   |
| S22-03 | LOW      | SAFE TO DEFER        | Documentation index and both roadmaps                                                                | Whole-file Prettier warnings also occur in the committed S2-1 baseline.                                                                                                                                                                                                                                                                             | Separate formatting cleanup; no unrelated reformat during review.                                                                                                                                                                                                                                                                                                                             |

S22-01 is an input-boundary correctness defect, not an incorrect ordinary RSI/ATR
formula, demonstrated live-market incident or architectural contradiction. Its
trigger is an extreme finite value allowed by the present contract, so severity
is bounded. Nevertheless, converting invalid arithmetic into successful absence
violates this review's explicit numeric/failure gate and warrants remediation.

### S22-01 reproducible evidence

Construct a normal validated 21-bar series with constant OHLC close 10, valid
high/low and volumes `[1e-310] * 20 + [100]`. All volumes are finite, nonnegative
and below the documented maximum. `relative_volume.20` computes positive infinity.
Apply a single supported ratio criterion against threshold 1:

| Operator | Direct scanner / common ProviderAccess result          |
| -------- | ------------------------------------------------------ |
| LT       | COMPLETE with zero matches                             |
| LTE      | COMPLETE with zero matches                             |
| EQ       | COMPLETE with zero matches                             |
| GT       | Typed INVALID_RESPONSE; direct reason MALFORMED_SERIES |
| GTE      | Typed INVALID_RESPONSE; direct reason MALFORMED_SERIES |

The evidence model catches infinity only after the scanner has selected a match.
For nonmatches that model is never constructed. A finiteness check on all computed
measurements before any decision closes this gap without changing domain semantics.
No implementation fix was applied during this review.

## Broker concurrency classification

**BROKER_CONCURRENCY_FAILURE_RELATED_TO_S2_2 = NO.** Classification: **B,
pre-existing timing-sensitive test**, NONBLOCKING for S2-2. The exact scheduler/load
cause of the earlier implementation run cannot be reconstructed from this review.

Evidence is independent of the implementation report:

1. Git history places the broker test in accepted Broker V1/V2 history (`4ffff9d`,
   `69a643e`); the incoming worktree has no broker/test changes.
2. The review's full 647-test suite passed, including the race test.
3. `git archive HEAD apps/api` exported the accepted baseline into
   `/tmp/twf-s22-baseline-review`. Ten separate unchanged-baseline invocations of
   the test passed (1.43–1.72 seconds each), using baseline `src`/`tests` on PYTHONPATH.
   No spontaneous failure was reproduced in those ten runs.
4. A separate temporary pytest plugin deliberately extended only this test's
   coordinator sleep to 400 ms, keeping its mock read at 150 ms. Against the same
   committed baseline, this reproduced the 200-versus-409 assertion failure:
   read completion at 05:23:05.262 UTC preceded disconnect at 05:23:05.502 UTC.
   The plugin asserted that no internal-scanner module was imported. This is a
   controlled scheduling reproduction, not a claim of an unmodified spontaneous
   failure or a production disconnect defect.

The failure can thus occur without any S2-2 code when the assumed overlap does not
occur. Runtime behavior is consistent with the observed ordering. The controlled
probe intentionally fails and is not counted as a regression-suite failure.

## Test quality and exact validation

The 129 new cases meaningfully extend 518 baseline cases, including the 124 S2-1
cases. They check independent expected values, warm-up, near misses, failures,
identity and immutable lineage, rather than asserting implementation-generated
answers alone. The uncovered gap is finite-input overflow before a nonmatch; that
regression is required by S22-01. Existing tests were neither edited nor weakened.

Commands below ran from the repository root unless a directory is stated.

| Command / check                                                                                                            | Result                                                                               |
| -------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `apps/api/.venv/bin/pytest -q apps/api/tests`                                                                              | **647 passed in 109.81s**, no warnings                                               |
| `apps/api/.venv/bin/ruff check apps/api/src apps/api/tests apps/api/alembic`                                               | PASS                                                                                 |
| `apps/api/.venv/bin/ruff format --check apps/api/src apps/api/tests apps/api/alembic`                                      | PASS; 92 files                                                                       |
| `.venv/bin/mypy` from `apps/api`                                                                                           | PASS; strict configuration, 91 source files                                          |
| `apps/api/.venv/bin/python -m compileall -q apps/api/src apps/api/tests`                                                   | PASS                                                                                 |
| `apps/api/.venv/bin/python -m pip check`                                                                                   | PASS; no broken requirements                                                         |
| `apps/api/.venv/bin/python -m pip wheel --no-build-isolation --no-deps --no-index ./apps/api -w /tmp/twf-s22-review-wheel` | PASS; offline wheel, all 13 discovery modules byte-equal to source                   |
| Isolated import with socket connect/create_connection prohibited                                                           | PASS; five functional scanner modules; no broker/database/app composition imports    |
| `PYTHONPATH=apps/api/src:apps/api/tests apps/api/.venv/bin/python /tmp/twf_s22_review_probes.py`                           | 102 assertions passed; numeric overflow defect reproduced separately                 |
| Common ProviderAccess overflow probe                                                                                       | Confirmed five operator outcomes shown above                                         |
| `apps/api/.venv/bin/python /tmp/twf_s22_baseline_probe.py`                                                                 | Ten committed-baseline broker repeats passed                                         |
| Baseline pytest with temporary `twf_s22_delay_plugin`                                                                      | Expected assertion failure under deliberately delayed coordinator; no scanner import |
| Local Prettier check of README, implementation record and review record                                                    | PASS                                                                                 |
| Local Prettier check of index and roadmaps, repeated against HEAD exports                                                  | Same three pre-existing warnings; no new formatting regression                       |
| Local Markdown parse/link/anchor validation                                                                                | PASS; six reviewed documents, including this record                                  |
| `git diff --check` and new-file trailing-whitespace check                                                                  | PASS                                                                                 |
| Final SHA-256 comparison against review-start inventory                                                                    | All 251 incoming files unchanged; review record is the only addition                 |

`REGRESSION_FREE = PASS` refers to existing regression behavior, not absence of the
new uncovered defect. No frontend/browser/Docker runs were needed: those inputs
are unchanged. Tests use fabricated data, fake transports and disposable local
storage. No external network, broker, credential or live-trading calls were made.

## Scorecard

PASS values apply to the bounded offline scanner. The three FAIL values below
are consequences of the single S22-01 finding, not three separate defects.

```ini
S2_2_SCOPE_DISCIPLINE = PASS
MARKET_SERIES_CONTRACT = PASS

SMA_CORRECT = PASS
EMA_CORRECT = PASS
RSI_CORRECT = PASS
ATR_CORRECT = PASS
RELATIVE_VOLUME_CORRECT = PASS
MOMENTUM_ROC_CORRECT = PASS
ROLLING_RANGE_CORRECT = PASS

RSI_SEMANTICS = PASS
ATR_SEMANTICS = PASS
RELATIVE_VOLUME_SEMANTICS = PASS
CROSSOVER_SEMANTICS = PASS
BREAKOUT_SEMANTICS = PASS
PULLBACK_PROFILE_SEMANTICS = PASS
CONDITION_ENGINE = PASS

TREND_CONTINUATION_PROFILE = PASS
BREAKOUT_VOLUME_PROFILE = PASS
PULLBACK_PROFILE = PASS
MOMENTUM_PROFILE = PASS
RELATIVE_VOLUME_PROFILE = PASS

LOOKAHEAD_BIAS_BLOCKED = PASS
COMPLETED_BAR_SEMANTICS = PASS
MULTI_INSTRUMENT_ISOLATION = PASS
SCANNER_FAILURE_POLICY = FAIL

INTERNAL_SCANNER_PROVIDER_CONTRACT = PASS
SCANNER_CAPABILITY_ADVERTISEMENT = PASS
SCANMATCH_LINEAGE = PASS
SCANRUN_LINEAGE = PASS
SCAN_ONLY_FLOW = PASS
SCAN_DISCOVERY_INTEROP = PASS
PROVIDER_NEUTRALITY_PRESERVED = PASS

MARKET_DATA_VALIDATION = PASS
NUMERIC_STABILITY = FAIL
SCANNER_DETERMINISM = PASS
SCANNER_COMPLEXITY_SANITY = PASS

S2_2_TEST_QUALITY = PASS
REGRESSION_FREE = PASS
S2_2_DOCUMENTATION_ACCURATE = FAIL

BROKER_CONCURRENCY_FAILURE_RELATED_TO_S2_2 = NO
```

Documentation accurately states formulas, profiles, scope, test counts and pending
milestones. Its FAIL is narrowly the assertion that computation failures cannot
silently become nonmatches; the demonstrated overflow path contradicts that claim.

## Review changes, next gate and Git recommendation

Created exactly:

- `docs/TWF_S2_2_INTERNAL_SCANNER_V0_ACCEPTANCE_REVIEW.md`.

Existing files modified by reviewer: **NONE**. Runtime source changed by reviewer:
**NO**. Tests changed: **NO**. No status promotion, DOCX change, Git mutation or
S2-3 implementation was performed. The four incoming status-document modifications
and all incoming source/test additions remain exactly as received.

**Final decision: HOLD_S2_2.** Remediate S22-01, add its regression cases, rerun
validation and obtain focused acceptance before S2-2 freeze or S2-3 authorization.

Central architecture answer: **YES, the existing core ScanDefinition, ScanRun,
ScanMatch, lineage, cutoff and Discovery semantics can support a real scan provider
without a structural rewrite.** The remaining defect is within scanner numeric
validation. That architectural conclusion does not override the failed acceptance
gate or authorize starting S2-3 now.

If a later focused review clears the hold, the next bounded authorization may be
**S2-3 Real Scan Provider Integration (TradingView MCP first)**, subject to the exact
server/version/tools/auth/schema, data rights and security gates. It must not imply
Tapetide, production market intelligence, production Discovery Engine, LLM Level-0,
TI/TM, LOB, broker execution from S&D, production ML, autonomous trading or an
event-trigger subsystem. Real internal-scanner inputs additionally require approved
calendars, adjustment/data sources and licensing. Durable history, production policy
and complete product UX remain later work; Sprint 2 is not complete.

Recommended Git action only: after remediation and successful focused re-review,
commit S2-2 implementation, tests and review/status evidence together; optionally
create an S2-2 freeze tag on the accepted commit. Do not freeze this held revision.
No commit, tag, push, merge, rebase, cherry-pick or reset was performed.

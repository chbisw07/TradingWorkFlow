# S2-2 — Internal Scanner V0

> **Current status — 2026-09-30: ACCEPTED / FROZEN.** The [focused independent re-review](TWF_S2_2_INTERNAL_SCANNER_V0_REREVIEW.md) closes S22-01 and records `GO_S2_3`. S2-3 Real Scan Provider Integration (TradingView MCP first) is now ACCEPTED / FROZEN WITH DEFERRED HARDENING; S2-4 is NEXT and S2-5 through S2-8 remain PENDING. Sprint 2 remains ACTIVE. The implementation/remediation account below retains its earlier status, validation and gate history; the historical HOLD review is preserved unchanged.

**2026-09-29 — IMPLEMENTED / REMEDIATED / READY FOR RE-REVIEW.** Sprint 2 remains ACTIVE.
S2-1 remains ACCEPTED / FROZEN. S2-3 through S2-8 remain PENDING; this record
is implementation evidence, not independent acceptance or authorization for S2-3.

The [independent HOLD review](TWF_S2_2_INTERNAL_SCANNER_V0_ACCEPTANCE_REVIEW.md)
remains unchanged historical evidence. S22-01 has been remediated as described in
the final section below; acceptance requires focused independent re-review. The
original implementation account and validation results below retain their history.

## Preflight and governing scope

Implementation started on clean `main` at
`caadc9d2a8bead840b5b0621d83d006bb2c5dde8`. The accepted S2-1 freeze tag
`twf-s2-1-discovery-foundation` resolves to that same commit. The
[S2-1 focused re-review](TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION_REREVIEW.md)
records GO_S2_2. Broker V2 remains frozen under `twf-broker-v2`.
No commit, tag, push, merge, rebase, reset or branch change was performed.

The [S&D architecture](TWF_SCAN_AND_DISCOVER_ARCHITECTURE.md),
[opportunity domain](TWF_OPPORTUNITY_DOMAIN_ARCHITECTURE.md),
[delivery plan](TWF_SPRINT2_SCAN_DISCOVER_DELIVERY_PLAN.md),
[architecture acceptance](TWF_SCAN_DISCOVER_ARCHITECTURE_ACCEPTANCE_REVIEW.md) and
[S2-1 implementation/contract record](TWF_S2_1_DOMAIN_CONTRACTS_SYNTHETIC_PROVIDER_FOUNDATION.md)
govern the design. The later approved S2-0…S2-8 breakdown remains current tracking.
The S2-2 implementation prompt explicitly selects the bounded EMA/RSI/ATR/momentum/
crossover/pullback extensions contemplated by the architecture, and confines all
input to offline fixtures. No real-data gate is closed by this implementation.

Architecture deviations: **NONE**. Existing S2-1 domain, provider, lifecycle,
normalization, discovery and history files are unchanged. No duplicate ScanRun,
ScanDefinition, ScanMatch, provider identity, error envelope or profile registry
was introduced. There is no public endpoint, app-startup registration, database,
frontend, broker integration or new dependency.

## Exact capabilities and placement

`InternalScannerV0` implements the existing asynchronous `ScanProvider` port.
Identity: `internal-scanner-v0`, provider `twf-native`, implementation version `1`,
contract `sd.scan.v1`, deployment `LOCAL`, source mode **SYNTHETIC only**.
The existing `ProviderAccess` guard supplies permission/version/schema/provenance
validation and a cooperative deadline. Direct calls are internal/test calls, not
an authorization bypass API. Local health means the implementation is available;
it does not assert dataset coverage, freshness, licensing or live connectivity.

Limits: 64 exact instruments per run, 1,024 bars per series, 16 criteria per
existing definition. Fixture-source construction allows at most 64 × 5 series
with unique instrument/interval keys. No cross-run cache or shared mutable indicator
state exists. Results are sorted by canonical instrument UUID, independently of
universe input ordering. Cancellation is propagated, with a yield between instruments.

| New module under `apps/api/src/twf/discovery/internal_scanner/`                     | Responsibility                                                                                    |
| ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| [**init**.py](../apps/api/src/twf/discovery/internal_scanner/__init__.py)           | Package boundary                                                                                  |
| [market_series.py](../apps/api/src/twf/discovery/internal_scanner/market_series.py) | Immutable bars/series, injected read port, bounded in-memory fixture source and safe data reasons |
| [indicators.py](../apps/api/src/twf/discovery/internal_scanner/indicators.py)       | Pure deterministic arithmetic and explicit warm-up failures                                       |
| [conditions.py](../apps/api/src/twf/discovery/internal_scanner/conditions.py)       | Finite metric allowlist and existing comparison operators                                         |
| [profiles.py](../apps/api/src/twf/discovery/internal_scanner/profiles.py)           | Five named definition recipes and bounded threshold parameters                                    |
| [scanner.py](../apps/api/src/twf/discovery/internal_scanner/scanner.py)             | Native adapter, normalized evidence/matches and returned execution report                         |

## Market-series and cutoff contract

A `Bar` contains aware UTC completion `timestamp`, `available_at`, open/high/low/
close and optional volume. Prices are finite positive values up to 10^12; volume
is finite, nonnegative and at most 10^18. Missing volume is null, not fabricated zero.
OHLC relationships, ordering and duplicate timestamps are validated. A bar cannot
be available before its completion. Nested values are frozen contracts and tuples.

`MarketSeries` retains exact instrument identity, interval, price unit/currency,
adjustment revision, session-basis revision and upstream provenance. The async
`MarketSeriesSource.read(context, instrument, interval)` port returns that contract;
`FixtureMarketSeriesSource` copies and validates caller-supplied immutable fixtures.
It performs no file, network, environment or credential access. No pandas/vendor
payload enters a domain contract.

Supported intervals are `1m`, `5m`, `15m`, `1h`, `1d`. For this offline gate,
fixtures use a **continuous regular clock**: eligible adjacent bars must be exactly
one interval apart. Gaps are diagnosed, never filled. This is deliberately not an
exchange-session/calendar engine: daily fixtures are 24-hour steps, not a claim
about actual trading days or holidays. Actual exchange calendars, corporate-action
adjustments and approved data rights remain gates before real input support.

A run uses only bars completed at or before `ScanRun.as_of`. Any completed bar not
yet available at the cutoff causes an explicit unavailable failure; the scanner
does not silently bridge it with an older window. Future completed bars are excluded
from computation and input digests. Source times remain those of the last eligible
bar, not the request clock. Repeated polling does not manufacture market observations.
Appending valid future bars leaves earlier normalized results and captures unchanged.

## Indicator definitions and numerical policy

Arithmetic uses Python finite floats and `math.fsum`; emitted numeric measurements
are converted through decimal strings into existing evidence contracts. No new
numeric/TA framework is installed. Generic comparison equality uses `math.isclose`
with relative and absolute tolerance 10^-9; GT/LT exclude that equality band and
GTE/LTE include it. Crossings and breakouts use the strict relations specified below.
Thresholds are bounded to absolute value 10^12. All periods are finite/allowlisted
at the provider boundary; pure indicator helpers accept integer periods 1…252.

| Measure / advertised metric          | Definition and warm-up                                                                                                                 |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| `close`, `volume`                    | Last completed bar; volume null is unavailable when requested                                                                          |
| `sma.20`, `.50`, `.200`              | Mean of N latest completed closes; N bars                                                                                              |
| `ema.20`                             | Seed with mean of first N closes in the supplied eligible dataset; recursively update with alpha 2/(N+1); N bars                       |
| `rsi.14`                             | Wilder mean gain/loss seeded from first N changes, then smoothing factor 1/N; N+1 bars. All flat = 50, gain-only = 100, loss-only = 0  |
| `atr.14`                             | True range max(high−low, abs(high−previous close), abs(low−previous close)); seed from first N true ranges, Wilder smoothing; N+1 bars |
| `average_volume.20`                  | Mean of N completed volumes strictly before the tested bar; N+1 bars                                                                   |
| `relative_volume.20`                 | Current completed volume / preceding N-volume average; N+1 bars. Zero baseline or missing required volume is unavailable               |
| `roc.1`, `.10`                       | 100 × (current close / close N bars earlier − 1); N+1 bars                                                                             |
| `momentum.10`                        | Current close − close N bars earlier; N+1 bars                                                                                         |
| `rolling_high.20`, `.252`            | Maximum preceding N highs, excluding current bar; N+1 bars                                                                             |
| `rolling_low.20`, `.252`             | Minimum preceding N lows, excluding current bar; N+1 bars                                                                              |
| `close_sma20_gap`, `close_sma50_gap` | 100 × (close / SMA − 1)                                                                                                                |
| `sma50_sma200_gap`                   | 100 × (SMA50 / SMA200 − 1)                                                                                                             |
| `breakout.20`                        | Boolean current close > maximum preceding 20 highs; current high excluded                                                              |
| `cross_above_sma.20`                 | Previous close ≤ previous SMA20 AND current close > current SMA20; 21 bars                                                             |
| `cross_below_sma.20`                 | Previous close ≥ previous SMA20 AND current close < current SMA20; 21 bars                                                             |

There are 23 advertised metrics. A 252-bar range is labelled by **bar count**, never
claimed to be a true 52-week/calendar range without an approved session basis.
EMA/RSI/ATR seeds depend on the supplied historical dataset; no hidden prehistory
or automatic truncation is assumed. Missing warm-up never returns invented values.

## Conditions and five initial profiles

Definitions use existing `GT`, `GTE`, `LT`, `LTE`, `EQ` comparisons with flat `ALL`
or `ANY`. Inclusive BETWEEN is represented by GTE/LTE in ALL. Crossings and breakout
are finite boolean measures compared with EQ 1 (or EQ 0); other boolean operators
are rejected. Thus no new core operator, parser, arbitrary expression or eval/exec
surface is needed. Unsupported metrics, intervals, units, required capabilities or
source modes fail with typed `UNSUPPORTED_CAPABILITY` before data reads.

`build_profile` expands a known recipe into the existing immutable `ScanDefinition`.
Callers supply definition identity/revision and the existing owner-scoped applied
`ScanProfileReference` within `ScanRun`. The scanner evaluates the definition;
it does not reinterpret profile UUIDs or install a settings registry. Unknown recipe
names are typed unsupported-capability failures. `supported_profiles` advertises
the five recipes alongside the manifest's metric/operator/timeframe lists.

| Recipe               | Default ALL conditions                                                                       |
| -------------------- | -------------------------------------------------------------------------------------------- |
| TREND_CONTINUATION   | close > SMA50; SMA50 > SMA200; RSI14 between 50 and 80 inclusive                             |
| BREAKOUT_WITH_VOLUME | strict prior-20-bar breakout; relative volume ≥ 1.5                                          |
| PULLBACK_IN_UPTREND  | SMA50 > SMA200; close > SMA50; close within ±1% of SMA20; current close below previous close |
| MOMENTUM             | ROC10 > 0; RSI14 ≥ 50                                                                        |
| RELATIVE_VOLUME      | relative volume ≥ 1.5                                                                        |

Bounded parameters permit RSI limits, relative-volume threshold, pullback percentage
zone and ROC minimum. Effective values appear in the expanded definition and its
existing canonical configuration fingerprint; callers must issue the corresponding
applied profile/definition revisions. Indicator periods remain the small advertised
set, rather than an unbounded indicator language. These recipes are deterministic
scan definitions, not profitable-strategy claims or trade recommendations.

## Run, evidence and failure behavior

The caller supplies the existing `ScanRun` identity, owner, request correlation,
cutoff, definition and applied profile. The adapter validates that context and
returns the existing `ProviderBatch[ScanMatch]`. Each match preserves exact subject,
run, definition/revision, profile, configuration fingerprint and actual provider.
Every condition has observed value, threshold, operator and matched flag; ANY retains
nonmatching condition evidence too. Input evidence separately retains the upstream
producer/source. Price unit, interval, adjustment/session basis and algorithm version
are retained or pinned into normalization provenance. Input digests cover only the
eligible bars and their source/basis metadata.

`scan_with_report` returns a small immutable `ScanExecution` composition of the
existing run, exact universe and its fingerprint, injected-clock start/completion
times, per-instrument source captures (including nonmatches), and normalized result.
Result count is derived. It is a returned direct-call audit value, not a new ScanRun
model, persistent coordinator, database registry or interrupted-job recovery system.
Using an injected fixed clock makes reports deterministic as well as results.

The selected policy is **fail-fast for the entire batch**. Insufficient history,
missing required volume, zero volume baseline, malformed data, unavailable input or
an unexpected reader/computation exception never silently becomes a nonmatch or
successful partial result. Direct calls raise `ScannerDataFailure`, a subtype of
existing `ProviderFailure`, with canonical `INVALID_RESPONSE`, affected instrument
ID and a safe `DataReason`. Raw exceptions are discarded. The existing generic
`ProviderAccess` boundary intentionally retains only canonical code/provider/
operation/request context; it does not claim to preserve adapter-specific diagnostics.
A valid empty universe or fully evaluated nonmatching universe returns COMPLETE empty.
There is no partial persistence or shared state to roll back after a failure.

## Tests and validation

New test/support files:

- [internal_scanner_support.py](../apps/api/tests/internal_scanner_support.py): bounded fabricated OHLCV builders, fixed clock and exact identities.
- [test_internal_scanner_indicators.py](../apps/api/tests/test_internal_scanner_indicators.py): 74 cases, independent SMA/EMA/RSI/ATR/relative-volume/range/ROC calculations, all 23 metric mappings, warm-up, zero/missing data, crossover/equality and comparison cases.
- [test_internal_scanner_provider.py](../apps/api/tests/test_internal_scanner_provider.py): 55 cases, five profiles × positive/near-miss/negative plus insufficient data, all intervals, multi-instrument reports, lineage, schema/permission/capability/timeout failures, bounds, malformed bars and discovery interoperability.

The **129 new cases** supplement the unchanged **518 baseline cases** (including
124 S2-1 cases). Fixture data spans rising/falling, flat, breakout/equality false
breakout, pullback, low/high volume, crossover/already-above and insufficient history.
No existing test was weakened or modified. Provider tests prohibit socket access.

Mandatory anti-look-ahead evidence: each of the five positive profiles is evaluated
at T, then reevaluated at T with later extreme bars appended. Entire normalized
results and input captures are equal. Completed-but-not-yet-available data is rejected.
The native S1 → replay → genuine S2 proof retains NEW after replay and promotes to
CURRENT only after the actual source bar advances, using unchanged S2-1 orchestration.
Changed adjustment lineage cannot silently continue the same discovery series.

Validation commands from `apps/api`:

- `.venv/bin/pytest -q`: 647 passed in 104.81s (518 baseline + 129 new cases), no warnings.
- `.venv/bin/ruff check src tests alembic`: passed.
- `.venv/bin/ruff format --check src tests alembic`: passed.
- `.venv/bin/mypy`: passed with strict configuration.
- `.venv/bin/python -m compileall -q src tests`: passed.
- `.venv/bin/python -m pip check`: passed.
- `.venv/bin/python -m pip wheel --no-build-isolation --no-deps --no-index . -w /tmp/twf-s22-wheel`: passed; all 13 discovery module bytes match the wheel, including six new modules.
- Import probe: scanner imports without broker/database/app composition or network access.
- README/new record Prettier, Markdown links/index registration and `git diff --check`: passed; five Markdown documents parsed and 148 local links/anchors resolved. Existing whole-file index/roadmap formatting warnings are baseline issues; no unrelated reformat was performed.

The first full run reported 646 passed and one failure in unchanged
`test_broker_v1.py::test_disconnect_during_provider_read_rejects_result`: the read
completed before the delayed disconnect, so the sleep-based race did not occur.
The isolated rerun passed (1.39s); a subsequent full run without a parallel package
build is recorded above. No broker source/test was changed or weakened. This timing
sensitivity remains a separate test-harness follow-up, not a scanner behavior change.

Backend regression uses fake transports, with no external or broker calls. No frontend,
database schema, container, settings persistence, broker source or dependency changed;
those layers did not require additional builds/migrations/browser checks.

## Exact change inventory and remaining gate

Created: the six modules and three test/support files linked above, and this record.
Modified: README, documentation index, detailed roadmap and UX bucket roadmap current
S2-2 status notices. Historical architecture/acceptance records and S2-1 source/tests
remain unchanged. No DOCX artifact was changed.

Deferred: real data/licensing/calendars/adjustment integration, TradingView MCP,
Tapetide, broker market data, live streams, scheduler, production market intelligence,
Discovery Engine/relevance calibration, LLM, TI/TM, construction/LOB, trading, ML,
advanced indicators/options/fundamentals, UI/charting and durable run/candidate history.

Next gate is independent S2-2 acceptance. This implementation does not authorize
S2-3, imply live-market readiness, complete Sprint 2 or change Broker V2 authority.

```ini
INTERNAL_SCANNER_PROVIDER_IMPLEMENTED = YES
MARKET_SERIES_CONTRACT_IMPLEMENTED = YES
SMA_IMPLEMENTED_AND_TESTED = YES
EMA_IMPLEMENTED_AND_TESTED = YES
RSI_IMPLEMENTED_AND_TESTED = YES
ATR_IMPLEMENTED_AND_TESTED = YES
RELATIVE_VOLUME_IMPLEMENTED_AND_TESTED = YES
MOMENTUM_IMPLEMENTED_AND_TESTED = YES
ROLLING_HIGH_LOW_IMPLEMENTED_AND_TESTED = YES
CONDITION_ENGINE_IMPLEMENTED = YES
CROSSOVER_SEMANTICS_PROVEN = YES
BREAKOUT_SEMANTICS_PROVEN = YES
INITIAL_SCAN_PROFILES_IMPLEMENTED = YES
MULTI_INSTRUMENT_SCAN_PROVEN = YES
SCAN_ONLY_FLOW_PROVEN = YES
SCAN_TO_DISCOVERY_INTEROP_PROVEN = YES
LOOKAHEAD_BIAS_BLOCKED = YES
PROVIDER_CAPABILITIES_PROVEN = YES
UNSUPPORTED_CAPABILITY_TYPED = YES
PROVENANCE_LINEAGE_PRESERVED = YES
NO_EXTERNAL_PROVIDER_REQUIRED = YES
NO_LLM_REQUIRED = YES
BROKER_V2_REGRESSION_FREE = YES
S2_1_REGRESSION_FREE = YES
TESTS_PASS = YES
READY_FOR_S2_2_REVIEW = YES
```

## S22-01 focused remediation — 2026-09-29

**IMPLEMENTED / REMEDIATED / READY FOR RE-REVIEW.** This section supersedes the
initial implementation's numeric-failure claim. It does not supersede the historical
[HOLD acceptance review](TWF_S2_2_INTERNAL_SCANNER_V0_ACCEPTANCE_REVIEW.md), accept or
freeze S2-2, or authorize S2-3. Sprint 2 remains ACTIVE; S2-3 through S2-8 remain PENDING.

Preflight: `main` at `caadc9d2a8bead840b5b0621d83d006bb2c5dde8`, the accepted S2-1
checkpoint. Incoming work comprised the six scanner modules, three test/support
files, implementation/review records and four status documents; no unrelated change
was present. No Git history or branch operation was performed.

The reproduced defect was finite schema-valid volume inputs
`[1e-310] * 20 + [100]` overflowing `relative_volume.20` to positive infinity.
LT/LTE/EQ previously returned normal empty success; GT/GTE failed only when evidence
was constructed. ROC can likewise overflow when a positive finite denominator close
is extremely small. These are invalid computed values, not legitimate nonmatches.

The invariant is now: **every calculated metric used for condition/profile evaluation
must be finite before any comparison**. One shared `indicators.require_finite`
helper raises the existing `DataUnavailable(MALFORMED_SERIES)` for NaN, positive
infinity or negative infinity. It is used at:

- The central `conditions.measure` boundary, after calculation and before the
  scanner builds any condition flags. Future metrics added to the internal dispatcher
  pass the same boundary automatically.
- Direct scalar comparison, validating both value and converted threshold before
  equality tolerance or GT/GTE/LT/LTE/EQ. Paired inclusive BETWEEN uses this path.
- All four crossover operands before either relation can short-circuit, and breakout
  operands before conversion of the strict relation to a boolean metric.
- Existing indicator input validation, reusing the same invariant.

No formula, seed, period, profile, operator, tolerance, cutoff, source contract,
ScanMatch/ScanRun lineage or generic provider contract changed. Pure arithmetic
helpers retain their formulas; evaluation rejects their non-finite outputs rather
than clamping, replacing, epsilon-adjusting or silently hiding them.

The existing scanner catch converts the typed data failure into
`ScannerDataFailure(INVALID_RESPONSE)` with instrument identity and safe
MALFORMED_SERIES reason. The common ProviderAccess guard preserves provider,
operation and request correlation using the existing canonical error envelope.
There is no raw arithmetic exception or value in the public error. Failures reject
the entire run even after an earlier instrument matched, and leave no shared state.
ALL/ANY cannot bypass validation because all requested metrics are evaluated first.

### Focused regression evidence

Created [test_internal_scanner_numeric.py](../apps/api/tests/test_internal_scanner_numeric.py)
with **75 cases**. Before the source fix, **60 failed and 15 passed**, demonstrating
actual regressions rather than tests that merely count successful calls. After the
fix, all 75 pass alongside the original 129 scanner cases (**204 scanner cases**).
Existing test files were not modified.

Coverage includes all five scalar operators for NaN/+inf/−inf; both crossovers
with each of their four operands invalid; breakout resistance validation; actual
relative-volume and ROC overflow with every operator through direct and guarded
provider calls; profile handling of all three non-finite values; ALL/ANY with an
otherwise matching or nonmatching first condition; whole-batch failure after a
valid match under paired BETWEEN; and finite range controls below, at, within and
above inclusive boundaries. Existing finite crossover, equality, indicator and
five-profile tests remain passing and unchanged.

Validation commands (repository root unless stated otherwise):

- `apps/api/.venv/bin/pytest -q apps/api/tests/test_internal_scanner_numeric.py apps/api/tests/test_internal_scanner_indicators.py apps/api/tests/test_internal_scanner_provider.py`: **204 passed in 1.23s**.
- `apps/api/.venv/bin/pytest -q apps/api/tests`: **722 passed in 126.91s**, no warnings (647 previous cases + 75 remediation cases).
- `apps/api/.venv/bin/ruff check apps/api/src apps/api/tests apps/api/alembic`: PASS.
- `apps/api/.venv/bin/ruff format --check apps/api/src apps/api/tests apps/api/alembic`: PASS; 93 files.
- `.venv/bin/mypy` from `apps/api`: PASS; strict configuration, 92 source files.
- `apps/api/.venv/bin/python -m compileall -q apps/api/src apps/api/tests`: PASS.
- `apps/api/.venv/bin/python -m pip check`: PASS.
- `apps/api/.venv/bin/python -m pip wheel --no-build-isolation --no-deps --no-index ./apps/api -w /tmp/twf-s22-remediation-wheel`: PASS; all 13 discovery module bytes match the built wheel.
- Socket-blocked import of all five functional scanner modules: PASS; no broker/database/app composition imported.
- Independent review probes rerun from `/tmp/twf_s22_review_probes.py`: **102 reference/cutoff/isolation assertions pass**; the formerly inconsistent LT/GT overflow paths now both return typed MALFORMED_SERIES failure.
- Local Prettier for README/implementation record, local Markdown links/anchors and `git diff --check`: checked after documentation updates. Index/roadmap whole-file warnings remain S22-03; no broad reformat.

Exact source changes: `indicators.py`, `conditions.py`. Exact new test file:
`test_internal_scanner_numeric.py`. Documentation changes: this implementation
record and current S2-2 status wording in README, documentation index, detailed
roadmap and UX bucket roadmap. The acceptance review remains byte-identical.
Scanner orchestration, original tests, broker code, frontend, dependencies,
persistence and accepted S2-1 code remain unchanged.

Architecture deviations: **NONE**. S22-02 broker timing-test sensitivity and
S22-03 pre-existing formatting warnings remain deferred, as independently reviewed.
No external provider/broker calls, UI work or later-scope integration were introduced.

```ini
S22_01_FINITE_VALUE_GUARD = PASS
S22_01_GT_NONFINITE_BLOCKED = PASS
S22_01_GTE_NONFINITE_BLOCKED = PASS
S22_01_LT_NONFINITE_BLOCKED = PASS
S22_01_LTE_NONFINITE_BLOCKED = PASS
S22_01_EQ_NONFINITE_BLOCKED = PASS
S22_01_BETWEEN_NONFINITE_BLOCKED = PASS
S22_01_CROSSOVER_NONFINITE_BLOCKED = PASS
S22_01_NAN_BLOCKED = PASS
S22_01_POS_INF_BLOCKED = PASS
S22_01_NEG_INF_BLOCKED = PASS
S22_01_MATCHING_PATH_BLOCKED = PASS
S22_01_NONMATCHING_PATH_BLOCKED = PASS
S22_01_TYPED_FAILURE = PASS
S22_01_WHOLE_BATCH_POLICY_PRESERVED = PASS
FINITE_VALUE_REGRESSION_FREE = PASS
LOOKAHEAD_BIAS_STILL_BLOCKED = PASS
S2_1_REGRESSION_FREE = PASS
BROKER_V2_REGRESSION_FREE = PASS
TESTS_PASS = PASS
READY_FOR_S2_2_REREVIEW = YES
```

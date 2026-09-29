import asyncio
import socket
from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal
from functools import partial
from typing import Any

import pytest
from discovery_support import (
    EPISODE,
    NOW,
    OTHER,
    OWNER,
    FixtureGrants,
    context,
    intent,
    proof,
    replace,
    window,
)
from internal_scanner_support import run_for, series, with_last
from pydantic import ValidationError

from twf.discovery.domain import Comparison, Criterion, ScanDefinition, ScanMatch, SourceMode
from twf.discovery.internal_scanner.market_series import (
    DataReason,
    FixtureMarketSeriesSource,
    MarketSeries,
)
from twf.discovery.internal_scanner.profiles import (
    IDENTITY,
    PROFILE_NAMES,
    ProfileParameters,
    build_profile,
)
from twf.discovery.internal_scanner.scanner import InternalScannerV0, ScannerDataFailure
from twf.discovery.providers import ProviderAccess, ProviderBatch, ProviderFailure
from twf.discovery.service import scan_input
from twf.discovery.synthetic import SyntheticUniverseProvider, fixture_id, fixture_instruments
from twf.integrations.contracts import ErrorCode


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def deny(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Internal Scanner must remain offline")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "create_connection", deny)


def definition(name: str = "RELATIVE_VOLUME") -> ScanDefinition:
    return build_profile(name, context(), fixture_id("internal-" + name), interval="1m")


def scanner(data: tuple[MarketSeries, ...]) -> InternalScannerV0:
    return InternalScannerV0(FixtureMarketSeriesSource(data), now=lambda: NOW)


def evaluate(data: MarketSeries, name: str = "RELATIVE_VOLUME") -> ProviderBatch[ScanMatch]:
    return asyncio.run(
        scanner((data,)).scan(context(), run_for(definition(name)), (data.instrument,))
    )


def fixture(name: str, outcome: str) -> MarketSeries:
    if name == "TREND_CONTINUATION":
        if outcome == "positive":
            return series([100 + i * 0.1 + (i % 4) * 0.15 for i in range(220)])
        # Trend criteria pass but RSI=100 breaches the upper bound.
        if outcome == "near":
            return series([100 + i * 0.1 for i in range(220)])
        return series([150 - i * 0.1 for i in range(220)])
    if name == "PULLBACK_IN_UPTREND":
        if outcome == "positive":
            return series([100 + i * 0.2 for i in range(219)] + [142])
        # In-zone/uptrend, but current close rises instead of pulling back.
        if outcome == "near":
            return series([100 + i * 0.2 for i in range(218)] + [141, 142])
        return series([150 - i * 0.1 for i in range(220)])
    if name == "MOMENTUM":
        if outcome == "positive":
            return series([100 + i for i in range(30)])
        if outcome == "near":
            return series([100] * 30)  # ROC exactly zero, RSI neutral 50.
        return series([150 - i for i in range(30)])
    closes = [10] * 20 + [10.2 if outcome == "positive" else 10.1 if outcome == "near" else 9]
    if name == "BREAKOUT_WITH_VOLUME":
        return series(closes, volumes=[100] * 20 + [200])
    volume = 150 if outcome == "positive" else 149.99 if outcome == "near" else 50
    return series([10] * 21, volumes=[100] * 20 + [volume])


@pytest.mark.parametrize("name", PROFILE_NAMES)
@pytest.mark.parametrize("outcome", ["positive", "near", "negative"])
def test_profiles_positive_near_miss_negative_with_lineage(name: str, outcome: str) -> None:
    data = fixture(name, outcome)
    result = evaluate(data, name)
    assert len(result.items) == (1 if outcome == "positive" else 0)
    if result.items:
        match = result.items[0]
        run = run_for(definition(name))
        assert match.lineage.run_id == run.run_id
        assert match.lineage.definition_id == run.definition.definition_id
        assert match.lineage.profile == run.profile
        assert match.lineage.configuration_fingerprint == run.configuration_fingerprint
        assert match.provenance.producer == IDENTITY
        assert match.instrument == data.instrument
        assert match.evidence[-1].provenance.producer == data.provenance.producer
        assert all(e.source_data_time == NOW for e in match.evidence)
        assert match.evidence[0].measures[-2].value is True


@pytest.mark.parametrize("name", PROFILE_NAMES)
def test_profiles_insufficient_data_fail_honestly(name: str) -> None:
    with pytest.raises(ScannerDataFailure) as exc:
        evaluate(series([10]), name)
    assert exc.value.reason == DataReason.INSUFFICIENT_HISTORY
    assert exc.value.error.code == ErrorCode.INVALID_RESPONSE
    assert exc.value.error.operation == "sd.scan"


def test_multi_instrument_scan_only_report_and_provider_contract() -> None:
    async def check() -> None:
        instruments = fixture_instruments()
        data = tuple(
            series([10] * 21, volumes=[100] * 20 + [200 if i % 2 == 0 else 50], instrument=ins)
            for i, ins in enumerate(instruments)
        )
        native = scanner(data)
        run = run_for(definition())
        access = ProviderAccess(FixtureGrants())
        result = await access.call(
            native,
            context(),
            "sd.scan",
            "sd.scan.v1",
            lambda: native.scan(context(), run, instruments),
        )
        assert {m.instrument for m in result.items} == {instruments[0], instruments[2]}
        assert [m.instrument.instrument_id.hex for m in result.items] == sorted(
            m.instrument.instrument_id.hex for m in result.items
        )
        assert ProviderBatch[ScanMatch].model_validate_json(result.model_dump_json()) == result
        report = await native.scan_with_report(context(), run, instruments)
        assert report.result == result and report.result_count == 2 and len(report.captures) == 4
        assert report.started_at == report.completed_at == NOW
        assert report.run == run and report.universe == instruments
        reverse = await native.scan_with_report(context(), run, tuple(reversed(instruments)))
        assert (
            reverse.result == result and reverse.universe_fingerprint == report.universe_fingerprint
        )
        assert (await native.health(context())).identity == IDENTITY
        assert native.manifest.supported_timeframes == ("1m", "5m", "15m", "1h", "1d")
        assert native.supported_profiles == PROFILE_NAMES
        # Existing scan-only orchestration and universe provider accept the native adapter.
        service = proof()
        assert (
            await service.scan_only(context(), run, SyntheticUniverseProvider(), native)
            == result.items
        )
        with pytest.raises(LookupError):
            service.history.episode(OWNER, EPISODE)

    asyncio.run(check())


def test_scan_to_discovery_s1_s2_and_replay_without_conversion_hacks() -> None:
    async def check() -> None:
        data = series([100 + i for i in range(220)])
        native = scanner((with_last(data, 320),))
        access = ProviderAccess(FixtureGrants())
        service = proof()
        snapshots = []
        for seconds in (0, 30, 60):
            ctx = context(seconds)
            run = run_for(definition("MOMENTUM"), seconds)
            result = await access.call(
                native,
                ctx,
                "sd.scan",
                "sd.scan.v1",
                partial(native.scan, ctx, run, (data.instrument,)),
            )
            match = result.items[0]
            candidate = service.discover(ctx, scan_input(match), intent(), window(), EPISODE)
            snapshot = service.history.snapshots(OWNER, EPISODE)[-1]
            snapshots.append(snapshot)
            assert snapshot.lineage.scan == match.lineage
            assert candidate.lifecycle == ("CURRENT" if seconds == 60 else "NEW")
        assert snapshots[0].source_data_time == snapshots[1].source_data_time
        assert service.history.comparable_observations(OWNER, EPISODE) == 2
        assert snapshots[0].provenance.producer == IDENTITY

    asyncio.run(check())


@pytest.mark.parametrize("name", PROFILE_NAMES)
def test_future_bars_cannot_change_past_evaluation(name: str) -> None:
    data = fixture(name, "positive")
    future = with_last(with_last(data, 500), 1, seconds=120)
    assert evaluate(data, name) == evaluate(future, name)
    a = asyncio.run(
        scanner((data,)).scan_with_report(context(), run_for(definition(name)), (data.instrument,))
    )
    b = asyncio.run(
        scanner((future,)).scan_with_report(
            context(), run_for(definition(name)), (data.instrument,)
        )
    )
    assert a.captures == b.captures


def test_unavailable_completed_bar_and_intrabar_future_are_not_used() -> None:
    data = fixture("RELATIVE_VOLUME", "positive")
    last = replace(data.bars[-1], available_at=NOW + timedelta(seconds=1))
    with pytest.raises(ScannerDataFailure) as exc:
        evaluate(replace(data, bars=(*data.bars[:-1], last)))
    assert exc.value.reason == DataReason.SERIES_UNAVAILABLE
    # The same bar is excluded before completion; the remaining history lacks warm-up.
    with pytest.raises(ScannerDataFailure) as exc:
        asyncio.run(
            scanner((data,)).scan(context(-1), run_for(definition(), -1), (data.instrument,))
        )
    assert exc.value.reason == DataReason.INSUFFICIENT_HISTORY


@pytest.mark.parametrize(
    "mutation", ["gap", "duplicate", "reversed", "ohlc", "volume", "nan", "naive"]
)
def test_malformed_market_data(mutation: str) -> None:
    data = fixture("RELATIVE_VOLUME", "positive")
    if mutation == "gap":
        with pytest.raises(ScannerDataFailure) as exc:
            evaluate(replace(data, bars=data.bars[1:10] + data.bars[11:]))
        assert exc.value.reason == DataReason.MALFORMED_SERIES
        return
    with pytest.raises(ValidationError):
        if mutation == "duplicate":
            replace(data, bars=(*data.bars, data.bars[-1]))
        elif mutation == "reversed":
            replace(data, bars=tuple(reversed(data.bars)))
        else:
            options: dict[str, dict[str, Any]] = {
                "ohlc": {"low": 99},
                "volume": {"volume": -1},
                "nan": {"close": float("nan")},
                "naive": {"timestamp": NOW.replace(tzinfo=None)},
            }
            replace(data.bars[-1], **options[mutation])


def test_fail_fast_no_successful_partial_or_empty_on_bad_instrument() -> None:
    good = fixture("RELATIVE_VOLUME", "positive")
    bad = series([10], instrument=fixture_instruments()[1])
    native = scanner((good, bad))
    with pytest.raises(ScannerDataFailure) as exc:
        asyncio.run(
            native.scan(context(), run_for(definition()), (good.instrument, bad.instrument))
        )
    assert exc.value.instrument_id == bad.instrument.instrument_id
    assert exc.value.reason == DataReason.INSUFFICIENT_HISTORY
    assert evaluate(good).items  # Failure creates no shared indicator/run state.


@pytest.mark.parametrize(
    "change", ["indicator", "interval", "unit", "capability", "mode", "boolean-op"]
)
def test_unsupported_request_before_data_read(change: str) -> None:
    class NeverRead:
        async def read(self, *args: Any) -> MarketSeries:
            raise AssertionError("Unsupported requests must not read data")

    d = definition()
    if change == "indicator":
        d = replace(d, criteria=(replace(d.criteria[0], metric="macd"),))
    elif change == "interval":
        d = replace(d, timeframe="3m")
    elif change == "unit":
        d = replace(d, criteria=(replace(d.criteria[0], unit="wrong"),))
    elif change == "capability":
        d = replace(d, required_capabilities=("sd.future",))
    elif change == "mode":
        d = replace(d, source_mode=SourceMode.LIVE_SNAPSHOT)
    else:
        d = replace(
            d,
            criteria=(
                Criterion(
                    metric="breakout.20",
                    operator=Comparison.GT,
                    threshold=Decimal(0),
                    unit="boolean",
                ),
            ),
        )
    with pytest.raises(ProviderFailure) as exc:
        asyncio.run(
            InternalScannerV0(NeverRead()).scan(context(), run_for(d), fixture_instruments())
        )
    assert exc.value.error.code == ErrorCode.UNSUPPORTED_CAPABILITY


def test_unknown_profile_parameters_and_user_scope() -> None:
    with pytest.raises(ProviderFailure) as exc:
        build_profile("UNKNOWN", context(), fixture_id("bad"))
    assert exc.value.error.code == ErrorCode.UNSUPPORTED_CAPABILITY
    with pytest.raises(ValidationError):
        ProfileParameters(rsi_min=80, rsi_max=20)
    data = fixture("RELATIVE_VOLUME", "positive")
    native = scanner((data,))
    with pytest.raises(ProviderFailure):
        asyncio.run(native.scan(context(), run_for(definition(), owner=OTHER), (data.instrument,)))
    with pytest.raises(ProviderFailure) as exc:
        asyncio.run(
            ProviderAccess(FixtureGrants(OTHER)).call(
                native,
                context(),
                "sd.scan",
                "sd.scan.v1",
                lambda: native.scan(context(), run_for(definition()), (data.instrument,)),
            )
        )
    assert exc.value.error.code == ErrorCode.AUTHORIZATION_FAILED


@pytest.mark.parametrize(
    "interval,step", [("1m", 60), ("5m", 300), ("15m", 900), ("1h", 3600), ("1d", 86400)]
)
def test_bounded_timeframes_and_aware_utc(interval: str, step: int) -> None:
    data = series([10] * 21, volumes=[100] * 20 + [200], interval=interval, step=step)
    d = build_profile("RELATIVE_VOLUME", context(), fixture_id("interval"), interval=interval)
    result = asyncio.run(scanner((data,)).scan(context(), run_for(d), (data.instrument,)))
    assert result.items[0].evidence[0].observed_at == NOW


def test_any_combination_and_paired_range_use_original_contract() -> None:
    data = series([10] * 25)
    d = replace(
        definition(),
        criteria=(
            Criterion(metric="close", operator=Comparison.GT, threshold=Decimal(11), unit="price"),
            Criterion(metric="close", operator=Comparison.LT, threshold=Decimal(12), unit="price"),
        ),
    )
    native = scanner((data,))
    assert not asyncio.run(native.scan(context(), run_for(d), (data.instrument,))).items
    assert asyncio.run(
        native.scan(context(), run_for(replace(d, combination="ANY")), (data.instrument,))
    ).items


def test_parallel_runs_deterministic_and_no_shared_state() -> None:
    async def check() -> None:
        data = fixture("RELATIVE_VOLUME", "positive")
        native = scanner((data,))
        run = run_for(definition())
        values = await asyncio.gather(
            *(native.scan(context(), run, (data.instrument,)) for _ in range(4))
        )
        assert all(v == values[0] for v in values)

    asyncio.run(check())


def test_malformed_reader_result_sanitized_and_cancelled_deadline() -> None:
    class Broken:
        async def read(self, *args: Any) -> MarketSeries:
            raise KeyError("private-reader-internals")

    with pytest.raises(ScannerDataFailure) as exc:
        asyncio.run(
            InternalScannerV0(Broken()).scan(
                context(), run_for(definition()), fixture_instruments()
            )
        )
    assert exc.value.reason == DataReason.MALFORMED_SERIES
    assert "private" not in str(exc.value)

    async def check() -> None:
        cancelled = False

        class Slow:
            async def read(self, *args: Any) -> MarketSeries:
                nonlocal cancelled
                try:
                    await asyncio.sleep(1)
                    return fixture("RELATIVE_VOLUME", "positive")
                finally:
                    cancelled = True

        native = InternalScannerV0(Slow())
        with pytest.raises(ProviderFailure) as failure:
            await ProviderAccess(FixtureGrants(), timeout_seconds=0.01).call(
                native,
                context(),
                "sd.scan",
                "sd.scan.v1",
                lambda: native.scan(context(), run_for(definition()), fixture_instruments()),
            )
        assert failure.value.error.code == ErrorCode.TIMEOUT and cancelled

    asyncio.run(check())


def test_immutable_source_and_missing_zero_volume_do_not_become_nonmatches() -> None:
    data = fixture("RELATIVE_VOLUME", "positive")
    with pytest.raises(ValidationError):
        data.bars[0].close = 999
    cases: list[tuple[Sequence[float | None], DataReason]] = [
        ([0] * 20 + [100], DataReason.ZERO_BASELINE),
        ([100] * 20 + [None], DataReason.MISSING_VOLUME),
    ]
    for volumes, reason in cases:
        with pytest.raises(ScannerDataFailure) as exc:
            evaluate(series([10] * 21, volumes=volumes))
        assert exc.value.reason == reason


def test_definition_config_changes_have_distinct_lineage() -> None:
    data = fixture("RELATIVE_VOLUME", "positive")
    d = definition()
    native = scanner((data,))
    a = asyncio.run(native.scan(context(), run_for(d), (data.instrument,))).items[0]
    revised = replace(d, revision=2, criteria=(replace(d.criteria[0], threshold=Decimal("1.4")),))
    b = asyncio.run(native.scan(context(), run_for(revised), (data.instrument,))).items[0]
    assert a.lineage.configuration_fingerprint != b.lineage.configuration_fingerprint
    assert a.scan_match_id != b.scan_match_id
    assert a.lineage.definition_revision == 1 and b.lineage.definition_revision == 2


def test_universe_and_dataset_bounds_are_explicit() -> None:
    data = fixture("RELATIVE_VOLUME", "positive")
    native = scanner((data,))
    for instruments in ((data.instrument, data.instrument), (data.instrument,) * 65):
        with pytest.raises(ProviderFailure) as exc:
            asyncio.run(native.scan(context(), run_for(definition()), instruments))
        assert exc.value.error.code.value == "INVALID_REQUEST"
    assert asyncio.run(native.scan(context(), run_for(definition()), ())).items == ()
    with pytest.raises(ValueError):
        FixtureMarketSeriesSource((data, data))
    with pytest.raises(ValidationError):
        series([10] * 1025)
    missing = scanner(())
    with pytest.raises(ScannerDataFailure) as exc:
        asyncio.run(missing.scan(context(), run_for(definition()), (data.instrument,)))
    assert exc.value.reason == DataReason.SERIES_UNAVAILABLE


def test_fresh_scan_rejects_mutated_unit_or_adjustment_continuation() -> None:
    async def check() -> None:
        data = series([100 + i for i in range(220)])
        service = proof()
        native = scanner((data,))
        d = definition("MOMENTUM")
        first = (await native.scan(context(), run_for(d), (data.instrument,))).items[0]
        service.discover(context(), scan_input(first), intent(), window(), EPISODE)
        before = service.history.snapshots(OWNER, EPISODE)
        changed = replace(with_last(data, 320), adjustment=replace(data.adjustment, version="2"))
        later = (
            await scanner((changed,)).scan(context(60), run_for(d, 60), (data.instrument,))
        ).items[0]
        with pytest.raises(ValueError, match="Incomparable"):
            service.discover(context(60), scan_input(later), intent(), window(), EPISODE)
        assert service.history.snapshots(OWNER, EPISODE) == before

    asyncio.run(check())

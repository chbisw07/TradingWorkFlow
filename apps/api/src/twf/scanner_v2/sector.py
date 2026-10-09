"""Dynamic sector V1: pure completed-session arithmetic and centralized policy."""

from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field

from twf.discovery.internal_scanner.indicators import sma
from twf.discovery.internal_scanner.market_series import Bar
from twf.instrument_metadata.contracts import InstrumentMetadataSummary
from twf.integrations.contracts import Contract

NEUTRAL_BAND_PP = 0.25
SECTOR_SCORES = {"STRONG": 5, "SUPPORTIVE": 3, "NEUTRAL": 0, "WEAK": -5, "UNKNOWN": 0}


class SectorContextEvidence(Contract):
    policy_version: str = "sector.v1"
    sector: str | None = None
    industry: str | None = None
    context_benchmark: str | None = None
    context_benchmark_symbol: str | None = None
    benchmark_trend: str = "UNKNOWN"
    benchmark_return_1d: float | None = None
    benchmark_return_5d: float | None = None
    benchmark_return_20d: float | None = None
    nifty_return_5d: float | None = None
    nifty_return_20d: float | None = None
    sector_rs_5d: float | None = None
    sector_rs_20d: float | None = None
    candidate_return_5d: float | None = None
    candidate_return_20d: float | None = None
    candidate_vs_sector_rs_5d: float | None = None
    candidate_vs_sector_rs_20d: float | None = None
    candidate_relative_state: str = "UNKNOWN"
    rotation_state: str = "UNKNOWN"
    sector_state: str = "UNKNOWN"
    contribution: int = Field(default=0, ge=-5, le=5)
    status: Literal["AVAILABLE", "PARTIAL", "UNAVAILABLE"] = "UNAVAILABLE"
    source: str = "dhan"
    identity_source: str = "Instrument Metadata"
    metadata_updated_at: AwareDatetime | None = None
    as_of: AwareDatetime | None = None
    nifty_as_of: AwareDatetime | None = None
    candidate_as_of: AwareDatetime | None = None
    received_at: AwareDatetime | None = None
    freshness: str = "UNAVAILABLE"
    missing_evidence: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    supporting_factors: tuple[str, ...] = ()
    contradicting_factors: tuple[str, ...] = ()
    neutral_factors: tuple[str, ...] = ()
    neutral_band_pp: float = NEUTRAL_BAND_PP


def daily_return(bars: tuple[Bar, ...], sessions: int) -> float | None:
    return 100 * (bars[-1].close / bars[-sessions - 1].close - 1) if len(bars) > sessions else None


def trend(bars: tuple[Bar, ...]) -> str:
    if len(bars) < 50:
        return "UNKNOWN"
    closes = [bar.close for bar in bars]
    fast, slow = sma(closes, 20), sma(closes, 50)
    return (
        "BULLISH"
        if closes[-1] > fast > slow
        else "BEARISH"
        if closes[-1] < fast < slow
        else "NEUTRAL"
    )


def relative_return(left: tuple[Bar, ...], right: tuple[Bar, ...], sessions: int) -> float | None:
    """Compare identical exchange-session windows, never different endpoints/gaps."""
    if len(left) <= sessions or len(right) <= sessions:
        return None

    def dates(bars: tuple[Bar, ...]) -> tuple[date, ...]:
        return tuple(
            b.timestamp.astimezone(ZoneInfo("Asia/Kolkata")).date() for b in bars[-sessions - 1 :]
        )

    if dates(left) != dates(right):
        return None
    a, b = daily_return(left, sessions), daily_return(right, sessions)
    assert a is not None and b is not None
    return a - b


def rotation(rs5: float | None, rs20: float | None, band: float = NEUTRAL_BAND_PP) -> str:
    if rs5 is None or rs20 is None:
        return "UNKNOWN"
    # Compare five-session excess return with one quarter of the 20-session
    # excess return: an explicitly linear momentum proxy, not equal horizons.
    acceleration = rs5 - rs20 / 4
    if rs5 > band and acceleration > band:
        return "IMPROVING"
    if rs5 < -band and acceleration < -band:
        return "DETERIORATING"
    return "STABLE"


def assessment(benchmark_trend: str, rs5: float | None, rs20: float | None) -> str:
    # Minimum usable assessment is SMA50 trend + aligned 5-session NIFTY RS.
    if benchmark_trend == "UNKNOWN" or rs5 is None:
        return "UNKNOWN"
    if benchmark_trend == "BULLISH" and rs5 > NEUTRAL_BAND_PP:
        return "STRONG" if rs20 is not None and rs20 > NEUTRAL_BAND_PP else "SUPPORTIVE"
    if benchmark_trend == "BEARISH" and rs5 < -NEUTRAL_BAND_PP:
        return "WEAK"
    if benchmark_trend == "BULLISH" and rs5 >= -NEUTRAL_BAND_PP:
        return "SUPPORTIVE"
    return "NEUTRAL"


def sector_score(state: str, direction: str) -> int:
    score = SECTOR_SCORES.get(state, 0)
    return score if direction == "BULLISH" else -score if direction == "BEARISH" else 0


def assess_sector(
    metadata: InstrumentMetadataSummary | None,
    benchmark: tuple[Bar, ...],
    nifty: tuple[Bar, ...],
    candidate: tuple[Bar, ...],
    *,
    direction: str,
    candidate_symbol: str,
    received_at: datetime | None = None,
    failures: tuple[str, ...] = (),
    neutral_band_pp: float = NEUTRAL_BAND_PP,
) -> SectorContextEvidence:
    missing = list(failures)
    warnings: list[str] = []
    if metadata is None or not metadata.context_benchmark_symbol or not metadata.context_benchmark:
        missing.append("No analytical context benchmark mapped")
        benchmark = ()
    if metadata and not metadata.present_in_latest_snapshot:
        warnings.append(
            "Benchmark mapping uses last-known metadata absent from the latest snapshot"
        )
    benchmark_trend = trend(benchmark)
    metrics = {
        "benchmark_return_1d": daily_return(benchmark, 1),
        "benchmark_return_5d": daily_return(benchmark, 5),
        "benchmark_return_20d": daily_return(benchmark, 20),
        "nifty_return_5d": daily_return(nifty, 5),
        "nifty_return_20d": daily_return(nifty, 20),
        "sector_rs_5d": relative_return(benchmark, nifty, 5),
        "sector_rs_20d": relative_return(benchmark, nifty, 20),
        "candidate_return_5d": daily_return(candidate, 5),
        "candidate_return_20d": daily_return(candidate, 20),
        "candidate_vs_sector_rs_5d": relative_return(candidate, benchmark, 5),
        "candidate_vs_sector_rs_20d": relative_return(candidate, benchmark, 20),
    }
    if benchmark_trend == "UNKNOWN":
        missing.append("Benchmark trend requires 50 completed daily bars")
    for key, val in metrics.items():
        if val is None:
            missing.append(
                f"{key.replace('_', ' ')} unavailable: insufficient or unaligned completed sessions"
            )
    rs5, rs20 = metrics["sector_rs_5d"], metrics["sector_rs_20d"]
    state = assessment(benchmark_trend, rs5, rs20)
    rotating = rotation(rs5, rs20)
    candidate_rs = metrics["candidate_vs_sector_rs_5d"]
    relative = (
        "UNKNOWN"
        if candidate_rs is None
        else "OUTPERFORMING"
        if candidate_rs > neutral_band_pp
        else "UNDERPERFORMING"
        if candidate_rs < -neutral_band_pp
        else "IN_LINE"
    )
    supporting: list[str] = []
    contradicting: list[str] = []
    neutral: list[str] = []
    name = metadata.context_benchmark if metadata else "Sector benchmark"

    def fact(text: str, sign: int) -> None:
        interpreted = sign if direction == "BULLISH" else -sign if direction == "BEARISH" else 0
        (supporting if interpreted > 0 else contradicting if interpreted < 0 else neutral).append(
            text
        )

    if benchmark_trend != "UNKNOWN":
        fact(
            f"{name} is in a {benchmark_trend.lower()} trend.",
            {"BULLISH": 1, "BEARISH": -1}.get(benchmark_trend, 0),
        )
    if rs5 is not None:
        fact(
            f"{name} relative to NIFTY: {rs5:+.2f} pp over 5 completed sessions.",
            1 if rs5 > NEUTRAL_BAND_PP else -1 if rs5 < -NEUTRAL_BAND_PP else 0,
        )
    if candidate_rs is not None:
        fact(
            f"{candidate_symbol} relative to {name}: {candidate_rs:+.2f} pp "
            f"over 5 completed sessions ({relative.lower().replace('_', ' ')}).",
            1 if relative == "OUTPERFORMING" else -1 if relative == "UNDERPERFORMING" else 0,
        )
    if rotating != "UNKNOWN":
        fact(
            f"Sector relative strength is {rotating.lower()}.",
            1 if rotating == "IMPROVING" else -1 if rotating == "DETERIORATING" else 0,
        )
    return SectorContextEvidence(
        sector=metadata.sector if metadata else None,
        industry=metadata.industry if metadata else None,
        context_benchmark=metadata.context_benchmark if metadata else None,
        context_benchmark_symbol=metadata.context_benchmark_symbol if metadata else None,
        metadata_updated_at=metadata.metadata_updated_at if metadata else None,
        benchmark_trend=benchmark_trend,
        benchmark_return_1d=metrics["benchmark_return_1d"],
        benchmark_return_5d=metrics["benchmark_return_5d"],
        benchmark_return_20d=metrics["benchmark_return_20d"],
        nifty_return_5d=metrics["nifty_return_5d"],
        nifty_return_20d=metrics["nifty_return_20d"],
        sector_rs_5d=metrics["sector_rs_5d"],
        sector_rs_20d=metrics["sector_rs_20d"],
        candidate_return_5d=metrics["candidate_return_5d"],
        candidate_return_20d=metrics["candidate_return_20d"],
        candidate_vs_sector_rs_5d=metrics["candidate_vs_sector_rs_5d"],
        candidate_vs_sector_rs_20d=metrics["candidate_vs_sector_rs_20d"],
        candidate_relative_state=relative,
        rotation_state=rotating,
        sector_state=state,
        contribution=sector_score(state, direction),
        status="UNAVAILABLE"
        if state == "UNKNOWN"
        else "PARTIAL"
        if missing or warnings
        else "AVAILABLE",
        as_of=benchmark[-1].timestamp if benchmark else None,
        nifty_as_of=nifty[-1].timestamp if nifty else None,
        candidate_as_of=candidate[-1].timestamp if candidate else None,
        received_at=received_at,
        freshness="COMPLETED_DAILY_AS_OF" if benchmark else "UNAVAILABLE",
        missing_evidence=tuple(dict.fromkeys(missing)),
        warnings=tuple(warnings),
        supporting_factors=tuple(supporting),
        contradicting_factors=tuple(contradicting),
        neutral_factors=tuple(neutral),
        neutral_band_pp=neutral_band_pp,
    )

"""Owner-scoped scanner storage and bounded Dhan-only deterministic execution."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from time import monotonic
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from twf.discovery.domain import InstrumentIdentity, SourceMode
from twf.discovery.internal_scanner.market_series import Bar, DataUnavailable, MarketSeries
from twf.discovery.market_data import (
    DhanMarketDataProvider,
    MarketDataErrorCode,
    MarketDataFailure,
    MarketDataProvider,
)
from twf.infrastructure.scanner_v2 import SavedScannerRow, ScannerRunRow
from twf.instrument_metadata.contracts import InstrumentMetadataSummary
from twf.instrument_metadata.service import InstrumentMetadataService
from twf.scanner_v2.context import (
    MarketContextSnapshot,
    analyze_candidate,
    infer_direction,
    normalize_context,
)
from twf.scanner_v2.contracts import ContextMode, SavedInput, ScanConfig
from twf.scanner_v2.engine import evaluate
from twf.scanner_v2.sector import assess_sector
from twf.watchlists.catalog import kind
from twf.watchlists.service import WatchlistFailure, WatchlistService
from twf.watchlists.system import SystemUniverseCatalog


def benchmark_failure_message(name: str, code: str, *, stage: str) -> str:
    """Safe human-readable projection of typed provider failures; no raw payloads."""
    if code == MarketDataErrorCode.BENCHMARK_UNSUPPORTED_BY_DHAN:
        return f"Dhan does not support completed daily history for {name}."
    if code in {
        MarketDataErrorCode.INSTRUMENT_NOT_FOUND,
        MarketDataErrorCode.BENCHMARK_ALIAS_UNRESOLVED,
        "BENCHMARK_INDEX_UNRESOLVED",
    }:
        return f"{name} could not be resolved in Dhan's index master."
    if code == MarketDataErrorCode.AMBIGUOUS_INSTRUMENT:
        return f"{name} has ambiguous Dhan index identities; no index was selected."
    if code == MarketDataErrorCode.BENCHMARK_INSUFFICIENT_HISTORY:
        return f"{name} has fewer than 50 completed daily bars from Dhan."
    if code == "BENCHMARK_FINALITY_UNAVAILABLE":
        return f"Completed daily bar finality could not be verified for {name}."
    if code == MarketDataErrorCode.RATE_LIMITED:
        return f"Dhan rate limited {name} {stage}; sector evidence is unavailable."
    if code in {MarketDataErrorCode.AUTH_REQUIRED, "DHAN_AUTH_REQUIRED"}:
        return f"Dhan authorization is required to retrieve {name} sector evidence."
    if code == MarketDataErrorCode.TIMEOUT:
        return f"Dhan {name} {stage} timed out; sector evidence is unavailable."
    return f"Dhan {name} {stage} is temporarily unavailable."


class ScannerHistory:
    """Single-flight/paced owner+generation cache. No SQL session across I/O."""

    def __init__(self) -> None:
        self.values: dict[tuple[UUID, int, UUID], tuple[float, MarketSeries]] = {}
        self.lock = asyncio.Lock()
        self.next_start = 0.0

    async def read(
        self,
        owner: UUID,
        generation: int,
        provider: MarketDataProvider,
        instrument: InstrumentIdentity,
    ) -> MarketSeries:
        key = owner, generation, instrument.instrument_id
        async with self.lock:
            cached = self.values.get(key)
            if cached and monotonic() - cached[0] < 300:
                return cached[1]
            await asyncio.sleep(max(0, self.next_start - monotonic()))
            self.next_start = monotonic() + 1.1
            series = await provider.get_ohlcv(instrument, "1d", as_of=datetime.now(UTC), count=300)
            if (
                series.provenance.producer.provider != "dhan"
                or series.provenance.mode == SourceMode.SYNTHETIC
            ):
                raise WatchlistFailure("REAL_DATA_PROVENANCE_REQUIRED", 502)
            if series.instrument != instrument or series.interval != "1d":
                raise WatchlistFailure("MARKET_SERIES_IDENTITY_MISMATCH", 502)
            self.values[key] = monotonic(), series
            if len(self.values) > 256:
                del self.values[next(iter(self.values))]
            return series


class ScannerService:
    def __init__(
        self,
        factory: sessionmaker[Session],
        owner: UUID,
        system_universes: SystemUniverseCatalog | None = None,
    ) -> None:
        self.factory, self.owner = factory, owner
        self.system_universes = system_universes

    def saved(self) -> list[dict[str, Any]]:
        with self.factory() as db:
            return [
                self.saved_view(r)
                for r in db.scalars(
                    select(SavedScannerRow)
                    .where(SavedScannerRow.owner_id == self.owner)
                    .order_by(SavedScannerRow.updated_at.desc())
                    .limit(100)
                )
            ]

    @staticmethod
    def saved_view(r: SavedScannerRow) -> dict[str, Any]:
        return {
            "id": str(r.id),
            "config": r.config,
            "archived": r.archived,
            "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat(),
        }

    def save(self, payload: SavedInput, key: UUID | None = None) -> dict[str, Any]:
        with self.factory.begin() as db:
            if key:
                row = db.get(SavedScannerRow, key)
                if row is None or row.owner_id != self.owner:
                    raise WatchlistFailure("SAVED_SCAN_NOT_FOUND", 404)
                row.config, row.archived, row.updated_at = (
                    payload.config.model_dump(mode="json"),
                    payload.archived,
                    datetime.now(UTC),
                )
            else:
                row = SavedScannerRow(
                    id=uuid4(),
                    owner_id=self.owner,
                    config=payload.config.model_dump(mode="json"),
                    archived=payload.archived,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                db.add(row)
            return self.saved_view(row)

    def history(self) -> list[dict[str, Any]]:
        with self.factory() as db:
            return [
                {k: v for k, v in r.payload.items() if k != "rows"}
                for r in db.scalars(
                    select(ScannerRunRow)
                    .where(ScannerRunRow.owner_id == self.owner)
                    .order_by(ScannerRunRow.created_at.desc())
                    .limit(50)
                )
            ]

    def run(self, key: UUID) -> dict[str, Any]:
        with self.factory() as db:
            row = db.get(ScannerRunRow, key)
            if row is None or row.owner_id != self.owner:
                raise WatchlistFailure("SCAN_NOT_FOUND", 404)
            return dict(row.payload)

    async def execute(
        self,
        config: ScanConfig,
        provider: MarketDataProvider | None,
        generation: int,
        cache: ScannerHistory,
        reference: Callable[[InstrumentIdentity], Awaitable[dict[str, Any]]] | None = None,
        context: Callable[[], Awaitable[MarketContextSnapshot]] | None = None,
    ) -> dict[str, Any]:
        source = config.universe
        if source.source not in {"CUSTOM", "WATCHLIST"}:
            raise WatchlistFailure("CONSTITUENT_SOURCE_NOT_CONFIGURED", 422)
        now = datetime.now(UTC)
        deadline = monotonic() + 120
        instruments: list[InstrumentIdentity] = []
        rows: list[dict[str, Any]] = []
        snapshot: dict[str, Any] = {}
        if source.source == "WATCHLIST":
            assert source.watchlist_id
            if (
                self.system_universes is not None
                and self.system_universes.definition(source.watchlist_id) is not None
            ):
                if not isinstance(provider, DhanMarketDataProvider):
                    raise WatchlistFailure("DHAN_AUTH_REQUIRED", 503)
                snap = await self.system_universes.snapshot(source.watchlist_id, provider)
            else:
                snap = WatchlistService(self.factory, self.owner).snapshot(source.watchlist_id)
            snapshot = snap.model_dump(mode="json")
            eligible = tuple(
                i
                for i in snap.instruments
                if not source.instrument_ids or i.instrument_id in source.instrument_ids
            )
            if source.instrument_ids and set(source.instrument_ids) - {
                i.instrument_id for i in snap.instruments
            }:
                raise WatchlistFailure("WATCHLIST_SELECTION_CHANGED", 409)
            if not eligible or len(eligible) > 20:
                raise WatchlistFailure("SELECT_1_TO_20_INSTRUMENTS", 422)
            for i in eligible:
                if kind(i) not in {"EQUITY", "INDEX"}:
                    rows.append(
                        {
                            "symbol": i.symbol,
                            "instrument": i.model_dump(mode="json"),
                            "outcome": "NOT_EVALUATED",
                            "failure": "DERIVATIVES_UNSUPPORTED",
                            "resolved": True,
                        }
                    )
                else:
                    instruments.append(i)
            requested = len(eligible)
        else:
            requested = len(source.symbols)
            for symbol in source.symbols:
                try:
                    if provider is None:
                        raise WatchlistFailure("DHAN_AUTH_REQUIRED", 503)
                    if monotonic() >= deadline:
                        raise WatchlistFailure("TIMEOUT", 503)
                    async with asyncio.timeout(max(0.01, deadline - monotonic())):
                        found = await provider.resolve_instruments((symbol,))
                    if len(found) != 1 or found[0].exchange != "NSE":
                        raise WatchlistFailure("UNRESOLVED_NSE_INSTRUMENT", 422)
                    if found[0].instrument_id in {i.instrument_id for i in instruments}:
                        raise WatchlistFailure("DUPLICATE_CANONICAL_INSTRUMENT", 422)
                    instruments.append(found[0])
                except (MarketDataFailure, WatchlistFailure, TimeoutError) as exc:
                    rows.append(
                        {
                            "symbol": symbol,
                            "outcome": "NOT_EVALUATED",
                            "failure": "TIMEOUT"
                            if isinstance(exc, TimeoutError)
                            else str(exc.code),
                            "resolved": False,
                        }
                    )
        acquired: dict[UUID, MarketSeries] = {}
        quotes: dict[UUID, dict[str, Any]] = {}
        quote_failure: str | None = None
        if provider is not None and instruments:
            try:
                if monotonic() >= deadline:
                    raise TimeoutError
                async with asyncio.timeout(min(10, deadline - monotonic())):
                    snapshots = await provider.get_quotes(tuple(instruments))
                for quote in snapshots:
                    if quote.provider == "dhan" and quote.instrument in instruments:
                        quotes[quote.instrument.instrument_id] = quote.model_dump(mode="json")
            except MarketDataFailure as exc:
                quote_failure = exc.code.value
            except TimeoutError:
                quote_failure = "TIMEOUT"
        if provider is None and instruments:
            for i in instruments:
                rows.append(
                    {
                        "symbol": i.symbol,
                        "instrument": i.model_dump(mode="json"),
                        "outcome": "NOT_EVALUATED",
                        "failure": "DHAN_AUTH_REQUIRED",
                        "resolved": True,
                    }
                )
        else:
            for i in instruments:
                row: dict[str, Any] = {
                    "symbol": i.symbol,
                    "instrument": i.model_dump(mode="json"),
                    "resolved": True,
                    "provider": "dhan",
                }
                try:
                    assert provider is not None
                    if monotonic() >= deadline:
                        raise TimeoutError
                    async with asyncio.timeout(max(0.01, deadline - monotonic())):
                        series = await cache.read(self.owner, generation, provider, i)
                    acquired[i.instrument_id] = series
                    bars = series.at(now)
                    snapshot_quote = quotes.get(i.instrument_id)
                    row["quote"] = snapshot_quote
                    row["quote_failure"] = (
                        None if snapshot_quote else quote_failure or "QUOTE_UNAVAILABLE"
                    )
                    extra: dict[str, float | str | None] = {
                        "ltp": float(snapshot_quote["last_price"]) if snapshot_quote else None
                    }
                    if any(f.source == "tapetide" for f in config.filters) and reference:
                        async with asyncio.timeout(max(0.01, deadline - monotonic())):
                            ref = await reference(i)
                        row["reference"] = ref
                        extra.update(
                            {
                                k: float(ref[k]) if ref.get(k) is not None else None
                                for k in ("market_cap_inr", "pe_ratio")
                            }
                        )
                    row.update(evaluate(bars, config.filters, extra))
                    row.update(
                        {
                            "bars": [b.model_dump(mode="json") for b in bars],
                            "provenance": series.provenance.model_dump(mode="json"),
                            "received_at": series.received_at.isoformat()
                            if series.received_at
                            else None,
                            "source_time": bars[-1].timestamp.isoformat() if bars else None,
                            "basis": "Completed daily bars; latest completed close",
                        }
                    )
                except (MarketDataFailure, WatchlistFailure) as exc:
                    row.update(outcome="NOT_EVALUATED", failure=str(exc.code))
                except DataUnavailable as exc:
                    row.update(outcome="NOT_EVALUATED", failure=exc.reason.value)
                except TimeoutError:
                    row.update(outcome="NOT_EVALUATED", failure="TIMEOUT")
                rows.append(row)
        with self.factory() as db:
            targets: dict[int, tuple[str, str]] = {}
            for index, row in enumerate(rows):
                if not row.get("instrument"):
                    continue
                instrument = InstrumentIdentity.model_validate(row["instrument"])
                if kind(instrument) == "EQUITY":
                    targets[index] = (instrument.exchange, instrument.symbol)
            metadata_service = InstrumentMetadataService(db)
            metadata = metadata_service.get_many_by_exchange_symbols(tuple(targets.values()))
            for index, row in enumerate(rows):
                target = targets.get(index)
                metadata_item = (
                    metadata.get((target[0].upper(), target[1].upper()))
                    if target is not None
                    else None
                )
                row["instrument_metadata"] = (
                    metadata_service.summary(
                        metadata_item,
                        applies_to_symbol=row["symbol"],
                        resolution_basis="DIRECT",
                    ).model_dump(mode="json")
                    if metadata_item is not None
                    else None
                )
        key = uuid4()
        context_snapshot = (
            await context() if context is not None else normalize_context(None, at=now)
        )
        # One short DB read has ended above; all optional benchmark I/O is outside SQL.
        benchmark_bars: dict[str, tuple[Bar, ...]] = {}
        benchmark_received: dict[str, datetime | None] = {}
        benchmark_failures: dict[str, str] = {}
        eligible_rows = [r for r in rows if r.get("outcome") == "MATCH"]
        symbols = sorted(
            {
                r["instrument_metadata"]["context_benchmark_symbol"]
                for r in eligible_rows
                if r.get("instrument_metadata")
                and r["instrument_metadata"].get("context_benchmark_symbol")
                and r["instrument_metadata"].get("context_benchmark")
            }
        )
        benchmark_names = {
            "NIFTY": "NIFTY 50",
            **{
                r["instrument_metadata"]["context_benchmark_symbol"]: r["instrument_metadata"][
                    "context_benchmark"
                ]
                for r in eligible_rows
                if r.get("instrument_metadata")
                and r["instrument_metadata"].get("context_benchmark_symbol")
                and r["instrument_metadata"].get("context_benchmark")
            },
        }
        if symbols and config.context_mode != ContextMode.OFF:
            # Reuse canonical NIFTY resolution used by the existing header/Watchlist.
            sector_deadline = min(deadline, monotonic() + 30)
            for symbol in dict.fromkeys(["NIFTY", *symbols]):
                stage = "index resolution"
                try:
                    if provider is None:
                        raise WatchlistFailure("DHAN_AUTH_REQUIRED", 503)
                    if monotonic() >= sector_deadline:
                        raise TimeoutError
                    async with asyncio.timeout(max(0.01, sector_deadline - monotonic())):
                        resolved = await provider.resolve_instruments((symbol,))
                        if (
                            len(resolved) != 1
                            or resolved[0].exchange != "NSE"
                            or kind(resolved[0]) != "INDEX"
                        ):
                            raise WatchlistFailure("BENCHMARK_INDEX_UNRESOLVED", 422)
                        instrument = resolved[0]
                        stage = "daily history"
                        benchmark_series = acquired.get(instrument.instrument_id)
                        if benchmark_series is None:
                            benchmark_series = await cache.read(
                                self.owner, generation, provider, instrument
                            )
                            acquired[instrument.instrument_id] = benchmark_series
                        bars = benchmark_series.at(now)
                        if any(b.finality != "COMPLETED" for b in bars):
                            raise WatchlistFailure("BENCHMARK_FINALITY_UNAVAILABLE", 422)
                        benchmark_bars[symbol] = bars
                        benchmark_received[symbol] = benchmark_series.received_at
                        if len(bars) < 50:
                            benchmark_failures[symbol] = benchmark_failure_message(
                                benchmark_names[symbol],
                                MarketDataErrorCode.BENCHMARK_INSUFFICIENT_HISTORY,
                                stage=stage,
                            )
                except (MarketDataFailure, WatchlistFailure, DataUnavailable, TimeoutError) as exc:
                    code = (
                        "TIMEOUT"
                        if isinstance(exc, TimeoutError)
                        else exc.reason.value
                        if isinstance(exc, DataUnavailable)
                        else str(exc.code)
                    )
                    if stage == "daily history" and code in {
                        "PROVIDER_ERROR",
                        "INVALID_RESPONSE",
                        "DATA_UNAVAILABLE",
                        "EMPTY_SERIES",
                    }:
                        code = MarketDataErrorCode.BENCHMARK_HISTORY_UNAVAILABLE
                    benchmark_failures[symbol] = benchmark_failure_message(
                        benchmark_names[symbol],
                        code,
                        stage=stage,
                    )

        if context_snapshot is not None:
            direction = infer_direction(config.filters)
            for row in rows:
                if row.get("outcome") == "NOT_EVALUATED":
                    row["matched"] = False
                    row["technical_match"] = False
                    continue
                sector = None
                if row.get("outcome") == "MATCH" and config.context_mode != ContextMode.OFF:
                    meta = (
                        InstrumentMetadataSummary.model_validate(row["instrument_metadata"])
                        if row.get("instrument_metadata")
                        else None
                    )
                    benchmark_symbol = meta.context_benchmark_symbol if meta else None
                    candidate_bars = tuple(Bar.model_validate(b) for b in row.get("bars", ()))
                    if any(b.finality != "COMPLETED" for b in candidate_bars):
                        candidate_bars = ()
                    sector = assess_sector(
                        meta,
                        benchmark_bars.get(benchmark_symbol or "", ()),
                        benchmark_bars.get("NIFTY", ()),
                        candidate_bars,
                        direction=direction.value,
                        candidate_symbol=row["symbol"],
                        received_at=benchmark_received.get(benchmark_symbol or ""),
                        failures=tuple(
                            benchmark_failures[x]
                            for x in dict.fromkeys((benchmark_symbol, "NIFTY"))
                            if x in benchmark_failures
                        ),
                    )
                analysis = analyze_candidate(
                    row["symbol"],
                    row,
                    context_snapshot,
                    config.context_mode,
                    config.context_filters,
                    direction,
                    now,
                    str(key),
                    str(row["instrument"]["instrument_id"]) if row.get("instrument") else None,
                    sector=sector,
                )
                row["analysis"] = analysis.model_dump(mode="json")
                row["matched"] = analysis.matched
                row["technical_match"] = analysis.technical_match
                if analysis.technical_match and not analysis.matched:
                    row["outcome"] = "NON_MATCH"
                    row["context_rejected"] = True
            if config.sort == "relevance":
                rows.sort(
                    key=lambda row: (
                        -int(row.get("analysis", {}).get("final_relevance", 0)),
                        str(row["symbol"]),
                    )
                )
        result = {
            "id": str(key),
            "created_at": now.isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
            "config": config.model_dump(mode="json"),
            "data_mode": "REAL",
            "market_data_provider": "dhan",
            "generation": generation,
            "universe_snapshot": snapshot
            or {"instruments": [i.model_dump(mode="json") for i in instruments]},
            "context_snapshot": context_snapshot.model_dump(mode="json")
            if context_snapshot is not None
            else None,
            "analysis_contract": "scanner.context.v1",
            "counts": {
                "requested": requested,
                "resolved": sum(bool(r["resolved"]) for r in rows),
                "evaluated": sum(r["outcome"] != "NOT_EVALUATED" for r in rows),
                "not_evaluated": sum(r["outcome"] == "NOT_EVALUATED" for r in rows),
                "matches": sum(r["outcome"] == "MATCH" for r in rows),
            },
            "rows": rows,
        }
        with self.factory.begin() as db:
            db.add(ScannerRunRow(id=key, owner_id=self.owner, payload=result, created_at=now))
        return result

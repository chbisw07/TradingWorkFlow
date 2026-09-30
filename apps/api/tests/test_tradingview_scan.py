"""Exact-universe TradingView capture, local evaluation, and broad-contract regressions."""

import asyncio
import base64
import hashlib
import json
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit
from uuid import NAMESPACE_URL, uuid4, uuid5

import httpx2
import pytest
from mcp_support import SyntheticServer, public_ip, setup

from twf.discovery.domain import (
    Comparison,
    Criterion,
    FreshnessState,
    InstrumentIdentity,
    ScanDefinition,
    ScanProfileReference,
    SourceMode,
    freshness,
)
from twf.discovery.providers import ProviderFailure
from twf.discovery.service import scan_input
from twf.discovery.synthetic import fixture_instruments
from twf.discovery.tradingview.config import TradingViewSettings, configuration
from twf.discovery.tradingview.provider import (
    BATCH_LIMIT,
    GET_BATCH_TOOL,
    GET_COLUMNS_TOOL,
    RUN_SCREENER_TOOL,
    TOOLS,
    TradingViewAdapter,
    TradingViewScanProvider,
    broad_screener_rows,
)
from twf.integrations.mcp.client import SDKClient
from twf.integrations.mcp.contracts import AuthMode, Code, Failure, ToolPolicy
from twf.integrations.mcp.http import HTTPFactory

FIXTURES = Path(__file__).parent / "fixtures" / "tradingview"


def fixture(name: str) -> dict[str, Any]:
    value: object = json.loads((FIXTURES / name).read_text())
    if not isinstance(value, dict):
        raise ValueError("Fixture must contain an object")
    return cast(dict[str, Any], value)


def exact_instruments(count: int = 2) -> tuple[InstrumentIdentity, ...]:
    base = fixture_instruments()[0]
    symbols = ["IDEA", "PCJEWELLER"] + [f"SYM{index:03d}" for index in range(2, count)]
    return tuple(
        base.model_copy(
            update={
                "instrument_id": uuid5(NAMESPACE_URL, f"tv-test:{symbol}"),
                "symbol": symbol,
                "exchange": "NSE",
                "segment": "EQ",
                "native": base.native.model_copy(
                    update={"namespace": "tradingview", "native_id": f"NSE:{symbol}"}
                ),
            }
        )
        for symbol in symbols
    )


def definition(
    *,
    combination: str = "ALL",
    criteria: tuple[Criterion, ...] | None = None,
    operator: Comparison = Comparison.GTE,
    threshold: Decimal = Decimal(10),
    metric: str = "close",
    unit: str = "price",
    timeframe: str = "provider-current",
) -> ScanDefinition:
    return ScanDefinition(
        definition_id=uuid4(),
        revision=1,
        criteria=criteria
        or (Criterion(metric=metric, operator=operator, threshold=threshold, unit=unit),),
        combination=cast(Any, combination),
        timeframe=timeframe,
        source_mode=SourceMode.SYNTHETIC,
        required_capabilities=("sd.scan",),
    )


class TVServer(SyntheticServer):
    def __init__(self, scenario: str = "success") -> None:
        super().__init__()
        self.scenario = scenario
        self.tool_calls: list[dict[str, Any]] = []
        self.batch_calls = 0

    @staticmethod
    def row(symbol: str, index: int) -> dict[str, Any]:
        known = {
            "NSE:IDEA": (13.56, 1_150_179_404),
            "NSE:PCJEWELLER": (13.23, 261_661_117),
        }
        close, volume = known.get(symbol, (20.0 + index, 1000 + index))
        return {"symbol": symbol, "close": close, "volume": volume}

    async def handle(self, req: httpx2.Request) -> httpx2.Response:
        if req.url.path == "/mcp/oauth/token":
            fields = parse_qs((await req.aread()).decode())
            assert fields["resource"] == ["https://mcp.tradingview.com/mcp"]
            assert (
                self.challenge
                == base64.urlsafe_b64encode(
                    hashlib.sha256(fields["code_verifier"][0].encode()).digest()
                )
                .rstrip(b"=")
                .decode()
            )
            return httpx2.Response(
                200,
                json={
                    "access_token": "synthetic-token",
                    "token_type": "Bearer",
                    "scope": "mcp:read mcp:tools",
                },
            )
        if req.method != "POST":
            return await super().handle(req)
        msg = json.loads(await req.aread())
        if msg["method"] not in {"tools/list", "tools/call"}:
            return await super().handle(req)
        if msg["method"] == "tools/list":
            tools = [{"name": name, "inputSchema": {"type": "object"}} for name in TOOLS]
            tools.append(
                {
                    "name": "mcp-tv-create-alert",
                    "inputSchema": {
                        "type": "object",
                        "patternProperties": {"^(webhook|monitor)$": {"type": "string"}},
                    },
                }
            )
            if self.scenario == "missing_tool":
                tools = [tool for tool in tools if tool["name"] != GET_BATCH_TOOL]
            return httpx2.Response(
                200, json={"jsonrpc": "2.0", "id": msg["id"], "result": {"tools": tools}}
            )

        self.tool_calls.append(msg["params"])
        name = msg["params"]["name"]
        if self.scenario == "auth":
            return httpx2.Response(401)
        if self.scenario == "rate":
            return httpx2.Response(429, headers={"Retry-After": "2"})
        if self.scenario == "unavailable":
            return httpx2.Response(503)
        if self.scenario == "timeout":
            await asyncio.Event().wait()

        if name == GET_COLUMNS_TOOL:
            result: Any = fixture("live_columns_sanitized.json")
            if self.scenario == "missing_columns":
                result = {
                    "success": True,
                    "count": 1,
                    "groups": [{"group": "price", "count": 1, "columns": ["close"]}],
                }
            if self.scenario == "schema_drift":
                result = {
                    "success": True,
                    "count": 2,
                    "groups": [
                        {"group": "price", "count": 2, "columns": ["close"]},
                        {
                            "group": "volume_liquidity",
                            "count": 1,
                            "columns": ["volume"],
                        },
                    ],
                }
        else:
            assert name == GET_BATCH_TOOL
            self.batch_calls += 1
            args = msg["params"]["arguments"]
            symbols = args["symbols"]
            columns = args["columns"]
            assert 1 <= len(symbols) <= BATCH_LIMIT
            assert len(symbols) == len(set(symbols))
            assert columns == sorted(columns)
            if self.scenario == "partial_chunk_failure" and self.batch_calls == 2:
                return httpx2.Response(503)
            if self.scenario == "provider_rate":
                result = fixture("live_rate_limited_sanitized.json")
            else:
                rows = [self.row(symbol, index) for index, symbol in enumerate(symbols)]
                missing: list[str] = []
                if self.scenario == "unresolved":
                    missing = [symbols[-1]]
                    rows = rows[:-1]
                if self.scenario == "nonmatch":
                    rows[0]["close"] = 1
                if self.scenario == "empty_matches":
                    for row in rows:
                        row["close"] = 1
                if self.scenario == "malformed":
                    result = {"success": True, "data": "bad", "missing": []}
                else:
                    if self.scenario == "wrong_symbol":
                        rows[0]["symbol"] = "NSE:OTHER"
                    if self.scenario == "duplicate":
                        rows.append(dict(rows[0]))
                    if self.scenario == "missing_metric":
                        del rows[0][columns[0]]
                    if self.scenario == "silent_omission":
                        rows = rows[:-1]
                    result = {"success": True, "data": rows, "missing": missing}
        return httpx2.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": msg["id"],
                "result": {"content": [], "structuredContent": result, "isError": False},
            },
        )


async def connected(
    tmp_path: Path, scenario: str = "success"
) -> tuple[Any, Any, Any, Any, TVServer]:
    manager, who, _, engine = setup(tmp_path / f"tv-{uuid4()}.db", AuthMode.OAUTH_2_1)
    server = TVServer(scenario)
    manager.providers = {
        "tradingview": configuration("synthetic-client", "http://localhost:3000/mcp/callback")
    }
    manager.http = HTTPFactory(lambda: httpx2.MockTransport(server.handle), public_ip)
    manager.client = SDKClient(manager.http)
    manager.oauth.http = manager.http
    row = await manager.create(who, "tradingview", "TradingView test")
    auth = await manager.begin(who, row.id, 0)
    params = parse_qs(urlsplit(auth.authorization_url).query)
    server.challenge = params["code_challenge"][0]
    row = await manager.callback(who, row.id, params["state"][0], "synthetic-code")
    assert await manager.operations.drain(2)
    return manager, who, row, engine, server


async def execute_case(
    tmp_path: Path,
    scenario: str = "success",
    *,
    scan_definition: ScanDefinition | None = None,
    instruments: tuple[InstrumentIdentity, ...] | None = None,
    max_items: int = 64,
    timeout: float = 5,
    synthetic: bool = True,
) -> tuple[Any, Any, Any, Any, TVServer]:
    manager, who, row, engine, server = await connected(tmp_path, scenario)
    adapter = TradingViewAdapter(
        manager,
        TradingViewSettings(
            enabled=True,
            max_items=max_items,
            timeout_seconds=timeout,
        ),
        synthetic=synthetic,
    )
    profile = ScanProfileReference(profile_id=uuid4(), owner_id=who.owner_id, applied_revision=1)
    result = await adapter.execute(
        who,
        row.id,
        row.generation,
        scan_definition or definition(),
        profile,
        instruments or exact_instruments(),
        uuid4(),
    )
    return result, manager, who, engine, server


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("malformed", "INVALID_RESPONSE"),
        ("wrong_symbol", "INVALID_RESPONSE"),
        ("duplicate", "INVALID_RESPONSE"),
        ("missing_metric", "INVALID_RESPONSE"),
        ("silent_omission", "INVALID_RESPONSE"),
        ("missing_columns", "INVALID_RESPONSE"),
        ("schema_drift", "INVALID_RESPONSE"),
        ("timeout", "TIMEOUT"),
        ("rate", "RATE_LIMITED"),
        ("provider_rate", "RATE_LIMITED"),
        ("auth", "AUTHENTICATION_FAILED"),
        ("unavailable", "SERVICE_UNAVAILABLE"),
        ("missing_tool", "UNSUPPORTED_CAPABILITY"),
    ],
)
def test_exact_batch_failures(tmp_path: Path, scenario: str, expected: str) -> None:
    async def run() -> None:
        manager, who, row, engine, _ = await connected(tmp_path, scenario)
        try:
            adapter = TradingViewAdapter(
                manager,
                TradingViewSettings(
                    enabled=True,
                    timeout_seconds=0.1 if scenario == "timeout" else 5,
                ),
                synthetic=True,
            )
            profile = ScanProfileReference(
                profile_id=uuid4(), owner_id=who.owner_id, applied_revision=1
            )
            with pytest.raises(ProviderFailure) as failed:
                await adapter.execute(
                    who,
                    row.id,
                    row.generation,
                    definition(),
                    profile,
                    exact_instruments(),
                    uuid4(),
                )
            assert failed.value.error.code.value == expected
            assert failed.value.error.request_id == who.correlation.request_id
        finally:
            engine.dispose()

    asyncio.run(run())


@pytest.mark.parametrize(
    ("scenario", "expected_count", "completeness"),
    [
        ("success", 2, "COMPLETE"),
        ("nonmatch", 1, "COMPLETE"),
        ("empty_matches", 0, "COMPLETE"),
        ("unresolved", 1, "PARTIAL"),
    ],
)
def test_exact_batch_normalizes_locally(
    tmp_path: Path, scenario: str, expected_count: int, completeness: str
) -> None:
    async def run() -> None:
        result, manager, who, engine, server = await execute_case(tmp_path, scenario)
        try:
            assert result.strategy == "EXACT_BATCH"
            assert result.tool == GET_BATCH_TOOL
            assert result.requested_universe == ("NSE:IDEA", "NSE:PCJEWELLER")
            assert result.requested_columns == ("close", "volume")
            assert result.chunk_count == 1
            assert result.result.completeness == completeness
            assert len(result.result.items) == expected_count
            assert result.unresolved_symbols == (
                ("NSE:PCJEWELLER",) if scenario == "unresolved" else ()
            )
            if scenario == "unresolved":
                assert "unresolved-symbols" in result.result.limitations
            for match in result.result.items:
                evidence = match.evidence[0]
                assert match.provenance.transformation.id == (
                    "tradingview-exact-batch-local-filter"
                )
                assert match.provenance.dependence_group == "tradingview-exact-batch"
                assert evidence.source_data_time is None
                assert freshness(evidence, datetime.now(UTC), 60) == FreshnessState.UNKNOWN
                assert scan_input(match).scan_lineage == match.lineage
            names = [call["name"] for call in server.tool_calls]
            assert names == [GET_COLUMNS_TOOL, GET_BATCH_TOOL]
            assert RUN_SCREENER_TOOL not in names
            status = TradingViewAdapter(
                manager, TradingViewSettings(enabled=True), synthetic=True
            ).status(who, result.connection_id)
            assert set(status.allowed_tools) == TOOLS
            assert "synthetic-token" not in status.model_dump_json()
            with pytest.raises(Failure) as denied:
                await manager.tools(
                    who,
                    result.connection_id,
                    result.generation,
                    policy=ToolPolicy(allowed=TOOLS),
                    name="mcp-tv-create-alert",
                )
            assert denied.value.code == Code.TOOL_NOT_ALLOWED
        finally:
            engine.dispose()

    asyncio.run(run())


def test_exact_batch_chunks_more_than_fifty_without_universe_drift(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        universe = exact_instruments(51)
        result, _, _, engine, server = await execute_case(
            tmp_path,
            instruments=universe,
            scan_definition=definition(threshold=Decimal(0)),
        )
        try:
            assert result.chunk_count == 2
            batches = [
                call["arguments"]["symbols"]
                for call in server.tool_calls
                if call["name"] == GET_BATCH_TOOL
            ]
            assert [len(batch) for batch in batches] == [50, 1]
            assert tuple(symbol for batch in batches for symbol in batch) == tuple(
                item.native.native_id for item in universe
            )
            assert len(result.result.items) == 51
        finally:
            engine.dispose()

    asyncio.run(run())


def test_one_failed_chunk_fails_the_whole_exact_call(tmp_path: Path) -> None:
    async def run() -> None:
        manager, who, row, engine, _ = await connected(tmp_path, "partial_chunk_failure")
        try:
            adapter = TradingViewAdapter(
                manager, TradingViewSettings(enabled=True, max_items=64), synthetic=True
            )
            profile = ScanProfileReference(
                profile_id=uuid4(), owner_id=who.owner_id, applied_revision=1
            )
            with pytest.raises(ProviderFailure) as failed:
                await adapter.execute(
                    who,
                    row.id,
                    row.generation,
                    definition(threshold=Decimal(0)),
                    profile,
                    exact_instruments(51),
                    uuid4(),
                )
            assert failed.value.error.code.value == "SERVICE_UNAVAILABLE"
        finally:
            engine.dispose()

    asyncio.run(run())


@pytest.mark.parametrize(
    ("operator", "threshold", "expected"),
    [
        (Comparison.LT, Decimal("13.5"), 1),
        (Comparison.LTE, Decimal("13.23"), 1),
        (Comparison.EQ, Decimal("13.56"), 1),
        (Comparison.GTE, Decimal("13.56"), 1),
        (Comparison.GT, Decimal("13.23"), 1),
    ],
)
def test_local_comparison_semantics_match_internal_scanner(
    tmp_path: Path, operator: Comparison, threshold: Decimal, expected: int
) -> None:
    async def run() -> None:
        result, _, _, engine, _ = await execute_case(
            tmp_path,
            scan_definition=definition(operator=operator, threshold=threshold),
        )
        try:
            assert len(result.result.items) == expected
        finally:
            engine.dispose()

    asyncio.run(run())


@pytest.mark.parametrize(("combination", "expected"), [("ALL", 0), ("ANY", 2)])
def test_local_all_any_semantics(tmp_path: Path, combination: str, expected: int) -> None:
    criteria = (
        Criterion(
            metric="close",
            operator=Comparison.GT,
            threshold=Decimal(100),
            unit="price",
        ),
        Criterion(
            metric="volume",
            operator=Comparison.GTE,
            threshold=Decimal(1),
            unit="volume",
        ),
    )

    async def run() -> None:
        result, _, _, engine, _ = await execute_case(
            tmp_path,
            scan_definition=definition(
                combination=combination,
                criteria=criteria,
            ),
        )
        try:
            assert len(result.result.items) == expected
        finally:
            engine.dispose()

    asyncio.run(run())


def test_duplicate_or_empty_exact_universe_is_rejected() -> None:
    adapter = TradingViewAdapter(cast(Any, None), TradingViewSettings(enabled=True), synthetic=True)
    with pytest.raises(Failure) as empty:
        adapter.arguments(definition(), ())
    assert empty.value.code == Code.INVALID_ARGUMENTS
    item = exact_instruments(1)[0]
    with pytest.raises(Failure) as duplicate:
        adapter.arguments(definition(), (item, item))
    assert duplicate.value.code == Code.INVALID_ARGUMENTS


@pytest.mark.parametrize(
    "scan_definition",
    [
        definition(metric="unknown", unit="ratio"),
        definition(timeframe="1d"),
    ],
)
def test_unsupported_definition_is_rejected_before_provider_io(
    scan_definition: ScanDefinition,
) -> None:
    adapter = TradingViewAdapter(cast(Any, None), TradingViewSettings(enabled=True), synthetic=True)
    with pytest.raises(Failure) as failed:
        adapter.arguments(scan_definition, exact_instruments())
    assert failed.value.code == Code.CONTRACT_MISMATCH


def test_broad_screener_contract_remains_available_without_ticker_symbolset() -> None:
    adapter = TradingViewAdapter(
        cast(Any, None), TradingViewSettings(enabled=True, max_items=2), synthetic=True
    )
    plan = adapter.broad_arguments(definition())
    assert plan.strategy == "PROVIDER_SCREENER"
    assert plan.tool == RUN_SCREENER_TOOL
    assert "symbolset" not in plan.arguments
    rows, total = broad_screener_rows(
        fixture("live_screener_sanitized.json"),
        limit=2,
        columns=("close", "volume"),
    )
    assert total == 7908
    assert [row["symbol"] for row in rows] == ["NSE:IDEA", "NSE:PCJEWELLER"]


def test_deadline_checked_after_local_normalization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = TradingViewScanProvider.scan

    async def delayed(self: Any, *args: Any) -> Any:
        result = await original(self, *args)
        time.sleep(0.15)
        return result

    monkeypatch.setattr(TradingViewScanProvider, "scan", delayed)

    async def run() -> None:
        manager, who, row, engine, _ = await connected(tmp_path)
        try:
            adapter = TradingViewAdapter(
                manager,
                TradingViewSettings(enabled=True, timeout_seconds=0.1),
                synthetic=True,
            )
            profile = ScanProfileReference(
                profile_id=uuid4(), owner_id=who.owner_id, applied_revision=1
            )
            with pytest.raises(ProviderFailure) as failed:
                await adapter.execute(
                    who,
                    row.id,
                    row.generation,
                    definition(),
                    profile,
                    exact_instruments(),
                    uuid4(),
                )
            assert failed.value.error.code.value == "TIMEOUT"
        finally:
            engine.dispose()

    asyncio.run(run())


def test_live_exact_timeout_budget_remains_bounded() -> None:
    assert TradingViewSettings(timeout_seconds=60).timeout_seconds == 60
    with pytest.raises(ValueError):
        TradingViewSettings(timeout_seconds=60.01)


def test_official_configuration_has_scoped_pkce_metadata() -> None:
    config = configuration("registered-public-client", "http://127.0.0.1:3000/mcp/callback")
    assert config.oauth and config.oauth.scopes == ("mcp:read", "mcp:tools")
    assert (
        config.endpoint == "https://mcp.tradingview.com/mcp"
        and config.auth_mode == AuthMode.OAUTH_2_1
    )

"""TradingView MCP capture with exact-universe and broad-screener strategies.

Exact TWF instrument universes are fetched in deterministic batches and evaluated
locally. TradingView's provider-side screener remains available only for genuine
provider-defined broad universes; its symbolset vocabulary is never populated
with arbitrary EXCHANGE:TICKER identities.
"""

import asyncio
import json
import math
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import JsonValue, ValidationError

from twf.discovery.domain import (
    Comparison,
    DiscoveryEvidence,
    EvidenceCategory,
    EvidencePolarity,
    InstrumentIdentity,
    Measure,
    ProducerIdentity,
    Provenance,
    RevisionRef,
    ScanDefinition,
    ScanMatch,
    ScanProfileReference,
    ScanRun,
    SourceMode,
    SourceReference,
    digest,
)
from twf.discovery.internal_scanner.conditions import compare
from twf.discovery.providers import (
    DomainErrorCode,
    OperationContext,
    ProviderAccess,
    ProviderBatch,
    ProviderFailure,
    ProviderHealth,
    ProviderManifest,
)
from twf.discovery.tradingview.config import ENDPOINT, TradingViewSettings
from twf.integrations.contracts import Contract, DeploymentMode, ErrorCode, Health
from twf.integrations.mcp.connection import ConnectionManager
from twf.integrations.mcp.contracts import (
    AuthMode,
    Code,
    ConnectionView,
    Context,
    Failure,
    ToolPolicy,
)

GET_COLUMNS_TOOL = "mcp-tv-get-screener-columns"
GET_BATCH_TOOL = "mcp-tv-get-symbol-data-batch"
RUN_SCREENER_TOOL = "mcp-tv-run-screener"
TOOLS = frozenset({GET_COLUMNS_TOOL, GET_BATCH_TOOL, RUN_SCREENER_TOOL})
BATCH_LIMIT = 50
IDENTITY = ProducerIdentity(
    service_id="tradingview-scan",
    provider="tradingview",
    service_version="1",
    contract_version="sd.scan.v1",
)
UNITS = {"close": "price", "volume": "volume"}
ALL_COMPARISONS = frozenset(Comparison)


class BatchRequest(Contract):
    symbols: tuple[str, ...]
    columns: tuple[str, ...]


class ExactPlan(Contract):
    strategy: Literal["EXACT_BATCH"] = "EXACT_BATCH"
    tool: Literal["mcp-tv-get-symbol-data-batch"] = "mcp-tv-get-symbol-data-batch"
    requested_universe: tuple[str, ...]
    requested_columns: tuple[str, ...]
    chunks: tuple[BatchRequest, ...]


class BroadPlan(Contract):
    strategy: Literal["PROVIDER_SCREENER"] = "PROVIDER_SCREENER"
    tool: Literal["mcp-tv-run-screener"] = "mcp-tv-run-screener"
    arguments: dict[str, JsonValue]


class Capture(Contract):
    owner_id: UUID
    connection_id: UUID
    generation: int
    request_id: str
    definition: ScanDefinition
    instruments: tuple[InstrumentIdentity, ...]
    started_at: datetime
    received_at: datetime
    source_mode: SourceMode
    plan: ExactPlan
    schema_hash: str
    rows_json: str
    total: int
    unresolved_symbols: tuple[str, ...] = ()


class Execution(Contract):
    run: ScanRun
    result: ProviderBatch[ScanMatch]
    connection_id: UUID
    generation: int
    started_at: datetime
    completed_at: datetime
    strategy: Literal["EXACT_BATCH"] = "EXACT_BATCH"
    tool: Literal["mcp-tv-get-symbol-data-batch"] = "mcp-tv-get-symbol-data-batch"
    requested_universe: tuple[str, ...]
    requested_columns: tuple[str, ...]
    chunk_count: int
    unresolved_symbols: tuple[str, ...] = ()
    schema_hash: str
    parameters: dict[str, JsonValue]
    response_contract: Literal["nested-data-v1"] = "nested-data-v1"


class Status(Contract):
    enabled: bool
    response_contract_verified: bool
    connection: ConnectionView
    allowed_tools: tuple[str, ...]
    schema_policy: Literal["DISCOVER_EACH_CAPTURE"] = "DISCOVER_EACH_CAPTURE"
    schema_status: Literal["UNVERIFIED", "VERIFY_ON_CAPTURE"]
    last_successful_scan: None = None
    retry_count: Literal[0] = 0
    freshness_policy: Literal["UNKNOWN_WITHOUT_SOURCE_TIME"] = "UNKNOWN_WITHOUT_SOURCE_TIME"


def payload(reply: dict[str, JsonValue] | None) -> dict[str, JsonValue]:
    if reply is None or reply.get("isError"):
        raise ValueError("Missing tool result")
    value = reply.get("structuredContent")
    if value is None:
        content = reply.get("content")
        if not isinstance(content, list) or len(content) != 1:
            raise ValueError("Ambiguous result content")
        item = content[0]
        if (
            not isinstance(item, dict)
            or item.get("type") != "text"
            or not isinstance(item.get("text"), str)
        ):
            raise ValueError("Invalid result content")
        value = json.loads(cast(str, item["text"]))
    if not isinstance(value, dict):
        raise ValueError("Expected result object")
    return value


def successful(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Require TradingView's structured success marker without exposing provider text."""

    if value.get("success") is True:
        return value
    error = value.get("error")
    if isinstance(error, str) and "429" in error:
        raise Failure(Code.RATE_LIMITED)
    raise Failure(Code.UNAVAILABLE)


def _validate_columns_schema(schema: dict[str, JsonValue], required: set[str]) -> str:
    groups = schema.get("groups")
    if (
        not isinstance(groups, list)
        or not 1 <= len(groups) <= 64
        or type(schema.get("count")) is not int
    ):
        raise ValueError("Unverified column shape")
    columns: list[str] = []
    for group in groups:
        group_columns = group.get("columns") if isinstance(group, dict) else None
        if (
            not isinstance(group, dict)
            or not isinstance(group.get("group"), str)
            or type(group.get("count")) is not int
            or not isinstance(group_columns, list)
            or group["count"] != len(group_columns)
            or not all(isinstance(column, str) for column in group_columns)
        ):
            raise ValueError("Unverified column group")
        columns.extend(cast(list[str], group_columns))
    if (
        len(columns) > 256
        or schema["count"] != len(columns)
        or len(set(columns)) != len(columns)
        or not required.issubset(columns)
    ):
        raise ValueError("Schema drift")
    return digest(schema)


def _numeric_row(
    row: object, requested: set[str], columns: tuple[str, ...]
) -> dict[str, JsonValue]:
    if not isinstance(row, dict) or not isinstance(row.get("symbol"), str):
        raise ValueError("Invalid result identity")
    symbol = cast(str, row["symbol"])
    if symbol not in requested:
        raise ValueError("Unexpected result identity")
    normalized: dict[str, JsonValue] = {"symbol": symbol}
    for column in columns:
        value = row.get(column)
        if (
            type(value) not in {float, int}
            or not math.isfinite(cast(float, value))
            or not 0 <= cast(float, value) <= 1e18
        ):
            raise ValueError("Invalid metric")
        normalized[column] = cast(float | int, value)
    return normalized


def _batch_rows(
    result: dict[str, JsonValue],
    requested: tuple[str, ...],
    columns: tuple[str, ...],
) -> tuple[list[dict[str, JsonValue]], tuple[str, ...]]:
    """Bind the documented batch result without inventing unresolved values."""

    data = result.get("data")
    top_missing = result.get("missing")
    if isinstance(data, dict):
        rows = data.get("rows")
        missing = data.get("missing", top_missing)
    else:
        rows = data
        missing = top_missing
    if not isinstance(rows, list) or not isinstance(missing, list):
        raise ValueError("Invalid batch result envelope")
    if not all(isinstance(symbol, str) for symbol in missing):
        raise ValueError("Invalid missing identities")
    missing_symbols = tuple(cast(list[str], missing))
    if len(set(missing_symbols)) != len(missing_symbols):
        raise ValueError("Duplicate missing identity")

    requested_set = set(requested)
    if not set(missing_symbols).issubset(requested_set):
        raise ValueError("Unexpected missing identity")
    normalized = [_numeric_row(row, requested_set, columns) for row in rows]
    row_symbols = [cast(str, row["symbol"]) for row in normalized]
    if len(set(row_symbols)) != len(row_symbols):
        raise ValueError("Duplicate result identity")
    if set(row_symbols) & set(missing_symbols):
        raise ValueError("Identity both resolved and missing")
    if set(row_symbols) | set(missing_symbols) != requested_set:
        raise ValueError("Requested identity silently omitted")
    ordered = {cast(str, row["symbol"]): row for row in normalized}
    return [ordered[symbol] for symbol in requested if symbol in ordered], missing_symbols


def broad_screener_rows(
    result: dict[str, JsonValue], *, limit: int, columns: tuple[str, ...]
) -> tuple[list[dict[str, JsonValue]], int]:
    """Strictly bind the retained broad-provider screener response contract."""

    data = result.get("data")
    if not isinstance(data, dict):
        raise ValueError("Invalid broad result envelope")
    rows, total = data.get("rows"), data.get("totalCount")
    if (
        not isinstance(rows, list)
        or type(total) is not int
        or not 0 <= total <= 1_000_000
        or len(rows) > limit
        or total < len(rows)
    ):
        raise ValueError("Invalid broad bounded result")
    seen: set[str] = set()
    normalized: list[dict[str, JsonValue]] = []
    for row in rows:
        requested = (
            {cast(str, row.get("symbol"))}
            if isinstance(row, dict) and isinstance(row.get("symbol"), str)
            else set()
        )
        item = _numeric_row(row, requested, columns)
        symbol = cast(str, item["symbol"])
        if symbol in seen:
            raise ValueError("Duplicate broad identity")
        seen.add(symbol)
        normalized.append(item)
    return normalized, total


class ScanPolicy:
    """Bounded server enablement for the authenticated owner, not a subscription grant."""

    def __init__(self, owner_id: UUID, settings: TradingViewSettings) -> None:
        self.owner_id, self.settings = owner_id, settings

    def allows(self, user_id: UUID, capability: str) -> bool:
        return user_id == self.owner_id and capability == "sd.scan" and self.settings.enabled


class TradingViewScanProvider:
    """One immutable exact-universe capture normalized through the shared scan port."""

    def __init__(self, capture: Capture, settings: TradingViewSettings) -> None:
        self.capture, self.settings = capture, settings
        self.mode = (
            DeploymentMode.SYNTHETIC
            if capture.source_mode == SourceMode.SYNTHETIC
            else DeploymentMode.REMOTE
        )
        self.manifest = ProviderManifest(
            identity=IDENTITY,
            capabilities=("sd.scan",),
            source_modes=(capture.source_mode,),
            max_items=settings.max_items,
            supported_metrics=tuple(UNITS),
            supported_operators=tuple(operator.value for operator in Comparison),
            supported_timeframes=("provider-current",),
        )

    async def health(self, context: OperationContext) -> ProviderHealth:
        return ProviderHealth(
            identity=IDENTITY,
            request_id=context.correlation.request_id,
            health=Health.AVAILABLE
            if context.owner_id == self.capture.owner_id
            else Health.UNAVAILABLE,
            as_of=context.as_of,
            source_mode=self.capture.source_mode,
        )

    async def scan(
        self, context: OperationContext, run: ScanRun, instruments: tuple[InstrumentIdentity, ...]
    ) -> ProviderBatch[ScanMatch]:
        c = self.capture
        if (
            context.owner_id != c.owner_id
            or run.owner_id != c.owner_id
            or run.as_of != context.as_of
            or run.request_id != c.request_id
            or context.correlation.request_id != c.request_id
            or run.definition != c.definition
            or instruments != c.instruments
        ):
            raise ProviderAccess.failure(self, context, DomainErrorCode.PROVENANCE_MISMATCH)
        if (
            c.received_at > context.as_of
            or (context.as_of - c.received_at).total_seconds() > self.settings.snapshot_ttl_seconds
        ):
            raise ProviderAccess.failure(self, context, DomainErrorCode.STALE_DATA)
        known = {i.native.native_id: i for i in instruments}
        rows = json.loads(c.rows_json)
        matches: list[ScanMatch] = []
        for row in rows:
            instrument = known[row["symbol"]]
            key = digest(
                {
                    "run": str(run.run_id),
                    "symbol": row["symbol"],
                    "schema": c.schema_hash,
                    "strategy": c.plan.strategy,
                }
            )
            provenance = Provenance(
                producer=IDENTITY,
                source=SourceReference(
                    namespace="tradingview",
                    native_id=f"{c.connection_id}:{row['symbol']}",
                    revision=c.schema_hash,
                ),
                mode=c.source_mode,
                observation_key=key,
                transformation=RevisionRef(id="tradingview-exact-batch-local-filter", version="1"),
                dependence_group="tradingview-exact-batch",
            )
            evidence = DiscoveryEvidence(
                evidence_id=uuid5(NAMESPACE_URL, key + "evidence"),
                owner_id=c.owner_id,
                subject_id=instrument.instrument_id,
                category=EvidenceCategory.PROVIDER_SCAN,
                polarity=EvidencePolarity.NEUTRAL,
                observation_basis="provider-current",
                observed_at=c.received_at,
                received_at=c.received_at,
                source_data_time=None,
                provenance=provenance,
                measures=tuple(
                    Measure(name=name, value=Decimal(str(row[name])), unit=UNITS[name])
                    for name in c.plan.requested_columns
                ),
            )
            matches.append(
                ScanMatch(
                    scan_match_id=uuid5(NAMESPACE_URL, key),
                    run_id=run.run_id,
                    owner_id=c.owner_id,
                    instrument=instrument,
                    definition_id=run.definition.definition_id,
                    definition_revision=run.definition.revision,
                    profile=run.profile,
                    configuration_fingerprint=run.configuration_fingerprint,
                    evidence=(evidence,),
                    provenance=provenance,
                )
            )
        incomplete = bool(c.unresolved_symbols) or c.total > len(rows)
        return ProviderBatch[ScanMatch](
            identity=IDENTITY,
            owner_id=c.owner_id,
            request_id=c.request_id,
            as_of=context.as_of,
            source_mode=c.source_mode,
            completeness="PARTIAL" if incomplete else "COMPLETE",
            limitations=(
                "source-time-unavailable",
                "bar-completion-unverified",
                *(("unresolved-symbols",) if c.unresolved_symbols else ()),
                *(("result-truncated",) if c.total > len(rows) else ()),
            ),
            items=tuple(matches),
        )


class TradingViewAdapter:
    def __init__(
        self, manager: ConnectionManager, settings: TradingViewSettings, *, synthetic: bool = False
    ) -> None:
        self.manager, self.settings, self.synthetic = manager, settings, synthetic

    def status(self, who: Context, identity: UUID) -> Status:
        row = self.manager.status(who, identity)
        if row.provider_id != "tradingview":
            raise Failure(Code.NOT_CONFIGURED)
        return Status(
            enabled=self.settings.enabled,
            response_contract_verified=self.settings.response_contract_verified,
            connection=row,
            allowed_tools=tuple(sorted(TOOLS)),
            schema_status="VERIFY_ON_CAPTURE"
            if self.settings.response_contract_verified
            else "UNVERIFIED",
        )

    def _validate_definition(self, definition: ScanDefinition) -> None:
        expected_mode = SourceMode.SYNTHETIC if self.synthetic else SourceMode.LIVE_SNAPSHOT
        if (
            definition.source_mode != expected_mode
            or definition.timeframe != "provider-current"
            or set(definition.required_capabilities) != {"sd.scan"}
        ):
            raise Failure(Code.CONTRACT_MISMATCH)
        for criterion in definition.criteria:
            if (
                criterion.metric not in UNITS
                or criterion.unit != UNITS[criterion.metric]
                or criterion.operator not in ALL_COMPARISONS
                or abs(criterion.threshold) > Decimal("1e12")
            ):
                raise Failure(Code.CONTRACT_MISMATCH)
            value = float(criterion.threshold)
            if not math.isfinite(value) or Decimal(str(value)) != criterion.threshold:
                raise Failure(Code.CONTRACT_MISMATCH)

    def arguments(
        self, definition: ScanDefinition, instruments: tuple[InstrumentIdentity, ...]
    ) -> ExactPlan:
        """Plan an exact universe; request order defines deterministic chunking."""

        self._validate_definition(definition)
        if (
            not instruments
            or len(instruments) > 64
            or len({i.native.native_id for i in instruments}) != len(instruments)
        ):
            raise Failure(Code.INVALID_ARGUMENTS)
        if any(
            i.native.namespace != "tradingview"
            or i.native.native_id != f"{i.exchange}:{i.symbol}"
            or i.exchange not in {"NSE", "BSE"}
            or i.segment != "EQ"
            for i in instruments
        ):
            raise Failure(Code.CONTRACT_MISMATCH)
        symbols = tuple(i.native.native_id for i in instruments)
        columns = tuple(
            sorted(
                {criterion.metric for criterion in definition.criteria} | {self.settings.sort_by}
            )
        )
        return ExactPlan(
            requested_universe=symbols,
            requested_columns=columns,
            chunks=tuple(
                BatchRequest(symbols=symbols[start : start + BATCH_LIMIT], columns=columns)
                for start in range(0, len(symbols), BATCH_LIMIT)
            ),
        )

    def broad_arguments(self, definition: ScanDefinition) -> BroadPlan:
        """Retain a truthful provider-defined broad screener path without exact tickers."""

        self._validate_definition(definition)
        if definition.combination != "ALL":
            raise Failure(Code.CONTRACT_MISMATCH)
        filters: dict[str, JsonValue] = {}
        for criterion in definition.criteria:
            if criterion.operator not in {Comparison.EQ, Comparison.GTE, Comparison.LTE}:
                raise Failure(Code.CONTRACT_MISMATCH)
            value = float(criterion.threshold)
            bounds = cast(list[JsonValue], filters.setdefault(criterion.metric, [None, None]))
            if criterion.operator in {Comparison.GTE, Comparison.EQ}:
                bounds[0] = (
                    max(float(cast(float, bounds[0])), value) if bounds[0] is not None else value
                )
            if criterion.operator in {Comparison.LTE, Comparison.EQ}:
                bounds[1] = (
                    min(float(cast(float, bounds[1])), value) if bounds[1] is not None else value
                )
            if (
                bounds[0] is not None
                and bounds[1] is not None
                and cast(float, bounds[0]) > cast(float, bounds[1])
            ):
                raise Failure(Code.INVALID_ARGUMENTS)
        columns = sorted(
            {"name", self.settings.sort_by}
            | {criterion.metric for criterion in definition.criteria}
        )
        return BroadPlan(
            arguments={
                "market": self.settings.market,
                "filters": filters,
                "sort_by": self.settings.sort_by,
                "sort_order": self.settings.sort_order,
                "limit": self.settings.max_items,
                "columns": cast(list[JsonValue], columns),
                "symbol_types": cast(list[JsonValue], ["stock"]),
            }
        )

    async def execute(
        self,
        who: Context,
        identity: UUID,
        generation: int,
        definition: ScanDefinition,
        profile: ScanProfileReference,
        instruments: tuple[InstrumentIdentity, ...],
        run_id: UUID,
    ) -> Execution:
        context = OperationContext(
            owner_id=who.owner_id, correlation=who.correlation, as_of=datetime.now(UTC)
        )
        started = context.as_of
        deadline = asyncio.get_running_loop().time() + self.settings.timeout_seconds

        def failed(code: ErrorCode | DomainErrorCode) -> ProviderFailure:
            from twf.discovery.providers import ProviderError

            return ProviderFailure(
                ProviderError(
                    code=code,
                    provider_id=IDENTITY.service_id,
                    operation="sd.scan",
                    request_id=who.correlation.request_id,
                )
            )

        try:
            if profile.owner_id != who.owner_id:
                raise Failure(Code.DENIED)
            if not self.settings.enabled:
                raise Failure(Code.CLOSED)
            if not self.synthetic and not self.settings.response_contract_verified:
                raise Failure(Code.CONTRACT_MISMATCH)
            config = self.manager.config("tradingview")
            if config.endpoint != ENDPOINT or config.auth_mode != AuthMode.OAUTH_2_1:
                raise Failure(Code.CONTRACT_MISMATCH)
            status = self.status(who, identity)
            if status.connection.generation != generation:
                raise Failure(Code.STALE)
            plan = self.arguments(definition, instruments)
            async with asyncio.timeout(self.settings.timeout_seconds):
                _, schema_reply = await self.manager.tools(
                    who,
                    identity,
                    generation,
                    policy=ToolPolicy(allowed=TOOLS),
                    name=GET_COLUMNS_TOOL,
                    arguments={"market": "stock"},
                )
                schema = successful(payload(schema_reply))
                schema_hash = _validate_columns_schema(schema, set(plan.requested_columns))

                all_rows: list[dict[str, JsonValue]] = []
                unresolved: list[str] = []
                resolved: set[str] = set()
                for chunk in plan.chunks:
                    _, reply = await self.manager.tools(
                        who,
                        identity,
                        generation,
                        policy=ToolPolicy(allowed=TOOLS),
                        name=GET_BATCH_TOOL,
                        arguments=chunk.model_dump(mode="json"),
                    )
                    result = successful(payload(reply))
                    rows, missing = _batch_rows(result, chunk.symbols, plan.requested_columns)
                    for row in rows:
                        symbol = cast(str, row["symbol"])
                        if symbol in resolved:
                            raise ValueError("Duplicate result across chunks")
                        resolved.add(symbol)
                    all_rows.extend(rows)
                    unresolved.extend(missing)

                matched: list[dict[str, JsonValue]] = []
                for row in all_rows:
                    flags = tuple(
                        compare(float(cast(float | int, row[criterion.metric])), criterion)
                        for criterion in definition.criteria
                    )
                    if all(flags) if definition.combination == "ALL" else any(flags):
                        matched.append(row)
                matched.sort(
                    key=lambda row: float(cast(float | int, row[self.settings.sort_by])),
                    reverse=self.settings.sort_order == "desc",
                )
                total = len(matched)
                rows = matched[: self.settings.max_items]
                received = datetime.now(UTC)
                capture = Capture(
                    owner_id=who.owner_id,
                    connection_id=identity,
                    generation=generation,
                    request_id=who.correlation.request_id,
                    definition=definition,
                    instruments=instruments,
                    started_at=started,
                    received_at=received,
                    source_mode=definition.source_mode,
                    plan=plan,
                    schema_hash=schema_hash,
                    rows_json=json.dumps(rows, separators=(",", ":"), sort_keys=True),
                    total=total,
                    unresolved_symbols=tuple(unresolved),
                )
                provider = TradingViewScanProvider(capture, self.settings)
                context = context.model_copy(update={"as_of": received})
                run = ScanRun(
                    run_id=run_id,
                    owner_id=who.owner_id,
                    request_id=who.correlation.request_id,
                    profile=profile,
                    definition=definition,
                    as_of=received,
                )
                batch = await ProviderAccess(ScanPolicy(who.owner_id, self.settings)).call(
                    provider,
                    context,
                    "sd.scan",
                    "sd.scan.v1",
                    lambda: provider.scan(context, run, instruments),
                )
                parameters = cast(dict[str, JsonValue], plan.model_dump(mode="json"))
                execution = Execution(
                    run=run,
                    result=batch,
                    connection_id=identity,
                    generation=generation,
                    started_at=started,
                    completed_at=datetime.now(UTC),
                    requested_universe=plan.requested_universe,
                    requested_columns=plan.requested_columns,
                    chunk_count=len(plan.chunks),
                    unresolved_symbols=tuple(unresolved),
                    schema_hash=capture.schema_hash,
                    parameters=parameters,
                )
                if asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError
                return execution
        except TimeoutError:
            raise failed(ErrorCode.TIMEOUT) from None
        except Failure as error:
            codes: dict[Code, ErrorCode | DomainErrorCode] = {
                Code.AUTH_REQUIRED: ErrorCode.AUTHENTICATION_FAILED,
                Code.AUTH_FAILED: ErrorCode.AUTHENTICATION_FAILED,
                Code.REAUTH_REQUIRED: ErrorCode.AUTHENTICATION_FAILED,
                Code.DENIED: ErrorCode.AUTHORIZATION_FAILED,
                Code.TIMEOUT: ErrorCode.TIMEOUT,
                Code.RATE_LIMITED: DomainErrorCode.RATE_LIMITED,
                Code.CONTRACT_MISMATCH: ErrorCode.UNSUPPORTED_CAPABILITY,
                Code.SCHEMA_MISMATCH: ErrorCode.INVALID_RESPONSE,
                Code.STALE: DomainErrorCode.PROVENANCE_MISMATCH,
                Code.TOOL_NOT_ALLOWED: ErrorCode.AUTHORIZATION_FAILED,
                Code.TOOL_NOT_FOUND: ErrorCode.UNSUPPORTED_CAPABILITY,
                Code.INVALID_ARGUMENTS: DomainErrorCode.INVALID_REQUEST,
            }
            raise failed(codes.get(error.code, ErrorCode.SERVICE_UNAVAILABLE)) from None
        except (ValueError, KeyError, TypeError, ValidationError):
            raise failed(ErrorCode.INVALID_RESPONSE) from None

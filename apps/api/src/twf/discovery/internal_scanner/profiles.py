"""Five versioned definition templates, not a parallel settings/profile registry."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from twf.discovery.domain import Criterion, ProducerIdentity, ScanDefinition, SourceMode
from twf.discovery.internal_scanner.conditions import METRICS
from twf.discovery.internal_scanner.market_series import INTERVAL_SECONDS
from twf.discovery.providers import OperationContext, ProviderError, ProviderFailure
from twf.integrations.contracts import Contract, ErrorCode

IDENTITY = ProducerIdentity(
    service_id="internal-scanner-v0",
    provider="twf-native",
    service_version="1",
    contract_version="sd.scan.v1",
)
PROFILE_NAMES = (
    "TREND_CONTINUATION",
    "BREAKOUT_WITH_VOLUME",
    "PULLBACK_IN_UPTREND",
    "MOMENTUM",
    "RELATIVE_VOLUME",
)


class ProfileParameters(Contract):
    rsi_min: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)] = 50
    rsi_max: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)] = 80
    relative_volume_min: Annotated[float, Field(gt=0, le=100, allow_inf_nan=False)] = 1.5
    pullback_zone_percent: Annotated[float, Field(gt=0, le=10, allow_inf_nan=False)] = 1
    roc_min: Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)] = 0

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.rsi_min > self.rsi_max:
            raise ValueError("RSI range reversed")
        return self


def build_profile(
    name: str,
    context: OperationContext,
    definition_id: UUID,
    *,
    interval: str = "1d",
    revision: int = 1,
    parameters: ProfileParameters | None = None,
    direction: Literal["LONG", "SHORT", "NEUTRAL"] = "NEUTRAL",
) -> ScanDefinition:
    if name not in PROFILE_NAMES or interval not in INTERVAL_SECONDS:
        raise ProviderFailure(
            ProviderError(
                code=ErrorCode.UNSUPPORTED_CAPABILITY,
                provider_id=IDENTITY.service_id,
                operation="sd.scan",
                request_id=context.correlation.request_id,
            )
        )
    parameters = parameters or ProfileParameters()
    long_recipes: dict[str, tuple[tuple[str, str, float], ...]] = {
        "TREND_CONTINUATION": (
            ("close_sma50_gap", "GT", 0),
            ("sma50_sma200_gap", "GT", 0),
            ("rsi.14", "GTE", parameters.rsi_min),
            ("rsi.14", "LTE", parameters.rsi_max),
        ),
        "BREAKOUT_WITH_VOLUME": (
            ("breakout.20", "EQ", 1),
            ("relative_volume.20", "GTE", parameters.relative_volume_min),
        ),
        "PULLBACK_IN_UPTREND": (
            ("sma50_sma200_gap", "GT", 0),
            ("close_sma50_gap", "GT", 0),
            ("close_sma20_gap", "GTE", -parameters.pullback_zone_percent),
            ("close_sma20_gap", "LTE", parameters.pullback_zone_percent),
            ("roc.1", "LT", 0),
        ),
        "MOMENTUM": (
            ("roc.10", "GT", parameters.roc_min),
            ("rsi.14", "GTE", parameters.rsi_min),
        ),
        "RELATIVE_VOLUME": (
            ("relative_volume.20", "GTE", parameters.relative_volume_min),
            ("roc.10", "GT", 0),
        ),
    }
    short_recipes: dict[str, tuple[tuple[str, str, float], ...]] = {
        "TREND_CONTINUATION": (
            ("close_sma50_gap", "LT", 0),
            ("sma50_sma200_gap", "LT", 0),
            ("rsi.14", "GTE", 100 - parameters.rsi_max),
            ("rsi.14", "LTE", 100 - parameters.rsi_min),
        ),
        "BREAKOUT_WITH_VOLUME": (
            ("breakdown.20", "EQ", 1),
            ("relative_volume.20", "GTE", parameters.relative_volume_min),
        ),
        "MOMENTUM": (
            ("roc.10", "LT", -parameters.roc_min),
            ("rsi.14", "LTE", 100 - parameters.rsi_min),
        ),
        "RELATIVE_VOLUME": (
            ("relative_volume.20", "GTE", parameters.relative_volume_min),
            ("roc.10", "LT", 0),
        ),
    }
    neutral_recipes = {
        **long_recipes,
        "RELATIVE_VOLUME": (("relative_volume.20", "GTE", parameters.relative_volume_min),),
    }
    recipes = (
        short_recipes
        if direction == "SHORT"
        else (long_recipes if direction == "LONG" else neutral_recipes)
    )
    if name not in recipes:
        raise ProviderFailure(
            ProviderError(
                code=ErrorCode.UNSUPPORTED_CAPABILITY,
                provider_id=IDENTITY.service_id,
                operation="sd.scan",
                request_id=context.correlation.request_id,
            )
        )
    return ScanDefinition(
        definition_id=definition_id,
        revision=revision,
        direction=direction,
        timeframe=interval,
        source_mode=SourceMode.SYNTHETIC,
        required_capabilities=("sd.scan",),
        criteria=tuple(
            Criterion.model_validate(
                {"metric": metric, "operator": op, "threshold": str(value), "unit": METRICS[metric]}
            )
            for metric, op, value in recipes[name]
        ),
    )

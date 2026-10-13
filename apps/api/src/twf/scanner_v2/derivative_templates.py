"""Explicit O4 option recipes and owner-scoped configuration-only templates."""

from datetime import UTC, date, datetime
from typing import Any, Literal, Self
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from twf.infrastructure.scanner_v2 import DerivativeTemplateRow
from twf.scanner_v2.derivatives import DerivativeFilter, DerivativeModel
from twf.scanner_v2.futures import FuturesFilter
from twf.watchlists.service import WatchlistFailure

TEMPLATE_SCHEMA_VERSION = 1
Horizon = Literal["INTRADAY", "POSITIONAL", "GENERAL"]
InstrumentScope = Literal["OPTIONS", "FUTURES"]


class DerivativeTemplateRecipe(DerivativeModel):
    """Only repeatable setup; no run, quote, chain, or evidence fields."""

    scanner_type: Literal["DERIVATIVES"] = "DERIVATIVES"
    instrument_scope: InstrumentScope = "OPTIONS"
    expiry_mode: Literal["NEAREST", "EXACT"] = "NEAREST"
    exact_expiry: date | None = None
    strike_window: Literal[5, 10, 15, 20] = 10
    watchlist_id: UUID | None = None
    predicates: tuple[DerivativeFilter | FuturesFilter, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def valid(self) -> Self:
        predicate_model = DerivativeFilter if self.instrument_scope == "OPTIONS" else FuturesFilter
        for item in self.predicates:
            predicate_model.model_validate(item.model_dump(mode="json"))
        if self.expiry_mode == "EXACT" and self.exact_expiry is None:
            raise ValueError("Choose an exact expiry")
        if len({item.field for item in self.predicates}) != len(self.predicates):
            raise ValueError("Use one predicate per field")
        return self


class DerivativeTemplateInput(DerivativeModel):
    template_schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=100)
    horizon: Horizon
    description: str = Field(default="", max_length=500)
    recipe: DerivativeTemplateRecipe

    @field_validator("name")
    @classmethod
    def meaningful_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Enter a template name")
        return name


def _predicate(field: str, operator: str, value: Any) -> DerivativeFilter:
    return DerivativeFilter.model_validate({"field": field, "operator": operator, "value": value})


def _builtin(
    slug: str,
    name: str,
    horizon: Horizon,
    purpose: str,
    option_type: str,
    moneyness: tuple[str, ...],
    rules: tuple[tuple[str, str, Any], ...],
) -> dict[str, Any]:
    recipe = DerivativeTemplateRecipe(
        predicates=(
            _predicate("option_type", "equals", option_type),
            _predicate("moneyness", "equals", moneyness),
            *(_predicate(*rule) for rule in rules),
        )
    )
    return {
        "template_id": f"builtin:{slug}",
        "name": name,
        "scanner_type": "DERIVATIVES",
        "instrument_scope": "OPTIONS",
        "horizon": horizon,
        "source": "BUILT_IN",
        "description": purpose,
        "template_schema_version": TEMPLATE_SCHEMA_VERSION,
        "recipe": recipe.model_dump(mode="json"),
    }


LIQUID = (("volume_percentile", ">=", 70), ("oi_percentile", ">=", 70), ("spread_percent", "<=", 2))
MOMENTUM = (
    ("volume_percentile", ">=", 70),
    ("oi_percentile", ">=", 60),
    ("spread_percent", "<=", 2),
)
POSITIONAL = (
    ("dte", ">=", 7),
    ("volume_percentile", ">=", 60),
    ("oi_percentile", ">=", 70),
    ("spread_percent", "<=", 2),
)


def _future_builtin(
    slug: str, name: str, horizon: Horizon, purpose: str, rules: tuple[tuple[str, str, Any], ...]
) -> dict[str, Any]:
    recipe = DerivativeTemplateRecipe(
        instrument_scope="FUTURES",
        predicates=tuple(
            FuturesFilter.model_validate({"field": field, "operator": op, "value": value})
            for field, op, value in rules
        ),
    )
    return {
        "template_id": f"builtin:{slug}",
        "name": name,
        "scanner_type": "DERIVATIVES",
        "instrument_scope": "FUTURES",
        "horizon": horizon,
        "source": "BUILT_IN",
        "description": purpose,
        "template_schema_version": TEMPLATE_SCHEMA_VERSION,
        "recipe": recipe.model_dump(mode="json"),
    }


FUTURES_BUILTIN_TEMPLATES: tuple[dict[str, Any], ...] = (
    _future_builtin(
        "futures-momentum-long",
        "Intraday — Futures Momentum Long",
        "INTRADAY",
        "Liquid futures with an upward spot day direction.",
        (
            ("volume_percentile", ">=", 70),
            ("oi_percentile", ">=", 60),
            ("underlying_trend", "equals", "Up"),
        ),
    ),
    _future_builtin(
        "futures-momentum-short",
        "Intraday — Futures Momentum Short",
        "INTRADAY",
        "Liquid futures with a downward spot day direction.",
        (
            ("volume_percentile", ">=", 70),
            ("oi_percentile", ">=", 60),
            ("underlying_trend", "equals", "Down"),
        ),
    ),
    _future_builtin(
        "futures-oi-buildup",
        "Intraday — Futures OI Buildup",
        "INTRADAY",
        "Requires comparable exact-contract archived OI within 30 minutes.",
        (
            ("change_in_open_interest", ">", 0),
            ("oi_change_percent", ">=", 1),
            ("oi_percentile", ">=", 70),
            ("volume_percentile", ">=", 60),
        ),
    ),
    _future_builtin(
        "futures-short-covering",
        "Intraday — Futures Short Covering",
        "INTRADAY",
        "Explicit inferred interpretation and liquid participation.",
        (
            ("interpretation", "equals", "Short covering"),
            ("volume_percentile", ">=", 60),
            ("oi_percentile", ">=", 60),
        ),
    ),
    _future_builtin(
        "futures-positional-long",
        "Positional — Futures Trend Long",
        "POSITIONAL",
        "At least seven days to expiry with spot day direction up and liquid OI.",
        (
            ("dte", ">=", 7),
            ("underlying_trend", "equals", "Up"),
            ("volume_percentile", ">=", 60),
            ("oi_percentile", ">=", 70),
        ),
    ),
    _future_builtin(
        "futures-positional-short",
        "Positional — Futures Trend Short",
        "POSITIONAL",
        "At least seven days to expiry with spot day direction down and liquid OI.",
        (
            ("dte", ">=", 7),
            ("underlying_trend", "equals", "Down"),
            ("volume_percentile", ">=", 60),
            ("oi_percentile", ">=", 70),
        ),
    ),
    _future_builtin(
        "futures-positional-oi",
        "Positional — Futures OI Buildup",
        "POSITIONAL",
        "At least seven days to expiry and comparable OI expansion.",
        (
            ("dte", ">=", 7),
            ("change_in_open_interest", ">", 0),
            ("oi_change_percent", ">=", 1),
            ("oi_percentile", ">=", 70),
        ),
    ),
    _future_builtin(
        "futures-positional-covering",
        "Positional — Futures Short Covering",
        "POSITIONAL",
        "At least seven days to expiry and explicit inferred covering evidence.",
        (
            ("dte", ">=", 7),
            ("interpretation", "equals", "Short covering"),
            ("volume_percentile", ">=", 60),
        ),
    ),
)


DERIVATIVES_BUILTIN_TEMPLATES: tuple[dict[str, Any], ...] = (
    _builtin(
        "intraday-liquid-atm",
        "Intraday — Liquid ATM Options",
        "INTRADAY",
        "Liquid ATM contracts for same-session discretionary review.",
        "BOTH",
        ("ATM",),
        LIQUID,
    ),
    _builtin(
        "intraday-bullish-call",
        "Intraday — Bullish Call Momentum",
        "INTRADAY",
        "Liquid calls with an upward underlying trend.",
        "CE",
        ("ATM", "OTM"),
        MOMENTUM + (("underlying_trend", "equals", "Up"),),
    ),
    _builtin(
        "intraday-bearish-put",
        "Intraday — Bearish Put Momentum",
        "INTRADAY",
        "Liquid puts with a downward underlying trend.",
        "PE",
        ("ATM", "OTM"),
        MOMENTUM + (("underlying_trend", "equals", "Down"),),
    ),
    _builtin(
        "intraday-unusual-activity",
        "Intraday — Unusual Option Activity",
        "INTRADAY",
        "Exceptional chain-relative volume without directional bias.",
        "BOTH",
        ("ATM", "OTM"),
        (("volume_percentile", ">=", 90), ("oi_percentile", ">=", 80)),
    ),
    _builtin(
        "intraday-fresh-oi",
        "Intraday — Fresh OI Buildup",
        "INTRADAY",
        "Contracts with observed positive OI change and active volume.",
        "BOTH",
        ("ATM", "OTM"),
        (
            ("oi_change_percent", ">=", 10),
            ("oi_change_percentile", ">=", 80),
            ("volume_percentile", ">=", 70),
            ("spread_percent", "<=", 2),
        ),
    ),
    _builtin(
        "intraday-best-liquidity",
        "Intraday — Best Liquidity",
        "INTRADAY",
        "Near-ATM contracts with strong volume, OI and narrow spread.",
        "BOTH",
        ("ATM", "OTM"),
        (
            ("volume_percentile", ">=", 80),
            ("oi_percentile", ">=", 80),
            ("spread_percent", "<=", 1.5),
        ),
    ),
    _builtin(
        "positional-bullish-call",
        "Positional — Bullish Call Setup",
        "POSITIONAL",
        "Liquid calls with at least seven days to expiry and an upward underlying trend.",
        "CE",
        ("ATM", "OTM"),
        POSITIONAL + (("underlying_trend", "equals", "Up"),),
    ),
    _builtin(
        "positional-bearish-put",
        "Positional — Bearish Put Setup",
        "POSITIONAL",
        "Liquid puts with at least seven days to expiry and a downward underlying trend.",
        "PE",
        ("ATM", "OTM"),
        POSITIONAL + (("underlying_trend", "equals", "Down"),),
    ),
    _builtin(
        "positional-bullish-oi-trend",
        "Positional — Bullish OI + Trend",
        "POSITIONAL",
        "Positive OI change in calls aligned with an upward underlying trend.",
        "CE",
        ("ATM", "OTM"),
        (
            ("dte", ">=", 7),
            ("volume_percentile", ">=", 60),
            ("oi_percentile", ">=", 80),
            ("oi_change_percent", ">", 0),
            ("spread_percent", "<=", 2),
            ("underlying_trend", "equals", "Up"),
        ),
    ),
    _builtin(
        "positional-bearish-oi-trend",
        "Positional — Bearish OI + Trend",
        "POSITIONAL",
        "Positive OI change in puts aligned with a downward underlying trend.",
        "PE",
        ("ATM", "OTM"),
        (
            ("dte", ">=", 7),
            ("volume_percentile", ">=", 60),
            ("oi_percentile", ">=", 80),
            ("oi_change_percent", ">", 0),
            ("spread_percent", "<=", 2),
            ("underlying_trend", "equals", "Down"),
        ),
    ),
    _builtin(
        "positional-liquid-near-atm",
        "Positional — Liquid Near-ATM Options",
        "POSITIONAL",
        "Near-ATM liquid options with at least seven days to expiry.",
        "BOTH",
        ("ATM", "OTM"),
        POSITIONAL,
    ),
    _builtin(
        "positional-best-liquidity",
        "Positional — Best Liquidity",
        "POSITIONAL",
        "High chain-relative volume and OI with a narrow spread and at least seven days to expiry.",
        "BOTH",
        ("ATM", "OTM"),
        (
            ("dte", ">=", 7),
            ("volume_percentile", ">=", 75),
            ("oi_percentile", ">=", 80),
            ("spread_percent", "<=", 2),
        ),
    ),
)


class DerivativeTemplateService:
    def __init__(self, factory: sessionmaker[Session], owner: UUID) -> None:
        self.factory, self.owner = factory, owner

    @staticmethod
    def view(row: DerivativeTemplateRow) -> dict[str, Any]:
        return {
            "template_id": str(row.id),
            "source": "USER",
            "scanner_type": "DERIVATIVES",
            "instrument_scope": row.payload.get("recipe", {}).get("instrument_scope", "OPTIONS"),
            **row.payload,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }

    def list(self) -> list[dict[str, Any]]:
        with self.factory() as db:
            rows = db.scalars(
                select(DerivativeTemplateRow)
                .where(DerivativeTemplateRow.owner_id == self.owner)
                .order_by(DerivativeTemplateRow.updated_at.desc())
                .limit(100)
            )
            return [self.view(row) for row in rows]

    def save(self, value: DerivativeTemplateInput, key: UUID | None = None) -> dict[str, Any]:
        with self.factory.begin() as db:
            row = db.get(DerivativeTemplateRow, key) if key else None
            if key is not None and (row is None or row.owner_id != self.owner):
                raise WatchlistFailure("TEMPLATE_NOT_FOUND", 404)
            now = datetime.now(UTC)
            if row is None:
                row = DerivativeTemplateRow(
                    id=uuid4(), owner_id=self.owner, payload={}, created_at=now, updated_at=now
                )
                db.add(row)
            row.payload = value.model_dump(mode="json")
            row.updated_at = now
            return self.view(row)

    def delete(self, key: UUID) -> None:
        with self.factory.begin() as db:
            row = db.get(DerivativeTemplateRow, key)
            if row is None or row.owner_id != self.owner:
                raise WatchlistFailure("TEMPLATE_NOT_FOUND", 404)
            db.delete(row)

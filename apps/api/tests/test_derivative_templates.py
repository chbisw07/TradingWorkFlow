"""Derivatives recipes are explicit filters, never archived market results."""

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_watchlists import HEADERS
from test_watchlists import client as client  # noqa: F401

from twf.infrastructure.scanner_v2 import DerivativeTemplateRow
from twf.scanner_v2.derivative_templates import (
    DERIVATIVES_BUILTIN_TEMPLATES,
    FUTURES_BUILTIN_TEMPLATES,
    DerivativeTemplateInput,
    DerivativeTemplateRecipe,
    DerivativeTemplateService,
)
from twf.scanner_v2.derivatives import DerivativeFilter, DerivativeScanConfig
from twf.scanner_v2.futures import FuturesFilter
from twf.watchlists.service import WatchlistFailure

BASE = "/api/v1/scanner/derivatives"


def recipe() -> dict[str, Any]:
    return {
        "scanner_type": "DERIVATIVES",
        "instrument_scope": "OPTIONS",
        "expiry_mode": "NEAREST",
        "strike_window": 10,
        "predicates": [
            {"field": "option_type", "operator": "equals", "value": "CE"},
            {"field": "volume_percentile", "operator": ">=", "value": 90},
        ],
    }


def template() -> dict[str, Any]:
    return {
        "template_schema_version": 1,
        "name": "My High Volume Calls",
        "horizon": "INTRADAY",
        "description": "Explicit configuration only",
        "recipe": recipe(),
    }


def test_all_builtin_recipes_are_typed_visible_and_horizon_named() -> None:
    assert len(DERIVATIVES_BUILTIN_TEMPLATES) == 12
    names = {item["name"] for item in DERIVATIVES_BUILTIN_TEMPLATES}
    assert "Intraday — Breakout Calls" not in names
    assert "Intraday — Breakdown Puts" not in names
    assert "Positional — Bullish OI + Trend" in names
    assert "Positional — Bearish OI + Trend" in names
    for item in DERIVATIVES_BUILTIN_TEMPLATES:
        assert item["name"].startswith(item["horizon"].title() + " — ")
        parsed = DerivativeTemplateRecipe.model_validate(item["recipe"])
        assert item["source"] == "BUILT_IN" and parsed.instrument_scope == "OPTIONS"
        assert all(isinstance(rule, DerivativeFilter) for rule in parsed.predicates)
        assert len({rule.field for rule in parsed.predicates}) == len(parsed.predicates)
        if item["horizon"] == "POSITIONAL":
            assert any(
                rule.field == "dte" and rule.operator == ">=" and rule.value == 7
                for rule in parsed.predicates
            )
        assert parsed.watchlist_id is None


def test_template_contract_refuses_results_unknown_filters_and_futures() -> None:
    with pytest.raises(ValidationError):
        DerivativeTemplateInput.model_validate({**template(), "rows": [{"ltp": 100}]})
    with pytest.raises(ValidationError):
        DerivativeTemplateRecipe.model_validate(
            {**recipe(), "predicates": [{"field": "unknown", "operator": ">=", "value": 1}]}
        )
    with pytest.raises(ValidationError):
        DerivativeTemplateRecipe.model_validate({**recipe(), "instrument_scope": "FUTURES"})
    with pytest.raises(ValidationError):
        DerivativeTemplateInput.model_validate({**template(), "template_schema_version": 0})
    with pytest.raises(ValidationError):
        DerivativeTemplateInput.model_validate({**template(), "name": "   "})


def test_template_api_is_owner_scoped_configuration_only_and_saved_scans_stay_separate(
    client: TestClient,
) -> None:
    catalog = client.get(BASE + "/templates")
    assert catalog.status_code == 200, catalog.text
    assert len(catalog.json()["built_in"]) == 20
    assert catalog.json()["user"] == []
    create = client.post(BASE + "/templates", json=template(), headers=HEADERS)
    assert create.status_code == 200, create.text
    value = create.json()
    key = UUID(value["template_id"])
    assert value["source"] == "USER" and value["recipe"]["watchlist_id"] is None
    assert value["recipe"]["predicates"][1]["value"] == 90
    assert client.get(BASE + "/saved").json() == []
    assert client.get(BASE + "/runs").json() == []
    factory = client.app.state.session_factory
    another_owner = DerivativeTemplateService(factory, uuid4())
    assert another_owner.list() == []
    with pytest.raises(WatchlistFailure, match="TEMPLATE_NOT_FOUND"):
        another_owner.delete(key)
    with factory() as db:
        stored = db.get(DerivativeTemplateRow, key).payload
        assert set(stored) == {
            "template_schema_version",
            "name",
            "horizon",
            "description",
            "recipe",
        }
        assert set(stored["recipe"]) == {
            "scanner_type",
            "instrument_scope",
            "expiry_mode",
            "exact_expiry",
            "strike_window",
            "watchlist_id",
            "predicates",
        }
        assert not any(
            field in str(stored)
            for field in ("result_rows", "source_time", "market_snapshot", "implied_volatility")
        )
    changed = {**template(), "name": "Renamed", "horizon": "GENERAL"}
    update = client.patch(BASE + f"/templates/{key}", json=changed, headers=HEADERS)
    assert update.status_code == 200, update.text
    assert client.get(BASE + "/templates").json()["user"][0]["name"] == "Renamed"
    assert client.delete(BASE + f"/templates/{key}", headers=HEADERS).json() == {"deleted": True}
    assert client.get(BASE + "/templates").json()["user"] == []
    assert (
        client.patch(BASE + f"/templates/{key}", json=changed, headers=HEADERS).status_code == 404
    )
    assert client.delete(BASE + f"/templates/{key}", headers=HEADERS).status_code == 404


def test_template_origin_does_not_replace_actual_executed_filters() -> None:
    original = DERIVATIVES_BUILTIN_TEMPLATES[0]
    modified = [dict(item) for item in original["recipe"]["predicates"]]
    next(item for item in modified if item["field"] == "volume_percentile")["value"] = 90
    config = DerivativeScanConfig.model_validate(
        {
            "universe": {"source": "CUSTOM", "symbols": ["NIFTY"]},
            "filters": modified,
            "origin_template_id": original["template_id"],
            "origin_template_name": original["name"],
        }
    )
    archived = config.model_dump(mode="json")
    assert archived["filters"][2]["value"] == 90
    assert archived["origin_template_id"] == original["template_id"]
    assert (
        next(
            item
            for item in original["recipe"]["predicates"]
            if item["field"] == "volume_percentile"
        )["value"]
        == 70
    )


def test_futures_builtin_recipes_are_explicit_and_separate_from_options() -> None:
    assert len(FUTURES_BUILTIN_TEMPLATES) == 8
    assert {item["instrument_scope"] for item in FUTURES_BUILTIN_TEMPLATES} == {"FUTURES"}
    names = {item["name"] for item in FUTURES_BUILTIN_TEMPLATES}
    assert "Intraday — Futures Momentum Long" in names
    assert "Intraday — Futures Momentum Short" in names
    assert "Intraday — Futures Short Covering" in names
    assert "Positional — Futures Trend Long" in names
    assert "Positional — Futures Short Covering" in names
    assert not any("Breakout" in name or "Breakdown" in name for name in names)
    for item in FUTURES_BUILTIN_TEMPLATES:
        parsed = DerivativeTemplateRecipe.model_validate(item["recipe"])
        assert parsed.instrument_scope == "FUTURES"
        assert parsed.watchlist_id is None
        assert all(
            isinstance(FuturesFilter.model_validate(rule.model_dump(mode="json")), FuturesFilter)
            for rule in parsed.predicates
        )
        assert len({rule.field for rule in parsed.predicates}) == len(parsed.predicates)
        if item["horizon"] == "POSITIONAL":
            assert any(rule.field == "dte" and rule.value == 7 for rule in parsed.predicates)


def test_futures_template_api_persists_configuration_without_results(client: TestClient) -> None:
    setup = {
        "template_schema_version": 1,
        "name": "My Futures Activity",
        "horizon": "INTRADAY",
        "description": "Explicit futures recipe",
        "recipe": {
            "instrument_scope": "FUTURES",
            "expiry_mode": "NEAREST",
            "strike_window": 10,
            "predicates": [
                {"field": "volume_percentile", "operator": ">=", "value": 75},
                {"field": "underlying_trend", "operator": "equals", "value": "Up"},
            ],
        },
    }
    response = client.post(BASE + "/templates", json=setup, headers=HEADERS)
    assert response.status_code == 200, response.text
    template = response.json()
    assert template["instrument_scope"] == "FUTURES"
    assert template["recipe"]["predicates"] == setup["recipe"]["predicates"]
    assert client.get(BASE + "/runs").json() == []
    assert client.get(BASE + "/saved").json() == []
    factory = client.app.state.session_factory
    with factory() as db:
        stored = db.get(DerivativeTemplateRow, UUID(template["template_id"])).payload
        assert "rows" not in stored and "quote" not in str(stored)

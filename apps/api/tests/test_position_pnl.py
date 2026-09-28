"""Position snapshot normalization; no orders or quotes are used to compute P&L."""

import asyncio
from decimal import Decimal
from typing import Any

import httpx
import pytest
from broker_provider_fixture import CLOSED_POSITION
from pydantic import SecretStr

from twf.brokers.contracts import Credentials
from twf.brokers.zerodha import ZerodhaAdapter


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        pytest.param(dict(quantity=10, realised=0, unrealised=40, pnl=40), (0, 40, 40), id="open"),
        pytest.param(
            dict(quantity=-10, realised=0, unrealised=-40, pnl=-40), (0, -40, -40), id="short"
        ),
        pytest.param(
            dict(quantity=0, realised=0, unrealised=100, pnl=100),
            (100, 0, 100),
            id="closed-win-legacy",
        ),
        pytest.param(
            CLOSED_POSITION, (Decimal("-1007.5"), 0, Decimal("-1007.5")), id="observed-closed-loss"
        ),
        pytest.param(
            dict(quantity=0, realised=100, unrealised=0, pnl=100),
            (100, 0, 100),
            id="closed-explicit",
        ),
        pytest.param(
            dict(quantity=5, buy_quantity=10, sell_quantity=5, realised=10, unrealised=30, pnl=40),
            (10, 30, 40),
            id="partial",
        ),
        pytest.param(dict(quantity=0, pnl=40), (40, 0, 40), id="closed-total-only"),
        pytest.param(dict(quantity=5, pnl=40), (None, None, 40), id="open-total-only"),
        pytest.param(
            dict(quantity=5, realised=10, pnl=40), (10, None, 40), id="missing-unrealized"
        ),
        pytest.param(dict(quantity=5), (None, None, None), id="open-unknown"),
        pytest.param(dict(quantity=0), (None, 0, None), id="closed-unknown-total"),
        pytest.param(
            dict(pnl=40, realised=0, unrealised=40), (0, 40, 40), id="unknown-quantity-not-closed"
        ),
        pytest.param(
            dict(quantity=False, pnl=40, realised=0, unrealised=40),
            (0, 40, 40),
            id="invalid-quantity-not-closed",
        ),
        pytest.param(
            dict(quantity=0, realised=10, unrealised=0),
            (10, 0, None),
            id="closed-explicit-missing-total",
        ),
        pytest.param(
            dict(quantity=0, realised=0, unrealised=10),
            (None, 0, None),
            id="closed-legacy-missing-total",
        ),
        pytest.param(
            dict(quantity=5, realised=True, unrealised="NaN", pnl="Infinity"),
            (None, None, None),
            id="invalid-amounts",
        ),
        pytest.param(
            dict(quantity=5, realised=10, unrealised=20, pnl=40),
            (None, None, 40),
            id="inconsistent-split",
        ),
        pytest.param(dict(quantity=0, realised=0, unrealised=0, pnl=0), (0, 0, 0), id="known-zero"),
    ],
)
def test_position_snapshot_pnl(
    fields: dict[str, Any], expected: tuple[Decimal | int | None, ...]
) -> None:
    row = {**CLOSED_POSITION, "m2m": 999, **fields}
    # Missing P&L/quantity fields must actually be absent, not inherited from the fixture.
    for field in ("quantity", "realised", "unrealised", "pnl"):
        if field not in fields:
            row.pop(field, None)
    calls: list[str] = []

    def provider(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        assert request.method == "GET" and request.url.path == "/portfolio/positions"
        return httpx.Response(200, json={"status": "success", "data": {"net": [row], "day": [row]}})

    adapter = ZerodhaAdapter(transport=httpx.MockTransport(provider))
    positions = asyncio.run(
        adapter.get_positions(
            Credentials(
                api_key=SecretStr("test-key"),
                api_secret=SecretStr("test-secret"),
                access_token=SecretStr("test-token"),
            )
        )
    )
    assert calls == ["/portfolio/positions"]
    assert len(positions) == 1  # Never sum net and day snapshots.
    position = positions[0]
    assert position.instrument.reference == "ZERODHA:NFO:HDFCBANK26OCT730PE"
    assert (position.realized, position.unrealized, position.pnl) == expected
    if (
        position.realized is not None
        and position.unrealized is not None
        and position.pnl is not None
    ):
        assert position.realized + position.unrealized == position.pnl
    serialized = position.model_dump(mode="json")
    for key, amount in zip(("realized", "unrealized", "pnl"), expected, strict=True):
        assert serialized[key] == (None if amount is None else str(amount))

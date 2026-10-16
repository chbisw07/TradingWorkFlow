"""Signed-but-malformed Queue cursors are untrusted HTTP input on both backends."""

import base64
import hmac
import json
import random
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from order_provider_fixture import OrderProvider
from test_broker_v1 import bound, service
from test_broker_v1 import client as client
from test_twf_queue_oe3 import BASE, queue_service

from twf.brokers.zerodha import ZerodhaAdapter


@pytest.fixture
def account(client: TestClient) -> str:
    broker = service(client)
    broker.settings = broker.settings.model_copy(update={"broker_manual_trading_enabled": True})
    broker.adapter = ZerodhaAdapter(transport=httpx.MockTransport(OrderProvider()))
    return bound(client)


def _token(payload: dict[str, Any], key: str) -> str:
    data = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return (
        base64.urlsafe_b64encode(data + hmac.digest(key.encode(), data, "sha256"))
        .decode()
        .rstrip("=")
    )


def test_signed_invalid_cursor_returns_typed_400(client: TestClient, account: str) -> None:
    queue = queue_service(client)
    owner = str(queue.context.owner_id)
    key = queue.context.session_hash
    baseline: dict[str, Any] = {
        "v": 1,
        "owner": owner,
        "state": None,
        "at": "2026-10-15T12:00:00+00:00",
        "id": str(uuid4()),
    }
    cases: list[dict[str, Any]] = []
    # Exact independent-review reproduction: valid HMAC, numeric id, formerly 500.
    cases.append({**baseline, "id": 0})
    id_values: list[Any] = [None, False, True, [], {}, "", "x" * 300, -1, 3.2]
    for value in id_values:
        cases.append({**baseline, "id": value})
    for value in (None, False, True, [], {}, 123, "", "bad", "0001-01-01T00:00:00+14:00"):
        cases.append({**baseline, "at": value})
    for value in (None, False, 0, 2, "1", [], {}):
        cases.append({**baseline, "v": value})
    for value in (False, 1, [], {}, "READY"):
        cases.append({**baseline, "state": value})
    cases.extend(
        (
            {**baseline, "owner": str(uuid4())},
            {k: v for k, v in baseline.items() if k != "id"},
            {**baseline, "extra": 1},
        )
    )
    rng = random.Random(26015)
    invalid: list[Any] = [None, False, True, [], {}, 42, -8, 1.5, "", "invalid"]
    for _ in range(180):
        field = rng.choice(("v", "owner", "state", "at", "id"))
        value = rng.choice(invalid)
        if field == "state" and value is None:
            value = "HELD"
        cases.append({**baseline, field: value})
    for payload in cases:
        response = client.get(BASE, params={"cursor": _token(payload, key)})
        assert response.status_code == 400, (payload, response.status_code)
        assert response.json()["error"]["code"] == "INVALID_CURSOR"
        assert "Traceback" not in response.text
    valid = _token(baseline, key)
    for altered in (valid + "x", valid[:-4], "not-a-cursor", "x" * 1025):
        response = client.get(BASE, params={"cursor": altered})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_CURSOR"
    # A valid signature cannot override the active filter scope.
    response = client.get(BASE, params={"cursor": valid, "state": "READY"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_CURSOR"

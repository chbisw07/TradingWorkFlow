from __future__ import annotations

import os
import secrets
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.orm import Session

from twf.auth import token_digest
from twf.infrastructure.broker import BrokerAccount
from twf.infrastructure.identity import AuthSession


BASE = "http://127.0.0.1:8000"
ORIGIN = "http://localhost:3000"


def request(
    client: httpx.Client, method: str, path: str, **kwargs: object
) -> httpx.Response:
    response = client.request(method, BASE + path, **kwargs)
    print(
        "HTTP",
        method,
        path,
        response.status_code,
        "request_id=" + response.headers.get("x-request-id", "missing"),
    )
    print(response.text[:1200])
    return response


def denied_probe(
    engine: object, label: str, statement: str, values: dict[str, object]
) -> None:
    try:
        with engine.begin() as connection:  # type: ignore[union-attr]
            connection.execute(text(statement), values)
            raise AssertionError(f"{label} unexpectedly succeeded")
    except AssertionError:
        raise
    except Exception as exc:
        original = getattr(exc, "orig", exc)
        diagnostic = getattr(original, "diag", None)
        print(
            "DENIED",
            label,
            "type=" + type(original).__name__,
            "sqlstate=" + str(getattr(original, "sqlstate", None)),
            "table=" + str(getattr(diagnostic, "table_name", None)),
            "message=" + str(getattr(diagnostic, "message_primary", original)),
        )


engine = create_engine(os.environ["TWF_DATABASE_URL"])
token = secrets.token_urlsafe(32)
token_hash = token_digest(token)
now = datetime.now(UTC)

with Session(engine) as db:
    account = db.scalar(
        select(BrokerAccount)
        .where(BrokerAccount.state == "connected")
        .order_by(BrokerAccount.updated_at.desc())
    )
    if account is None:
        account = db.scalar(
            select(BrokerAccount).order_by(BrokerAccount.updated_at.desc())
        )
    if account is None:
        raise RuntimeError("No broker account exists for normal-flow reproduction")
    account_id = account.id
    owner_id = account.user_id
    db.add(
        AuthSession(
            token_hash=token_hash,
            user_id=owner_id,
            created_at=now,
            expires_at=now + timedelta(minutes=15),
            revoked_at=None,
        )
    )
    db.commit()

try:
    with httpx.Client(
        cookies={"twf_session": token}, headers={"Origin": ORIGIN}, timeout=30.0
    ) as client:
        request(client, "GET", "/api/v1/auth/me")
        policy = request(client, "GET", f"/api/v1/twf-queue/policy/{account_id}")
        catalog = request(
            client,
            "GET",
            f"/api/v1/brokers/accounts/{account_id}/instruments?q=RELIANCE&kind=EQ&limit=100",
        )
        if catalog.status_code == 200:
            items = catalog.json()["data"]["items"]
            eligible = [
                item
                for item in items
                if item.get("native_token")
                and item.get("reference")
                and item.get("exchange") in {"NSE", "BSE"}
            ]
            if not eligible:
                eligible = [
                    item
                    for item in items
                    if item.get("native_token") and item.get("reference")
                ]
            if eligible:
                item = next(
                    (
                        candidate
                        for candidate in eligible
                        if candidate["symbol"] == "RELIANCE"
                    ),
                    eligible[0],
                )
                derivative = item.get("kind") in {"CE", "PE", "FUT"}
                quantity = int(item.get("lot_size") or 1) if derivative else 1
                order = {
                    "account_id": str(account_id),
                    "reference": item["reference"],
                    "native_token": item["native_token"],
                    "side": "BUY",
                    "quantity": quantity,
                    "order_type": "LIMIT",
                    "limit_price": "1.00",
                    "product": "NRML" if derivative else "CNC",
                    "validity": "DAY",
                    "notes": "OE-4 privilege reproduction; no broker submission",
                }
                preview = request(
                    client, "POST", "/api/v1/twf-orders/preview", json=order
                )
                if preview.status_code == 200:
                    created = request(
                        client,
                        "POST",
                        "/api/v1/twf-orders",
                        json={**order, "preview_id": preview.json()["preview_id"]},
                    )
                    assert created.status_code == 200, created.text
                    payload = created.json()["order"]
                    assert payload["state"] == "READY"
                    assert payload["provenance"]["source"] == "MANUAL"
                    print(
                        "ORDER_VERIFIED",
                        payload["twf_order_id"],
                        payload["state"],
                        payload["provenance"]["source"],
                    )
                else:
                    print("ORDER_CREATE_SKIPPED preview did not succeed")
            else:
                print("ORDER_CREATE_SKIPPED catalog had no eligible instrument")
        else:
            print("ORDER_CREATE_SKIPPED catalog request did not succeed")
        assert policy.status_code == 200, policy.text
        current = policy.json()
        assert current["execution_enabled"] is False
        original_mode = current["current_dispatch_mode"]
        target_mode = "AUTO" if original_mode == "MANUAL" else "MANUAL"
        changed = request(
            client,
            "POST",
            f"/api/v1/twf-queue/policy/{account_id}",
            json={
                "current_dispatch_mode": target_mode,
                "expected_version": current["version"],
            },
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["execution_enabled"] is False
        restored = request(
            client,
            "POST",
            f"/api/v1/twf-queue/policy/{account_id}",
            json={
                "current_dispatch_mode": original_mode,
                "expected_version": changed.json()["version"],
            },
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["execution_enabled"] is False
        print(
            "POLICY_VERIFIED",
            original_mode,
            target_mode,
            original_mode,
            "execution_enabled=false",
        )

finally:
    with Session(engine) as db:
        db.execute(
            update(AuthSession)
            .where(
                AuthSession.token_hash == token_hash, AuthSession.revoked_at.is_(None)
            )
            .values(revoked_at=datetime.now(UTC))
        )
        db.commit()

"""Credential encryption and persistence regressions; only disposable test secrets."""

import base64
import io
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from test_broker_v1 import CREDENTIALS, HEADERS, bound, configure, service
from test_broker_v1 import client as client

from twf.brokers.contracts import BrokerFailure
from twf.brokers.secrets import CredentialCipher, EncryptedSecretStore
from twf.config.settings import Settings
from twf.infrastructure.broker import BrokerAccount, BrokerAttempt, BrokerSecret
from twf.infrastructure.database import Base
from twf.observability import JsonFormatter


def cipher() -> CredentialCipher:
    return CredentialCipher(
        Settings(credential_master_key=SecretStr(Fernet.generate_key().decode()))
    )


def test_roundtrip_fresh_iv_and_wrong_key() -> None:
    crypto = cipher()
    first, second = crypto.encrypt(b"test-secret"), crypto.encrypt(b"test-secret")
    assert first != second
    # Standard Fernet: version (1), timestamp (8), IV (16), ciphertext, HMAC.
    assert base64.urlsafe_b64decode(first)[9:25] != base64.urlsafe_b64decode(second)[9:25]
    assert crypto.decrypt(first) == crypto.decrypt(second) == b"test-secret"
    with pytest.raises(BrokerFailure):
        cipher().decrypt(first)


@pytest.mark.parametrize("offset", [0, 1, 9, 25, -1])
def test_tamper_never_returns_plaintext(offset: int) -> None:
    crypto = cipher()
    raw = bytearray(base64.urlsafe_b64decode(crypto.encrypt(b"test-secret")))
    raw[offset] ^= 1
    with pytest.raises(BrokerFailure):
        crypto.decrypt(base64.urlsafe_b64encode(raw).decode())
    with pytest.raises(BrokerFailure):
        crypto.decrypt(crypto.encrypt(b"test-secret"), "unknown-version")


@pytest.mark.parametrize("value", [None, "", "invalid", "é" * 44, "YQ==", "!" * 44])
def test_key_failure_is_actionable_and_redacted(value: str | None) -> None:
    settings = Settings(credential_master_key=SecretStr(value) if value is not None else None)
    with pytest.raises(BrokerFailure) as failure:
        CredentialCipher(settings)
    assert failure.value.status == 503
    assert "TWF_CREDENTIAL_MASTER_KEY" in failure.value.message
    assert "restart TWF" in failure.value.message
    assert "credential_master_key=" not in repr(settings)


def test_old_key_name_and_ciphertext_remain_compatible(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key()
    old_token = Fernet(key).encrypt(b"test-secret").decode()
    monkeypatch.setenv("TWF_BROKER_SECRET_KEY", key.decode())
    assert CredentialCipher(Settings()).decrypt(old_token) == b"test-secret"
    monkeypatch.setenv("TWF_CREDENTIAL_MASTER_KEY", key.decode())
    assert CredentialCipher(Settings(environment="production")).decrypt(old_token) == b"test-secret"
    # The new name is authoritative: neither invalid nor wrong keys fall back.
    monkeypatch.setenv("TWF_CREDENTIAL_MASTER_KEY", "bad")
    with pytest.raises(BrokerFailure):
        CredentialCipher(Settings())
    monkeypatch.setenv("TWF_CREDENTIAL_MASTER_KEY", Fernet.generate_key().decode())
    with pytest.raises(BrokerFailure):
        CredentialCipher(Settings()).decrypt(old_token)


def test_setup_and_missing_key_leave_no_partial_records(client: TestClient) -> None:
    broker = service(client)
    info = client.get("/api/v1/brokers/setup")
    assert info.json()["storage_available"] is True
    assert info.json()["storage_message"] is None
    broker.secrets = EncryptedSecretStore(Settings())
    info = client.get("/api/v1/brokers/setup")
    assert info.status_code == 200
    assert info.json()["storage_available"] is False
    assert info.json()["storage_message"] == (
        "Credential encryption key is not configured. "
        "Set TWF_CREDENTIAL_MASTER_KEY and restart TWF."
    )
    result = client.post("/api/v1/brokers/accounts", json=CREDENTIALS, headers=HEADERS)
    assert result.status_code == 503
    with broker.factory() as db:
        assert list(db.scalars(select(BrokerAccount))) == []
        assert list(db.scalars(select(BrokerSecret))) == []


@pytest.mark.parametrize("damage", ["ciphertext", "key", "algorithm"])
def test_corrupt_credentials_block_connect_without_attempt(client: TestClient, damage: str) -> None:
    account_id = configure(client)
    broker = service(client)
    with broker.factory() as db:
        secret = db.scalar(select(BrokerSecret))
        assert secret
        if damage == "ciphertext":
            secret.ciphertext = "corrupt-test-token"
        elif damage == "algorithm":
            secret.algorithm = "unsupported"
        else:
            broker.secrets = EncryptedSecretStore(
                Settings(credential_master_key=SecretStr(Fernet.generate_key().decode()))
            )
        db.commit()
    result = client.post(f"/api/v1/brokers/accounts/{account_id}/connect", headers=HEADERS)
    assert result.status_code == 503
    assert result.json()["error"]["code"] == "SECRET_STORE_UNAVAILABLE"
    with broker.factory() as db:
        assert list(db.scalars(select(BrokerAttempt))) == []
        row = db.get(BrokerAccount, UUID(account_id))
        assert row and row.state == "configured" and row.generation == 0


def test_replace_persists_only_ciphertext_and_safe_logs(client: TestClient) -> None:
    app = cast(FastAPI, client.app)
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JsonFormatter(app.state.settings))
    app.state.logger.handlers = [handler]
    broker = service(client)
    account_id = bound(client)
    with broker.factory() as db:
        original = db.scalar(select(BrokerSecret))
        assert original
        old_token, created, updated = original.ciphertext, original.created_at, original.updated_at
        assert broker.secrets.open(old_token).access_token is not None
    result = client.post(
        "/api/v1/brokers/accounts",
        json={**CREDENTIALS, "api_secret": "replacementsecret123", "account_id": account_id},
        headers=HEADERS,
    )
    assert result.status_code == 200
    with broker.factory() as db:
        rows = list(db.scalars(select(BrokerSecret)))
        assert len(rows) == 1
        saved = rows[0]
        assert saved.ciphertext != old_token and saved.algorithm == "fernet-v1"
        assert saved.created_at == created and saved.updated_at > updated
        decoded = broker.secrets.open(saved.ciphertext, saved.algorithm)
        assert decoded.api_secret.get_secret_value() == "replacementsecret123"
        assert decoded.access_token is None
        assert saved.updated_at.replace(tzinfo=UTC).year == datetime.now(UTC).year
        # Include all durable tables, including settings audit/change records.
        persisted = repr([list(db.execute(select(table))) for table in Base.metadata.sorted_tables])
    broker.secrets = EncryptedSecretStore(Settings())
    rejected = client.post(f"/api/v1/brokers/accounts/{account_id}/connect", headers=HEADERS)
    assert rejected.status_code == 503
    events = [json.loads(line) for line in output.getvalue().splitlines()]
    assert any(event["event"] == "broker_request_rejected" for event in events)
    for marker in ("testsecret123", "replacementsecret123", "testtoken123"):
        assert marker not in result.text + rejected.text + output.getvalue() + persisted


def test_metadata_migration_preserves_existing_credentials(client: TestClient) -> None:
    account_id = bound(client)
    broker = service(client)
    with broker.factory() as db:
        secret = db.scalar(select(BrokerSecret))
        assert secret
        token, secret_id = secret.ciphertext, secret.id
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.downgrade(config, "0004_broker_v1")
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    command.check(config)
    with broker.factory() as db:
        account = db.get(BrokerAccount, UUID(account_id))
        secret = db.get(BrokerSecret, secret_id)
        assert account and account.secret_id == secret_id and account.identity == "AB1234"
        assert secret and secret.ciphertext == token and secret.algorithm == "fernet-v1"
        assert secret.created_at.year == datetime.now(UTC).year
        assert broker.secrets.open(secret.ciphertext).access_token is not None
    assert client.get(f"/api/v1/brokers/accounts/{account_id}/holdings").status_code == 200

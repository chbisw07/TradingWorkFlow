from collections.abc import Iterator
from pathlib import Path
from typing import cast
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from twf.auth import create_user
from twf.config.settings import Settings
from twf.infrastructure.database import (
    create_database_engine,
    create_session_factory,
    session_scope,
)
from twf.infrastructure.preferences import PreferenceChange, UserPreferences
from twf.main import create_app
from twf.preferences import Preferences, SettingsFailure
from twf.settings_contracts import FoundationPolicy, PreferenceValues, SecretReference

ORIGIN = "https://web.example"
HEADERS = {"Origin": ORIGIN}
BASE = "/api/v1/settings"


@pytest.fixture
def client() -> Iterator[TestClient]:
    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")
    engine = create_database_engine(Settings())
    with session_scope(create_session_factory(engine)) as session:
        for name in ("alice", "other"):
            create_user(session, name, name, "test-only-settings-password")
        session.commit()
    with TestClient(
        create_app(Settings(cors_origins=(ORIGIN,)), engine_factory=lambda _: engine)
    ) as c:
        yield c


def login(client: TestClient, name: str = "alice") -> UUID:
    r = client.post(
        "/api/v1/auth/login",
        headers=HEADERS,
        json={"username": name, "password": "test-only-settings-password"},
    )
    assert r.status_code == 200
    return UUID(r.json()["id"])


def test_defaults_persistence_reset_and_audit(client: TestClient) -> None:
    user_id = login(client)
    initial = client.get(BASE + "/values")
    assert initial.headers["cache-control"] == "no-store"
    assert initial.json()["revision"] == 0
    assert initial.json()["sources"] == {"density": "PLATFORM", "default_horizon": "PLATFORM"}
    definitions = client.get(BASE + "/definitions").json()
    assert len(definitions) == 2 and all(d["allowed_scopes"] == ["USER"] for d in definitions)
    response = client.put(
        BASE + "/values",
        headers={**HEADERS, "X-Request-ID": "settings-change"},
        json={"revision": 0, "values": {"density": "compact"}},
    )
    assert response.status_code == 200
    assert response.json()["effective"] == {"density": "compact", "default_horizon": "5d"}
    assert response.json()["sources"]["density"] == "USER"
    assert client.get(BASE + "/values").json() == response.json()
    stale = client.put(BASE + "/values", headers=HEADERS, json={"revision": 0, "values": {}})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "HTTP_409"
    reset = client.post(BASE + "/reset", headers=HEADERS, json={"revision": 1})
    assert reset.status_code == 200 and reset.json()["overrides"] == {}
    with session_scope(cast(FastAPI, client.app).state.session_factory) as session:
        events = list(
            session.scalars(
                select(PreferenceChange)
                .where(PreferenceChange.user_id == user_id)
                .order_by(PreferenceChange.revision)
            )
        )
        assert [e.action for e in events] == ["APPLY", "RESET"]
        assert events[0].request_id == "settings-change"


@pytest.mark.parametrize(
    "payload",
    [
        {"revision": 0, "values": {"api_key": "do-not-leak"}},
        {"revision": 0, "values": {"density": True}},
        {"revision": 0, "values": {"density": "giant"}},
        {"revision": 0, "values": {"density": None}},
        {"revision": 0, "scope": "ACCOUNT", "values": {}},
        {"revision": True, "values": {}},
        {"revision": -1, "values": {}},
        {"revision": 0, "user_id": "someone-else", "values": {}},
    ],
)
def test_invalid_settings_rejected(client: TestClient, payload: dict[str, object]) -> None:
    login(client)
    response = client.put(BASE + "/values", headers=HEADERS, json=payload)
    assert response.status_code == 422
    assert "do-not-leak" not in response.text
    assert client.get(BASE + "/values").json()["revision"] == 0


def test_auth_csrf_and_horizontal_isolation(client: TestClient) -> None:
    assert client.get(BASE + "/values").status_code == 401
    assert client.get(BASE + "/definitions").status_code == 401
    assert (
        client.post(
            BASE + "/profiles", headers=HEADERS, json={"name": "Test", "values": {}}
        ).status_code
        == 401
    )
    login(client)
    assert client.put(BASE + "/values", json={"revision": 0, "values": {}}).status_code == 403
    assert (
        client.post(
            BASE + "/reset", headers={"Origin": "https://evil.example"}, json={"revision": 0}
        ).status_code
        == 403
    )
    profile = client.post(
        BASE + "/profiles",
        headers=HEADERS,
        json={"name": "Personal", "values": {"density": "compact"}},
    ).json()
    client.put(
        BASE + "/values", headers=HEADERS, json={"revision": 0, "values": {"density": "compact"}}
    )
    login(client, "other")
    assert client.get(BASE + "/values").json()["effective"]["density"] == "comfortable"
    assert client.get(BASE + "/profiles").json() == []
    assert (
        client.put(
            BASE + "/profiles/" + profile["id"],
            headers=HEADERS,
            json={"name": "Stolen", "revision": 1, "values": {}},
        ).status_code
        == 404
    )
    assert (
        client.post(
            BASE + "/profiles/" + profile["id"] + "/apply",
            headers=HEADERS,
            json={"revision": 0, "profile_revision": 1},
        ).status_code
        == 404
    )


def test_profile_revision_apply_reset_and_deactivation(client: TestClient) -> None:
    login(client)
    p = client.post(
        BASE + "/profiles",
        headers=HEADERS,
        json={"name": "Desk", "values": {"density": "compact", "default_horizon": "15d"}},
    )
    assert p.status_code == 201
    path = BASE + "/profiles/" + p.json()["id"]
    assert client.get(BASE + "/values").json()["revision"] == 0
    assert (
        client.post(
            path + "/apply", headers=HEADERS, json={"revision": 0, "profile_revision": 1}
        ).status_code
        == 200
    )
    edit = {"name": "Desk", "values": {}, "revision": 1}
    assert client.put(path, headers=HEADERS, json=edit).status_code == 200
    assert client.put(path, headers=HEADERS, json=edit).status_code == 409
    # Editing an applied profile preserves its applied snapshot.
    current = client.get(BASE + "/values").json()
    assert current["effective"]["density"] == "compact"
    assert current["applied_profile_revision"] == 1
    assert (
        client.post(
            path + "/apply", headers=HEADERS, json={"revision": 1, "profile_revision": 1}
        ).status_code
        == 409
    )
    assert (
        client.post(
            path + "/apply", headers=HEADERS, json={"revision": 0, "profile_revision": 2}
        ).status_code
        == 409
    )
    response = client.post(
        path + "/apply", headers=HEADERS, json={"revision": 1, "profile_revision": 2}
    )
    assert response.status_code == 200 and response.json()["effective"]["density"] == "comfortable"
    detached = client.post(BASE + "/deactivate", headers=HEADERS, json={"revision": 2})
    assert detached.status_code == 200 and detached.json()["active_profile_id"] is None


def test_failed_commit_rolls_back_values_and_audit(client: TestClient) -> None:
    user = login(client)
    with patch.object(Session, "commit", side_effect=RuntimeError("private-secret")):
        response = client.put(
            BASE + "/values",
            headers=HEADERS,
            json={"revision": 0, "values": {"density": "compact"}},
        )
    assert response.status_code == 500 and "private-secret" not in response.text
    assert client.get(BASE + "/values").json()["revision"] == 0
    with session_scope(cast(FastAPI, client.app).state.session_factory) as session:
        assert session.scalar(select(func.count()).select_from(PreferenceChange)) == 0
        assert session.get(UserPreferences, user) is None


def test_policy_and_secret_contract(client: TestClient) -> None:
    user = login(client)
    saved = client.put(
        BASE + "/values", headers=HEADERS, json={"revision": 0, "values": {"density": "compact"}}
    )
    assert saved.status_code == 200
    policy = FoundationPolicy()
    assert policy.allows(user, "foundation.appearance")
    assert not policy.allows(user, "llm.openai")
    with pytest.raises(ValidationError):
        SecretReference.model_validate(
            {
                "reference_id": uuid4(),
                "owner_id": user,
                "ownership": "USER_MANAGED",
                "secret": "never-store-this",
            }
        )

    class Denied:
        def allows(self, user_id: UUID, capability: str) -> bool:
            return False

    with session_scope(cast(FastAPI, client.app).state.session_factory) as session:
        use = Preferences(session, user, Denied())
        with pytest.raises(SettingsFailure) as error:
            use.write(1, PreferenceValues(density="comfortable"))
        assert error.value.status == 403
    assert client.get(BASE + "/values").json() == saved.json()


def test_concurrent_writes_have_one_winner(client: TestClient) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    user = login(client)
    factory = cast(FastAPI, client.app).state.session_factory
    for revision in (0, 1):
        barrier = Barrier(2)

        def write(density: str, revision: int = revision, barrier: Barrier = barrier) -> int:
            with session_scope(factory) as session:
                use = Preferences(session, user, FoundationPolicy())
                barrier.wait(timeout=5)
                try:
                    use.write(revision, PreferenceValues.model_validate({"density": density}))
                    return 200
                except SettingsFailure as error:
                    return error.status

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(write, ["compact", "comfortable"]))
        assert sorted(outcomes) == [200, 409]
        assert client.get(BASE + "/values").json()["revision"] == revision + 1

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--db-backend", choices=("postgres", "sqlite"), default="postgres")


@pytest.fixture(autouse=True)
def isolated_database_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, request: pytest.FixtureRequest
) -> Iterator[None]:
    """Never inherit deployment credentials; each PG test owns a disposable schema."""
    test_url = os.environ.get("TWF_TEST_DATABASE_URL")
    for key in os.environ:
        if key.startswith("TWF_"):
            monkeypatch.delenv(key)
    monkeypatch.chdir(tmp_path)
    if request.config.getoption("--db-backend") == "sqlite":
        monkeypatch.setenv("TWF_DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'isolated.db'}")
        yield
        return
    if not test_url:
        pytest.fail(
            "PostgreSQL tests require tools/test-postgres.sh; fallback: --db-backend=sqlite"
        )
    url = make_url(test_url)
    if url.get_backend_name() != "postgresql" or not (url.database or "").startswith("twf_test_"):
        pytest.fail("TWF_TEST_DATABASE_URL must name a disposable twf_test_* PostgreSQL database")
    schema = "twf_test_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT", hide_parameters=True)
    with admin.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    isolated = url.update_query_dict({"options": f"-csearch_path={schema}"})
    monkeypatch.setenv("TWF_DATABASE_URL", isolated.render_as_string(hide_password=False))
    try:
        yield
    finally:
        with admin.connect() as connection:
            connection.execute(text("SET lock_timeout = '5s'"))
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def migrated_database(isolated_database_environment: None) -> None:
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config(str(Path(__file__).parents[1] / "alembic.ini")), "head")

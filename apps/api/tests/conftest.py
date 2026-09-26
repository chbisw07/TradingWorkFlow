import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_database_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No test can inherit a deployment URL or developer dotenv configuration."""
    for key in os.environ:
        if key.startswith("TWF_"):
            monkeypatch.delenv(key)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TWF_DATABASE_URL", f"sqlite+pysqlite:///{tmp_path / 'isolated.db'}")


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--broker-postgres-url",
        default=None,
        help="Explicit disposable PostgreSQL URL for BW-2.1 tests (each test uses a new schema)",
    )

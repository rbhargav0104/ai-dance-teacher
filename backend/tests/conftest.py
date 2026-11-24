from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parent.parent

pytest_plugins = ["tests.media_factory"]


def _clear_caches() -> None:
    from app.config import get_settings
    from app.db.session import get_engine, get_sessionmaker
    from app.storage import get_storage

    for fn in (get_settings, get_engine, get_sessionmaker, get_storage):
        fn.cache_clear()


def migrate(url: str) -> None:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "models" / "missing.task"))
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough-123456")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _clear_caches()
    yield tmp_path
    _clear_caches()


@pytest.fixture
def migrated(env: Path) -> Path:
    from app.config import get_settings

    migrate(get_settings().resolved_database_url)
    return env


@pytest.fixture
def client(migrated: Path) -> Iterator[TestClient]:
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    token = client.post("/api/session").json()["token"]
    return {"Authorization": f"Bearer {token}"}

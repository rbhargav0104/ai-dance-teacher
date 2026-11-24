from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_cors_origins_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example")
    assert Settings().cors_origins == ["https://a.example", "https://b.example"]


def test_default_sqlite_url_lives_in_data_dir(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert Settings().resolved_database_url == f"sqlite:///{tmp_path.as_posix()}/app.db"


def test_production_rejects_dev_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ValidationError) as err:
        Settings()
    msg = str(err.value)
    for needle in ("https", "PostgreSQL", "AUTH_MODE", "STORAGE_PROVIDER", "SECRET_KEY"):
        assert needle in msg


def test_production_accepts_safe_config(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in {
        "APP_ENV": "production",
        "API_PUBLIC_URL": "https://api.example.com",
        "DATABASE_URL": "postgresql+psycopg://u:p@db/app",
        "AUTH_MODE": "supabase",
        "STORAGE_PROVIDER": "supabase",
        "SECRET_KEY": "x" * 48,
        "CORS_ORIGINS": "https://app.example.com",
    }.items():
        monkeypatch.setenv(k, v)
    assert Settings().production_problems() == []


def test_relative_paths_anchor_to_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import REPO_ROOT

    monkeypatch.setenv("DATA_DIR", "./data")
    monkeypatch.setenv("MODEL_PATH", "models/x.task")
    s = Settings()
    assert s.data_dir == REPO_ROOT / "data"
    assert s.model_path == REPO_ROOT / "models" / "x.task"

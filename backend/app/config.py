"""Typed application settings, loaded from environment variables (see `.env.example`)."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent

DEV_SECRET_PLACEHOLDER = "dev-only-insecure-secret-change-me"  # noqa: S105 - documented dev default


class AppEnv(StrEnum):
    development = "development"
    test = "test"
    production = "production"


class AuthMode(StrEnum):
    local = "local"
    supabase = "supabase"


class StorageProvider(StrEnum):
    local = "local"
    supabase = "supabase"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), str(BACKEND_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: AppEnv = AppEnv.development
    database_url: str = ""
    secret_key: str = DEV_SECRET_PLACEHOLDER
    auth_mode: AuthMode = AuthMode.local
    storage_provider: StorageProvider = StorageProvider.local
    api_public_url: str = "http://localhost:8000"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    data_dir: Path = REPO_ROOT / "data"
    model_path: Path = REPO_ROOT / "models" / "pose_landmarker_full.task"
    model_sha256: str = "4eaa5eb7a98365221087693fcc286334cf0858e2eb6e15b506aa4a7ecdcec4ad"
    analysis_fps: float = 12.0
    max_duration_seconds: float = 120.0
    max_upload_mb: int = 200
    max_projects_per_user: int = 20
    max_sessions_per_project: int = 50
    job_max_attempts: int = 3
    session_ttl_seconds: int = 60 * 60 * 24 * 7

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_bucket: str = "dance-media"

    @model_validator(mode="before")
    @classmethod
    def _split_origins(cls, data: object) -> object:
        if isinstance(data, dict):
            raw = data.get("cors_origins") or data.get("CORS_ORIGINS")
            if isinstance(raw, str):
                key = "cors_origins" if "cors_origins" in data else "CORS_ORIGINS"
                data[key] = [o.strip() for o in raw.split(",") if o.strip()]
        return data

    @field_validator("data_dir", "model_path", mode="after")
    @classmethod
    def _anchor_relative_paths(cls, value: Path) -> Path:
        # Relative paths in .env are relative to the repo root, whatever the cwd.
        return value if value.is_absolute() else (REPO_ROOT / value).resolve()

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'app.db').as_posix()}"

    @property
    def objects_dir(self) -> Path:
        return self.data_dir / "objects"

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def production_problems(self) -> list[str]:
        """Return reasons this config is unsafe for production (empty list = OK)."""
        problems: list[str] = []
        if not self.api_public_url.startswith("https://"):
            problems.append("API_PUBLIC_URL must use https")
        if not self.resolved_database_url.startswith(("postgresql", "postgres")):
            problems.append("DATABASE_URL must point at PostgreSQL")
        if self.auth_mode is not AuthMode.supabase:
            problems.append("AUTH_MODE must be supabase (local sessions are dev-only)")
        if self.storage_provider is StorageProvider.local:
            problems.append("STORAGE_PROVIDER must be a private object store, not local disk")
        if self.secret_key == DEV_SECRET_PLACEHOLDER or len(self.secret_key) < 32:
            problems.append("SECRET_KEY must be a strong random value (>= 32 chars)")
        if not self.cors_origins or any(o == "*" for o in self.cors_origins):
            problems.append("CORS_ORIGINS must be an explicit allowlist")
        return problems

    @model_validator(mode="after")
    def _validate_production(self) -> Settings:
        if self.app_env is AppEnv.production:
            problems = self.production_problems()
            if problems:
                raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

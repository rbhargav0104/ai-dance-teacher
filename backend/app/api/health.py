"""GET /api/health — capability state that drives the READY / LIMITED / OFFLINE UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from app import __version__
from app.config import Settings, get_settings
from app.db.session import database_ok, schema_revision
from app.jobs.worker import worker_available
from app.media.probe import ACCEPTED_EXTENSIONS, ffprobe_available
from app.media.transcode import ffmpeg_available
from app.pose.runtime import probe, selftest
from app.storage import get_storage

router = APIRouter(tags=["health"])

# The real reference pipeline (Outcome 2: transcode → MediaPipe → features → quality gates).
ANALYSIS_PIPELINE_IMPLEMENTED = True


class ComponentState(BaseModel):
    ok: bool
    detail: str | None = None


class AnalysisState(BaseModel):
    available: bool
    pipeline_implemented: bool
    runtime_installed: bool
    runtime_version: str | None
    model_present: bool
    model_verified: bool
    model_version: str
    runtime_selftest: bool
    worker_running: bool
    reason: str | None


class Limits(BaseModel):
    max_upload_mb: int
    max_duration_seconds: float
    accepted_extensions: list[str]


class HealthResponse(BaseModel):
    status: Literal["ready", "limited", "offline"]
    message: str
    version: str
    app_env: str
    auth_mode: str
    storage_provider: str
    database: ComponentState
    storage: ComponentState
    media_inspection: ComponentState
    uploads_available: bool
    analysis: AnalysisState
    limits: Limits


@dataclass(frozen=True)
class Capability:
    available: bool
    reason: str | None
    runtime_ok: bool
    worker_ok: bool


def analysis_capability(settings: Settings) -> Capability:
    """Single source of truth for 'can this server analyse movement right now?'."""
    pose = probe(settings.model_path, settings.model_sha256)
    reason = pose.problem
    runtime_ok = False
    if reason is None:
        runtime_ok, reason = selftest(settings.model_path, settings.model_sha256)
    worker_ok = worker_available(settings)
    if reason is None and not worker_ok:
        reason = "The analysis worker isn't running."
    convert_ok = ffprobe_available() and ffmpeg_available()
    if reason is None and not convert_ok:
        reason = "Video conversion tools are not installed."
    available = (
        pose.available and runtime_ok and worker_ok and convert_ok and ANALYSIS_PIPELINE_IMPLEMENTED
    )
    return Capability(available, None if available else reason, runtime_ok, worker_ok)


def _storage_ok() -> bool:
    try:
        return get_storage().healthy()
    except Exception:
        return False


@router.get("/api/health", response_model=HealthResponse)
def health(
    settings: Annotated[Settings, Depends(get_settings)], response: Response
) -> HealthResponse:
    response.headers["Cache-Control"] = "no-store"
    db_ok = database_ok()
    revision = schema_revision() if db_ok else None
    storage_ok = _storage_ok()
    pose = probe(settings.model_path, settings.model_sha256)
    inspect_ok = ffprobe_available()

    cap = analysis_capability(settings)
    analysis_available = cap.available
    reason = cap.reason

    persistence_ok = db_ok and revision is not None and storage_ok
    status: Literal["ready", "limited", "offline"]
    if not persistence_ok:
        status = "offline"
        if not db_ok:
            message = "The studio database is unreachable."
        elif revision is None:
            message = "The studio database has not been migrated."
        else:
            message = "Private video storage is unavailable."
    elif analysis_available:
        status, message = "ready", "Studio ready."
    else:
        status, message = "limited", reason or "Movement analysis is unavailable."

    return HealthResponse(
        status=status,
        message=message,
        version=__version__,
        app_env=settings.app_env.value,
        auth_mode=settings.auth_mode.value,
        storage_provider=settings.storage_provider.value,
        database=ComponentState(ok=db_ok and revision is not None, detail=revision),
        storage=ComponentState(ok=storage_ok),
        media_inspection=ComponentState(
            ok=inspect_ok, detail=None if inspect_ok else "FFprobe is not installed."
        ),
        uploads_available=persistence_ok and inspect_ok,
        analysis=AnalysisState(
            available=analysis_available,
            pipeline_implemented=ANALYSIS_PIPELINE_IMPLEMENTED,
            runtime_installed=pose.runtime_installed,
            runtime_version=pose.runtime_version,
            model_present=pose.model_present,
            model_verified=pose.model_verified,
            model_version=pose.model_version,
            runtime_selftest=cap.runtime_ok,
            worker_running=cap.worker_ok,
            reason=None if analysis_available else reason,
        ),
        limits=Limits(
            max_upload_mb=settings.max_upload_mb,
            max_duration_seconds=settings.max_duration_seconds,
            accepted_extensions=list(ACCEPTED_EXTENSIONS),
        ),
    )


@router.get("/api/health/live", include_in_schema=False)
def live() -> dict[str, str]:
    """Liveness for platform health checks: the process is up and serving."""
    return {"status": "alive"}

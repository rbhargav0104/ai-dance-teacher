"""Reference intake and project endpoints (spec sections 11, 23, 27)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.auth.deps import CurrentUser
from app.config import Settings, get_settings
from app.db.session import get_db
from app.errors import ApiError
from app.media.probe import MediaRejected, ffprobe_available, probe_file
from app.media.signing import MEDIA_TOKEN_TTL_SECONDS, MediaGrant, sign_media
from app.media.upload import MULTIPART_OVERHEAD_BYTES, receive_upload
from app.models import AnalysisJob, DanceProject
from app.pose.runtime import probe as pose_probe
from app.services.intake import (
    IntakeRequest,
    clean_filename,
    delete_project,
    enforce_project_quota,
    find_by_idempotency,
    load_samples,
    persist_reference,
    title_from,
    validate_idempotency_key,
)
from app.storage import get_storage

router = APIRouter(tags=["projects"])

CONTENT_TYPES = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm"}


class ReferenceOut(BaseModel):
    original_filename: str | None
    duration: float
    width: int
    height: int
    source_fps: float
    size_bytes: int | None
    codec: str | None
    has_audio: bool | None
    warnings: list[str]


class JobOut(BaseModel):
    id: str
    kind: str
    status: str
    stage: str | None
    progress: float
    message: str | None
    error_code: str | None
    updated_at: datetime


class ProjectOut(BaseModel):
    id: str
    title: str
    status: str
    progress: float
    is_demo: bool
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    reference: ReferenceOut | None
    latest_job: JobOut | None


class ProjectList(BaseModel):
    projects: list[ProjectOut]
    limit: int


class SampleOut(BaseModel):
    id: str
    title: str
    license: str
    attribution: str
    framing: str


class SampleRequest(BaseModel):
    sample_id: str = Field(min_length=1, max_length=64)


class MediaUrl(BaseModel):
    url: str
    expires_in: int
    content_type: str
    kind: Literal["source"]


def _latest_job(db: Session, project_id: str) -> AnalysisJob | None:
    return db.scalars(
        select(AnalysisJob)
        .where(AnalysisJob.project_id == project_id)
        .order_by(AnalysisJob.created_at.desc(), AnalysisJob.id.desc())
    ).first()


def to_out(db: Session, project: DanceProject) -> ProjectOut:
    ref = project.reference_video
    job = _latest_job(db, project.id)
    return ProjectOut(
        id=project.id,
        title=project.title,
        status=project.status,
        progress=project.progress,
        is_demo=project.is_demo,
        error_code=project.error_code,
        error_message=project.error_message,
        created_at=project.created_at,
        updated_at=project.updated_at,
        reference=ReferenceOut(
            original_filename=ref.original_filename,
            duration=ref.duration,
            width=ref.width,
            height=ref.height,
            source_fps=ref.source_fps,
            size_bytes=ref.source_size_bytes,
            codec=ref.source_codec,
            has_audio=ref.has_audio,
            warnings=list(ref.warnings or []),
        )
        if ref
        else None,
        latest_job=JobOut(
            id=job.id,
            kind=job.kind,
            status=job.status,
            stage=job.stage,
            progress=job.progress,
            message=job.message,
            error_code=job.error_code,
            updated_at=job.updated_at,
        )
        if job
        else None,
    )


def owned_project(db: Session, user_id: str, project_id: str) -> DanceProject:
    project = db.get(DanceProject, project_id) if len(project_id) <= 64 else None
    # Same 404 for "missing" and "someone else's": never confirm other users' IDs exist.
    if project is None or project.owner_id != user_id:
        raise ApiError(404, "project_not_found", "That dance doesn't exist or was deleted.")
    return project


def _reject(exc: MediaRejected) -> ApiError:
    return ApiError(exc.status_code, exc.code, exc.message)


@router.post("/api/projects", response_model=ProjectOut, status_code=201)
async def create_project(
    request: Request,
    response: Response,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    content_length: Annotated[int | None, Header()] = None,
) -> ProjectOut:
    """Streaming multipart upload (`file`, optional `title`). Rejections leave no residue."""
    key = validate_idempotency_key(idempotency_key)
    existing = await run_in_threadpool(find_by_idempotency, db, user.id, key)
    if existing is not None:
        response.status_code = 200
        return await run_in_threadpool(to_out, db, existing)
    await run_in_threadpool(enforce_project_quota, db, user.id, settings.max_projects_per_user)
    if not ffprobe_available():
        raise ApiError(503, "inspection_unavailable", "Video inspection is unavailable right now.")
    if content_length is not None and content_length > settings.max_upload_bytes + (
        MULTIPART_OVERHEAD_BYTES
    ):
        raise ApiError(
            413, "file_too_large", f"Videos must be {settings.max_upload_mb} MB or smaller."
        )

    try:
        received = await receive_upload(
            request.stream(),
            request.headers.get("content-type"),
            tmp_dir=settings.tmp_dir,
            max_bytes=settings.max_upload_bytes,
        )
    except MediaRejected as exc:
        raise _reject(exc) from exc

    try:
        probe = await run_in_threadpool(
            probe_file,
            received.path,
            max_duration=settings.max_duration_seconds,
            timeout_s=settings.ffprobe_timeout_seconds,
        )
        filename = clean_filename(received.filename)
        req = IntakeRequest(
            owner=user,
            source_path=received.path,
            extension=received.extension,
            filename=filename,
            title=title_from(received.fields.get("title"), filename),
            probe=probe,
            size_bytes=received.size,
            idempotency_key=key,
        )
        project = await run_in_threadpool(persist_reference, db, get_storage(), req)
        return await run_in_threadpool(to_out, db, project)
    except MediaRejected as exc:
        raise _reject(exc) from exc
    finally:
        received.path.unlink(missing_ok=True)


@router.get("/api/samples", response_model=list[SampleOut])
def list_samples(settings: Annotated[Settings, Depends(get_settings)]) -> list[SampleOut]:
    return [
        SampleOut(
            id=s.id, title=s.title, license=s.license, attribution=s.attribution, framing=s.framing
        )
        for s in load_samples(settings.fixtures_dir)
    ]


@router.post("/api/projects/sample", response_model=ProjectOut, status_code=201)
def create_sample_project(
    body: SampleRequest,
    response: Response,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProjectOut:
    """Add a bundled, licensed sample clip through the same validation + storage path."""
    sample = next((s for s in load_samples(settings.fixtures_dir) if s.id == body.sample_id), None)
    if sample is None:
        raise ApiError(404, "sample_not_found", "That sample isn't available.")
    key = f"sample:{sample.id}"
    existing = find_by_idempotency(db, user.id, key)
    if existing is not None:
        response.status_code = 200
        return to_out(db, existing)
    enforce_project_quota(db, user.id, settings.max_projects_per_user)
    try:
        probe = probe_file(
            sample.path,
            max_duration=settings.max_duration_seconds,
            timeout_s=settings.ffprobe_timeout_seconds,
        )
        project = persist_reference(
            db,
            get_storage(),
            IntakeRequest(
                owner=user,
                source_path=sample.path,
                extension=sample.path.suffix.lower(),
                filename=sample.path.name,
                title=sample.title,
                probe=probe,
                size_bytes=sample.path.stat().st_size,
                idempotency_key=key,
                is_demo=True,
            ),
        )
    except MediaRejected as exc:
        raise _reject(exc) from exc
    return to_out(db, project)


@router.get("/api/projects", response_model=ProjectList)
def list_projects(
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProjectList:
    rows = db.scalars(
        select(DanceProject)
        .where(DanceProject.owner_id == user.id)
        .order_by(DanceProject.created_at.desc(), DanceProject.id.desc())
    ).all()
    return ProjectList(projects=[to_out(db, p) for p in rows], limit=settings.max_projects_per_user)


@router.get("/api/projects/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: str, user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> ProjectOut:
    return to_out(db, owned_project(db, user.id, project_id))


@router.delete("/api/projects/{project_id}", status_code=204)
def remove_project(
    project_id: str, user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> Response:
    project = owned_project(db, user.id, project_id)
    delete_project(db, get_storage(), project)
    return Response(status_code=204)


@router.get("/api/projects/{project_id}/media/source", response_model=MediaUrl)
def source_media_url(
    project_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
) -> MediaUrl:
    project = owned_project(db, user.id, project_id)
    ref = project.reference_video
    if ref is None:
        raise ApiError(404, "media_not_found", "This dance has no video.")
    ext = "." + ref.source_object_key.rsplit(".", 1)[-1]
    ctype = CONTENT_TYPES.get(ext, "application/octet-stream")
    token = sign_media(settings, MediaGrant(ref.source_object_key, user.id, ctype))
    response.headers["Cache-Control"] = "no-store"
    return MediaUrl(
        url=f"/api/media/{token}",
        expires_in=MEDIA_TOKEN_TTL_SECONDS,
        content_type=ctype,
        kind="source",
    )


@router.post("/api/projects/{project_id}/analysis", status_code=202)
def start_analysis(
    project_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Backend-enforced LIMITED state: refuse with 503 until real inference is available."""
    owned_project(db, user.id, project_id)
    from app.api.health import ANALYSIS_PIPELINE_IMPLEMENTED

    status = pose_probe(settings.model_path, settings.model_sha256)
    if not (status.available and ANALYSIS_PIPELINE_IMPLEMENTED):
        raise ApiError(
            503,
            "analysis_unavailable",
            status.problem or "Movement analysis isn't available on this server yet.",
        )
    raise ApiError(503, "analysis_unavailable", "Movement analysis is not wired up yet.")

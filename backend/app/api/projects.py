"""Reference intake and project endpoints (spec sections 11, 23, 27)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.health import analysis_capability
from app.auth.deps import CurrentUser
from app.config import Settings, get_settings
from app.db.session import get_db
from app.errors import ApiError
from app.jobs.queue import enqueue_reference_analysis
from app.media.probe import MediaRejected, ffprobe_available, probe_file
from app.media.signing import MEDIA_TOKEN_TTL_SECONDS, MediaGrant, sign_media
from app.media.upload import MULTIPART_OVERHEAD_BYTES, receive_upload
from app.models import AnalysisJob, DanceProject, ReferencePoseFrame
from app.pose import landmarks as LM
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

CONTENT_TYPES = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".jpg": "image/jpeg",
}


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
    # Filled by the analysis job (null until then).
    canonical_width: int | None = None
    canonical_height: int | None = None
    canonical_fps: float | None = None
    canonical_duration: float | None = None
    has_canonical: bool = False
    has_poster: bool = False
    analysis_fps: float | None = None
    pose_coverage: float | None = None
    quality: dict[str, Any] | None = None
    pipeline_version: str | None = None
    model_version: str | None = None
    analyzed_at: datetime | None = None


class JobOut(BaseModel):
    id: str
    kind: str
    status: str
    stage: str | None
    progress: float
    message: str | None
    error_code: str | None
    attempts: int = 0
    retryable: bool = False
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


MediaKind = Literal["source", "canonical", "poster"]


class MediaUrl(BaseModel):
    url: str
    expires_in: int
    content_type: str
    kind: MediaKind


def _latest_job(db: Session, project_id: str) -> AnalysisJob | None:
    return db.scalars(
        select(AnalysisJob)
        .where(AnalysisJob.project_id == project_id, AnalysisJob.practice_session_id.is_(None))
        .order_by(AnalysisJob.created_at.desc(), AnalysisJob.id.desc())
    ).first()


def job_out(job: AnalysisJob) -> JobOut:
    return JobOut(
        id=job.id,
        kind=job.kind,
        status=job.status,
        stage=job.stage,
        progress=job.progress,
        message=job.message,
        error_code=job.error_code,
        attempts=job.attempts,
        retryable=job.retryable,
        updated_at=job.updated_at,
    )


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
            canonical_width=ref.canonical_width,
            canonical_height=ref.canonical_height,
            canonical_fps=ref.canonical_fps,
            canonical_duration=ref.canonical_duration,
            has_canonical=ref.canonical_object_key is not None,
            has_poster=ref.thumbnail_key is not None,
            analysis_fps=ref.analysis_fps,
            pose_coverage=ref.pose_coverage,
            quality=ref.quality,
            pipeline_version=ref.pipeline_version,
            model_version=ref.model_version,
            analyzed_at=ref.analyzed_at,
        )
        if ref
        else None,
        latest_job=job_out(job) if job else None,
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
    # Demo journey: a sample starts real analysis straight away when the server can run it
    # (same queue, same pipeline as any upload). In LIMITED mode it simply stays uploaded.
    if analysis_capability(settings).available:
        enqueue_reference_analysis(db, project)
        db.refresh(project)
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


@router.get("/api/projects/{project_id}/media/{kind}", response_model=MediaUrl)
def project_media_url(
    project_id: str,
    kind: MediaKind,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
) -> MediaUrl:
    """Short-lived signed URL for the private original, canonical copy or poster frame."""
    project = owned_project(db, user.id, project_id)
    ref = project.reference_video
    key = None
    if ref is not None:
        key = {
            "source": ref.source_object_key,
            "canonical": ref.canonical_object_key,
            "poster": ref.thumbnail_key,
        }[kind]
    if ref is None or key is None:
        raise ApiError(404, "media_not_found", "This video isn't available yet.")
    ext = "." + key.rsplit(".", 1)[-1]
    ctype = CONTENT_TYPES.get(ext, "application/octet-stream")
    token = sign_media(settings, MediaGrant(key, user.id, ctype))
    response.headers["Cache-Control"] = "no-store"
    return MediaUrl(
        url=f"/api/media/{token}",
        expires_in=MEDIA_TOKEN_TTL_SECONDS,
        content_type=ctype,
        kind=kind,
    )


class AnalysisRequest(BaseModel):
    rerun: bool = False


@router.post("/api/projects/{project_id}/analysis", response_model=JobOut, status_code=202)
def start_analysis(
    project_id: str,
    user: CurrentUser,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    body: AnalysisRequest | None = None,
) -> JobOut:
    """Queue reference analysis. Idempotent: an active job is returned instead of a new one;
    an analysed dance returns its last job unless `rerun` is set. Backend-enforced LIMITED:
    503 when real inference isn't available."""
    project = owned_project(db, user.id, project_id)
    cap = analysis_capability(settings)
    if not cap.available:
        raise ApiError(
            503,
            "analysis_unavailable",
            cap.reason or "Movement analysis isn't available on this server right now.",
        )
    if project.status == "analyzed" and not (body and body.rerun):
        latest = _latest_job(db, project.id)
        if latest is not None:
            response.status_code = 200
            return job_out(latest)
    job, created = enqueue_reference_analysis(db, project)
    if not created:
        response.status_code = 200
    return job_out(job)


class PoseFrameOut(BaseModel):
    t: float
    frame: int
    valid: bool
    confidence: float
    data: dict[str, Any]


class PosesOut(BaseModel):
    project_id: str
    status: str
    pipeline_version: str | None
    model_version: str | None
    analysis_fps: float | None
    width: int | None
    height: int | None
    duration: float | None
    coverage: float | None
    quality: dict[str, Any] | None
    landmark_names: list[str]
    connections: list[tuple[int, int]]
    core_landmarks: list[int]
    major_landmarks: list[int]
    angle_definitions: dict[str, tuple[int, int, int]]
    frames: list[PoseFrameOut]


@router.get("/api/projects/{project_id}/poses", response_model=PosesOut)
def get_poses(
    project_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    response: Response,
) -> PosesOut:
    """Every analysed frame with measured landmarks and features (owner only)."""
    project = owned_project(db, user.id, project_id)
    ref = project.reference_video
    if ref is None or ref.analyzed_at is None:
        raise ApiError(409, "not_analyzed", "This dance hasn't been analysed yet.")
    rows = db.scalars(
        select(ReferencePoseFrame)
        .where(ReferencePoseFrame.reference_video_id == ref.id)
        .order_by(ReferencePoseFrame.frame_number)
    ).all()
    response.headers["Cache-Control"] = "private, no-store"
    return PosesOut(
        project_id=project.id,
        status=project.status,
        pipeline_version=ref.pipeline_version,
        model_version=ref.model_version,
        analysis_fps=ref.analysis_fps,
        width=ref.canonical_width,
        height=ref.canonical_height,
        duration=ref.canonical_duration,
        coverage=ref.pose_coverage,
        quality=ref.quality,
        landmark_names=list(LM.NAMES),
        connections=list(LM.CONNECTIONS),
        core_landmarks=list(LM.CORE),
        major_landmarks=list(LM.MAJOR),
        angle_definitions=dict(LM.ANGLES),
        frames=[
            PoseFrameOut(
                t=r.timestamp,
                frame=r.frame_number,
                valid=r.valid,
                confidence=r.confidence,
                data=r.payload,
            )
            for r in rows
        ],
    )

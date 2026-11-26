"""Practice attempts (spec 16, 23 'Practice', Journey D): learner webcam/upload intake, real
learner pose through the same pipeline, attempt review data. Owner-scoped throughout."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.health import analysis_capability
from app.api.projects import (
    CONTENT_TYPES,
    JobOut,
    MediaKind,
    MediaUrl,
    PoseFrameOut,
    PosesOut,
    job_out,
    owned_project,
)
from app.auth.deps import CurrentUser
from app.config import Settings, get_settings
from app.db.session import get_db
from app.errors import ApiError
from app.jobs.queue import enqueue_practice_analysis, latest_practice_job
from app.media.probe import MediaRejected, ffprobe_available
from app.media.repair import probe_or_repair
from app.media.signing import MEDIA_TOKEN_TTL_SECONDS, MediaGrant, sign_media
from app.media.upload import MULTIPART_OVERHEAD_BYTES, receive_upload
from app.models import DanceSegment, PracticeSession, UserPoseFrame
from app.pose import landmarks as LM  # noqa: N812
from app.services.intake import clean_filename, validate_idempotency_key
from app.services.practice import (
    CAPTURE_SOURCES,
    PracticeIntake,
    delete_practice,
    enforce_quota,
    find_by_idempotency,
    owned_practice,
    persist_practice,
    require_practicable,
    resolve_segment,
    target_duration,
)
from app.storage import get_storage

router = APIRouter(tags=["practice"])


class TargetOut(BaseModel):
    """What the attempt practises, in reference-video time."""

    segment_id: str | None
    title: str
    start: float
    end: float


class PracticeOut(BaseModel):
    id: str
    project_id: str
    status: str
    progress: float
    error_code: str | None
    error_message: str | None
    capture_source: str
    declared_mirrored: bool | None
    target: TargetOut
    original_filename: str | None
    duration: float | None
    width: int | None
    height: int | None
    source_fps: float | None
    size_bytes: int | None
    warnings: list[str]
    canonical_width: int | None
    canonical_height: int | None
    canonical_duration: float | None
    has_canonical: bool
    has_poster: bool
    analysis_fps: float | None
    tracking_coverage: float | None
    quality: dict[str, Any] | None
    pipeline_version: str | None
    model_version: str | None
    analyzed_at: datetime | None
    created_at: datetime
    latest_job: JobOut | None
    # Comparison and scoring arrive in Outcomes 6-7; nothing here is a dance score.
    scored: bool = False


class PracticeList(BaseModel):
    project_id: str
    sessions: list[PracticeOut]
    limit: int


def _target(db: Session, practice: PracticeSession) -> TargetOut:
    seg = db.get(DanceSegment, practice.segment_id) if practice.segment_id else None
    if seg is not None:
        return TargetOut(segment_id=seg.id, title=seg.title, start=seg.start_time, end=seg.end_time)
    project = owned_project(db, practice.owner_id, practice.project_id)
    end = target_duration(project, None) or 0.0
    return TargetOut(segment_id=None, title="Full dance", start=0.0, end=round(end, 3))


def to_out(db: Session, practice: PracticeSession) -> PracticeOut:
    job = latest_practice_job(db, practice.id)
    return PracticeOut(
        id=practice.id,
        project_id=practice.project_id,
        status=practice.status,
        progress=practice.progress,
        error_code=practice.error_code,
        error_message=practice.error_message,
        capture_source=practice.capture_source,
        declared_mirrored=practice.declared_mirrored,
        target=_target(db, practice),
        original_filename=practice.original_filename,
        duration=practice.duration,
        width=practice.width,
        height=practice.height,
        source_fps=practice.source_fps,
        size_bytes=practice.source_size_bytes,
        warnings=list(practice.warnings or []),
        canonical_width=practice.canonical_width,
        canonical_height=practice.canonical_height,
        canonical_duration=practice.canonical_duration,
        has_canonical=practice.canonical_object_key is not None,
        has_poster=practice.thumbnail_key is not None,
        analysis_fps=practice.analysis_fps,
        tracking_coverage=practice.tracking_coverage,
        quality=practice.quality,
        pipeline_version=practice.pipeline_version,
        model_version=practice.model_version,
        analyzed_at=practice.analyzed_at,
        created_at=practice.created_at,
        latest_job=job_out(job) if job else None,
    )


def _bool_field(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


@router.post(
    "/api/projects/{project_id}/practice-sessions", response_model=PracticeOut, status_code=201
)
async def create_practice(
    project_id: str,
    request: Request,
    response: Response,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    content_length: Annotated[int | None, Header()] = None,
) -> PracticeOut:
    """Multipart: `file` (webcam recording or upload), optional `segment_id`,
    `capture_source` (webcam|upload), `mirrored` (the video itself is a mirror image).
    Analysis starts straight away when the server can run it; rejections leave no residue."""
    key = validate_idempotency_key(idempotency_key)
    existing = await run_in_threadpool(find_by_idempotency, db, user.id, key)
    if existing is not None:
        response.status_code = 200
        return await run_in_threadpool(to_out, db, existing)
    project = await run_in_threadpool(owned_project, db, user.id, project_id)
    await run_in_threadpool(require_practicable, project)
    await run_in_threadpool(enforce_quota, db, project.id, settings.max_sessions_per_project)
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
        raise ApiError(exc.status_code, exc.code, exc.message) from exc

    repaired_path = None
    try:
        capture = (received.fields.get("capture_source") or "upload").strip().lower()
        if capture not in CAPTURE_SOURCES:
            raise ApiError(
                422, "invalid_capture_source", "capture_source must be webcam or upload."
            )
        segment = await run_in_threadpool(
            resolve_segment, db, project, (received.fields.get("segment_id") or "").strip() or None
        )
        source_path, probe, repaired_path = await run_in_threadpool(
            probe_or_repair, received.path, received.extension, settings
        )
        intake = PracticeIntake(
            owner=user,
            project=project,
            segment=segment,
            source_path=source_path,
            extension=source_path.suffix.lower() or received.extension,
            filename=clean_filename(received.filename),
            probe=probe,
            capture_source=capture,
            declared_mirrored=_bool_field(received.fields.get("mirrored")),
            idempotency_key=key,
        )
        practice = await run_in_threadpool(persist_practice, db, get_storage(), intake)
    except MediaRejected as exc:
        raise ApiError(exc.status_code, exc.code, exc.message) from exc
    finally:
        received.path.unlink(missing_ok=True)
        if repaired_path is not None:
            repaired_path.unlink(missing_ok=True)

    if await run_in_threadpool(lambda: analysis_capability(settings).available):
        await run_in_threadpool(enqueue_practice_analysis, db, practice)
        await run_in_threadpool(db.refresh, practice)
    return await run_in_threadpool(to_out, db, practice)


@router.get("/api/projects/{project_id}/practice-sessions", response_model=PracticeList)
def list_practice(
    project_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PracticeList:
    project = owned_project(db, user.id, project_id)
    rows = db.scalars(
        select(PracticeSession)
        .where(PracticeSession.project_id == project.id, PracticeSession.owner_id == user.id)
        .order_by(PracticeSession.created_at.desc(), PracticeSession.id.desc())
    ).all()
    return PracticeList(
        project_id=project.id,
        sessions=[to_out(db, p) for p in rows],
        limit=settings.max_sessions_per_project,
    )


@router.get("/api/practice-sessions/{session_id}", response_model=PracticeOut)
def get_practice(
    session_id: str, user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> PracticeOut:
    return to_out(db, owned_practice(db, user.id, session_id))


@router.delete("/api/practice-sessions/{session_id}", status_code=204)
def remove_practice(
    session_id: str, user: CurrentUser, db: Annotated[Session, Depends(get_db)]
) -> Response:
    delete_practice(db, get_storage(), owned_practice(db, user.id, session_id))
    return Response(status_code=204)


class PracticeAnalysisRequest(BaseModel):
    rerun: bool = False


@router.post("/api/practice-sessions/{session_id}/analysis", response_model=JobOut, status_code=202)
def start_practice_analysis(
    session_id: str,
    user: CurrentUser,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    body: PracticeAnalysisRequest | None = None,
) -> JobOut:
    """Idempotent; 503 `analysis_unavailable` in LIMITED mode (never a simulated result)."""
    practice = owned_practice(db, user.id, session_id)
    cap = analysis_capability(settings)
    if not cap.available:
        raise ApiError(
            503,
            "analysis_unavailable",
            cap.reason or "Movement analysis isn't available on this server right now.",
        )
    if practice.status == "analyzed" and not (body and body.rerun):
        latest = latest_practice_job(db, practice.id)
        if latest is not None:
            response.status_code = 200
            return job_out(latest)
    job, created = enqueue_practice_analysis(db, practice)
    if not created:
        response.status_code = 200
    return job_out(job)


@router.get("/api/practice-sessions/{session_id}/poses", response_model=PosesOut)
def get_practice_poses(
    session_id: str,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    response: Response,
) -> PosesOut:
    """The learner's measured landmarks and features, same shape as the reference poses."""
    practice = owned_practice(db, user.id, session_id)
    if practice.analyzed_at is None:
        raise ApiError(409, "not_analyzed", "This attempt hasn't been analysed yet.")
    rows = db.scalars(
        select(UserPoseFrame)
        .where(UserPoseFrame.practice_session_id == practice.id)
        .order_by(UserPoseFrame.frame_number)
    ).all()
    response.headers["Cache-Control"] = "private, no-store"
    return PosesOut(
        project_id=practice.project_id,
        status=practice.status,
        pipeline_version=practice.pipeline_version,
        model_version=practice.model_version,
        analysis_fps=practice.analysis_fps,
        width=practice.canonical_width,
        height=practice.canonical_height,
        duration=practice.canonical_duration,
        coverage=practice.tracking_coverage,
        quality=practice.quality,
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


@router.get("/api/practice-sessions/{session_id}/media/{kind}", response_model=MediaUrl)
def practice_media_url(
    session_id: str,
    kind: MediaKind,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
) -> MediaUrl:
    practice = owned_practice(db, user.id, session_id)
    key = {
        "source": practice.source_object_key,
        "canonical": practice.canonical_object_key,
        "poster": practice.thumbnail_key,
    }[kind]
    if key is None:
        raise ApiError(404, "media_not_found", "This video isn't available yet.")
    ext = "." + key.rsplit(".", 1)[-1]
    ctype = CONTENT_TYPES.get(ext, "application/octet-stream")
    token = sign_media(settings, MediaGrant(key, user.id, ctype))
    response.headers["Cache-Control"] = "no-store"
    return MediaUrl(
        url=f"/api/media/{token}", expires_in=MEDIA_TOKEN_TTL_SECONDS, content_type=ctype, kind=kind
    )

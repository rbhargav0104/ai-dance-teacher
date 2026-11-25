"""Durable job records: idempotent creation, atomic claiming, heartbeats, recovery (spec 24).

Claiming is a conditional UPDATE (`... WHERE id = ? AND status = 'queued'`), so two workers can
never both win the same job, on SQLite or PostgreSQL. (Outcome 10 adds `FOR UPDATE SKIP LOCKED`
selection for many concurrent Postgres workers.)
"""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models import AnalysisJob, DanceProject

log = logging.getLogger("app.jobs")

REFERENCE_ANALYSIS = "reference_analysis"
ACTIVE = ("queued", "running")

# User-facing stage names (spec 24): inspecting, preparing, tracking, segmenting, comparing,
# scoring, saving.
STAGE_MESSAGES = {
    "queued": "Waiting for the analysis worker…",
    "preparing": "Preparing a steady 24 fps copy of your video…",
    "tracking": "Tracking the dancer's body frame by frame…",
    "saving": "Saving landmarks and measurements…",
    "segmenting": "Suggesting teachable sections…",
}


class JobLost(Exception):
    """The job was deleted, cancelled or reclaimed; the current worker must stop."""


def active_job(db: Session, project_id: str, kind: str = REFERENCE_ANALYSIS) -> AnalysisJob | None:
    return db.scalars(
        select(AnalysisJob)
        .where(
            AnalysisJob.project_id == project_id,
            AnalysisJob.kind == kind,
            AnalysisJob.status.in_(ACTIVE),
        )
        .order_by(AnalysisJob.created_at.desc())
    ).first()


def enqueue_reference_analysis(db: Session, project: DanceProject) -> tuple[AnalysisJob, bool]:
    """Return (job, created). Re-requests while a job is active return that job."""
    existing = active_job(db, project.id)
    if existing is not None:
        return existing, False
    n = db.scalar(
        select(func.count())
        .select_from(AnalysisJob)
        .where(AnalysisJob.project_id == project.id, AnalysisJob.kind == REFERENCE_ANALYSIS)
    )
    job = AnalysisJob(
        owner_id=project.owner_id,
        project_id=project.id,
        kind=REFERENCE_ANALYSIS,
        idempotency_key=f"analysis:{project.id}:{(n or 0) + 1}",
        status="queued",
        stage="queued",
        progress=0.0,
        message=STAGE_MESSAGES["queued"],
        attempts=0,
    )
    project.status = "queued"
    project.progress = 0.0
    project.error_code = None
    project.error_message = None
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = active_job(db, project.id)
        if existing is None:
            raise
        return existing, False
    return job, True


def claim_next(db: Session, worker_id: str) -> str | None:
    candidates = db.scalars(
        select(AnalysisJob.id)
        .where(AnalysisJob.status == "queued")
        .order_by(AnalysisJob.created_at, AnalysisJob.id)
        .limit(5)
    ).all()
    for job_id in candidates:
        now = utcnow()
        res = db.execute(
            update(AnalysisJob)
            .where(AnalysisJob.id == job_id, AnalysisJob.status == "queued")
            .values(
                status="running",
                worker_id=worker_id,
                locked_at=now,
                heartbeat_at=now,
                started_at=now,
                attempts=AnalysisJob.attempts + 1,
                updated_at=now,
            )
        )
        db.commit()
        if res.rowcount == 1:
            return job_id
    return None


def heartbeat(
    db: Session,
    job_id: str,
    worker_id: str,
    *,
    stage: str,
    progress: float,
    message: str | None = None,
) -> None:
    now = utcnow()
    res = db.execute(
        update(AnalysisJob)
        .where(
            AnalysisJob.id == job_id,
            AnalysisJob.worker_id == worker_id,
            AnalysisJob.status == "running",
        )
        .values(
            stage=stage,
            progress=round(progress, 4),
            message=message or STAGE_MESSAGES.get(stage),
            heartbeat_at=now,
            updated_at=now,
        )
    )
    if res.rowcount != 1:
        db.rollback()
        raise JobLost(job_id)
    project_id = db.scalar(select(AnalysisJob.project_id).where(AnalysisJob.id == job_id))
    if project_id:
        db.execute(
            update(DanceProject)
            .where(DanceProject.id == project_id)
            .values(status="processing", progress=round(progress, 4), updated_at=now)
        )
    db.commit()


def finish(
    db: Session,
    job_id: str,
    worker_id: str,
    *,
    status: str,
    message: str,
    error_code: str | None = None,
    retryable: bool = False,
    project_status: str | None = None,
    project_error: str | None = None,
) -> None:
    now = utcnow()
    res = db.execute(
        update(AnalysisJob)
        .where(
            AnalysisJob.id == job_id,
            AnalysisJob.worker_id == worker_id,
            AnalysisJob.status == "running",
        )
        .values(
            status=status,
            progress=1.0 if status == "succeeded" else AnalysisJob.progress,
            message=message,
            error_code=error_code,
            retryable=retryable,
            finished_at=now,
            updated_at=now,
        )
    )
    if res.rowcount != 1:
        db.rollback()
        raise JobLost(job_id)
    project_id = db.scalar(select(AnalysisJob.project_id).where(AnalysisJob.id == job_id))
    if project_id and project_status:
        db.execute(
            update(DanceProject)
            .where(DanceProject.id == project_id)
            .values(
                status=project_status,
                progress=1.0 if project_status == "analyzed" else 0.0,
                error_code=error_code,
                error_message=project_error,
                updated_at=now,
            )
        )
    db.commit()


def requeue(db: Session, job_id: str, worker_id: str, message: str) -> None:
    now = utcnow()
    db.execute(
        update(AnalysisJob)
        .where(AnalysisJob.id == job_id, AnalysisJob.worker_id == worker_id)
        .values(status="queued", worker_id=None, locked_at=None, message=message, updated_at=now)
    )
    db.commit()


def recover(db: Session, *, lease_seconds: float, max_attempts: int) -> int:
    """Requeue running jobs whose heartbeat lapsed (worker died); fail them after
    `max_attempts`; repair projects stuck in queued/processing with no live job."""
    now = utcnow()
    cutoff = now - timedelta(seconds=lease_seconds)
    stale = db.scalars(
        select(AnalysisJob).where(
            AnalysisJob.status == "running", AnalysisJob.heartbeat_at < cutoff
        )
    ).all()
    repaired = 0
    for job in stale:
        repaired += 1
        project = db.get(DanceProject, job.project_id) if job.project_id else None
        if job.attempts >= max_attempts:
            job.status = "failed"
            job.error_code = "interrupted"
            job.retryable = True
            job.message = "Analysis was interrupted repeatedly. You can try again."
            job.finished_at = now
            if project is not None:
                project.status = "failed"
                project.error_code = "interrupted"
                project.error_message = job.message
                project.progress = 0.0
        else:
            log.warning("job_requeued_after_lapse", extra={"job_id": job.id})
            job.status = "queued"
            job.worker_id = None
            job.locked_at = None
            job.stage = "queued"
            job.message = "Analysis was interrupted; resuming…"
            if project is not None:
                project.status = "queued"
    db.commit()

    # Projects that claim to be busy without any active job (e.g. a crash between commits).
    busy = db.scalars(
        select(DanceProject).where(DanceProject.status.in_(("queued", "processing")))
    ).all()
    for project in busy:
        if active_job(db, project.id) is None:
            repaired += 1
            project.status = "failed"
            project.error_code = "interrupted"
            project.error_message = "Analysis stopped unexpectedly. You can try again."
            project.progress = 0.0
    db.commit()
    return repaired

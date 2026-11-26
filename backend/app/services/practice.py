"""Learner attempt intake (spec 16, Journey D): validated temp file → private object + rows.

Same no-residue invariant as reference intake: the object is written under a fresh
attempt prefix first, then the practice-session row commits; any failure rolls back and
deletes the prefix. Attempts live under their dance's prefix, so deleting the dance removes
every attempt's media too.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import new_id
from app.errors import ApiError
from app.media.probe import ProbeResult
from app.models import DanceProject, DanceSegment, PracticeSession, User
from app.services.intake import intake_warnings, project_prefix
from app.storage.base import ObjectStorage

log = logging.getLogger("app.practice")

CAPTURE_SOURCES = ("webcam", "upload")
# An attempt much shorter than what it practises can't cover the movement; say so up front.
SHORT_ATTEMPT_RATIO = 0.75


def practice_prefix(owner_id: str, project_id: str, session_id: str) -> str:
    return f"{project_prefix(owner_id, project_id)}/practice/{session_id}"


def owned_practice(db: Session, user_id: str, session_id: str) -> PracticeSession:
    practice = db.get(PracticeSession, session_id) if len(session_id) <= 64 else None
    # Same 404 for missing and foreign: never confirm another user's attempt exists.
    if practice is None or practice.owner_id != user_id:
        raise ApiError(404, "practice_not_found", "That attempt doesn't exist or was deleted.")
    return practice


def find_by_idempotency(db: Session, owner_id: str, key: str | None) -> PracticeSession | None:
    if key is None:
        return None
    return db.scalars(
        select(PracticeSession).where(
            PracticeSession.owner_id == owner_id, PracticeSession.idempotency_key == key
        )
    ).first()


def require_practicable(project: DanceProject) -> None:
    ref = project.reference_video
    if project.status != "analyzed" or ref is None or ref.analyzed_at is None:
        raise ApiError(
            409,
            "reference_not_ready",
            "Analyse this dance before practising it — the comparison needs its measured moves.",
        )


def resolve_segment(
    db: Session, project: DanceProject, segment_id: str | None
) -> DanceSegment | None:
    if not segment_id:
        return None
    seg = db.get(DanceSegment, segment_id) if len(segment_id) <= 64 else None
    if seg is None or seg.project_id != project.id:
        raise ApiError(404, "section_not_found", "That section isn't part of this dance.")
    return seg


def enforce_quota(db: Session, project_id: str, limit: int) -> None:
    count = db.scalar(
        select(func.count())
        .select_from(PracticeSession)
        .where(PracticeSession.project_id == project_id)
    )
    if (count or 0) >= limit:
        raise ApiError(
            409,
            "practice_limit",
            f"This dance has {limit} attempts already. Delete an old one to record another.",
        )


def target_duration(project: DanceProject, segment: DanceSegment | None) -> float | None:
    if segment is not None:
        return segment.end_time - segment.start_time
    ref = project.reference_video
    if ref is None:
        return None
    return ref.canonical_duration or ref.duration


def attempt_warnings(probe: ProbeResult, target: float | None) -> list[str]:
    warnings = intake_warnings(probe)
    if target and probe.duration < target * SHORT_ATTEMPT_RATIO:
        warnings.append("shorter_than_target")
    return warnings


@dataclass
class PracticeIntake:
    owner: User
    project: DanceProject
    segment: DanceSegment | None
    source_path: Path
    extension: str
    filename: str
    probe: ProbeResult
    capture_source: str
    declared_mirrored: bool
    idempotency_key: str | None


def persist_practice(db: Session, storage: ObjectStorage, req: PracticeIntake) -> PracticeSession:
    session_id = new_id()
    prefix = practice_prefix(req.owner.id, req.project.id, session_id)
    source_key = f"{prefix}/source{req.extension}"
    try:
        stored = storage.put_file(source_key, req.source_path)
        practice = PracticeSession(
            id=session_id,
            owner_id=req.owner.id,
            project_id=req.project.id,
            segment_id=req.segment.id if req.segment else None,
            source_object_key=source_key,
            status="uploaded",
            progress=0.0,
            duration=req.probe.duration,
            source_fps=req.probe.fps,
            width=req.probe.display_width,
            height=req.probe.display_height,
            declared_mirrored=req.declared_mirrored,
            capture_source=req.capture_source,
            original_filename=req.filename,
            source_size_bytes=stored,
            source_codec=req.probe.video_codec[:32],
            has_audio=req.probe.has_audio,
            idempotency_key=req.idempotency_key,
            warnings=attempt_warnings(req.probe, target_duration(req.project, req.segment)),
        )
        db.add(practice)
        db.commit()
        return practice
    except IntegrityError:
        db.rollback()
        storage.delete_prefix(prefix)
        existing = find_by_idempotency(db, req.owner.id, req.idempotency_key)
        if existing is not None:  # a concurrent retry of the same recording won the race
            return existing
        raise
    except BaseException:
        db.rollback()
        try:
            storage.delete_prefix(prefix)
        except Exception:  # pragma: no cover - logged, original error re-raised
            log.exception("practice_cleanup_failed")
        raise


def delete_practice(db: Session, storage: ObjectStorage, practice: PracticeSession) -> None:
    prefix = practice_prefix(practice.owner_id, practice.project_id, practice.id)
    db.delete(practice)
    db.commit()
    storage.delete_prefix(prefix)

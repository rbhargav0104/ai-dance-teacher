"""Attempt ↔ reference alignment (Outcome 6): loads both stored pose tracks, runs the pure
alignment in app.pose.alignment and caches the result on the attempt.

The cache key covers everything the result depends on (alignment version, both analyses and
the reference window), so editing sections or re-analysing either video recomputes it.
Alignment needs no pose model (it works on stored, really measured frames), only numpy from
the vision extra, imported lazily: without it a cached alignment is still served and a new
one is refused honestly (503) rather than approximated.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import (
    DanceProject,
    DanceSegment,
    PracticeSession,
    ReferencePoseFrame,
    ReferenceVideo,
    UserPoseFrame,
)

log = logging.getLogger("app.alignment")

# Mirrors app.pose.alignment.ALIGN_VERSION without importing numpy.
ALIGN_VERSION = "align-1"


def _stamp(dt: datetime | None) -> str:
    return dt.isoformat(timespec="seconds") if dt else "-"


def reference_window(
    db: Session, practice: PracticeSession, project: DanceProject, ref: ReferenceVideo
) -> tuple[float, float, str | None]:
    seg = db.get(DanceSegment, practice.segment_id) if practice.segment_id else None
    if seg is not None:
        return float(seg.start_time), float(seg.end_time), seg.id
    end = ref.canonical_duration or ref.duration
    return 0.0, float(end), None


def cache_key(practice: PracticeSession, ref: ReferenceVideo, lo: float, hi: float) -> str:
    return "|".join(
        [
            ALIGN_VERSION,
            f"ref:{ref.id}:{_stamp(ref.analyzed_at)}",
            f"att:{_stamp(practice.analyzed_at)}",
            f"win:{lo:.3f}-{hi:.3f}",
            f"mir:{int(bool(practice.declared_mirrored))}",
        ]
    )


def _require_ready(db: Session, practice: PracticeSession) -> tuple[DanceProject, ReferenceVideo]:
    project = db.get(DanceProject, practice.project_id)
    ref = db.scalars(
        select(ReferenceVideo).where(ReferenceVideo.project_id == practice.project_id)
    ).first()
    if project is None or ref is None or ref.analyzed_at is None or project.status != "analyzed":
        raise ApiError(
            409, "reference_not_analyzed", "The dance itself needs to be analysed before comparing."
        )
    if practice.status != "analyzed" or practice.analyzed_at is None:
        if practice.status == "failed":
            raise ApiError(
                409,
                "attempt_not_comparable",
                practice.error_message
                or "This attempt couldn't be measured well enough to compare. Try re-recording.",
            )
        raise ApiError(409, "not_analyzed", "This attempt hasn't been analysed yet.")
    return project, ref


def get_alignment(db: Session, practice: PracticeSession) -> tuple[dict[str, Any], bool]:
    """Returns (alignment, cached). Raises ApiError for honest refusals."""
    project, ref = _require_ready(db, practice)
    lo, hi, seg_id = reference_window(db, practice, project, ref)
    key = cache_key(practice, ref, lo, hi)
    if practice.alignment is not None and practice.alignment_key == key:
        return practice.alignment, True
    try:
        from app.pose.alignment import align, sequence_from_payloads
    except ImportError as exc:  # vision extra not installed
        raise ApiError(
            503, "analysis_unavailable", "Comparing movement isn't available on this server."
        ) from exc

    ref_rows = db.scalars(
        select(ReferencePoseFrame)
        .where(
            ReferencePoseFrame.reference_video_id == ref.id,
            ReferencePoseFrame.timestamp >= lo - 1e-6,
            ReferencePoseFrame.timestamp <= hi + 1e-6,
        )
        .order_by(ReferencePoseFrame.frame_number)
    ).all()
    att_rows = db.scalars(
        select(UserPoseFrame)
        .where(UserPoseFrame.practice_session_id == practice.id)
        .order_by(UserPoseFrame.frame_number)
    ).all()
    ref_seq = sequence_from_payloads(
        [r.timestamp for r in ref_rows],
        [r.payload for r in ref_rows],
        [r.valid for r in ref_rows],
        start=lo,
    )
    att_seq = sequence_from_payloads(
        [r.timestamp for r in att_rows],
        [r.payload for r in att_rows],
        [r.valid for r in att_rows],
    )
    preferred = "mirrored" if practice.declared_mirrored else "direct"
    result = align(ref_seq, att_seq, preferred_mode=preferred)
    result["window"] = {"start": round(lo, 3), "end": round(hi, 3), "segment_id": seg_id}
    result["preferred_reason"] = (
        "the video was marked as mirrored"
        if practice.declared_mirrored
        else "the learner uses the same body side as the dancer"
    )
    practice.alignment = result
    practice.alignment_key = key
    mirror = result.get("mirror")
    if isinstance(mirror, dict):
        practice.detected_mirror_choice = str(mirror.get("chosen"))[:16]
    db.commit()
    log.info(
        "alignment_computed",
        extra={"practice_id": practice.id, "status": result.get("status")},
    )
    return result, False

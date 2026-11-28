"""Attempt scoring (Outcome 7): alignment (cached) → pure versioned scoring
(app.pose.scoring) → stored `performance_scores` row.

The stored row is reused only while its key matches: scoring version, the alignment key (both
analyses, the window, the declared mirror) and — for full-dance attempts — the section
boundaries used for the per-section breakdown. Anything else recomputes from stored frames.
Without numpy a still-valid stored score is served; a new one is refused honestly (503).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import DanceSegment, PerformanceScore, PracticeSession
from app.services.alignment import get_alignment, load_sequences, reference_window, require_ready

log = logging.getLogger("app.scoring")

# Mirrors app.pose.scoring.SCORE_VERSION without importing numpy.
SCORE_VERSION = "score-1"


def _sections(db: Session, practice: PracticeSession) -> list[dict[str, Any]]:
    """Sections for the per-section breakdown (full-dance attempts only)."""
    if practice.segment_id is not None:
        return []
    rows = db.scalars(
        select(DanceSegment)
        .where(DanceSegment.project_id == practice.project_id)
        .order_by(DanceSegment.position)
    ).all()
    return [
        {"id": s.id, "title": s.title, "start": float(s.start_time), "end": float(s.end_time)}
        for s in rows
    ]


def score_key(practice: PracticeSession, sections: list[dict[str, Any]]) -> str:
    secs = ",".join(f"{s['id']}:{s['start']:.3f}-{s['end']:.3f}" for s in sections)
    return f"{SCORE_VERSION}|{practice.alignment_key}|sec:{secs}"


def stored_score(db: Session, practice: PracticeSession) -> PerformanceScore | None:
    return db.scalars(
        select(PerformanceScore)
        .where(PerformanceScore.practice_session_id == practice.id)
        .order_by(PerformanceScore.created_at.desc())
    ).first()


def current_summary(db: Session, practice: PracticeSession) -> dict[str, Any] | None:
    """Compact summary of a still-valid stored score (for lists), never computed here."""
    row = stored_score(db, practice)
    if row is None or practice.alignment_key is None:
        return None
    if (row.report or {}).get("key") != score_key(practice, _sections(db, practice)):
        return None
    rep = row.report or {}
    return {
        "status": rep.get("status"),
        "overall": row.overall,
        "version": row.scoring_version,
        "confidence": row.confidence,
    }


def get_report(db: Session, practice: PracticeSession) -> tuple[dict[str, Any], bool]:
    """Returns (report, cached). Raises ApiError for honest refusals (409/503)."""
    project, ref = require_ready(db, practice)
    sections = _sections(db, practice)
    alignment, _ = get_alignment(db, practice)
    key = score_key(practice, sections)
    row = stored_score(db, practice)
    if row is not None and (row.report or {}).get("key") == key:
        return row.report, True
    try:
        from app.pose.scoring import score
    except ImportError as exc:  # vision extra (numpy) not installed
        raise ApiError(
            503, "analysis_unavailable", "Scoring isn't available on this server."
        ) from exc
    lo, hi, seg_id = reference_window(db, practice, project, ref)
    ref_seq, att_seq = load_sequences(db, practice, ref, lo, hi)
    # Sections are in reference-video time; the breakdown works in window time.
    win_sections = [
        {**s, "start": s["start"] - lo, "end": s["end"] - lo}
        for s in sections
        if s["end"] > lo and s["start"] < hi
    ]
    try:
        report = score(ref_seq, att_seq, alignment, sections=win_sections)
    except ValueError as exc:  # alignment no longer matches the stored frames
        log.warning("score_alignment_mismatch", extra={"practice_id": practice.id})
        raise ApiError(
            409, "comparison_stale", "The comparison is out of date. Reload to recompute it."
        ) from exc
    # Back to reference-video time for clients.
    for s in report.get("sections", []):
        s["start"] = round(s["start"] + lo, 3)
        s["end"] = round(s["end"] + lo, 3)
    report["key"] = key
    report["window"] = {"start": round(lo, 3), "end": round(hi, 3), "segment_id": seg_id}
    cov = report.get("coverage") or {}
    db.execute(delete(PerformanceScore).where(PerformanceScore.practice_session_id == practice.id))
    db.add(
        PerformanceScore(
            practice_session_id=practice.id,
            scoring_version=report["version"],
            overall=report.get("overall"),
            components=report.get("components") or {},
            weights=report.get("weights") or {},
            coverage=float(cov.get("learner_tracking") or 0.0),
            confidence=float(cov.get("confidence") or 0.0),
            report=report,
        )
    )
    db.commit()
    log.info(
        "score_computed",
        extra={
            "practice_id": practice.id,
            "status": report.get("status"),
            "version": report.get("version"),
        },
    )
    return report, False

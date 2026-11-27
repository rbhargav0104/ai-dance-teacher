"""Learner attempt analysis: the SAME canonical transcode, pose model, smoothing, features and
quality gates as the reference (spec 16). Nothing is compared or scored here yet (Outcomes
6-7); this stores the learner's real measured pose so the attempt can be reviewed.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.base import new_id, utcnow
from app.models import AnalysisJob, PracticeSession, UserPoseFrame
from app.pipeline.common import (
    ProgressFn,
    frame_rows,
    measure,
    prepare,
    quality_dict,
    raise_if_choice_needed,
    require_runtime,
    span,
    subject_record,
)
from app.pipeline.errors import AnalysisFailed
from app.pose.quality import WARNING_MESSAGES
from app.services.practice import practice_prefix
from app.storage.base import ObjectStorage

PIPELINE_VERSION = "learner-pose-1"


@dataclass(frozen=True)
class PracticeOutcome:
    coverage: float
    warnings: list[str]
    frames: int


def run_practice_analysis(
    db: Session,
    storage: ObjectStorage,
    settings: Settings,
    job: AnalysisJob,
    progress: ProgressFn,
) -> PracticeOutcome:
    practice = db.get(PracticeSession, job.practice_session_id) if job.practice_session_id else None
    if practice is None or practice.source_object_key is None:
        raise AnalysisFailed("practice_not_found", "This attempt no longer exists.")
    status = require_runtime(settings)
    prefix = practice_prefix(practice.owner_id, practice.project_id, practice.id)

    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=settings.tmp_dir, prefix="practice-") as tmp:
        progress("preparing", 0.02)
        prepared = prepare(storage.local_path(practice.source_object_key), Path(tmp), settings)
        progress("preparing", 0.12)
        canonical_key = f"{prefix}/canonical.mp4"
        poster_key = f"{prefix}/poster.jpg"
        storage.put_file(canonical_key, prepared.canonical)
        storage.put_file(poster_key, prepared.poster)
        cp = prepared.probe
        practice.canonical_object_key = canonical_key
        practice.thumbnail_key = poster_key
        practice.canonical_width = cp.display_width
        practice.canonical_height = cp.display_height
        practice.canonical_fps = cp.fps
        practice.canonical_duration = cp.duration
        db.commit()
        progress("preparing", 0.15)

        measured = measure(
            prepared,
            settings,
            span(0.15, 0.9, progress, "tracking"),
            choice=(practice.subject or {}).get("choice"),
        )
        subject = subject_record(
            measured,
            prepared.canonical,
            Path(tmp),
            storage,
            f"{prefix}/people.jpg",
            practice.subject,
        )

    report = measured.report
    progress("saving", 0.92)
    db.execute(delete(UserPoseFrame).where(UserPoseFrame.practice_session_id == practice.id))
    rows = [
        UserPoseFrame(
            id=new_id(),
            practice_session_id=practice.id,
            timestamp=r.timestamp,
            frame_number=r.frame_number,
            payload=r.payload,
            valid=r.valid,
            confidence=r.confidence,
            pipeline_version=PIPELINE_VERSION,
        )
        for r in frame_rows(measured)
    ]
    db.add_all(rows)
    kept = [w for w in (practice.warnings or []) if w not in WARNING_MESSAGES]
    practice.analysis_fps = measured.raw.analysis_fps
    practice.subject = subject
    practice.tracking_coverage = round(report.coverage, 4)
    practice.warnings = kept + report.warnings
    practice.quality = quality_dict(measured)
    practice.pipeline_version = PIPELINE_VERSION
    practice.model_version = status.model_version
    practice.analyzed_at = utcnow()
    db.commit()
    progress("saving", 0.99)

    raise_if_choice_needed(measured)
    if report.failure is not None:
        raise AnalysisFailed(report.failure, report.failure_message or report.failure)
    return PracticeOutcome(report.coverage, report.warnings, len(rows))

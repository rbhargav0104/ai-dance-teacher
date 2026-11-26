"""Reference analysis job: canonical transcode → real pose extraction → features → quality gates.

Every number stored here comes from MediaPipe landmarks measured on the user's video.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.base import new_id, utcnow
from app.models import AnalysisJob, DanceProject, ReferencePoseFrame, ReferenceVideo
from app.pipeline.common import (
    ProgressFn,
    frame_rows,
    measure,
    prepare,
    quality_dict,
    require_runtime,
    span,
)
from app.pipeline.errors import AnalysisFailed
from app.pose.quality import WARNING_MESSAGES
from app.services.intake import project_prefix
from app.storage.base import ObjectStorage

PIPELINE_VERSION = "ref-pose-1"

__all__ = ["PIPELINE_VERSION", "AnalysisOutcome", "ProgressFn", "run_reference_analysis"]


@dataclass(frozen=True)
class AnalysisOutcome:
    coverage: float
    warnings: list[str]
    frames: int


def run_reference_analysis(
    db: Session,
    storage: ObjectStorage,
    settings: Settings,
    job: AnalysisJob,
    progress: ProgressFn,
) -> AnalysisOutcome:
    project = db.get(DanceProject, job.project_id) if job.project_id else None
    if project is None or project.reference_video is None:
        raise AnalysisFailed("project_not_found", "This dance no longer exists.")
    ref: ReferenceVideo = project.reference_video
    status = require_runtime(settings)
    prefix = project_prefix(project.owner_id, project.id)

    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=settings.tmp_dir, prefix="job-") as tmp:
        # --- preparing: canonical copy + poster --------------------------------------------
        progress("preparing", 0.02)
        prepared = prepare(storage.local_path(ref.source_object_key), Path(tmp), settings)
        progress("preparing", 0.12)
        canonical_key = f"{prefix}/canonical.mp4"
        poster_key = f"{prefix}/poster.jpg"
        storage.put_file(canonical_key, prepared.canonical)
        storage.put_file(poster_key, prepared.poster)
        cp = prepared.probe
        ref.canonical_object_key = canonical_key
        ref.thumbnail_key = poster_key
        ref.canonical_width = cp.display_width
        ref.canonical_height = cp.display_height
        ref.canonical_fps = cp.fps
        ref.canonical_duration = cp.duration
        db.commit()
        progress("preparing", 0.15)

        # --- tracking: real MediaPipe inference --------------------------------------------
        measured = measure(prepared, settings, span(0.15, 0.85, progress, "tracking"))

    report = measured.report
    progress("saving", 0.88)

    # --- saving -----------------------------------------------------------------------------
    db.execute(delete(ReferencePoseFrame).where(ReferencePoseFrame.reference_video_id == ref.id))
    rows = [
        ReferencePoseFrame(
            id=new_id(),
            reference_video_id=ref.id,
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
    intake_warnings = [w for w in (ref.warnings or []) if w not in WARNING_MESSAGES]
    ref.analysis_fps = measured.raw.analysis_fps
    ref.pose_coverage = round(report.coverage, 4)
    ref.warnings = intake_warnings + report.warnings
    ref.quality = quality_dict(measured)
    ref.pipeline_version = PIPELINE_VERSION
    ref.model_version = status.model_version
    ref.analyzed_at = utcnow()
    db.commit()
    progress("saving", 0.98)

    if report.failure is not None:
        raise AnalysisFailed(report.failure, report.failure_message or report.failure)

    # --- segmenting: suggested teachable sections from the stored measurements -------------
    progress("segmenting", 0.985)
    from app.services.sections import generate_automatic

    db.refresh(project)
    generate_automatic(db, storage, settings, project, require_analysed=False)
    progress("segmenting", 0.995)
    return AnalysisOutcome(report.coverage, report.warnings, len(rows))

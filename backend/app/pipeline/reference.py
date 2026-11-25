"""Reference analysis job: canonical transcode → real pose extraction → features → quality gates.

Every number stored here comes from MediaPipe landmarks measured on the user's video.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.base import new_id, utcnow
from app.media.probe import MediaRejected, probe_file
from app.media.transcode import TranscodeFailed, make_canonical, make_poster
from app.models import AnalysisJob, DanceProject, ReferencePoseFrame, ReferenceVideo
from app.pipeline.errors import AnalysisFailed
from app.pose import landmarks as L
from app.pose.extract import ExtractionFailed, extract
from app.pose.features import QualityConfig, compute_features, frame_payload
from app.pose.quality import WARNING_MESSAGES, assess, select_track
from app.pose.runtime import probe as pose_probe
from app.services.intake import project_prefix
from app.storage.base import ObjectStorage

log = logging.getLogger("app.pipeline")

PIPELINE_VERSION = "ref-pose-1"

ProgressFn = Callable[[str, float], None]


@dataclass(frozen=True)
class AnalysisOutcome:
    coverage: float
    warnings: list[str]
    frames: int


def _span(lo: float, hi: float, progress: ProgressFn, stage: str) -> Callable[[float], None]:
    return lambda f: progress(stage, lo + (hi - lo) * max(0.0, min(1.0, f)))


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
    status = pose_probe(settings.model_path, settings.model_sha256)
    if not status.available:
        raise AnalysisFailed(
            "analysis_unavailable",
            status.problem or "Movement analysis is unavailable.",
            retryable=True,
        )
    prefix = project_prefix(project.owner_id, project.id)

    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=settings.tmp_dir, prefix="job-") as tmp:
        work = Path(tmp)
        # --- preparing: canonical copy + poster --------------------------------------------
        progress("preparing", 0.02)
        source = storage.local_path(ref.source_object_key)
        try:
            source_probe = probe_file(
                source,
                max_duration=settings.max_duration_seconds,
                timeout_s=settings.ffprobe_timeout_seconds,
            )
            canonical = make_canonical(
                source,
                work / "canonical.mp4",
                source_probe,
                max_duration=settings.max_duration_seconds,
                timeout_s=settings.transcode_timeout_seconds,
                probe_timeout_s=settings.ffprobe_timeout_seconds,
            )
            poster = work / "poster.jpg"
            make_poster(
                canonical.path,
                poster,
                at_seconds=min(1.0, canonical.probe.duration / 2),
                timeout_s=60,
            )
        except (TranscodeFailed, MediaRejected) as exc:
            raise AnalysisFailed(exc.code, exc.message) from exc
        progress("preparing", 0.12)
        canonical_key = f"{prefix}/canonical.mp4"
        poster_key = f"{prefix}/poster.jpg"
        storage.put_file(canonical_key, canonical.path)
        storage.put_file(poster_key, poster)
        cp = canonical.probe
        ref.canonical_object_key = canonical_key
        ref.thumbnail_key = poster_key
        ref.canonical_width = cp.display_width
        ref.canonical_height = cp.display_height
        ref.canonical_fps = cp.fps
        ref.canonical_duration = cp.duration
        db.commit()
        progress("preparing", 0.15)

        # --- tracking: real MediaPipe inference --------------------------------------------
        try:
            raw = extract(
                canonical.path,
                width=cp.display_width,
                height=cp.display_height,
                duration=cp.duration,
                model_path=settings.model_path,
                analysis_fps=settings.analysis_fps,
                timeout_s=settings.analysis_timeout_seconds,
                progress=_span(0.15, 0.85, progress, "tracking"),
            )
        except ExtractionFailed as exc:
            raise AnalysisFailed(exc.code, exc.message) from exc
        except (ImportError, OSError, RuntimeError) as exc:
            log.exception("pose_runtime_error")
            raise AnalysisFailed(
                "analysis_unavailable",
                "The movement-analysis runtime failed to start on this server.",
                retryable=True,
            ) from exc

    cfg = QualityConfig()
    track, counts, chosen = select_track(raw.detections, cfg.visibility_threshold)
    feats = compute_features(track, raw.times, cp.display_width, cp.display_height, cfg)
    report = assess(feats, counts, cfg)
    progress("saving", 0.88)

    # --- saving -----------------------------------------------------------------------------
    db.execute(delete(ReferencePoseFrame).where(ReferencePoseFrame.reference_video_id == ref.id))
    rows = []
    for t in range(len(raw.times)):
        payload = frame_payload(feats, t, int(counts[t]))
        k = int(chosen[t])
        world = raw.world[t][k] if k >= 0 and k < len(raw.world[t]) else None
        payload["world"] = (
            [[round(float(v), 4) for v in world[j]] for j in range(L.NUM_LANDMARKS)]
            if world is not None
            else None
        )
        rows.append(
            ReferencePoseFrame(
                id=new_id(),
                reference_video_id=ref.id,
                timestamp=round(float(raw.times[t]), 4),
                frame_number=int(raw.frame_numbers[t]),
                payload=payload,
                valid=bool(feats.valid[t]),
                confidence=round(float(feats.confidence[t]), 4),
                pipeline_version=PIPELINE_VERSION,
            )
        )
    db.add_all(rows)
    intake_warnings = [w for w in (ref.warnings or []) if w not in WARNING_MESSAGES]
    ref.analysis_fps = raw.analysis_fps
    ref.pose_coverage = round(report.coverage, 4)
    ref.warnings = intake_warnings + report.warnings
    ref.quality = {
        **report.as_dict(),
        "torso_scale": None if feats.scale != feats.scale else round(feats.scale, 4),
        "thresholds": {
            "visibility": cfg.visibility_threshold,
            "min_major_joints": cfg.min_major_joints,
            "fail_coverage": cfg.fail_coverage,
            "warn_coverage": cfg.warn_coverage,
            "max_multi_person_fraction": cfg.max_multi_person_fraction,
            "max_gap_frames": cfg.max_gap_frames,
        },
        "smoothing": "one_euro(min_cutoff=1.7, beta=0.3)",
    }
    ref.pipeline_version = PIPELINE_VERSION
    ref.model_version = status.model_version
    ref.analyzed_at = utcnow()
    db.commit()
    progress("saving", 0.98)

    if report.failure is not None:
        raise AnalysisFailed(report.failure, report.failure_message or report.failure)
    return AnalysisOutcome(report.coverage, report.warnings, len(rows))

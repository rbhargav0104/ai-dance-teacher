"""Shared analysis stages for reference AND learner footage (spec 16: same model, same
normalization, same features, same quality thresholds).

canonical transcode → real MediaPipe extraction → track selection → features → quality gates.
Every number produced here comes from landmarks measured on the given video.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from app.config import Settings
from app.media.probe import MediaRejected, ProbeResult, probe_file
from app.media.transcode import TranscodeFailed, make_canonical, make_poster
from app.pipeline.errors import AnalysisFailed
from app.pose import landmarks as L
from app.pose.extract import ExtractionFailed, RawExtraction, extract
from app.pose.features import QualityConfig, TrackFeatures, compute_features, frame_payload
from app.pose.quality import QualityReport, assess, select_track
from app.pose.runtime import PoseRuntimeStatus
from app.pose.runtime import probe as pose_probe

log = logging.getLogger("app.pipeline")

ProgressFn = Callable[[str, float], None]

SMOOTHING_LABEL = "one_euro(min_cutoff=1.7, beta=0.3)"


def span(lo: float, hi: float, progress: ProgressFn, stage: str) -> Callable[[float], None]:
    return lambda f: progress(stage, lo + (hi - lo) * max(0.0, min(1.0, f)))


def require_runtime(settings: Settings) -> PoseRuntimeStatus:
    status = pose_probe(settings.model_path, settings.model_sha256)
    if not status.available:
        raise AnalysisFailed(
            "analysis_unavailable",
            status.problem or "Movement analysis is unavailable.",
            retryable=True,
        )
    return status


@dataclass(frozen=True)
class Prepared:
    canonical: Path
    poster: Path
    probe: ProbeResult


def prepare(source: Path, work: Path, settings: Settings) -> Prepared:
    """Canonical 24 fps H.264 copy + poster frame (spec 11 'canonical representation')."""
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
    return Prepared(canonical.path, poster, canonical.probe)


@dataclass(frozen=True)
class Measured:
    raw: RawExtraction
    feats: TrackFeatures
    report: QualityReport
    counts: NDArray[np.int64]
    chosen: NDArray[np.int64]
    cfg: QualityConfig


def measure(
    prepared: Prepared, settings: Settings, on_progress: Callable[[float], None]
) -> Measured:
    cp = prepared.probe
    try:
        raw = extract(
            prepared.canonical,
            width=cp.display_width,
            height=cp.display_height,
            duration=cp.duration,
            model_path=settings.model_path,
            analysis_fps=settings.analysis_fps,
            timeout_s=settings.analysis_timeout_seconds,
            progress=on_progress,
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
    return Measured(raw, feats, report, counts, chosen, cfg)


@dataclass(frozen=True)
class FrameRow:
    timestamp: float
    frame_number: int
    payload: dict[str, Any]
    valid: bool
    confidence: float


def frame_rows(m: Measured) -> list[FrameRow]:
    rows: list[FrameRow] = []
    for t in range(len(m.raw.times)):
        payload = frame_payload(m.feats, t, int(m.counts[t]))
        k = int(m.chosen[t])
        world = m.raw.world[t][k] if k >= 0 and k < len(m.raw.world[t]) else None
        payload["world"] = (
            [[round(float(v), 4) for v in world[j]] for j in range(L.NUM_LANDMARKS)]
            if world is not None
            else None
        )
        rows.append(
            FrameRow(
                timestamp=round(float(m.raw.times[t]), 4),
                frame_number=int(m.raw.frame_numbers[t]),
                payload=payload,
                valid=bool(m.feats.valid[t]),
                confidence=round(float(m.feats.confidence[t]), 4),
            )
        )
    return rows


def quality_dict(m: Measured) -> dict[str, Any]:
    cfg = m.cfg
    scale = m.feats.scale
    return {
        **m.report.as_dict(),
        "torso_scale": None if scale != scale else round(scale, 4),
        "thresholds": {
            "visibility": cfg.visibility_threshold,
            "min_major_joints": cfg.min_major_joints,
            "fail_coverage": cfg.fail_coverage,
            "warn_coverage": cfg.warn_coverage,
            "max_multi_person_fraction": cfg.max_multi_person_fraction,
            "max_gap_frames": cfg.max_gap_frames,
        },
        "smoothing": SMOOTHING_LABEL,
    }

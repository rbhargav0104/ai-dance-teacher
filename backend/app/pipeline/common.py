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
from app.pipeline.errors import AnalysisFailed, SubjectChoiceNeeded
from app.pose import landmarks as L
from app.pose import people as P
from app.pose.extract import ExtractionFailed, RawExtraction, extract
from app.pose.features import QualityConfig, TrackFeatures, compute_features, frame_payload
from app.pose.quality import CHOOSE_DANCER_MESSAGE, QualityReport, assess, select_track
from app.pose.runtime import PoseRuntimeStatus
from app.pose.runtime import probe as pose_probe
from app.storage.base import ObjectStorage

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
    counts: NDArray[np.int64]  # distinct people per frame
    chosen: NDArray[np.int64]  # detection index followed per frame (-1 = none)
    cfg: QualityConfig
    survey: P.PeopleSurvey | None = None  # who is in the video (A2), when 2+ people seen apart
    follow: P.FollowResult | None = None  # set when following a person the user chose
    needs_choice: bool = False  # several people for much of the video and no choice yet


def _run_extraction(
    prepared: Prepared, settings: Settings, on_progress: Callable[[float], None]
) -> RawExtraction:
    cp = prepared.probe
    try:
        return extract(
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


def measure(
    prepared: Prepared,
    settings: Settings,
    on_progress: Callable[[float], None],
    choice: dict[str, Any] | None = None,
) -> Measured:
    """Real extraction → who to follow → features → quality gates.

    Without a `choice`, the largest body is followed (unchanged single-dancer behaviour); if
    several people are clearly visible for much of the video, `needs_choice` is set instead of
    failing (A2). With a `choice` ({"t", "root"} of the person the user picked), only that person
    is followed; frames where they are lost or uncertain are masked, never filled by someone else.
    """
    cp = prepared.probe
    raw = _run_extraction(prepared, settings, on_progress)
    cfg = QualityConfig()
    distinct, counts = P.distinct_detections(raw.detections, cfg.visibility_threshold)
    multi = float((counts >= 2).mean()) if len(counts) else 0.0

    if choice is not None:
        located = P.locate_choice(
            raw.detections,
            distinct,
            raw.times,
            float(choice["t"]),
            (float(choice["root"][0]), float(choice["root"][1])),
        )
        if located is None:
            raise AnalysisFailed(
                "chosen_dancer_not_found",
                "We couldn't find the person you picked in this video any more. "
                "Please choose again.",
            )
        picked = P.follow_person(raw.detections, raw.appearances, distinct, located[0], located[1])
        track = P.track_from_follow(raw.detections, picked)
        feats = compute_features(track, raw.times, cp.display_width, cp.display_height, cfg)
        lost = sum(st != "followed" for st in picked.status)
        report = assess(feats, counts, cfg, chosen_person=True, lost_chosen_frames=lost)
        return Measured(raw, feats, report, counts, picked.chosen, cfg, follow=picked)

    survey = (
        P.survey_people(
            raw.detections, raw.appearances, distinct, raw.times, cfg.visibility_threshold
        )
        if multi > 0
        else None
    )
    if survey is not None and len(survey.candidates) >= 2:
        # Several people seen apart: follow the biggest of them with the identity-aware
        # follower (never switches silently when people cross), until the user chooses.
        main = max(survey.candidates, key=lambda c: P.box_area(np.asarray(c.box)))
        default = P.follow_person(
            raw.detections, raw.appearances, distinct, survey.frame, main.detection
        )
        chosen = default.chosen
        track = P.track_from_follow(raw.detections, default)
    else:
        filtered = [
            [poses[i] for i in keep] for poses, keep in zip(raw.detections, distinct, strict=True)
        ]
        track, _, picked_idx = select_track(filtered, cfg.visibility_threshold)
        chosen = np.asarray(
            [distinct[t][int(k)] if k >= 0 else -1 for t, k in enumerate(picked_idx)],
            dtype=np.int64,
        )
    feats = compute_features(track, raw.times, cp.display_width, cp.display_height, cfg)
    report = assess(feats, counts, cfg)
    needs_choice = (
        survey is not None and len(survey.candidates) >= 2 and multi > cfg.max_multi_person_fraction
    )
    return Measured(
        raw, feats, report, counts, chosen, cfg, survey=survey, needs_choice=needs_choice
    )


def subject_record(
    m: Measured,
    canonical: Path,
    work: Path,
    storage: ObjectStorage,
    frame_key: str,
    previous: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """The stored "who is in this video" record (A2). Keeps the earlier candidates and frame
    while a choice is in force, so "Follow someone else" offers the same people."""
    choice = (previous or {}).get("choice")
    if m.follow is not None and previous is not None:
        record = dict(previous)
        st = m.follow.status
        record["followed"] = {
            "fraction": round(m.follow.followed_fraction, 4),
            "lost_spans": [
                [round(a, 3), round(b, 3)] for a, b in P.status_spans(m.raw.times, st, ("lost",))
            ],
            "uncertain_spans": [
                [round(a, 3), round(b, 3)]
                for a, b in P.status_spans(m.raw.times, st, ("uncertain",))
            ],
        }
        return record
    if m.survey is None or len(m.survey.candidates) < 2:
        return None
    frame = work / "people.jpg"
    make_poster(canonical, frame, at_seconds=m.survey.time, timeout_s=60)
    storage.put_file(frame_key, frame)
    return {
        "version": P.PEOPLE_VERSION,
        "frame_time": round(m.survey.time, 4),
        "frame_key": frame_key,
        "candidates": [c.as_dict() for c in m.survey.candidates],
        "choice": choice,
        "followed": None,
    }


def raise_if_choice_needed(m: Measured) -> None:
    if m.needs_choice:
        raise SubjectChoiceNeeded(CHOOSE_DANCER_MESSAGE)


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
        payload["subject"] = m.follow.status[t] if m.follow is not None else None
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

"""Dancer selection and clip-level quality gates (spec sections 11 'tracking suitability' and 12).

Tracking confidence is about whether we can *see* the body. It is never a dance score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from app.pose import landmarks as L
from app.pose.features import QualityConfig, TrackFeatures, confidence_of

FloatArray = NDArray[np.float64]

FailureCode = Literal["no_dancer_detected", "multiple_people", "low_coverage"]

FAILURE_MESSAGES: dict[str, str] = {
    "no_dancer_detected": (
        "We couldn't find a dancer in this video. Use a clip with one person whose shoulders "
        "and hips are clearly visible."
    ),
    "multiple_people": (
        "More than one person appears in much of this video. Crop or trim it so only one dancer "
        "is visible, then upload it again."
    ),
    "low_coverage": (
        "The dancer's body was only trackable in {coverage}% of the video. Record with the full "
        "body in frame, steady lighting and nothing blocking the view."
    ),
}

WARNING_MESSAGES: dict[str, str] = {
    "partial_coverage": "Part of the video couldn't be tracked; those moments are left out.",
    "cropped_body": (
        "Feet are out of frame for most of the clip; leg and footwork detail is limited."
    ),
    "low_tracking_confidence": "Tracking confidence is low; joint measurements may be noisy.",
    "brief_extra_person": "Another person appears briefly; we followed the main dancer.",
}


def _pose_root(pose: FloatArray) -> FloatArray:
    return np.asarray((pose[L.L_HIP, :2] + pose[L.R_HIP, :2]) / 2, dtype=np.float64)


def _pose_area(pose: FloatArray, threshold: float) -> float:
    conf = confidence_of(pose)
    pts = pose[conf >= threshold, :2]
    if len(pts) < 2:
        return 0.0
    span = pts.max(axis=0) - pts.min(axis=0)
    return float(span[0] * span[1])


def select_track(
    detections: list[list[FloatArray]],
    threshold: float = 0.5,
    *,
    max_jump: float = 0.2,
    reacquire_after: int = 12,
) -> tuple[FloatArray, NDArray[np.int64], NDArray[np.int64]]:
    """Pick one dancer per frame without silently switching identities.

    Start with the largest detected body; afterwards follow the detection whose hip midpoint
    is closest to the last chosen one. A detection whose hips are more than `max_jump`
    (image-normalized) away is treated as someone else, so that frame has no pose; after
    `reacquire_after` frames without our dancer the largest body is picked again. Returns
    (T,33,5) landmarks (NaN when no pose), the number of poses detected in each frame, and
    the chosen detection index (-1 = none).
    """
    t_count = len(detections)
    out = np.full((t_count, L.NUM_LANDMARKS, 5), np.nan)
    counts = np.zeros(t_count, dtype=np.int64)
    chosen_idx = np.full(t_count, -1, dtype=np.int64)
    last_root: FloatArray | None = None
    missing = 0
    for t, poses in enumerate(detections):
        counts[t] = len(poses)
        if not poses:
            missing += 1
            continue
        if last_root is not None and missing >= reacquire_after:
            last_root = None
        if last_root is None:
            k = max(range(len(poses)), key=lambda i: _pose_area(poses[i], threshold))
        else:
            lr = last_root
            k = min(
                range(len(poses)), key=lambda i: float(np.linalg.norm(_pose_root(poses[i]) - lr))
            )
            if float(np.linalg.norm(_pose_root(poses[k]) - lr)) > max_jump:
                missing += 1
                continue
        missing = 0
        out[t] = poses[k]
        chosen_idx[t] = k
        last_root = _pose_root(poses[k])
    return out, counts, chosen_idx


@dataclass
class QualityReport:
    analyzed_frames: int
    valid_frames: int
    coverage: float
    multi_person_fraction: float
    feet_visible_fraction: float
    mean_confidence: float
    measured_joint_confidence: float
    interpolated_frames: int
    failure: str | None
    failure_message: str | None
    warnings: list[str] = field(default_factory=list)
    excluded_joints: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "analyzed_frames": self.analyzed_frames,
            "valid_frames": self.valid_frames,
            "coverage": round(self.coverage, 4),
            "multi_person_fraction": round(self.multi_person_fraction, 4),
            "feet_visible_fraction": round(self.feet_visible_fraction, 4),
            "mean_confidence": round(self.mean_confidence, 4),
            "measured_joint_confidence": round(self.measured_joint_confidence, 4),
            "interpolated_frames": self.interpolated_frames,
            "failure": self.failure,
            "failure_message": self.failure_message,
            "warnings": list(self.warnings),
            "excluded_joints": dict(self.excluded_joints),
        }


def assess(
    f: TrackFeatures, poses_per_frame: NDArray[np.int64], cfg: QualityConfig | None = None
) -> QualityReport:
    cfg = cfg or QualityConfig()
    total = len(f.valid)
    valid_n = int(f.valid.sum())
    coverage = valid_n / total if total else 0.0
    multi = float((poses_per_frame >= 2).mean()) if total else 0.0
    if valid_n:
        feet = f.reliable[f.valid][:, [L.L_ANKLE, L.R_ANKLE]].all(axis=1)
        feet_fraction = float(feet.mean())
        mean_conf = float(f.confidence[f.valid].mean())
        # Confidence of the joints we actually measure (out-of-frame joints are already
        # reported as cropped/excluded and must not double-count as "noisy tracking").
        conf = confidence_of(f.raw)[f.valid][:, list(L.MAJOR)]
        used = f.reliable[f.valid][:, list(L.MAJOR)]
        measured_conf = float(conf[used].mean()) if used.any() else 0.0
    else:
        feet_fraction, mean_conf, measured_conf = 0.0, 0.0, 0.0
    interp_frames = int((f.interpolated[:, list(L.CORE)].any(axis=1) & ~f.valid).sum())

    failure: str | None = None
    if int((poses_per_frame > 0).sum()) == 0:
        failure = "no_dancer_detected"
    elif multi > cfg.max_multi_person_fraction:
        failure = "multiple_people"
    elif coverage < cfg.fail_coverage or valid_n < cfg.min_valid_frames:
        failure = "low_coverage"

    warnings: list[str] = []
    if failure is None:
        if coverage < cfg.warn_coverage:
            warnings.append("partial_coverage")
        if feet_fraction < cfg.min_feet_visible_fraction:
            warnings.append("cropped_body")
        if measured_conf < 0.75:
            warnings.append("low_tracking_confidence")
        if multi > 0:
            warnings.append("brief_extra_person")

    message = None
    if failure is not None:
        message = FAILURE_MESSAGES[failure].format(coverage=round(coverage * 100))
    return QualityReport(
        analyzed_frames=total,
        valid_frames=valid_n,
        coverage=coverage,
        multi_person_fraction=multi,
        feet_visible_fraction=feet_fraction,
        mean_confidence=mean_conf,
        measured_joint_confidence=measured_conf,
        interpolated_frames=interp_frames,
        failure=failure,
        failure_message=message,
        warnings=warnings,
        excluded_joints=f.exclusions,
    )

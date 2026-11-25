"""Pure movement math: validity, smoothing, normalization, angles and motion features.

Spec sections 12–13. Input is a landmark track already selected for one dancer:

- `lm`: (T, 33, 5) float array of image-normalized x, y, z, visibility, presence
  (NaN rows where no pose was detected);
- `times`: (T,) seconds on the canonical timeline;
- frame size in pixels (for aspect-ratio correction).

Everything here is deterministic and free of I/O so it can be unit-tested with synthetic
landmark sequences (the only place synthetic landmarks are allowed).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from app.pose import landmarks as L
from app.pose.smoothing import fill_short_gaps, one_euro

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]

# Approximate segment mass fractions (after Dempster/Winter, simplified to what BlazePose
# sees). Used only for a clearly labelled centre-of-mass *estimate*.
_COM_SEGMENTS: tuple[tuple[tuple[int, ...], float], ...] = (
    ((L.NOSE,), 0.08),
    ((L.L_SHOULDER, L.R_SHOULDER, L.L_HIP, L.R_HIP), 0.50),
    ((L.L_SHOULDER, L.L_ELBOW), 0.03),
    ((L.R_SHOULDER, L.R_ELBOW), 0.03),
    ((L.L_ELBOW, L.L_WRIST), 0.02),
    ((L.R_ELBOW, L.R_WRIST), 0.02),
    ((L.L_HIP, L.L_KNEE), 0.10),
    ((L.R_HIP, L.R_KNEE), 0.10),
    ((L.L_KNEE, L.L_ANKLE), 0.06),
    ((L.R_KNEE, L.R_ANKLE), 0.06),
)


@dataclass(frozen=True)
class QualityConfig:
    visibility_threshold: float = 0.5
    min_major_joints: int = 8
    max_gap_frames: int = 2
    fail_coverage: float = 0.55
    warn_coverage: float = 0.85
    max_multi_person_fraction: float = 0.2
    min_feet_visible_fraction: float = 0.5
    min_valid_frames: int = 6


@dataclass
class TrackFeatures:
    times: FloatArray
    raw: FloatArray  # (T,33,5) as detected
    smoothed: FloatArray  # (T,33,3) image-normalized x,y,z after smoothing / gap fill (NaN = none)
    reliable: BoolArray  # (T,33) landmark measured with enough confidence
    interpolated: BoolArray  # (T,33) bridged short gap (display only, never scored as measured)
    valid: BoolArray  # (T,) frame passes the core-body gate
    confidence: FloatArray  # (T,) mean confidence of major joints (0 when no pose)
    scale: float  # robust torso length in aspect-corrected image-height units
    norm: FloatArray  # (T,33,3) hip-centred, torso-scaled (NaN where unreliable)
    angles: dict[str, FloatArray]  # degrees, NaN when any landmark is unreliable
    root: FloatArray  # (T,2) hip midpoint, aspect-corrected image units
    travel: FloatArray  # (T,2) root displacement from first valid frame, torso units
    com: FloatArray  # (T,2) estimated centre of mass, hip-centred torso units
    speed: FloatArray  # (T,33) landmark speed, torso units / s (NaN when unknown)
    energy: FloatArray  # (T,) mean speed of reliable major joints
    lean: FloatArray  # (T,) torso lean from vertical, degrees (+ = leaning to image right)
    shoulder_tilt: FloatArray  # (T,) degrees
    hip_tilt: FloatArray  # (T,) degrees
    yaw: FloatArray  # (T,) EXPERIMENTAL facing estimate, degrees (0 = facing camera)
    exclusions: dict[str, int] = field(default_factory=dict)


def confidence_of(lm: FloatArray) -> FloatArray:
    """Per-landmark confidence = min(visibility, presence); 0 where nothing was detected."""
    conf = np.minimum(lm[..., 3], lm[..., 4])
    return np.nan_to_num(conf, nan=0.0)


def frame_validity(reliable: BoolArray, cfg: QualityConfig) -> BoolArray:
    core = reliable[:, list(L.CORE)].all(axis=1)
    major = reliable[:, list(L.MAJOR)].sum(axis=1) >= cfg.min_major_joints
    return np.asarray(core & major, dtype=bool)


def aspect_correct(xyz: FloatArray, width: int, height: int) -> FloatArray:
    """Image-normalized → units of image height, so x and y distances are comparable.
    MediaPipe z uses roughly the same scale as x."""
    k = width / height
    out = xyz.copy()
    out[..., 0] *= k
    out[..., 2] *= k
    return out


def _angle(a: FloatArray, b: FloatArray, c: FloatArray) -> FloatArray:
    """Angle ABC in degrees for (T,2) arrays; NaN propagates."""
    ba = a - b
    bc = c - b
    dot = (ba * bc).sum(axis=-1)
    n = np.linalg.norm(ba, axis=-1) * np.linalg.norm(bc, axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        cos = np.clip(dot / n, -1.0, 1.0)
        out = np.degrees(np.arccos(cos))
    out[n < 1e-9] = np.nan
    return np.asarray(out, dtype=np.float64)


def _tilt(a: FloatArray, b: FloatArray) -> FloatArray:
    """Signed angle of line a→b from horizontal, degrees (image y points down)."""
    d = b - a
    with np.errstate(invalid="ignore"):
        return np.asarray(np.degrees(np.arctan2(-d[:, 1], np.abs(d[:, 0]))), dtype=np.float64)


def compute_features(
    lm: FloatArray,
    times: FloatArray,
    width: int,
    height: int,
    cfg: QualityConfig | None = None,
) -> TrackFeatures:
    cfg = cfg or QualityConfig()
    t_count = lm.shape[0]
    conf = confidence_of(lm)
    reliable = np.asarray(conf >= cfg.visibility_threshold, dtype=bool)
    valid = frame_validity(reliable, cfg)
    frame_conf = np.where(np.isnan(lm[:, 0, 0]), 0.0, conf[:, list(L.MAJOR)].mean(axis=1)).astype(
        np.float64
    )

    # Smooth each reliable landmark coordinate; bridge only short gaps, and mark them.
    smoothed = np.full((t_count, L.NUM_LANDMARKS, 3), np.nan)
    interpolated = np.zeros((t_count, L.NUM_LANDMARKS), dtype=bool)
    for j in range(L.NUM_LANDMARKS):
        mask = reliable[:, j]
        for d in range(3):
            filt = one_euro(lm[:, j, d].astype(np.float64), times, mask)
            filled, interp = fill_short_gaps(filt, mask, cfg.max_gap_frames)
            smoothed[:, j, d] = filled
            if d == 0:
                interpolated[:, j] = interp

    pts = aspect_correct(smoothed, width, height)
    measured = np.where(reliable[..., None], pts, np.nan)  # features use measured points only

    mid_sh = (measured[:, L.L_SHOULDER, :2] + measured[:, L.R_SHOULDER, :2]) / 2
    mid_hip = (measured[:, L.L_HIP, :2] + measured[:, L.R_HIP, :2]) / 2
    torso = np.linalg.norm(mid_sh - mid_hip, axis=1)
    torso_valid = torso[valid & ~np.isnan(torso)]
    scale = float(np.median(torso_valid)) if torso_valid.size else float("nan")

    root = mid_hip
    norm = np.full_like(measured, np.nan)
    if math.isfinite(scale) and scale > 0:
        norm[..., :2] = (measured[..., :2] - root[:, None, :]) / scale
        norm[..., 2] = measured[..., 2] / scale

    first_valid = int(np.argmax(valid)) if valid.any() else -1
    travel = np.full((t_count, 2), np.nan)
    if first_valid >= 0 and math.isfinite(scale) and scale > 0:
        travel = (root - root[first_valid]) / scale

    angles: dict[str, FloatArray] = {}
    xy = measured[..., :2]
    for name, (a, b, c) in L.ANGLES.items():
        angles[name] = _angle(xy[:, a], xy[:, b], xy[:, c])

    # Speed in torso units per second from absolute (root-including) positions.
    speed = np.full((t_count, L.NUM_LANDMARKS), np.nan)
    if t_count >= 2 and math.isfinite(scale) and scale > 0:
        absn = xy / scale
        dt = np.gradient(times)
        for j in range(L.NUM_LANDMARKS):
            g = np.gradient(absn[:, j, :], axis=0) / dt[:, None]
            speed[:, j] = np.linalg.norm(g, axis=1)
    with np.errstate(invalid="ignore"):
        major_speed = speed[:, list(L.MAJOR)]
        counts = (~np.isnan(major_speed)).sum(axis=1)
        energy = np.where(
            counts > 0, np.nansum(major_speed, axis=1) / np.maximum(counts, 1), np.nan
        )

    com = np.full((t_count, 2), np.nan)
    for t in range(t_count):
        if not valid[t]:
            continue
        acc = np.zeros(2)
        wsum = 0.0
        for idxs, w in _COM_SEGMENTS:
            seg = norm[t, list(idxs), :2]
            if np.isnan(seg).any():
                continue
            acc += seg.mean(axis=0) * w
            wsum += w
        if wsum >= 0.7:  # renormalise only when most of the mass is visible
            com[t] = acc / wsum

    lean_vec = mid_sh - mid_hip
    with np.errstate(invalid="ignore"):
        lean = np.degrees(np.arctan2(lean_vec[:, 0], -lean_vec[:, 1]))
    shoulder_tilt = _tilt(measured[:, L.R_SHOULDER, :2], measured[:, L.L_SHOULDER, :2])
    hip_tilt = _tilt(measured[:, L.R_HIP, :2], measured[:, L.L_HIP, :2])

    # EXPERIMENTAL yaw: shoulder width relative to its widest observed span, signed by the
    # depth difference between shoulders. Monocular depth is weak; label it as such everywhere.
    sw = np.abs(measured[:, L.L_SHOULDER, 0] - measured[:, L.R_SHOULDER, 0])
    sw_valid = sw[valid & ~np.isnan(sw)]
    yaw = np.full(t_count, np.nan)
    if sw_valid.size:
        ref = float(np.percentile(sw_valid, 95))
        if ref > 0:
            ratio = np.clip(sw / ref, 0.0, 1.0)
            dz = measured[:, L.L_SHOULDER, 2] - measured[:, L.R_SHOULDER, 2]
            with np.errstate(invalid="ignore"):
                yaw = np.degrees(np.arccos(ratio)) * np.sign(dz)

    exclusions: dict[str, int] = {}
    for j in L.MAJOR:
        missing = int((~reliable[valid, j]).sum())
        if missing:
            exclusions[L.NAMES[j]] = missing

    return TrackFeatures(
        times=times,
        raw=lm,
        smoothed=smoothed,
        reliable=reliable,
        interpolated=interpolated,
        valid=valid,
        confidence=frame_conf,
        scale=scale,
        norm=norm,
        angles=angles,
        root=root,
        travel=travel,
        com=com,
        speed=speed,
        energy=np.asarray(energy, dtype=np.float64),
        lean=np.asarray(lean, dtype=np.float64),
        shoulder_tilt=shoulder_tilt,
        hip_tilt=hip_tilt,
        yaw=np.asarray(yaw, dtype=np.float64),
        exclusions=exclusions,
    )


def _r(v: float, nd: int = 4) -> float | None:
    return None if v is None or not math.isfinite(v) else round(float(v), nd)


def frame_payload(f: TrackFeatures, t: int, poses_detected: int) -> dict[str, Any]:
    """JSON payload stored per analysed frame (reference_pose_frames.payload)."""
    raw = f.raw[t]
    has_pose = not math.isnan(float(raw[0, 0]))
    lm = [[_r(v) for v in raw[j]] for j in range(L.NUM_LANDMARKS)] if has_pose else None
    smooth = [
        None if math.isnan(float(f.smoothed[t, j, 0])) else [_r(v) for v in f.smoothed[t, j]]
        for j in range(L.NUM_LANDMARKS)
    ]
    norm = [
        None if math.isnan(float(f.norm[t, j, 0])) else [_r(v) for v in f.norm[t, j]]
        for j in range(L.NUM_LANDMARKS)
    ]
    return {
        "poses_detected": poses_detected,
        "landmarks": lm,
        "smoothed": smooth,
        "reliable": [bool(b) for b in f.reliable[t]],
        "interpolated": [bool(b) for b in f.interpolated[t]],
        "normalized": norm,
        "angles": {k: _r(v[t], 1) for k, v in f.angles.items()},
        "root": [_r(v) for v in f.root[t]],
        "travel": [_r(v) for v in f.travel[t]],
        "com_estimate": [_r(v) for v in f.com[t]],
        "speed": [_r(v, 3) for v in f.speed[t]],
        "motion_energy": _r(f.energy[t], 3),
        "torso_lean": _r(f.lean[t], 1),
        "shoulder_tilt": _r(f.shoulder_tilt[t], 1),
        "hip_tilt": _r(f.hip_tilt[t], 1),
        "yaw_experimental": _r(f.yaw[t], 1),
    }

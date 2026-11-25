"""Choreography segmentation: deterministic, suggestion-only section boundaries (spec 14).

Pure functions over per-frame movement features already measured by the pose pipeline:

- `times`: (T,) analysed-frame timestamps in seconds;
- `energy`: (T,) motion energy (mean speed of reliable major joints, torso units/s), NaN = unknown;
- `pose`: (T, J, 2) hip-centred, torso-scaled major-joint positions, NaN = unreliable.

The algorithm scores every analysed frame as a candidate cut ("how natural a boundary is here")
from low motion energy, local pauses, direction reversals and pose transitions, then picks the
set of cuts that minimises cut cost + a section-length penalty with dynamic programming.
Sections prefer 3–7 s, are never shorter than `min_len` or longer than `max_len` (unless the
whole clip is shorter), and always tile [0, duration] exactly.

Boundaries are suggestions about movement changes only; nothing here claims to understand
choreography, music or style. Users can edit every boundary (`validate_sections`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from app.pose.section_rules import InvalidSections, SegmentationConfig, validate_sections

FloatArray = NDArray[np.float64]

SEGMENTATION_VERSION = "seg-1"

__all__ = [
    "SEGMENTATION_VERSION",
    "CutScores",
    "InvalidSections",
    "SegmentationConfig",
    "cut_scores",
    "suggest_boundaries",
    "validate_sections",
]


@dataclass(frozen=True)
class CutScores:
    """Per-frame boundary cost in [0, 1] (lower = more natural place to cut) and its parts."""

    cost: FloatArray
    energy: FloatArray  # smoothed, normalised 0..1 (NaN = unknown)
    pause: FloatArray  # 1 where this frame is a local energy minimum
    reversal: FloatArray  # 0..1 direction reversal strength
    transition: FloatArray  # 0..1 pose change between the windows before/after


def _moving_mean(x: FloatArray, half: int) -> FloatArray:
    """NaN-aware centred moving average."""
    out = np.full_like(x, np.nan)
    n = len(x)
    for i in range(n):
        w = x[max(0, i - half) : min(n, i + half + 1)]
        w = w[~np.isnan(w)]
        if w.size:
            out[i] = float(w.mean())
    return out


def _frames(seconds: float, times: FloatArray) -> int:
    if len(times) < 2:
        return 1
    dt = float(np.median(np.diff(times)))
    return max(1, int(round(seconds / dt))) if dt > 0 else 1


def cut_scores(
    times: FloatArray,
    energy: FloatArray,
    pose: FloatArray,
    cfg: SegmentationConfig | None = None,
) -> CutScores:
    cfg = cfg or SegmentationConfig()
    n = len(times)
    if n == 0:
        z = np.zeros(0)
        return CutScores(z, z, z, z, z)

    e = _moving_mean(energy.astype(np.float64), _frames(cfg.smooth_window_s, times) // 2)
    finite = e[~np.isnan(e)]
    ref = float(np.percentile(finite, 90)) if finite.size else 0.0
    # A clip with (almost) no movement anywhere: every frame is an equally good place to cut.
    e_norm = np.clip(e / ref, 0.0, 1.0) if ref > 0.05 else np.where(np.isnan(e), np.nan, 0.0)

    # Local pauses: frame is the minimum of its neighbourhood and clearly below the clip's level.
    half_p = _frames(cfg.pause_window_s, times)
    pause = np.zeros(n)
    for i in range(n):
        if math.isnan(e_norm[i]):
            continue
        w = e_norm[max(0, i - half_p) : min(n, i + half_p + 1)]
        w = w[~np.isnan(w)]
        if w.size and e_norm[i] <= float(w.min()) + 1e-9 and e_norm[i] < 0.6:
            pause[i] = 1.0

    # Direction reversals and pose transitions from the joint positions either side of a frame.
    half_r = _frames(cfg.reversal_window_s, times)
    reversal = np.zeros(n)
    transition = np.zeros(n)
    for i in range(half_r, n - half_r):
        before = pose[i] - pose[i - half_r]  # (J, 2)
        after = pose[i + half_r] - pose[i]
        ok = ~(np.isnan(before).any(axis=1) | np.isnan(after).any(axis=1))
        if ok.sum() < 3:
            continue
        b, a = before[ok], after[ok]
        nb, na = np.linalg.norm(b, axis=1), np.linalg.norm(a, axis=1)
        moving = (nb > 0.05) & (na > 0.05)  # ignore jitter of still joints
        if moving.sum() >= 2:
            cos = (b[moving] * a[moving]).sum(axis=1) / (nb[moving] * na[moving])
            reversal[i] = float(np.clip(-cos.mean(), 0.0, 1.0))
        span = pose[i + half_r] - pose[i - half_r]
        ok2 = ~np.isnan(span).any(axis=1)
        if ok2.sum() >= 3:
            transition[i] = float(np.clip(np.linalg.norm(span[ok2], axis=1).mean() / 1.0, 0.0, 1.0))

    cost = np.where(
        np.isnan(e_norm),
        cfg.unknown_cost,
        0.65 * np.nan_to_num(e_norm) - 0.15 * pause - 0.1 * reversal - 0.1 * transition + 0.35,
    )
    cost = np.clip(cost, 0.0, 1.0)
    return CutScores(cost, e_norm, pause, reversal, transition)


def _length_penalty(length: float, cfg: SegmentationConfig) -> float:
    pen = ((length - cfg.pref_len) / (cfg.pref_max - cfg.pref_min)) ** 2 * 0.3
    if length < cfg.pref_min:
        pen += (cfg.pref_min - length) * 0.5
    if length > cfg.pref_max:
        pen += (length - cfg.pref_max) * 0.5
    return pen


def suggest_boundaries(
    times: FloatArray,
    energy: FloatArray,
    pose: FloatArray,
    duration: float,
    cfg: SegmentationConfig | None = None,
) -> list[tuple[float, float]]:
    """Automatic sections as (start, end) pairs covering [0, duration] without gaps or overlap."""
    cfg = cfg or SegmentationConfig()
    if not math.isfinite(duration) or duration <= 0:
        return []
    duration = round(float(duration), 3)
    if duration <= cfg.pref_max or duration < 2 * cfg.min_len:
        return [(0.0, duration)]

    scores = cut_scores(times, energy, pose, cfg)
    # Candidate cuts: analysed frames that leave at least min_len on both ends.
    cand = [
        (round(float(t), 3), float(c))
        for t, c in zip(times, scores.cost, strict=True)
        if cfg.min_len <= t <= duration - cfg.min_len
    ]
    points = [(0.0, 0.0), *cand, (duration, 0.0)]
    m = len(points)
    best = [math.inf] * m
    prev = [-1] * m
    best[0] = 0.0
    for j in range(1, m):
        tj, cj = points[j]
        cut = 0.0 if j == m - 1 else cj + cfg.boundary_penalty
        for i in range(j - 1, -1, -1):
            length = tj - points[i][0]
            if length < cfg.min_len - 1e-9:
                continue
            if length > cfg.max_len + 1e-9:
                break
            if best[i] == math.inf:
                continue
            total = best[i] + _length_penalty(length, cfg) + cut
            if total < best[j] - 1e-12:
                best[j] = total
                prev[j] = i
    if best[m - 1] == math.inf:  # no feasible tiling (sparse frames): fall back to even split
        k = max(1, math.ceil(duration / cfg.pref_len))
        edges = [round(duration * i / k, 3) for i in range(k + 1)]
        return list(zip(edges[:-1], edges[1:], strict=True))
    cuts: list[float] = []
    j = m - 1
    while j > 0:
        cuts.append(points[j][0])
        j = prev[j]
    edges = [0.0, *reversed(cuts)]
    return list(zip(edges[:-1], edges[1:], strict=True))

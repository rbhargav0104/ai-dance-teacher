"""Normalized, mirror-aware, bounded temporal alignment of a learner attempt to a reference
window (spec 13 'Mirroring', spec 17, Outcome 6).

Pure and deterministic: input is the per-frame payload already stored for both videos (the
same features from the same pipeline), output is a JSON-ready dict. Nothing here is a score —
Outcome 7 turns these measurements into versioned scores.

Design (all coefficients live in `AlignConfig` and are versioned by `ALIGN_VERSION`):

* Shape = hip-centred, torso-scaled landmarks (features.py), then one extra *global* body-size
  factor for the learner: the median ratio of reference/learner limb-segment lengths. Torso
  length alone is fragile when the hips sit on the frame edge (measured 2026-11-27).
* Mirroring: the learner is compared both as recorded ("direct") and reflected with left/right
  swapped ("mirrored"). The cheaper interpretation wins only when it is clearly cheaper;
  otherwise the declared/default mode is kept and the decision is marked ambiguous.
* Per-pair cost = visibility-masked landmark distance (depth down-weighted) + joint-angle error
  + torso-lean difference + motion-direction disagreement. A pair where either frame lacks
  enough measured joints is *unmeasured* (fixed cost, never counted as wrong).
* Bounded DTW: a pair is only allowed when the timestamps differ by at most the band
  (Sakoe-Chiba style, in seconds). Non-diagonal steps pay a warp penalty. The learner may
  start late / stop late (free leading and trailing learner frames); every reference frame
  must be matched.
* Original timestamps are kept for every pair, so timing (offset, speed, local lateness) is
  measured after the alignment instead of being erased by it.
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from app.pose import landmarks as L

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]

ALIGN_VERSION = "align-1"

# Joints compared for shape and motion (MediaPipe indices).
COMPARE_JOINTS: tuple[int, ...] = L.MAJOR
# Angles compared (names from landmarks.ANGLES); ankles are too noisy on monocular video.
COMPARE_ANGLES: tuple[str, ...] = (
    "left_elbow",
    "right_elbow",
    "left_shoulder",
    "right_shoulder",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
)
# Segments used for the global body-size factor (landmark index pairs).
SIZE_SEGMENTS: tuple[tuple[int, int], ...] = (
    (L.L_SHOULDER, L.R_SHOULDER),
    (L.L_SHOULDER, L.L_ELBOW),
    (L.R_SHOULDER, L.R_ELBOW),
    (L.L_ELBOW, L.L_WRIST),
    (L.R_ELBOW, L.R_WRIST),
    (L.L_HIP, L.L_KNEE),
    (L.R_HIP, L.R_KNEE),
    (L.L_KNEE, L.L_ANKLE),
    (L.R_KNEE, L.R_ANKLE),
)


@dataclass(frozen=True)
class AlignConfig:
    # Per-pair cost mixture. Each term is ~1.0 for "clearly different".
    w_position: float = 0.45
    w_angle: float = 0.30
    w_lean: float = 0.10
    w_direction: float = 0.15
    position_unit: float = 0.6  # torso lengths of mean joint distance that cost 1.0
    angle_unit_deg: float = 60.0
    lean_unit_deg: float = 30.0
    z_weight: float = 0.3  # monocular depth is weaker than x/y
    moving_speed: float = 0.6  # torso lengths / s: below this a joint counts as still
    term_cap: float = 2.0
    pair_scale_clamp: float = 0.15  # per-pair uniform scale fit, ±15 %
    focus_joints: int = 3  # position term = ½ mean + ½ mean of the 3 worst joints
    focus_angles: int = 2
    min_shared_joints: int = 6
    min_shared_angles: int = 3
    unmeasured_cost: float = 0.8  # pass 1; pass 2 uses the attempt's median measured cost
    unmeasured_floor: float = 0.1
    # Alignment.
    step_penalty: float = 0.15  # per non-diagonal DTW step
    band_min_s: float = 2.0
    band_fraction: float = 0.35  # of the reference window duration
    max_frames: int = 360  # per side, before strided downsampling
    # Mirror decision.
    mirror_margin: float = 0.10  # relative cost advantage needed to switch interpretation
    # Body-size factor.
    size_min_frames: int = 5
    size_clamp: tuple[float, float] = (0.67, 1.5)
    # Accounting.
    miss_cost: float = 0.75  # measured pair at/above this cost = clearly different movement
    still_ratio: float = 0.3  # learner energy below this share of the reference = not moving
    reference_moving_energy: float = 0.15  # torso lengths / s (absolute floor)
    reference_moving_share: float = 0.5  # ... and at least half the window's median energy
    min_span_s: float = 0.5
    bridge_masked_s: float = 1.0  # untracked frames inside a missed passage don't split it
    timing_tolerance_s: float = 0.3
    min_valid_frames: int = 6
    min_measured_fraction: float = 0.5
    immobile_energy: float = 0.1  # median reference energy below this = no choreography


@dataclass
class AlignSeq:
    """Comparison features of one video window (frames at the analysis rate)."""

    times: FloatArray  # (T,) seconds from the window start
    source_times: FloatArray  # (T,) seconds on the video's own canonical timeline
    pos: FloatArray  # (T,J,3) normalized, NaN where unreliable
    angles: FloatArray  # (T,A) degrees, NaN where unreliable
    lean: FloatArray  # (T,) degrees
    vel: FloatArray  # (T,J,2) torso lengths / s of the body shape (hip-relative)
    energy: FloatArray  # (T,) motion energy (absolute, torso lengths / s)
    usable: BoolArray  # (T,) frame valid and enough joints measured

    def __len__(self) -> int:
        return int(self.times.shape[0])


def _num(v: Any) -> float:
    return float(v) if isinstance(v, int | float) and math.isfinite(float(v)) else math.nan


def sequence_from_payloads(
    source_times: Sequence[float],
    payloads: Sequence[dict[str, Any]],
    valid: Sequence[bool],
    *,
    start: float = 0.0,
    cfg: AlignConfig | None = None,
) -> AlignSeq:
    """Build comparison features from stored per-frame payloads (features.frame_payload)."""
    cfg = cfg or AlignConfig()
    t_count = len(payloads)
    j_count = len(COMPARE_JOINTS)
    pos = np.full((t_count, j_count, 3), np.nan)
    angles = np.full((t_count, len(COMPARE_ANGLES)), np.nan)
    lean = np.full(t_count, np.nan)
    energy = np.full(t_count, np.nan)
    for t, p in enumerate(payloads):
        if not valid[t]:
            continue
        norm = p.get("normalized") or []
        reliable = p.get("reliable") or []
        for k, j in enumerate(COMPARE_JOINTS):
            pt = norm[j] if j < len(norm) else None
            if pt is None or not (j < len(reliable) and reliable[j]):
                continue
            pos[t, k] = [_num(pt[0]), _num(pt[1]), _num(pt[2])]
        ang = p.get("angles") or {}
        for a, name in enumerate(COMPARE_ANGLES):
            angles[t, a] = _num(ang.get(name))
        lean[t] = _num(p.get("torso_lean"))
        energy[t] = _num(p.get("motion_energy"))
    times_src = np.asarray(source_times, dtype=np.float64)
    times = times_src - float(start)
    vel = _velocity(pos, times)
    shared = (~np.isnan(pos[..., 0])).sum(axis=1)
    usable = np.asarray(valid, dtype=bool) & (shared >= cfg.min_shared_joints)
    return AlignSeq(times, times_src, pos, angles, lean, vel, energy, usable)


def _velocity(pos: FloatArray, times: FloatArray) -> FloatArray:
    """Central-difference velocity of hip-relative shape; NaN where a neighbour is missing."""
    t_count = pos.shape[0]
    vel = np.full(pos.shape[:2] + (2,), np.nan)
    if t_count < 2:
        return vel
    for t in range(t_count):
        a = max(t - 1, 0)
        b = min(t + 1, t_count - 1)
        dt = times[b] - times[a]
        if dt <= 0:
            continue
        vel[t] = (pos[b, :, :2] - pos[a, :, :2]) / dt
    return vel


def window(seq: AlignSeq, lo: float, hi: float) -> AlignSeq:
    """Frames whose window time lies in [lo, hi] (inclusive)."""
    m = (seq.times >= lo - 1e-6) & (seq.times <= hi + 1e-6)
    return AlignSeq(
        seq.times[m],
        seq.source_times[m],
        seq.pos[m],
        seq.angles[m],
        seq.lean[m],
        seq.vel[m],
        seq.energy[m],
        seq.usable[m],
    )


def downsample(seq: AlignSeq, max_frames: int) -> tuple[AlignSeq, int]:
    n = len(seq)
    if n <= max_frames:
        return seq, 1
    stride = math.ceil(n / max_frames)
    idx = np.arange(0, n, stride)
    return (
        AlignSeq(
            seq.times[idx],
            seq.source_times[idx],
            seq.pos[idx],
            seq.angles[idx],
            seq.lean[idx],
            seq.vel[idx],
            seq.energy[idx],
            seq.usable[idx],
        ),
        stride,
    )


# Indices into COMPARE_JOINTS / COMPARE_ANGLES of each item's anatomical opposite.
_JOINT_SWAP = tuple(COMPARE_JOINTS.index(L.MIRROR[j]) for j in COMPARE_JOINTS)


def _angle_swap() -> tuple[int, ...]:
    out = []
    for name in COMPARE_ANGLES:
        other = (
            "right_" + name[5:]
            if name.startswith("left_")
            else "left_" + name[6:]
            if name.startswith("right_")
            else name
        )
        out.append(COMPARE_ANGLES.index(other))
    return tuple(out)


_ANGLE_SWAP = _angle_swap()


def mirrored(seq: AlignSeq) -> AlignSeq:
    """Reflect across the vertical axis and swap left/right labels (an anatomical mirror)."""
    pos = seq.pos[:, list(_JOINT_SWAP)].copy()
    pos[..., 0] *= -1
    vel = seq.vel[:, list(_JOINT_SWAP)].copy()
    vel[..., 0] *= -1
    return AlignSeq(
        seq.times.copy(),
        seq.source_times.copy(),
        pos,
        seq.angles[:, list(_ANGLE_SWAP)].copy(),
        -seq.lean,
        vel,
        seq.energy.copy(),
        seq.usable.copy(),
    )


def _segment_lengths(seq: AlignSeq) -> FloatArray:
    """(S,) median length of each SIZE_SEGMENTS segment over usable frames (NaN if too few)."""
    out = np.full(len(SIZE_SEGMENTS), np.nan)
    for s, (a, b) in enumerate(SIZE_SEGMENTS):
        ka, kb = COMPARE_JOINTS.index(a), COMPARE_JOINTS.index(b)
        d = np.linalg.norm(seq.pos[:, ka, :2] - seq.pos[:, kb, :2], axis=1)
        d = d[seq.usable & ~np.isnan(d)]
        if d.size >= AlignConfig().size_min_frames:
            out[s] = float(np.median(d))
    return out


def body_size_factor(ref: AlignSeq, learner: AlignSeq, cfg: AlignConfig) -> tuple[float, int]:
    """Global factor that scales the learner's torso-normalized shape onto the reference's
    proportions: median of per-segment length ratios. Returns (factor, segments used)."""
    r = _segment_lengths(ref)
    u = _segment_lengths(learner)
    ok = ~np.isnan(r) & ~np.isnan(u) & (u > 1e-6)
    if ok.sum() < 3:
        return 1.0, int(ok.sum())
    f = float(np.median(r[ok] / u[ok]))
    lo, hi = cfg.size_clamp
    return float(min(max(f, lo), hi)), int(ok.sum())


def scaled(seq: AlignSeq, factor: float) -> AlignSeq:
    return AlignSeq(
        seq.times,
        seq.source_times,
        seq.pos * factor,
        seq.angles,
        seq.lean,
        seq.vel * factor,
        seq.energy * factor,
        seq.usable,
    )


@dataclass(frozen=True)
class CostTerms:
    total: FloatArray  # (N,M) per-pair cost (unmeasured pairs = cfg.unmeasured_cost)
    measured: BoolArray  # (N,M) both frames usable and enough shared joints/angles
    position: FloatArray
    angle: FloatArray
    lean: FloatArray
    direction: FloatArray


def _nanmean_last(x: FloatArray, axis: int = -1) -> tuple[FloatArray, NDArray[np.int64]]:
    cnt = (~np.isnan(x)).sum(axis=axis)
    s = np.nansum(x, axis=axis)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(cnt > 0, s / np.maximum(cnt, 1), np.nan)
    return np.asarray(mean, dtype=np.float64), np.asarray(cnt, dtype=np.int64)


def _focus_mean(x: FloatArray, k: int) -> tuple[FloatArray, NDArray[np.int64]]:
    """0.5 × mean + 0.5 × mean of the k largest values over the last axis (NaN ignored), so
    one clearly wrong limb is not diluted away by many correct joints."""
    mean, cnt = _nanmean_last(x)
    filled = np.where(np.isnan(x), -np.inf, x)
    top = -np.sort(-filled, axis=-1)[..., :k]
    top_ok = np.isfinite(top)
    with np.errstate(invalid="ignore", divide="ignore"):
        top_mean = np.where(
            top_ok.sum(axis=-1) > 0,
            np.where(top_ok, top, 0.0).sum(axis=-1) / np.maximum(top_ok.sum(axis=-1), 1),
            np.nan,
        )
    return np.asarray(0.5 * mean + 0.5 * top_mean, dtype=np.float64), cnt


def pair_costs(ref: AlignSeq, learner: AlignSeq, cfg: AlignConfig) -> CostTerms:
    """Documented per-pair cost for every (reference frame, learner frame)."""
    rp = ref.pos[:, None]  # (N,1,J,3)
    up = learner.pos[None]  # (1,M,J,3)
    both = ~np.isnan(rp[..., 0]) & ~np.isnan(up[..., 0])  # (N,M,J)
    # Per pair, remove the mean offset of the joints measured on both and fit one uniform
    # scale (clamped to ±cfg.pair_scale_clamp around the global factor). The hip root is the
    # least reliable landmark on cropped footage (hips on the frame edge): a misplaced root or
    # torso length would otherwise move or stretch every joint. One wrong limb still shows,
    # because the fit uses all shared joints and its scale is tightly bounded.
    with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN pairs stay NaN
        rm = np.where(both[..., None], rp, np.nan)
        um = np.where(both[..., None], up, np.nan)
        rc = rm - np.nanmean(rm, axis=2, keepdims=True)
        uc = um - np.nanmean(um, axis=2, keepdims=True)
        num = np.nansum((rc[..., :2] * uc[..., :2]).sum(axis=-1), axis=2)
        den = np.nansum((uc[..., :2] ** 2).sum(axis=-1), axis=2)
        k = np.where(den > 1e-9, num / np.maximum(den, 1e-9), 1.0)
    lo, hi = 1 - cfg.pair_scale_clamp, 1 + cfg.pair_scale_clamp
    k = np.clip(k, lo, hi)
    diff = rc - uc * k[..., None, None]
    w = np.array([1.0, 1.0, cfg.z_weight])
    dist = np.sqrt(np.einsum("nmjk,k->nmj", diff * diff, w * w))  # (N,M,J)
    pos_mean, shared = _focus_mean(dist, cfg.focus_joints)
    position = np.minimum(pos_mean / cfg.position_unit, cfg.term_cap)

    ad = np.abs(ref.angles[:, None] - learner.angles[None])  # (N,M,A)
    ang_mean, shared_ang = _focus_mean(ad, cfg.focus_angles)
    angle = np.minimum(ang_mean / cfg.angle_unit_deg, cfg.term_cap)

    lean = np.minimum(
        np.abs(ref.lean[:, None] - learner.lean[None]) / cfg.lean_unit_deg, cfg.term_cap
    )

    # Direction: joints moving on at least one side. Same direction 0, still-vs-moving 0.5,
    # opposite 1.0. If neither side moves anything, the term is 0 (stillness agrees).
    rv = ref.vel[:, None]  # (N,1,J,2)
    uv = learner.vel[None]
    rs = np.linalg.norm(rv, axis=-1)
    us = np.linalg.norm(uv, axis=-1)
    r_mov = rs >= cfg.moving_speed
    u_mov = us >= cfg.moving_speed
    with np.errstate(invalid="ignore", divide="ignore"):
        cos = (rv * uv).sum(axis=-1) / (rs * us)
    both = r_mov & u_mov
    one = r_mov ^ u_mov
    dterm = np.where(both, (1 - np.clip(np.nan_to_num(cos), -1, 1)) / 2, np.nan)
    dterm = np.where(one, 0.5, dterm)
    known = ~np.isnan(rs) & ~np.isnan(us)
    dterm = np.where(known, dterm, np.nan)
    dir_mean, dir_cnt = _nanmean_last(dterm)
    any_known = known.sum(axis=-1) > 0
    direction = np.where(dir_cnt > 0, dir_mean, np.where(any_known, 0.0, np.nan))

    measured = (
        ref.usable[:, None]
        & learner.usable[None]
        & (shared >= cfg.min_shared_joints)
        & (shared_ang >= cfg.min_shared_angles)
    )
    # Weighted mixture; a missing optional term (lean/direction) is dropped and the rest
    # renormalised so the scale of the cost stays comparable.
    terms = [
        (position, cfg.w_position),
        (angle, cfg.w_angle),
        (lean, cfg.w_lean),
        (direction, cfg.w_direction),
    ]
    num = np.zeros(measured.shape)
    den = np.zeros(measured.shape)
    for arr, wt in terms:
        ok = ~np.isnan(arr)
        num += np.where(ok, arr * wt, 0.0)
        den += np.where(ok, wt, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        mix = np.where(den > 0, num / np.maximum(den, 1e-9), np.nan)
    total = np.where(measured & ~np.isnan(mix), mix, cfg.unmeasured_cost)
    measured = measured & ~np.isnan(mix)
    return CostTerms(total, measured, position, angle, lean, direction)


@dataclass(frozen=True)
class DtwResult:
    path: list[tuple[int, int]]  # (reference frame, learner frame), monotone
    total: float
    band: BoolArray  # (N,M) allowed cells


def bounded_dtw(
    cost: FloatArray, ref_t: FloatArray, learner_t: FloatArray, band_s: float, step_penalty: float
) -> DtwResult | None:
    """Sakoe-Chiba-like DTW in time: pair (i, j) allowed only if |t_l - t_r| <= band_s.
    Free learner frames before the first and after the last pair (open begin/end on the
    learner side); every reference frame is matched. None when no path fits the band."""
    n, m = cost.shape
    if n == 0 or m == 0:
        return None
    allowed = np.abs(learner_t[None, :] - ref_t[:, None]) <= band_s + 1e-9
    # A recording that stops before the reference passage ends may hold its last frame for
    # the remaining reference frames (reported as `attempt_ended_early_s`, never hidden).
    allowed[:, m - 1] |= ref_t >= learner_t[m - 1] - band_s
    inf = math.inf
    acc = np.full((n, m), inf)
    back = np.zeros((n, m), dtype=np.int8)  # 0 diag, 1 from (i-1, j), 2 from (i, j-1)
    acc[0] = np.where(allowed[0], cost[0], inf)
    for j in range(1, m):  # ref frame 0 held while learner advances: never better than a
        if allowed[0, j]:  # free start at j, so open begin covers it.
            back[0, j] = 0
    for i in range(1, n):
        cols = np.nonzero(allowed[i])[0]
        prev = acc[i - 1]
        row = acc[i]
        ci = cost[i]
        for j in cols:
            best = prev[j - 1] if j > 0 else inf
            mv = 0
            up = prev[j] + step_penalty
            if up < best:
                best, mv = up, 1
            if j > 0:
                left = row[j - 1] + step_penalty
                if left < best:
                    best, mv = left, 2
            if best < inf:
                row[j] = best + ci[j]
                back[i, j] = mv
    end = int(np.argmin(acc[n - 1]))
    if not math.isfinite(acc[n - 1, end]):
        return None
    path: list[tuple[int, int]] = []
    i, j = n - 1, end
    while True:
        path.append((i, j))
        if i == 0:
            break
        mv = back[i, j]
        if mv == 0:
            i, j = i - 1, j - 1
        elif mv == 1:
            i -= 1
        else:
            j -= 1
    path.reverse()
    return DtwResult(path, float(acc[n - 1, end]), allowed)


def _theil_sen(x: FloatArray, y: FloatArray, *, fallback: float) -> tuple[float, float]:
    """Robust line fit (median of pairwise slopes): a held tail or a noisy start does not
    tilt the learner's measured speed."""
    if x.size < 2:
        return 1.0, fallback
    i, j = np.triu_indices(x.size, k=1)
    dx = x[j] - x[i]
    keep = dx > 1e-6
    if not keep.any():
        return 1.0, fallback
    slope = float(np.median((y[j] - y[i])[keep] / dx[keep]))
    intercept = float(np.median(y - slope * x))
    return slope, intercept


def _bridge(flags: BoolArray, gaps: BoolArray, max_frames: int) -> BoolArray:
    """Join flagged runs separated only by `gaps` frames (e.g. untracked reference frames)
    when the gap is at most `max_frames` long, so one missed passage reads as one span."""
    out = flags.copy()
    n = len(flags)
    i = 0
    while i < n:
        if flags[i] or not gaps[i]:
            i += 1
            continue
        k = i
        while k + 1 < n and gaps[k + 1] and not flags[k + 1]:
            k += 1
        if i > 0 and flags[i - 1] and k + 1 < n and flags[k + 1] and (k - i + 1) <= max_frames:
            out[i : k + 1] = True
        i = k + 1
    return out


def _spans(times: FloatArray, flags: BoolArray, min_s: float, step: float) -> list[list[float]]:
    out: list[list[float]] = []
    n = len(flags)
    i = 0
    while i < n:
        if not flags[i]:
            i += 1
            continue
        k = i
        while k + 1 < n and flags[k + 1]:
            k += 1
        lo, hi = float(times[i]), float(times[k]) + step
        if hi - lo >= min_s - 1e-9:
            out.append([round(lo, 3), round(hi, 3)])
        i = k + 1
    return out


def _r(v: float, nd: int = 4) -> float | None:
    return None if v is None or not math.isfinite(v) else round(float(v), nd)


@dataclass(frozen=True)
class ModeTrial:
    mode: str
    seq: AlignSeq
    terms: CostTerms
    dtw: DtwResult | None
    mean_cost: float  # mean measured pair cost along the path (inf when no path)


def _trial(
    mode: str, ref: AlignSeq, learner: AlignSeq, cfg: AlignConfig, band_s: float
) -> ModeTrial:
    """Two passes. Pass 1 uses the fixed unmeasured cost; pass 2 prices unmeasured pairs at
    this attempt's own median measured cost (clamped), so the path neither detours to avoid
    untracked frames (holding one measured frame for seconds) nor hides in them."""
    terms = pair_costs(ref, learner, cfg)
    dtw = bounded_dtw(terms.total, ref.times, learner.times, band_s, cfg.step_penalty)
    if dtw is None:
        return ModeTrial(mode, learner, terms, None, math.inf)
    vals = [terms.total[i, j] for i, j in dtw.path if terms.measured[i, j]]
    if vals:
        neutral = min(max(float(np.median(vals)), cfg.unmeasured_floor), cfg.unmeasured_cost)
        total = np.where(terms.measured, terms.total, neutral)
        second = bounded_dtw(total, ref.times, learner.times, band_s, cfg.step_penalty)
        if second is not None:
            terms = CostTerms(
                total, terms.measured, terms.position, terms.angle, terms.lean, terms.direction
            )
            dtw = second
            vals = [terms.total[i, j] for i, j in dtw.path if terms.measured[i, j]]
    mean = float(np.mean(vals)) if vals else math.inf
    return ModeTrial(mode, learner, terms, dtw, mean)


def _equal_time_cost(terms: CostTerms, ref: AlignSeq, learner: AlignSeq) -> float | None:
    """Mean measured cost pairing frames at the same time (the naive baseline, for debug)."""
    vals = []
    for i, t in enumerate(ref.times):
        j = int(np.argmin(np.abs(learner.times - t)))
        if abs(float(learner.times[j]) - float(t)) <= 0.1 and terms.measured[i, j]:
            vals.append(terms.total[i, j])
    return _r(float(np.mean(vals))) if vals else None


def align(
    ref: AlignSeq,
    learner: AlignSeq,
    *,
    preferred_mode: str = "direct",
    cfg: AlignConfig | None = None,
) -> dict[str, Any]:
    """Align a learner attempt to a reference window. Returns a JSON-ready report with
    `status` 'aligned' or an honest reason why not ('insufficient_reference',
    'insufficient_tracking', 'out_of_band')."""
    cfg = cfg or AlignConfig()
    ref, ref_stride = downsample(ref, cfg.max_frames)
    learner, l_stride = downsample(learner, cfg.max_frames)
    base: dict[str, Any] = {
        "version": ALIGN_VERSION,
        "config": asdict(cfg),
        "reference_frames": len(ref),
        "learner_frames": len(learner),
        "downsample_stride": {"reference": ref_stride, "learner": l_stride},
        "scorable": False,
    }
    ref_usable = int(ref.usable.sum())
    l_usable = int(learner.usable.sum())
    base["reference_usable_frames"] = ref_usable
    base["learner_usable_frames"] = l_usable
    if len(ref) == 0 or ref_usable < cfg.min_valid_frames:
        return {
            **base,
            "status": "insufficient_reference",
            "message": "Too little of the dancer was tracked in this part of the reference.",
        }
    if len(learner) == 0 or l_usable < cfg.min_valid_frames:
        return {
            **base,
            "status": "insufficient_tracking",
            "message": "Too little of your body was tracked in this attempt to compare it.",
        }

    duration = float(ref.times[-1] - ref.times[0]) if len(ref) > 1 else 0.0
    step = float(np.median(np.diff(ref.times))) if len(ref) > 1 else 1 / 12
    band_s = max(cfg.band_min_s, cfg.band_fraction * duration)
    factor, segs = body_size_factor(ref, learner, cfg)
    direct_seq = scaled(learner, factor)
    trials = {
        "direct": _trial("direct", ref, direct_seq, cfg, band_s),
        "mirrored": _trial("mirrored", ref, mirrored(direct_seq), cfg, band_s),
    }
    preferred = preferred_mode if preferred_mode in trials else "direct"
    other = "mirrored" if preferred == "direct" else "direct"
    pc, oc = trials[preferred].mean_cost, trials[other].mean_cost
    if math.isfinite(oc) and (not math.isfinite(pc) or oc < pc * (1 - cfg.mirror_margin)):
        chosen, decision = other, "clear"
    elif math.isfinite(pc) and math.isfinite(oc) and pc < oc * (1 - cfg.mirror_margin):
        chosen, decision = preferred, "clear"
    else:
        chosen, decision = preferred, "ambiguous"
    trial = trials[chosen]
    mode_info = {
        "chosen": chosen,
        "decision": decision,
        "preferred": preferred,
        "margin": cfg.mirror_margin,
        "mean_cost": {k: _r(v.mean_cost) for k, v in trials.items()},
    }
    base["mirror"] = mode_info
    base["body_size_factor"] = _r(factor)
    base["body_size_segments"] = segs
    base["band_s"] = _r(band_s, 3)
    if trial.dtw is None:
        return {
            **base,
            "status": "out_of_band",
            "message": "The attempt's timing is too far from the reference to pair moves.",
        }

    terms, dtw, lseq = trial.terms, trial.dtw, trial.seq
    n = len(ref)
    # Per reference frame: the matched learner frames; representative = lowest-cost one.
    per_ref: list[list[int]] = [[] for _ in range(n)]
    for i, j in dtw.path:
        per_ref[i].append(j)
    rep_list: list[int] = []
    for i, js in enumerate(per_ref):
        costs = [float(terms.total[i, j]) for j in js]
        rep_list.append(js[int(np.argmin(costs))])
    rep = np.array(rep_list, dtype=np.int64)
    rep_cost = np.array([terms.total[i, rep[i]] for i in range(n)])
    rep_measured = np.array([bool(terms.measured[i, rep[i]]) for i in range(n)])
    # Collapse: a learner frame can earn credit for only one reference frame.
    first_use: dict[int, int] = {}
    reused = np.zeros(n, dtype=bool)
    for i in range(n):
        j = int(rep[i])
        if j in first_use:
            reused[i] = True
        else:
            first_use[j] = i

    # Timing on original timestamps.
    t_r = ref.times
    t_l = lseq.times[rep]
    offset = t_l - t_r
    ok = rep_measured & ~reused
    slope, intercept = _theil_sen(t_r[ok], t_l[ok], fallback=float(np.median(offset)))
    med_offset = float(np.median(offset[ok])) if ok.any() else float(np.median(offset))
    local_dev = offset - med_offset

    steps = len(dtw.path) - 1
    diag = sum(
        1
        for (a, b), (c, d) in zip(dtw.path, dtw.path[1:], strict=False)
        if c == a + 1 and d == b + 1
    )
    holds_ref = 0  # learner frame held while the reference moves on (vertical run)
    run = 0
    for (a, b), (c, d) in zip(dtw.path, dtw.path[1:], strict=False):
        run = run + 1 if (c == a + 1 and d == b) else 0
        holds_ref = max(holds_ref, run)
    holds_learner = 0
    run = 0
    for (a, b), (c, d) in zip(dtw.path, dtw.path[1:], strict=False):
        run = run + 1 if (c == a and d == b + 1) else 0
        holds_learner = max(holds_learner, run)
    nondiag = (steps - diag) / steps if steps > 0 else 0.0
    # Reference frames at the end all paired with the attempt's LAST frame: the recording
    # stopped before the reference passage did.
    tail = 0
    last_j = len(lseq) - 1
    for i in range(n - 1, -1, -1):
        if int(rep[i]) != last_j:
            break
        tail += 1
    ended_early_s = max(0, tail - 1) * step

    # Accounting: masked (not trackable) vs missing (reference moves, learner does not or
    # does something clearly different). Masked frames are never counted as wrong.
    ref_energy = np.nan_to_num(ref.energy, nan=0.0)
    l_energy = np.nan_to_num(lseq.energy[rep], nan=0.0)
    ref_med_energy = float(np.median(ref_energy[ref.usable])) if ref.usable.any() else 0.0
    moving_floor = max(cfg.reference_moving_energy, cfg.reference_moving_share * ref_med_energy)
    ref_moving = ref.usable & (ref_energy >= moving_floor)
    masked = ~rep_measured
    learner_still = rep_measured & ref_moving & (l_energy < cfg.still_ratio * ref_energy)
    different = rep_measured & ref_moving & (rep_cost >= cfg.miss_cost)
    missing = (learner_still | different) & ~masked
    timing_off = ok & (np.abs(local_dev) > cfg.timing_tolerance_s)

    measured_fraction = float(rep_measured.mean())
    immobile = ref_med_energy < cfg.immobile_energy
    confidence = measured_fraction * (1 - 0.5 * min(1.0, max(0.0, nondiag - 0.25) / 0.5))

    measured_costs = rep_cost[rep_measured]
    status = "aligned"
    message = None
    if measured_fraction < cfg.min_measured_fraction:
        status = "insufficient_tracking"
        message = "Less than half of this part could be measured on both videos."
    frames = [
        {
            "ref_t": _r(float(ref.times[i]), 3),
            "ref_src_t": _r(float(ref.source_times[i]), 3),
            "learner_t": _r(float(t_l[i]), 3),
            "learner_src_t": _r(float(lseq.source_times[rep[i]]), 3),
            "cost": _r(float(rep_cost[i]), 3) if rep_measured[i] else None,
            "position": _r(float(terms.position[i, rep[i]]), 3) if rep_measured[i] else None,
            "angle": _r(float(terms.angle[i, rep[i]]), 3) if rep_measured[i] else None,
            "lean": _r(float(terms.lean[i, rep[i]]), 3) if rep_measured[i] else None,
            "direction": _r(float(terms.direction[i, rep[i]]), 3) if rep_measured[i] else None,
            "measured": bool(rep_measured[i]),
            "reused": bool(reused[i]),
            "offset_s": _r(float(offset[i]), 3),
            "missing": bool(missing[i]),
        }
        for i in range(n)
    ]
    return {
        **base,
        "status": status,
        "message": message,
        "scorable": status == "aligned" and not immobile,
        "reference_immobile": immobile,
        "reference_median_energy": _r(ref_med_energy, 3),
        "path": [[int(i), int(j)] for i, j in dtw.path],
        "frames": frames,
        "summary": {
            "mean_cost": _r(float(measured_costs.mean())) if measured_costs.size else None,
            "median_cost": _r(float(np.median(measured_costs))) if measured_costs.size else None,
            "equal_time_cost": _equal_time_cost(terms, ref, lseq),
            "measured_fraction": _r(measured_fraction),
            "masked_fraction": _r(float(masked.mean())),
            "missing_fraction": _r(float(missing.mean())),
            "reuse_fraction": _r(float(reused.mean())),
            "confidence": _r(confidence),
        },
        "timing": {
            "median_offset_s": _r(med_offset, 3),
            "speed_ratio": _r(float(slope), 3),  # learner seconds per reference second
            "fit_intercept_s": _r(float(intercept), 3),
            "max_local_deviation_s": _r(
                float(np.max(np.abs(local_dev[ok])) if ok.any() else 0.0), 3
            ),
            "off_spans": _spans(t_r, timing_off, cfg.min_span_s, step),
        },
        "warp": {
            "non_diagonal_fraction": _r(nondiag),
            "max_learner_hold_s": _r(holds_ref * step, 3),
            "max_reference_hold_s": _r(holds_learner * step, 3),
            "learner_start_s": _r(float(lseq.times[dtw.path[0][1]]), 3),
            "learner_end_s": _r(float(lseq.times[dtw.path[-1][1]]), 3),
            "attempt_ended_early_s": _r(ended_early_s, 3),
        },
        "masked_spans": _spans(t_r, masked, cfg.min_span_s, step),
        "missing_spans": _spans(
            t_r,
            _bridge(missing, masked, max(1, round(cfg.bridge_masked_s / step))),
            cfg.min_span_s,
            step,
        ),
    }

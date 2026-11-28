"""Versioned movement scoring (spec 18, Outcome 7).

Pure and deterministic: inputs are the two comparison sequences built from stored, really
measured frames (app.pose.alignment.sequence_from_payloads) and the alignment report that
`alignment.align` produced for them. Output is a JSON-ready report. No randomness, no
hard-coded results: every number is a documented function of measured quantities, and the
report lists the measured inputs ("evidence") next to each component.

Components (requested product weights, *not* scientifically validated — see SCORE_VERSION):

* pose (30 %)          visibility-masked normalized skeleton distance per matched pair (same
                       per-pair translation + bounded scale fit as the alignment) plus torso
                       lean difference (torso orientation).
* timing (25 %)        original-timestamp lag of each matched move (alignment pairs the move,
                       timing still measures how early/late it happened).
* sequence (20 %)      share of the reference's moves that were matched by a distinct, similar
                       learner move, × motion-direction agreement, × an excessive-warp factor.
* joint_angles (15 %)  absolute error of the joint angles measured on both sides.
* rhythm (10 %)        motion-envelope similarity along the alignment + tempo (pace) ratio.
                       Gated: unavailable (and the rest re-weighted) when the window is short,
                       too little was compared or the reference has no clear motion accents.

Each matched pair gets a 0–100 value through the curve 100 / (1 + (x / x50)²) — 100 at no
error, 50 at the documented "half credit" error x50 — and a component is the mean over the
pairs it can measure. Masked (unmeasured) pairs are never counted as wrong; they lower
coverage and confidence instead. When the data are not good enough the overall score is
suppressed (no numbers) or qualified (shown, labelled low confidence).
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from app.pose import landmarks as L
from app.pose.alignment import (
    COMPARE_JOINTS,
    AlignConfig,
    AlignSeq,
    downsample,
    mirrored,
    scaled,
)

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]

SCORE_VERSION = "score-1"

WEIGHTS: dict[str, float] = {
    "pose": 0.30,
    "timing": 0.25,
    "sequence": 0.20,
    "joint_angles": 0.15,
    "rhythm": 0.10,
}
CORE_COMPONENTS = ("pose", "timing", "sequence", "joint_angles")

# Body parts (indices into COMPARE_JOINTS), named in the reference dancer's terms.
BODY_PARTS: dict[str, tuple[int, ...]] = {
    "left_arm": tuple(COMPARE_JOINTS.index(j) for j in (L.L_ELBOW, L.L_WRIST)),
    "right_arm": tuple(COMPARE_JOINTS.index(j) for j in (L.R_ELBOW, L.R_WRIST)),
    "torso": tuple(COMPARE_JOINTS.index(j) for j in L.CORE),
    "left_leg": tuple(COMPARE_JOINTS.index(j) for j in (L.L_KNEE, L.L_ANKLE)),
    "right_leg": tuple(COMPARE_JOINTS.index(j) for j in (L.R_KNEE, L.R_ANKLE)),
}


@dataclass(frozen=True)
class ScoreConfig:
    # Half-credit errors of the per-pair curve.
    pose_x50: float = 0.30  # torso lengths of mean joint distance (+ lean term)
    lean_per_torso: float = 0.01  # 10° of lean difference counts like 0.1 torso lengths
    angle_x50_deg: float = 30.0
    angle_focus: int = 2  # per pair: ½ mean + ½ mean of the 2 worst angles (one wrong elbow shows)
    timing_tolerance_s: float = 0.12  # lag below this is "on time" (≈ 1.5 frames at 12 fps)
    timing_x50_s: float = 0.5
    # Sequence.
    # Mean direction disagreement (0 same … 1 opposite). Even a re-encode of the reference
    # itself measures ≈ 0.14 (joints hovering around the 'moving' threshold), so the first
    # 0.15 is free.
    direction_free: float = 0.15
    direction_x50: float = 0.35
    warp_free: float = 0.35  # non-diagonal step share that costs nothing
    warp_full: float = 0.80  # ... at which the warp factor reaches its floor
    warp_floor: float = 0.7
    # Rhythm gating + curve.
    rhythm_min_window_s: float = 4.0
    rhythm_min_pairs: int = 30
    rhythm_min_reference_cv: float = 0.25  # reference motion envelope needs accents
    rhythm_smooth_s: float = 0.75  # per-frame motion energy is noisy; compare envelopes
    envelope_full_corr: float = 0.7  # correlation that earns full envelope credit
    tempo_x50: float = 0.15  # |log(pace ratio)|; 0.15 ≈ 16 % faster/slower
    # Confidence / coverage rules.
    min_compared_pairs: int = 12
    suppress_confidence: float = 0.40
    suppress_joint_coverage: float = 0.50
    qualify_confidence: float = 0.70
    qualify_joint_coverage: float = 0.75
    qualify_masked_fraction: float = 0.25
    # Sections / evidence.
    section_min_pairs: int = 8
    worst_moments: int = 3
    moment_separation_s: float = 1.0
    body_part_min_pairs: int = 6


def curve(x: float | FloatArray, x50: float) -> Any:
    """100 / (1 + (x / x50)²): 100 at zero error, 50 at x50, → 0 for large errors."""
    xa = np.maximum(np.asarray(x, dtype=np.float64), 0.0)
    return 100.0 / (1.0 + (xa / x50) ** 2)


def _r(v: float | None, nd: int = 1) -> float | None:
    if v is None or not math.isfinite(v):
        return None
    return round(float(v), nd)


@dataclass
class PairDetails:
    """Measured residuals of the representative matched pair of every reference frame."""

    ref_t: FloatArray  # (N,) window seconds
    learner_t: FloatArray  # (N,) attempt seconds
    joint_dist: FloatArray  # (N,J) torso lengths after the per-pair fit, NaN unmeasured
    ref_joint: BoolArray  # (N,J) joint measured on the reference frame
    angle_err: FloatArray  # (N,A) degrees, NaN where either side lacks the angle
    lean_err: FloatArray  # (N,) degrees
    direction: FloatArray  # (N,) alignment's direction term (0 same … 1 opposite)
    offset: FloatArray  # (N,) learner_t - ref_t
    measured: BoolArray  # (N,)
    reused: BoolArray  # (N,)
    missing: BoolArray  # (N,)
    ref_energy: FloatArray  # (N,)
    learner_energy: FloatArray  # (N,)
    extra: dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return int(self.ref_t.shape[0])


def _pair_fit(rp: FloatArray, up: FloatArray, cfg: AlignConfig) -> tuple[FloatArray, int]:
    """Per-joint distance for ONE pair, with the alignment's translation + bounded scale fit."""
    both = ~np.isnan(rp[:, 0]) & ~np.isnan(up[:, 0])
    out = np.full(rp.shape[0], np.nan)
    if not both.any():
        return out, 0
    rc = rp[both] - rp[both].mean(axis=0)
    uc = up[both] - up[both].mean(axis=0)
    den = float((uc[:, :2] ** 2).sum())
    k = float((rc[:, :2] * uc[:, :2]).sum()) / den if den > 1e-9 else 1.0
    k = min(max(k, 1 - cfg.pair_scale_clamp), 1 + cfg.pair_scale_clamp)
    diff = rc - uc * k
    w = np.array([1.0, 1.0, cfg.z_weight])
    out[both] = np.sqrt(((diff * w) ** 2).sum(axis=1))
    return out, int(both.sum())


def rebuild_learner(learner: AlignSeq, alignment: dict[str, Any]) -> AlignSeq:
    """The learner sequence exactly as the alignment compared it (downsampled, body-size
    scaled, mirrored when that interpretation was chosen)."""
    cfg = AlignConfig(**alignment["config"]) if "config" in alignment else AlignConfig()
    lseq, _ = downsample(learner, cfg.max_frames)
    lseq = scaled(lseq, float(alignment.get("body_size_factor") or 1.0))
    if (alignment.get("mirror") or {}).get("chosen") == "mirrored":
        lseq = mirrored(lseq)
    return lseq


def pair_details(ref: AlignSeq, learner: AlignSeq, alignment: dict[str, Any]) -> PairDetails:
    """Residuals of the alignment's representative pair per reference frame."""
    acfg = AlignConfig(**alignment["config"]) if "config" in alignment else AlignConfig()
    rseq, _ = downsample(ref, acfg.max_frames)
    lseq = rebuild_learner(learner, alignment)
    frames: list[dict[str, Any]] = alignment["frames"]
    n = len(frames)
    if n != len(rseq) or alignment.get("learner_frames") != len(lseq):
        raise ValueError("alignment does not belong to these sequences")
    per_ref: list[list[int]] = [[] for _ in range(n)]
    for i, j in alignment["path"]:
        per_ref[int(i)].append(int(j))
    rep = np.zeros(n, dtype=np.int64)
    for i, fr in enumerate(frames):
        js = per_ref[i]
        if not js:
            raise ValueError("alignment path skips a reference frame")
        target = float(fr["learner_t"])
        rep[i] = min(js, key=lambda j: abs(float(lseq.times[j]) - target))
    j_count = len(COMPARE_JOINTS)
    joint_dist = np.full((n, j_count), np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        for i in range(n):
            if frames[i]["measured"]:
                joint_dist[i], _ = _pair_fit(rseq.pos[i], lseq.pos[rep[i]], acfg)
        angle_err = np.abs(rseq.angles - lseq.angles[rep])
        lean_err = np.abs(rseq.lean - lseq.lean[rep])
    measured = np.array([bool(f["measured"]) for f in frames])
    angle_err[~measured] = np.nan
    lean_err[~measured] = np.nan
    direction = np.array(
        [f["direction"] if f["direction"] is not None else np.nan for f in frames], dtype=float
    )
    return PairDetails(
        ref_t=rseq.times.copy(),
        learner_t=lseq.times[rep].copy(),
        joint_dist=joint_dist,
        ref_joint=~np.isnan(rseq.pos[..., 0]),
        angle_err=angle_err,
        lean_err=lean_err,
        direction=direction,
        offset=lseq.times[rep] - rseq.times,
        measured=measured,
        reused=np.array([bool(f["reused"]) for f in frames]),
        missing=np.array([bool(f["missing"]) for f in frames]),
        ref_energy=np.nan_to_num(rseq.energy, nan=0.0),
        learner_energy=np.nan_to_num(lseq.energy[rep], nan=0.0),
    )


def _mean(x: FloatArray) -> float | None:
    x = x[np.isfinite(x)]
    return float(x.mean()) if x.size else None


def _focus(x: FloatArray, k: int) -> FloatArray:
    """Per row: ½ × mean + ½ × mean of the k largest finite values (NaN where none)."""
    out = np.full(x.shape[0], np.nan)
    for i, row in enumerate(x):
        v = row[np.isfinite(row)]
        if v.size:
            top = np.sort(v)[-k:]
            out[i] = 0.5 * float(v.mean()) + 0.5 * float(top.mean())
    return out


def _smooth(x: FloatArray, k: int) -> FloatArray:
    if k <= 1 or x.size < k:
        return x
    kernel = np.ones(k) / k
    pad = k // 2
    xp = np.pad(x, pad, mode="edge")
    return np.convolve(xp, kernel, mode="valid")[: x.size]


def _components(
    d: PairDetails, sel: BoolArray, cfg: ScoreConfig, *, alignment: dict[str, Any] | None
) -> dict[str, Any]:
    """Core component values + evidence over the pairs selected by `sel`."""
    comp = sel & d.measured & ~d.reused
    n_sel = int(sel.sum())
    n_comp = int(comp.sum())
    out: dict[str, Any] = {"pairs": n_sel, "compared_pairs": n_comp}
    if n_comp == 0:
        return out
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        jd = np.nanmean(d.joint_dist[comp], axis=1)
    lean = np.nan_to_num(d.lean_err[comp], nan=0.0)
    pose_x = jd + cfg.lean_per_torso * lean
    pose_pair = curve(pose_x, cfg.pose_x50)
    ang = _focus(d.angle_err[comp], cfg.angle_focus)
    ang_ok = np.isfinite(ang)
    ang_pair = curve(ang[ang_ok], cfg.angle_x50_deg)
    lag = np.maximum(np.abs(d.offset[comp]) - cfg.timing_tolerance_s, 0.0)
    timing_pair = curve(lag, cfg.timing_x50_s)
    # Sequence: reference frames (measured) credited with a distinct, similar learner move.
    measured_sel = sel & d.measured
    n_meas = int(measured_sel.sum())
    credited = measured_sel & ~d.missing & ~d.reused
    matched_share = float(credited.sum()) / n_meas if n_meas else 0.0
    dir_mean = _mean(d.direction[comp]) or 0.0
    dir_factor = float(curve(max(0.0, dir_mean - cfg.direction_free), cfg.direction_x50)) / 100.0
    nondiag = float(((alignment or {}).get("warp") or {}).get("non_diagonal_fraction") or 0.0)
    span = max(cfg.warp_full - cfg.warp_free, 1e-6)
    over = min(max((nondiag - cfg.warp_free) / span, 0.0), 1.0)
    warp_factor = 1.0 - (1.0 - cfg.warp_floor) * over
    sequence = 100.0 * matched_share * dir_factor * warp_factor
    out.update(
        {
            "pose": float(pose_pair.mean()),
            "joint_angles": float(ang_pair.mean()) if ang_pair.size else None,
            "timing": float(timing_pair.mean()),
            "sequence": sequence,
            "evidence": {
                "pose": {
                    "mean_joint_distance_torso": _r(float(jd.mean()), 3),
                    "mean_lean_difference_deg": _r(float(lean.mean()), 1),
                    "half_credit_at": cfg.pose_x50,
                    "pairs": n_comp,
                },
                "joint_angles": {
                    "focused_angle_error_deg": _r(float(ang[ang_ok].mean()), 1)
                    if ang_ok.any()
                    else None,
                    "half_credit_at_deg": cfg.angle_x50_deg,
                    "pairs": int(ang_ok.sum()),
                },
                "timing": {
                    "median_offset_s": _r(float(np.median(d.offset[comp])), 3),
                    "mean_abs_offset_s": _r(float(np.abs(d.offset[comp]).mean()), 3),
                    "on_time_share": _r(float((lag == 0).mean()), 3),
                    "tolerance_s": cfg.timing_tolerance_s,
                    "half_credit_at_s": cfg.timing_x50_s,
                },
                "sequence": {
                    "matched_share": _r(matched_share, 3),
                    "missing_share": _r(float((measured_sel & d.missing).sum()) / n_meas, 3)
                    if n_meas
                    else None,
                    "held_share": _r(float((measured_sel & d.reused).sum()) / n_meas, 3)
                    if n_meas
                    else None,
                    "mean_direction_disagreement": _r(dir_mean, 3),
                    "direction_factor": _r(dir_factor, 3),
                    "non_diagonal_fraction": _r(nondiag, 3),
                    "warp_factor": _r(warp_factor, 3),
                },
            },
        }
    )
    return out


def _rhythm(
    d: PairDetails, cfg: ScoreConfig, alignment: dict[str, Any]
) -> tuple[float | None, dict[str, Any]]:
    comp = d.measured & ~d.reused
    window_s = float(d.ref_t[-1] - d.ref_t[0]) if len(d) > 1 else 0.0
    ev: dict[str, Any] = {"window_s": _r(window_s, 2), "pairs": int(comp.sum())}
    if window_s < cfg.rhythm_min_window_s:
        return None, {**ev, "unavailable": "too_short"}
    if int(comp.sum()) < cfg.rhythm_min_pairs:
        return None, {**ev, "unavailable": "too_few_pairs"}
    step = float(np.median(np.diff(d.ref_t))) if len(d) > 1 else 1 / 12
    k = max(1, round(cfg.rhythm_smooth_s / max(step, 1e-3)))
    re = _smooth(d.ref_energy, k)[comp]
    le = _smooth(d.learner_energy, k)[comp]
    mean_r = float(re.mean())
    cv = float(re.std() / mean_r) if mean_r > 1e-9 else 0.0
    ev["reference_envelope_cv"] = _r(cv, 3)
    if cv < cfg.rhythm_min_reference_cv:
        return None, {**ev, "unavailable": "no_clear_accents"}
    corr = 0.0 if float(le.std()) < 1e-9 else float(np.corrcoef(re, le)[0, 1])
    pace = float(((alignment.get("timing") or {}).get("speed_ratio")) or 1.0)
    pace = min(max(pace, 0.25), 4.0)
    tempo = float(curve(abs(math.log(pace)), cfg.tempo_x50))
    envelope = 100.0 * min(max(corr / cfg.envelope_full_corr, 0.0), 1.0)
    value = 0.5 * envelope + 0.5 * tempo
    ev.update(
        {
            "envelope_correlation": _r(corr, 3),
            "envelope_value": _r(envelope),
            "pace_ratio": _r(pace, 3),
            "tempo_value": _r(tempo),
            "basis": "body-motion envelope (no audio beat detection)",
            "experimental": True,
        }
    )
    return value, ev


def _weighted(values: dict[str, float | None]) -> tuple[float | None, dict[str, float]]:
    avail = {k: v for k, v in values.items() if v is not None}
    total = sum(WEIGHTS[k] for k in avail)
    if total <= 0:
        return None, {}
    used = {k: WEIGHTS[k] / total for k in avail}
    return sum(used[k] * v for k, v in avail.items()), used


def _body_parts(d: PairDetails, comp: BoolArray, cfg: ScoreConfig) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for part, idx in BODY_PARTS.items():
        sub = d.joint_dist[np.ix_(comp, list(idx))]
        ref_has = d.ref_joint[np.ix_(comp, list(idx))]
        vals = sub[np.isfinite(sub)]
        pairs = int(np.isfinite(sub).any(axis=1).sum())
        if pairs < cfg.body_part_min_pairs:
            shown = int(ref_has.any(axis=1).sum())
            out[part] = {
                "tracked": False,
                "reason": "not_in_reference" if shown < cfg.body_part_min_pairs else "not_tracked",
            }
            continue
        out[part] = {
            "tracked": True,
            "mean_distance_torso": _r(float(vals.mean()), 3),
            "value": _r(float(curve(float(vals.mean()), cfg.pose_x50))),
            "pairs": pairs,
        }
    return out


def _moments(d: PairDetails, comp: BoolArray, cfg: ScoreConfig) -> dict[str, Any]:
    """Evidence links: the worst and best matched moments by per-pair pose value."""
    idx = np.flatnonzero(comp)
    if idx.size == 0:
        return {"worst": [], "best": None}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        jd = np.nanmean(d.joint_dist[idx], axis=1)
    lean = np.nan_to_num(d.lean_err[idx], nan=0.0)
    vals = curve(jd + cfg.lean_per_torso * lean, cfg.pose_x50)

    def moment(k: int) -> dict[str, Any]:
        i = int(idx[k])
        row = d.joint_dist[i]
        parts = []
        for part, jj in BODY_PARTS.items():
            v = row[list(jj)]
            if np.isfinite(v).any():
                parts.append((float(np.nanmean(v)), part))
        parts.sort(reverse=True)
        return {
            "ref_t": _r(float(d.ref_t[i]), 3),
            "learner_t": _r(float(d.learner_t[i]), 3),
            "pose_value": _r(float(vals[k])),
            "joint_distance_torso": _r(float(jd[k]), 3),
            "largest_differences": [p for _, p in parts[:2]],
        }

    worst: list[dict[str, Any]] = []
    taken: list[float] = []
    for k in np.argsort(vals, kind="stable"):
        t = float(d.ref_t[idx[k]])
        if all(abs(t - u) >= cfg.moment_separation_s for u in taken):
            worst.append(moment(int(k)))
            taken.append(t)
        if len(worst) >= cfg.worst_moments:
            break
    best = moment(int(np.argmax(vals)))
    return {"worst": worst, "best": best}


def score(
    ref: AlignSeq,
    learner: AlignSeq,
    alignment: dict[str, Any],
    *,
    sections: Sequence[dict[str, Any]] = (),
    cfg: ScoreConfig | None = None,
) -> dict[str, Any]:
    """Score an aligned attempt. `sections`: [{id, title, start, end}] in window seconds
    (only for full-dance attempts) for a per-section breakdown."""
    cfg = cfg or ScoreConfig()
    base: dict[str, Any] = {
        "version": SCORE_VERSION,
        "alignment_version": alignment.get("version"),
        "weights": dict(WEIGHTS),
        "config": asdict(cfg),
        "overall": None,
        "components": {k: None for k in WEIGHTS},
        "weights_used": {},
        "warnings": [],
    }
    if not alignment.get("scorable") or alignment.get("status") != "aligned":
        reason = (
            "reference_immobile" if alignment.get("reference_immobile") else alignment.get("status")
        )
        return {
            **base,
            "status": "not_scored",
            "reason": reason,
            "message": alignment.get("message")
            or (
                "The reference barely moves in this part, so there is nothing to score."
                if reason == "reference_immobile"
                else "This attempt couldn't be compared with the reference."
            ),
            "coverage": _coverage_block(alignment, None, None, cfg),
        }

    d = pair_details(ref, learner, alignment)
    allsel = np.ones(len(d), dtype=bool)
    comp_mask = d.measured & ~d.reused
    core = _components(d, allsel, cfg, alignment=alignment)
    rhythm_value, rhythm_ev = _rhythm(d, cfg, alignment)
    joint_cov = _joint_coverage(d, comp_mask)
    coverage = _coverage_block(alignment, d, joint_cov, cfg)
    confidence = float(coverage["confidence"] or 0.0)

    values: dict[str, float | None] = {k: core.get(k) for k in CORE_COMPONENTS}
    values["rhythm"] = rhythm_value
    overall, used = _weighted(values)
    warn: list[str] = []
    if rhythm_value is None:
        warn.append(f"rhythm_unavailable:{rhythm_ev.get('unavailable')}")
    if (alignment.get("mirror") or {}).get("chosen") == "mirrored":
        warn.append("compared_mirrored")
    if (alignment.get("mirror") or {}).get("decision") == "ambiguous":
        warn.append("sides_ambiguous")
    masked = float((alignment.get("summary") or {}).get("masked_fraction") or 0.0)
    if masked > 0:
        warn.append("untracked_moments_skipped")
    ended = float((alignment.get("warp") or {}).get("attempt_ended_early_s") or 0.0)
    if ended >= 0.5:
        warn.append("attempt_ended_early")
    parts = _body_parts(d, comp_mask, cfg)
    if any(p.get("reason") == "not_in_reference" for p in parts.values()):
        warn.append("reference_hides_some_body_parts")
    if any(p.get("reason") == "not_tracked" for p in parts.values()):
        warn.append("some_body_parts_untracked")

    reasons: list[str] = []
    if core["compared_pairs"] < cfg.min_compared_pairs:
        reasons.append("too_few_compared_moments")
    if confidence < cfg.suppress_confidence:
        reasons.append("low_confidence")
    if joint_cov is None or joint_cov < cfg.suppress_joint_coverage:
        reasons.append("too_few_visible_joints")
    if any(values[k] is None for k in CORE_COMPONENTS):
        reasons.append("core_component_unavailable")
    qualifiers: list[str] = []
    if confidence < cfg.qualify_confidence:
        qualifiers.append("low_confidence")
    if joint_cov is not None and joint_cov < cfg.qualify_joint_coverage:
        qualifiers.append("partial_body_visible")
    if masked > cfg.qualify_masked_fraction:
        qualifiers.append("many_untracked_moments")

    report = {
        **base,
        "warnings": warn,
        "coverage": coverage,
        "body_parts": parts,
        "moments": _moments(d, comp_mask, cfg),
        "evidence": {**core.get("evidence", {}), "rhythm": rhythm_ev},
        "sections": _section_scores(d, sections, cfg, alignment),
    }
    if reasons:
        return {
            **report,
            "status": "suppressed",
            "reason": reasons[0],
            "reasons": reasons,
            "message": _SUPPRESS_MESSAGES.get(reasons[0], "Not enough reliable data to score."),
        }
    report["components"] = {k: _r(v) for k, v in values.items()}
    report["overall"] = _r(overall)
    report["weights_used"] = {k: round(v, 4) for k, v in used.items()}
    report["status"] = "qualified" if qualifiers else "scored"
    report["qualifiers"] = qualifiers
    return report


_SUPPRESS_MESSAGES = {
    "too_few_compared_moments": "Too few moments could be compared to give a fair score.",
    "low_confidence": "Tracking or alignment was too uncertain to give a fair score.",
    "too_few_visible_joints": "Too few of your joints were visible to give a fair score.",
    "core_component_unavailable": "Part of the comparison couldn't be measured.",
}


def _joint_coverage(d: PairDetails, comp: BoolArray) -> float | None:
    """Share of the joints shown on the reference that were also measured on the learner,
    over the compared pairs (the reference's own cropping is not the learner's fault)."""
    if not comp.any():
        return None
    shown = d.ref_joint[comp].sum()
    both = np.isfinite(d.joint_dist[comp]).sum()
    return float(both / shown) if shown else None


def _coverage_block(
    alignment: dict[str, Any], d: PairDetails | None, joint_cov: float | None, cfg: ScoreConfig
) -> dict[str, Any]:
    summary = alignment.get("summary") or {}
    ref_frames = alignment.get("reference_frames") or 0
    l_frames = alignment.get("learner_frames") or 0
    ref_cov = (alignment.get("reference_usable_frames") or 0) / ref_frames if ref_frames else None
    l_cov = (alignment.get("learner_usable_frames") or 0) / l_frames if l_frames else None
    align_conf = summary.get("confidence")
    compared = int((d.measured & ~d.reused).sum()) if d is not None else 0
    confidence: float | None = None
    if align_conf is not None and joint_cov is not None:
        # Alignment confidence (measured share × warp) × visible-joint share, and a small-
        # sample discount below 2 × the minimum compared moments.
        sample = min(1.0, compared / (2.0 * cfg.min_compared_pairs))
        confidence = float(align_conf) * min(1.0, joint_cov / cfg.qualify_joint_coverage) * sample
    return {
        "reference_tracking": _r(ref_cov, 3),
        "learner_tracking": _r(l_cov, 3),
        "compared_frames": compared,
        "reference_frames": ref_frames,
        "visible_joint_coverage": _r(joint_cov, 3),
        "masked_fraction": summary.get("masked_fraction"),
        "alignment_confidence": align_conf,
        "warp": (alignment.get("warp") or {}).get("non_diagonal_fraction"),
        "confidence": _r(confidence, 3),
    }


def _section_scores(
    d: PairDetails,
    sections: Sequence[dict[str, Any]],
    cfg: ScoreConfig,
    alignment: dict[str, Any],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in sections:
        lo, hi = float(s["start"]), float(s["end"])
        sel = (d.ref_t >= lo - 1e-6) & (d.ref_t < hi - 1e-6)
        c = _components(d, sel, cfg, alignment=alignment)
        entry: dict[str, Any] = {
            "id": s.get("id"),
            "title": s.get("title"),
            "start": round(lo, 3),
            "end": round(hi, 3),
            "compared_pairs": c["compared_pairs"],
        }
        if c["compared_pairs"] < cfg.section_min_pairs:
            entry.update({"status": "insufficient", "overall": None, "components": None})
        else:
            vals: dict[str, float | None] = {k: c.get(k) for k in CORE_COMPONENTS}
            overall, _ = _weighted(vals)
            entry.update(
                {
                    "status": "scored",
                    "overall": _r(overall),
                    "components": {k: _r(v) for k, v in vals.items()},
                }
            )
        out.append(entry)
    return out

"""Invariance and sensitivity tests for normalized, mirror-aware bounded DTW (spec 17,
Outcome 6). Synthetic landmark sequences are allowed here: they test geometry, not claims
about real dancers. Real-footage checks live in test_alignment_api.py.

Every synthetic clip goes through the production path: image landmarks → compute_features →
frame_payload (what is stored) → sequence_from_payloads → align.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np
import pytest

from app.pose import landmarks as L
from app.pose.alignment import (
    AlignConfig,
    AlignSeq,
    align,
    body_size_factor,
    bounded_dtw,
    mirrored,
    sequence_from_payloads,
)
from app.pose.features import compute_features, frame_payload

FPS = 12.0


def arm_angles(t: float) -> tuple[float, float, float, float]:
    """Choreography (degrees from 'arm hanging down', elbow bend): deliberately asymmetric.
    Left arm sweeps up and down over 4 s; right arm pulses faster at lower amplitude."""
    left = 20 + 140 * (0.5 - 0.5 * math.cos(2 * math.pi * t / 4.0))
    right = 30 + 60 * (0.5 - 0.5 * math.cos(2 * math.pi * t / 1.6))
    l_elbow = 20 + 60 * (0.5 - 0.5 * math.cos(2 * math.pi * t / 2.0))
    r_elbow = 10.0
    return left, right, l_elbow, r_elbow


Pose = Callable[[float], tuple[float, float, float, float]]


def body(
    t: float,
    pose: Pose = arm_angles,
    lean_deg: float = 0.0,
    limb: float = 1.0,
    leg: float = 1.0,
) -> dict[int, tuple[float, float]]:
    """Body-unit 2-D skeleton (y down, hips at origin, torso length 2)."""
    la, ra, le, re = pose(t)
    pts: dict[int, tuple[float, float]] = {
        L.L_SHOULDER: (0.8, -2.0),
        L.R_SHOULDER: (-0.8, -2.0),
        L.L_HIP: (0.5, 0.0),
        L.R_HIP: (-0.5, 0.0),
        L.L_KNEE: (0.55, 1.8 * leg),
        L.R_KNEE: (-0.55, 1.8 * leg),
        L.L_ANKLE: (0.55, 3.6 * leg),
        L.R_ANKLE: (-0.55, 3.6 * leg),
        L.L_FOOT: (0.9, 3.7 * leg),
        L.R_FOOT: (-0.9, 3.7 * leg),
        L.NOSE: (0.0, -2.6),
    }

    def arm(sx: float, side: float, a: float, e: float) -> tuple[tuple[float, float], ...]:
        # side +1 = subject's left (image right when facing camera)
        th = math.radians(a)
        ux, uy = side * math.sin(th), math.cos(th)
        elbow = (sx + 1.1 * limb * ux, -2.0 + 1.1 * limb * uy)
        th2 = th + side * math.radians(e) * side
        vx, vy = side * math.sin(th2), math.cos(th2)
        wrist = (elbow[0] + 1.0 * limb * vx, elbow[1] + 1.0 * limb * vy)
        return elbow, wrist

    pts[L.L_ELBOW], pts[L.L_WRIST] = arm(0.8, 1.0, la, le)
    pts[L.R_ELBOW], pts[L.R_WRIST] = arm(-0.8, -1.0, ra, re)
    if lean_deg:
        c, s = math.cos(math.radians(lean_deg)), math.sin(math.radians(lean_deg))
        for j in list(pts):
            x, y = pts[j]
            if y < 0:  # upper body rotates about the hips
                pts[j] = (x * c - y * s, x * s + y * c)
    return pts


def clip(
    seconds: float = 8.0,
    *,
    time_map: Callable[[float], float] = lambda t: t,
    cx: float = 0.5,
    cy: float = 0.45,
    s: float = 0.06,
    width: int = 1280,
    height: int = 720,
    mirror: bool = False,
    missing: tuple[float, float] | None = None,
    **body_kw: object,
) -> AlignSeq:
    n = int(round(seconds * FPS))
    times = np.arange(n) / FPS
    lm = np.full((n, 33, 5), np.nan)
    k = width / height
    for i, t in enumerate(times):
        if missing and missing[0] <= t < missing[1]:
            continue  # nothing detected (occluded)
        pts = body(time_map(float(t)), **body_kw)  # type: ignore[arg-type]
        frame = np.zeros((33, 5))
        frame[:, 3:] = 0.99
        for j in range(33):
            x, y = pts.get(j, (0.0, -2.4))
            # s is in image-height units; x divided by aspect so the body isn't squashed.
            frame[j, 0] = cx + x * s / k
            frame[j, 1] = cy + y * s
            frame[j, 2] = 0.0
        if mirror:  # what the pose model reports for a mirror image: reflected + sides swapped
            frame = frame[list(L.MIRROR)]
            frame[:, 0] = 1.0 - frame[:, 0]
        lm[i] = frame
    feats = compute_features(lm, times, width, height)
    payloads = [frame_payload(feats, t, 1) for t in range(n)]
    return sequence_from_payloads(times.tolist(), payloads, feats.valid.tolist())


REF = clip()


def run(learner: AlignSeq, ref: AlignSeq = REF, **kw: object) -> dict[str, object]:
    out = align(ref, learner, **kw)  # type: ignore[arg-type]
    assert out["version"] == "align-1"
    return out


def cost(out: dict[str, object]) -> float:
    summary = out["summary"]
    assert isinstance(summary, dict)
    v = summary["mean_cost"]
    assert isinstance(v, float)
    return v


@pytest.fixture(scope="module")
def baseline() -> float:
    return cost(run(clip()))


# ---------------------------------------------------------------- invariance


def test_identical_attempt_aligns_on_the_diagonal_with_near_zero_cost(baseline: float) -> None:
    out = run(clip())
    assert out["status"] == "aligned" and out["scorable"] is True
    assert baseline < 0.02
    timing = out["timing"]
    assert isinstance(timing, dict)
    assert abs(timing["median_offset_s"]) < 1e-6
    assert timing["speed_ratio"] == pytest.approx(1.0, abs=0.01)
    assert out["warp"]["non_diagonal_fraction"] == 0  # type: ignore[index]
    assert out["mirror"]["chosen"] == "direct"  # type: ignore[index]
    assert out["mirror"]["decision"] == "clear"  # type: ignore[index]


@pytest.mark.parametrize(
    "variant",
    [
        {"s": 0.035},  # further from the camera
        {"s": 0.09},  # closer
        {"cx": 0.25},  # left of frame
        {"cx": 0.75, "cy": 0.4},  # right and higher
        {"width": 640, "height": 360},  # lower resolution
        {"width": 720, "height": 1280, "s": 0.045},  # portrait phone
        {"limb": 1.08, "leg": 1.1, "s": 0.055},  # a taller subject, slightly longer limbs
    ],
)
def test_size_position_resolution_and_height_do_not_dominate(
    variant: dict[str, float], baseline: float
) -> None:
    out = run(clip(**variant))  # type: ignore[arg-type]
    assert out["status"] == "aligned"
    assert cost(out) < baseline + 0.06, out["summary"]
    assert out["mirror"]["chosen"] == "direct"  # type: ignore[index]


def test_body_size_factor_ignores_torso_scale_errors() -> None:
    """Hips measured too high (as on frames that crop at the hips) shrink the torso; the
    limb-ratio factor recovers the true proportions."""
    ref = clip()
    shrunk = clip()
    # Simulate torso normalised 25 % too large: every coordinate 0.8×.
    shrunk.pos = shrunk.pos * 0.8
    f, segs = body_size_factor(ref, shrunk, AlignConfig())
    assert segs >= 5
    assert f == pytest.approx(1.25, rel=0.03)


@pytest.mark.parametrize("speed", [0.8, 1.25])
def test_moderate_speed_difference_is_absorbed_by_alignment_but_measured(
    speed: float, baseline: float
) -> None:
    # Learner performs at `speed`× → their time t shows reference time t·speed.
    seconds = 8.0 / speed
    out = run(clip(seconds, time_map=lambda t: t * speed))
    assert out["status"] == "aligned"
    assert cost(out) < baseline + 0.08, out["summary"]
    timing = out["timing"]
    assert isinstance(timing, dict)
    assert timing["speed_ratio"] == pytest.approx(1 / speed, rel=0.06)  # timing preserved
    summary = out["summary"]
    assert isinstance(summary, dict)
    assert summary["equal_time_cost"] > cost(out) + 0.05  # naive pairing is clearly worse


# ---------------------------------------------------------------- sensitivity


def lower_left_arm(t: float) -> tuple[float, float, float, float]:
    la, ra, le, re = arm_angles(t)
    return la * 0.45, ra, le, re


def straight_left_elbow(t: float) -> tuple[float, float, float, float]:
    la, ra, _, re = arm_angles(t)
    return la, ra, 100.0, re


def opposite_left_sweep(t: float) -> tuple[float, float, float, float]:
    """Same positions visited, opposite direction of travel (phase-reversed sweep)."""
    la, ra, le, re = arm_angles(t)
    return arm_angles(t + 2.0)[0], ra, le, re


@pytest.mark.parametrize(
    ("name", "kw"),
    [
        ("wrong arm height", {"pose": lower_left_arm}),
        ("wrong elbow angle", {"pose": straight_left_elbow}),
        ("wrong movement direction", {"pose": opposite_left_sweep}),
        ("large torso lean", {"lean_deg": 28.0}),
    ],
)
def test_wrong_movements_stay_distinguishable(
    name: str, kw: dict[str, object], baseline: float
) -> None:
    out = run(clip(**kw))  # type: ignore[arg-type]
    assert out["status"] == "aligned"
    assert cost(out) > baseline + 0.12, (name, out["summary"])
    # ... and clearly worse than every invariance variant.
    assert cost(out) > cost(run(clip(s=0.035, cx=0.3))) + 0.08


def test_missing_movement_is_reported_where_it_happens() -> None:
    def frozen_middle(t: float) -> tuple[float, float, float, float]:
        return arm_angles(min(t, 3.0) if t < 6.0 else t)  # holds still 3–6 s

    out = run(clip(pose=frozen_middle))
    spans = out["missing_spans"]
    assert isinstance(spans, list) and spans
    covered = sum(hi - lo for lo, hi in spans if lo >= 2.5 and hi <= 6.6)
    assert covered >= 1.5, spans
    assert all(lo >= 2.5 for lo, _ in spans), spans  # nothing flagged before the freeze
    assert out["summary"]["missing_fraction"] > 0.15  # type: ignore[index]


def test_late_movement_keeps_its_timing() -> None:
    """The middle move happens 1 s late: alignment pairs it, timing reports it."""

    def late(t: float) -> float:
        if t < 3.0:
            return t
        if t < 4.0:
            return 3.0  # hesitates
        if t < 6.0:
            return t - 1.0  # performs 3–5 s of the reference one second late
        return 5.0 + (t - 6.0) * 1.5  # catches up by 8 s

    out = run(clip(time_map=late))
    timing = out["timing"]
    assert isinstance(timing, dict)
    assert timing["max_local_deviation_s"] >= 0.7, timing
    spans = timing["off_spans"]
    assert any(lo <= 4.5 and hi >= 3.5 for lo, hi in spans), spans
    # Offsets are on the original timestamps: the learner shows ref t=4 s at ≈ 5 s.
    frames = out["frames"]
    assert isinstance(frames, list)
    at4 = min(frames, key=lambda f: abs(f["ref_t"] - 4.0))
    assert at4["offset_s"] == pytest.approx(1.0, abs=0.25)


def ramp(t: float) -> tuple[float, float, float, float]:
    """A non-periodic phrase: left arm rises over 8 s while the right arm lowers."""
    return 20 + 17 * t, 160 - 15 * t, 20 + 5 * t, 10.0


def test_reversed_sequence_is_not_matched_cheaply() -> None:
    ref = clip(pose=ramp)
    same = cost(align(ref, clip(pose=ramp)))
    out = align(ref, clip(pose=ramp, time_map=lambda t: 8.0 - 1 / FPS - t))
    assert out["status"] in {"aligned", "out_of_band"}
    if out["status"] == "aligned":
        assert cost(out) > same + 0.12, out["summary"]


# ---------------------------------------------------------------- mirroring


def test_mirror_image_is_detected_and_recorded(baseline: float) -> None:
    out = run(clip(mirror=True))
    mirror = out["mirror"]
    assert isinstance(mirror, dict)
    assert mirror["chosen"] == "mirrored" and mirror["decision"] == "clear"
    assert mirror["mean_cost"]["direct"] > mirror["mean_cost"]["mirrored"] + 0.1
    assert cost(out) < baseline + 0.02


def test_mirror_transform_swaps_sides_and_reflects_x() -> None:
    m = mirrored(REF)
    li = 2  # COMPARE_JOINTS index of left elbow (13) is 2, right elbow (14) is 3
    np.testing.assert_allclose(m.pos[:, li, 0], -REF.pos[:, 3, 0], equal_nan=True)
    np.testing.assert_allclose(m.pos[:, li, 1], REF.pos[:, 3, 1], equal_nan=True)
    np.testing.assert_allclose(m.angles[:, 0], REF.angles[:, 1], equal_nan=True)  # elbows
    np.testing.assert_allclose(mirrored(m).pos, REF.pos, equal_nan=True)  # involution
    np.testing.assert_allclose(m.lean, -REF.lean, equal_nan=True)


def test_symmetric_movement_keeps_preferred_mode_and_says_ambiguous() -> None:
    def symmetric(t: float) -> tuple[float, float, float, float]:
        a = 20 + 140 * (0.5 - 0.5 * math.cos(2 * math.pi * t / 4.0))
        return a, a, 30.0, 30.0

    ref = clip(pose=symmetric)
    out = align(ref, clip(pose=symmetric), preferred_mode="mirrored")
    assert out["mirror"]["decision"] == "ambiguous"
    assert out["mirror"]["chosen"] == "mirrored"


# ---------------------------------------------------------------- masking + gates


def test_untracked_frames_are_masked_not_missing() -> None:
    out = run(clip(missing=(3.0, 5.0)))
    assert out["status"] == "aligned"
    masked = out["masked_spans"]
    assert isinstance(masked, list)
    assert any(lo <= 3.3 and hi >= 4.7 for lo, hi in masked), masked
    assert out["missing_spans"] == []
    frames = out["frames"]
    assert isinstance(frames, list)
    assert all(f["cost"] is None for f in frames if 3.2 <= f["ref_t"] <= 4.8)


def test_mostly_untracked_attempt_is_refused() -> None:
    out = run(clip(missing=(0.5, 8.0)))
    assert out["status"] == "insufficient_tracking"
    assert out["scorable"] is False


def test_untracked_reference_is_refused() -> None:
    out = align(clip(missing=(0.3, 8.0)), clip())
    assert out["status"] == "insufficient_reference"


def test_immobile_reference_is_aligned_but_not_scorable() -> None:
    def still(t: float) -> tuple[float, float, float, float]:
        return 40.0, 40.0, 20.0, 20.0

    out = align(clip(pose=still), clip(pose=still))
    assert out["status"] == "aligned"
    assert out["reference_immobile"] is True and out["scorable"] is False


def test_frozen_learner_cannot_earn_many_matches() -> None:
    out = run(clip(time_map=lambda t: 2.0))  # holds one pose for the whole attempt
    summary = out["summary"]
    assert isinstance(summary, dict)
    assert summary["reuse_fraction"] > 0.5 or summary["missing_fraction"] > 0.5


# ---------------------------------------------------------------- DTW mechanics


def test_bounded_dtw_respects_the_band_and_monotonicity() -> None:
    rng = np.random.default_rng(7)
    n, m = 40, 55
    c = rng.random((n, m))
    rt = np.arange(n) / FPS
    lt = np.arange(m) / FPS
    res = bounded_dtw(c, rt, lt, band_s=1.0, step_penalty=0.08)
    assert res is not None
    assert [i for i, _ in res.path][0] == 0 and res.path[-1][0] == n - 1
    for (a, b), (x, y) in zip(res.path, res.path[1:], strict=False):
        assert (x - a, y - b) in {(1, 1), (1, 0), (0, 1)}
    assert all(abs(lt[j] - rt[i]) <= 1.0 + 1e-9 for i, j in res.path)
    assert sorted({i for i, _ in res.path}) == list(range(n))  # every reference frame matched


def test_bounded_dtw_returns_none_when_nothing_fits_the_band() -> None:
    c = np.zeros((10, 10))
    rt = np.arange(10) / FPS
    assert bounded_dtw(c, rt, rt + 5.0, band_s=1.0, step_penalty=0.1) is None


def test_bounded_dtw_finds_a_known_shift() -> None:
    sig = np.sin(np.arange(60) / 4.0)
    shifted = np.concatenate([np.full(6, sig[0]), sig])  # learner starts 0.5 s late
    c = np.abs(sig[:, None] - shifted[None])
    res = bounded_dtw(c, np.arange(60) / FPS, np.arange(66) / FPS, 2.0, 0.08)
    assert res is not None
    offsets = [j - i for i, j in res.path[5:-5]]
    assert np.median(offsets) == 6


def test_alignment_is_deterministic() -> None:
    a = run(clip(s=0.05, time_map=lambda t: t * 0.9, seconds=8.8))
    b = run(clip(s=0.05, time_map=lambda t: t * 0.9, seconds=8.8))
    assert a == b


def test_recording_that_stops_early_is_reported() -> None:
    out = run(clip(5.0))  # learner stopped 3 s before the 8 s reference passage ended
    warp = out["warp"]
    assert isinstance(warp, dict)
    assert warp["attempt_ended_early_s"] == pytest.approx(3.0, abs=0.35)
    assert run(clip())["warp"]["attempt_ended_early_s"] == 0  # type: ignore[index]

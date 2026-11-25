"""Deterministic unit tests for pure movement math.

Synthetic landmark sequences are allowed here (and only here): they test geometry, not the
product's claims about real dancers.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.pose import landmarks as L
from app.pose.features import QualityConfig, compute_features
from app.pose.quality import assess, select_track
from app.pose.smoothing import ema, fill_short_gaps, one_euro, savitzky_golay

pytest.importorskip("scipy")


def standing_pose(cx: float = 0.5, cy: float = 0.5, s: float = 0.1) -> np.ndarray:
    """A plausible upright pose in image-normalized coords (y down), arms out to the side."""
    p = np.zeros((33, 5))
    p[:, 3:] = 0.99
    pts = {
        L.NOSE: (0, -2.6),
        L.L_SHOULDER: (0.8, -2.0),
        L.R_SHOULDER: (-0.8, -2.0),
        L.L_ELBOW: (1.8, -2.0),  # left upper arm horizontal
        L.R_ELBOW: (-1.8, -2.0),
        L.L_WRIST: (1.8, -3.0),  # left forearm straight up → 90° elbow
        L.R_WRIST: (-2.8, -2.0),  # right arm straight → 180° elbow
        L.L_HIP: (0.5, 0.0),
        L.R_HIP: (-0.5, 0.0),
        L.L_KNEE: (0.5, 1.8),
        L.R_KNEE: (-0.5, 1.8),
        L.L_ANKLE: (0.5, 3.6),
        L.R_ANKLE: (-0.5, 3.6),
        L.L_FOOT: (0.9, 3.7),
        L.R_FOOT: (-0.9, 3.7),
    }
    for j in range(33):
        x, y = pts.get(j, (0.0, -2.4))
        p[j, 0] = cx + x * s
        p[j, 1] = cy + y * s
    return p


def seq(n: int = 24, **kw: float) -> tuple[np.ndarray, np.ndarray]:
    lm = np.stack([standing_pose(**kw) for _ in range(n)])
    times = np.arange(n) / 12.0
    return lm, times


def test_mirror_map_is_an_involution_that_swaps_sides() -> None:
    for i, j in enumerate(L.MIRROR):
        assert L.MIRROR[j] == i
        a, b = L.NAMES[i], L.NAMES[j]
        if a.startswith("left_"):
            assert b == "right_" + a[5:]
    assert L.MIRROR[L.NOSE] == L.NOSE
    assert L.MIRROR[L.L_KNEE] == L.R_KNEE


def test_joint_angles_measured_correctly() -> None:
    lm, t = seq()
    f = compute_features(lm, t, 1000, 1000)
    assert f.angles["left_elbow"][0] == pytest.approx(90.0, abs=0.5)
    assert f.angles["right_elbow"][0] == pytest.approx(180.0, abs=0.5)
    assert f.angles["left_knee"][0] == pytest.approx(180.0, abs=0.5)
    assert f.angles["left_shoulder"][0] == pytest.approx(
        math.degrees(math.atan2(1.0, 0.0)) + math.degrees(math.atan2(0.3, 2.0)), abs=0.5
    )


def test_angle_is_null_when_a_required_landmark_is_unreliable() -> None:
    lm, t = seq()
    lm[:, L.L_WRIST, 3] = 0.1  # wrist not visible
    f = compute_features(lm, t, 1000, 1000)
    assert np.isnan(f.angles["left_elbow"]).all()
    assert not np.isnan(f.angles["right_elbow"]).any()


def test_normalization_is_invariant_to_position_and_size() -> None:
    a, t = seq(cx=0.3, cy=0.4, s=0.05)
    b, _ = seq(cx=0.7, cy=0.6, s=0.12)
    fa = compute_features(a, t, 1280, 720)
    fb = compute_features(b, t, 1280, 720)
    np.testing.assert_allclose(fa.norm[..., :2], fb.norm[..., :2], atol=1e-6)
    for k in fa.angles:
        np.testing.assert_allclose(fa.angles[k], fb.angles[k], atol=1e-6)


def test_aspect_ratio_correction_matters() -> None:
    # The same image-normalized coordinates describe a wider body on a 16:9 frame.
    lm, t = seq()
    square = compute_features(lm, t, 1000, 1000)
    wide = compute_features(lm, t, 1920, 1080)
    sq_w = abs(square.norm[0, L.L_SHOULDER, 0] - square.norm[0, L.R_SHOULDER, 0])
    wd_w = abs(wide.norm[0, L.L_SHOULDER, 0] - wide.norm[0, L.R_SHOULDER, 0])
    assert wd_w == pytest.approx(sq_w * 1920 / 1080, rel=1e-6)


def test_root_travel_is_kept_separately_from_shape() -> None:
    frames = [standing_pose(cx=0.3 + 0.01 * i) for i in range(24)]
    lm = np.stack(frames)
    t = np.arange(24) / 12.0
    f = compute_features(lm, t, 1000, 1000)
    # Shape is identical every frame…
    np.testing.assert_allclose(f.norm[0, :, :2], f.norm[-1, :, :2], atol=1e-3)
    # …but travel records the move to the right in torso units (torso = 0.2).
    assert f.travel[-1, 0] == pytest.approx(0.23 / 0.2, rel=0.05)
    assert f.energy[12] > 0


def test_frame_validity_requires_core_body() -> None:
    lm, t = seq(n=12)
    lm[3:6, L.L_HIP, 3] = 0.0  # hip hidden for three frames
    lm[8, :, :] = np.nan  # no detection at all
    f = compute_features(lm, t, 1000, 1000)
    assert f.valid.tolist() == [True] * 3 + [False] * 3 + [True] * 2 + [False] + [True] * 3
    assert f.confidence[8] == 0.0


def test_short_gaps_are_bridged_and_marked_long_gaps_are_not() -> None:
    v = np.arange(12, dtype=float)
    rel = np.ones(12, dtype=bool)
    rel[[3, 4]] = False  # 2-sample gap → bridged
    rel[7:11] = False  # 4-sample gap → left empty
    out, interp = fill_short_gaps(v, rel, max_gap=2)
    assert interp.tolist() == [i in (3, 4) for i in range(12)]
    assert out[3] == pytest.approx(3.0) and out[4] == pytest.approx(4.0)
    assert np.isnan(out[7:11]).all()


def test_smoothers_reduce_jitter_and_one_euro_tracks_fast_moves() -> None:
    """Comparison required by spec 12: EMA vs One-Euro vs Savitzky-Golay."""
    rng = np.random.default_rng(7)
    t = np.arange(120) / 12.0
    still = 0.5 + rng.normal(0, 0.004, size=120)
    rel = np.ones(120, dtype=bool)
    noise_raw = float(np.std(np.diff(still)))
    for out in (ema(still, rel, 0.4), one_euro(still, t, rel), savitzky_golay(still, rel, 7, 2)):
        assert float(np.std(np.diff(out))) < noise_raw * 0.8

    # A fast arm swing: 0 → 1 in 0.25 s. One-Euro must not lag far behind.
    step = np.clip((t - 2.0) / 0.25, 0, 1)
    oe = one_euro(step, t, rel)
    ex = ema(step, rel, 0.3)
    i = int(np.searchsorted(t, 2.35))
    assert abs(oe[i] - step[i]) < abs(ex[i] - step[i])
    assert abs(oe[i] - step[i]) < 0.35


def test_smoothing_restarts_after_unreliable_samples() -> None:
    v = np.array([0.0, 0.0, 0.0, 9.0, 1.0, 1.0])
    rel = np.array([True, True, True, False, True, True])
    out = one_euro(v, np.arange(6) / 12.0, rel)
    assert np.isnan(out[3])
    assert out[4] == pytest.approx(1.0)  # no smoothing across the gap


def test_select_track_follows_one_dancer_without_switching() -> None:
    a = standing_pose(cx=0.3)
    b = standing_pose(cx=0.75, s=0.12)  # bigger person on the right
    dets = [[b, a], [a, b], [a], [b, a]]
    track, counts, chosen = select_track(dets)
    assert counts.tolist() == [2, 2, 1, 2]
    # Starts on the larger body (b) and keeps following it. When only the other person is
    # visible, that frame has no pose for our dancer rather than a silent identity switch.
    assert chosen.tolist() == [0, 1, -1, 0]
    assert np.isnan(track[2]).all()
    assert track[0, L.L_HIP, 0] == pytest.approx(b[L.L_HIP, 0])
    assert track[3, L.L_HIP, 0] == pytest.approx(b[L.L_HIP, 0])


def test_quality_gates() -> None:
    cfg = QualityConfig()
    lm, t = seq(n=40)
    counts = np.ones(40, dtype=np.int64)
    ok = assess(compute_features(lm, t, 1000, 1000), counts, cfg)
    assert ok.failure is None and ok.coverage == 1.0 and ok.warnings == []

    cropped = lm.copy()
    cropped[:, list(L.FEET), 3] = 0.0
    rep = assess(compute_features(cropped, t, 1000, 1000), counts, cfg)
    assert rep.failure is None and "cropped_body" in rep.warnings

    sparse = lm.copy()
    sparse[:24] = np.nan  # 40% coverage
    c2 = counts.copy()
    c2[:24] = 0
    rep = assess(compute_features(sparse, t, 1000, 1000), c2, cfg)
    assert rep.failure == "low_coverage" and "40%" in (rep.failure_message or "")

    partial = lm.copy()
    partial[:10] = np.nan  # 75% coverage → warn, continue
    c3 = counts.copy()
    c3[:10] = 0
    rep = assess(compute_features(partial, t, 1000, 1000), c3, cfg)
    assert rep.failure is None and "partial_coverage" in rep.warnings

    many = counts.copy()
    many[:20] = 2
    rep = assess(compute_features(lm, t, 1000, 1000), many, cfg)
    assert rep.failure == "multiple_people"

    nothing = np.full_like(lm, np.nan)
    rep = assess(compute_features(nothing, t, 1000, 1000), np.zeros(40, dtype=np.int64), cfg)
    assert rep.failure == "no_dancer_detected"


def test_com_estimate_needs_most_of_the_body() -> None:
    lm, t = seq(n=4)
    f = compute_features(lm, t, 1000, 1000)
    assert not np.isnan(f.com[0]).any()
    # Upright symmetric pose: COM sits between shoulders and hips, above the hip root.
    assert f.com[0, 1] < 0 and abs(f.com[0, 0]) < 0.2
    no_shins = lm.copy()
    no_shins[:, [L.L_ANKLE, L.R_ANKLE], 3] = 0.0  # 12% of mass unseen → still estimated
    assert not np.isnan(compute_features(no_shins, t, 1000, 1000).com[0]).any()
    legless = lm.copy()
    legless[:, [L.L_KNEE, L.R_KNEE, L.L_ANKLE, L.R_ANKLE], 3] = 0.0  # 32% unseen → no estimate
    f2 = compute_features(legless, t, 1000, 1000)
    assert f2.valid[0] and np.isnan(f2.com[0]).all()

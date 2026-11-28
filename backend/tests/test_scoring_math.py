"""Versioned scoring (spec 18, Outcome 7) — pure maths on synthetic landmark sequences that go
through the production path (landmarks → features → stored payload → sequence → align →
score). They test the scoring rules, not claims about real dancers; the golden relationships
on real footage live in test_scoring_golden.py.
"""

from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pytest

from app.pose.alignment import align
from app.pose.scoring import SCORE_VERSION, WEIGHTS, ScoreConfig, curve, score
from tests.test_alignment_math import (
    REF,
    arm_angles,
    clip,
    lower_left_arm,
    straight_left_elbow,
)

Report = dict[str, Any]


def scored(learner: Any, ref: Any = REF, **kw: Any) -> Report:
    a = align(ref, learner)
    out: Report = score(ref, learner, a, **kw)
    assert out["version"] == SCORE_VERSION == "score-1"
    return out


def comp(r: Report, name: str) -> float:
    v = r["components"][name]
    assert isinstance(v, float), (name, r["status"], r.get("reason"))
    return v


@pytest.fixture(scope="module")
def perfect() -> Report:
    return scored(clip())


def test_curve_is_bounded_monotonic_and_half_at_x50() -> None:
    xs = np.linspace(0, 10, 101)
    ys = curve(xs, 0.3)
    assert ys[0] == pytest.approx(100.0)
    assert float(curve(0.3, 0.3)) == pytest.approx(50.0)
    assert np.all(np.diff(ys) <= 0) and np.all((ys >= 0) & (ys <= 100))
    assert float(curve(-1.0, 0.3)) == pytest.approx(100.0)  # negative error clamps to 0


def test_weights_are_the_requested_product_weights() -> None:
    assert WEIGHTS == {
        "pose": 0.30,
        "timing": 0.25,
        "sequence": 0.20,
        "joint_angles": 0.15,
        "rhythm": 0.10,
    }
    assert math.isclose(sum(WEIGHTS.values()), 1.0)


def test_identical_attempt_scores_near_the_top(perfect: Report) -> None:
    assert perfect["status"] == "scored"
    for k in ("pose", "timing", "sequence", "joint_angles"):
        assert comp(perfect, k) >= 97, (k, perfect["components"])
    assert perfect["overall"] >= 95
    assert math.isclose(sum(perfect["weights_used"].values()), 1.0, abs_tol=1e-3)
    cov = perfect["coverage"]
    assert cov["visible_joint_coverage"] == pytest.approx(1.0, abs=0.02)
    assert cov["compared_frames"] >= 80
    assert cov["confidence"] >= 0.8


def test_report_is_deterministic_and_json_ready(perfect: Report) -> None:
    again = scored(clip())
    assert json.dumps(again, sort_keys=True) == json.dumps(perfect, sort_keys=True)


def test_size_and_position_do_not_dominate(perfect: Report) -> None:
    r = scored(clip(s=0.035, cx=0.3, cy=0.55))
    assert r["overall"] >= perfect["overall"] - 4


def test_small_timing_shift_hits_timing_more_than_pose(perfect: Report) -> None:
    r = scored(clip(time_map=lambda t: max(0.0, t - 0.5)))  # every move 0.5 s late
    timing_drop = comp(perfect, "timing") - comp(r, "timing")
    pose_drop = comp(perfect, "pose") - comp(r, "pose")
    assert timing_drop >= 20 and timing_drop > pose_drop + 15, r["components"]
    assert r["evidence"]["timing"]["median_offset_s"] == pytest.approx(0.5, abs=0.12)


def test_wrong_arm_lowers_pose_and_angles_and_points_at_the_arm(perfect: Report) -> None:
    r = scored(clip(pose=lower_left_arm))
    assert comp(r, "pose") < comp(perfect, "pose") - 10, r["components"]
    assert r["body_parts"]["left_arm"]["value"] < r["body_parts"]["right_arm"]["value"] - 10
    assert all("left_arm" in m["largest_differences"] for m in r["moments"]["worst"])
    elbow = scored(clip(pose=straight_left_elbow))
    assert comp(elbow, "joint_angles") < comp(perfect, "joint_angles") - 10, elbow["components"]
    assert elbow["overall"] < perfect["overall"]


def test_missing_movement_lowers_sequence(perfect: Report) -> None:
    def frozen_middle(t: float) -> tuple[float, float, float, float]:
        return arm_angles(min(t, 3.0) if t < 6.0 else t)

    r = scored(clip(pose=frozen_middle))
    assert comp(r, "sequence") < comp(perfect, "sequence") - 10, r["evidence"]["sequence"]
    assert r["evidence"]["sequence"]["missing_share"] > 0.1


def test_untracked_moments_cost_confidence_not_points(perfect: Report) -> None:
    r = scored(clip(missing=(3.0, 4.5)))
    assert r["status"] in {"scored", "qualified"}
    assert r["coverage"]["confidence"] < perfect["coverage"]["confidence"]
    assert r["coverage"]["compared_frames"] < perfect["coverage"]["compared_frames"]
    assert "untracked_moments_skipped" in r["warnings"]
    for k in ("pose", "joint_angles", "sequence"):
        assert comp(r, k) >= comp(perfect, k) - 4, (k, r["components"])


def test_mostly_untracked_attempt_is_not_scored() -> None:
    r = scored(clip(missing=(0.5, 7.5)))
    assert r["status"] == "not_scored"
    assert r["overall"] is None and all(v is None for v in r["components"].values())


def test_low_confidence_suppresses_every_number() -> None:
    strict = ScoreConfig(suppress_confidence=0.99)
    r = scored(clip(missing=(2.0, 5.0)), cfg=strict)
    assert r["status"] == "suppressed" and r["reason"] == "low_confidence"
    assert r["overall"] is None and all(v is None for v in r["components"].values())
    assert r["message"]


def test_moderately_uncertain_attempt_is_qualified_not_hidden() -> None:
    cfg = ScoreConfig(qualify_confidence=1.01)
    r = scored(clip(), cfg=cfg)
    assert r["status"] == "qualified" and "low_confidence" in r["qualifiers"]
    assert isinstance(r["overall"], float)


def test_immobile_reference_is_not_scored() -> None:
    def still(t: float) -> tuple[float, float, float, float]:
        return 40.0, 40.0, 20.0, 20.0

    ref = clip(pose=still)
    r = scored(clip(pose=still), ref=ref)
    assert r["status"] == "not_scored" and r["reason"] == "reference_immobile"


def test_rhythm_is_gated_and_the_rest_reweighted() -> None:
    short_ref = clip(seconds=3.0)
    r = scored(clip(seconds=3.0), ref=short_ref)
    assert r["components"]["rhythm"] is None
    assert r["evidence"]["rhythm"]["unavailable"] == "too_short"
    assert "rhythm" not in r["weights_used"]
    assert math.isclose(sum(r["weights_used"].values()), 1.0, abs_tol=1e-3)
    assert r["weights_used"]["pose"] == pytest.approx(0.30 / 0.90, abs=1e-3)
    assert any(w.startswith("rhythm_unavailable") for w in r["warnings"])


def accented(t: float) -> tuple[float, float, float, float]:
    """Move for half a second, hold for half a second: a clear motion accent every second."""
    k = math.floor(t)
    return arm_angles(k + min(1.0, 2.0 * (t - k)))


def test_rhythm_needs_motion_accents(perfect: Report) -> None:
    # Smooth sinusoidal arms have no accents: rhythm is unavailable, not penalised.
    assert perfect["components"]["rhythm"] is None
    assert perfect["evidence"]["rhythm"]["unavailable"] == "no_clear_accents"


def test_rhythm_reflects_tempo() -> None:
    ref = clip(pose=accented)
    same = scored(clip(pose=accented), ref=ref)
    fast = scored(clip(pose=accented, time_map=lambda t: t * 1.25, seconds=6.4), ref=ref)
    assert isinstance(same["components"]["rhythm"], float), same["evidence"]["rhythm"]
    assert isinstance(fast["components"]["rhythm"], float), fast["evidence"]["rhythm"]
    assert same["components"]["rhythm"] >= 90
    assert fast["evidence"]["rhythm"]["pace_ratio"] == pytest.approx(0.8, abs=0.08)
    assert fast["components"]["rhythm"] < same["components"]["rhythm"] - 10


def test_section_breakdown_finds_the_weak_part(perfect: Report) -> None:
    def wrong_second_half(t: float) -> tuple[float, float, float, float]:
        return lower_left_arm(t) if t >= 4.0 else arm_angles(t)

    sections = [
        {"id": "a", "title": "Section 1", "start": 0.0, "end": 4.0},
        {"id": "b", "title": "Section 2", "start": 4.0, "end": 8.0},
    ]
    r = scored(clip(pose=wrong_second_half), sections=sections)
    a, b = r["sections"]
    assert a["status"] == b["status"] == "scored"
    assert b["overall"] < a["overall"] - 5, r["sections"]
    assert a["compared_pairs"] + b["compared_pairs"] <= r["coverage"]["compared_frames"] + 1


def test_scores_are_bounded_for_arbitrary_movement() -> None:
    rng = np.random.default_rng(7)  # deterministic seed: a property check, not a result
    for _ in range(4):
        a, b, c, d = rng.uniform(0, 160, 4)
        p = rng.uniform(1.0, 3.0)

        def pose(
            t: float, a: float = a, b: float = b, c: float = c, d: float = d, p: float = p
        ) -> tuple[float, float, float, float]:
            w = 0.5 - 0.5 * math.cos(2 * math.pi * t / p)
            return a * w + 10, b * (1 - w) + 10, c * w, d * w

        r = scored(clip(pose=pose))
        for v in [r["overall"], *r["components"].values()]:
            assert v is None or 0.0 <= v <= 100.0
        for s in r["sections"]:
            assert s["overall"] is None or 0 <= s["overall"] <= 100


def test_alignment_from_other_sequences_is_rejected() -> None:
    a = align(REF, clip())
    with pytest.raises(ValueError):
        score(REF, clip(seconds=5.0), a)

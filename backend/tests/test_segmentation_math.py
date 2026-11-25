"""Pure segmentation + instruction maths (spec 14, 15). Synthetic feature sequences are allowed
here only: these tests check the algorithm, not the pose model."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.pose import landmarks as L
from app.pose.instructions import SectionInput, describe_section
from app.pose.segmentation import (
    InvalidSections,
    SegmentationConfig,
    cut_scores,
    suggest_boundaries,
    validate_sections,
)

FPS = 12.0
CFG = SegmentationConfig()
J = len(L.MAJOR)


def timeline(duration: float) -> np.ndarray:
    return np.arange(int(duration * FPS)) / FPS


def still_pose(n: int) -> np.ndarray:
    base = np.stack([np.linspace(-0.5, 0.5, J), np.linspace(-1.0, 1.0, J)], axis=1)
    return np.repeat(base[None], n, axis=0).astype(np.float64)


def moving_pose(times: np.ndarray, moving: np.ndarray) -> np.ndarray:
    """Joints oscillate where `moving` is true and freeze elsewhere."""
    pose = still_pose(len(times))
    phase = np.cumsum(moving.astype(float)) / FPS
    pose[:, :, 0] += (0.4 * np.sin(2 * math.pi * 1.0 * phase))[:, None]
    return pose


def energy_of(pose: np.ndarray, times: np.ndarray) -> np.ndarray:
    v = np.gradient(pose, axis=0) / np.gradient(times)[:, None, None]
    return np.linalg.norm(v, axis=2).mean(axis=1)


def assert_tiles(sections: list[tuple[float, float]], duration: float) -> None:
    assert sections[0][0] == 0.0
    assert sections[-1][1] == pytest.approx(duration, abs=1e-6)
    for (_, e), (s, _) in zip(sections[:-1], sections[1:], strict=True):
        assert s == e  # no gap, no overlap
    for s, e in sections:
        assert e > s


@pytest.mark.parametrize("duration", [0.6, 3.0, 6.9])
def test_short_clip_is_one_section(duration: float) -> None:
    t = timeline(duration)
    pose = moving_pose(t, np.ones(len(t), bool))
    out = suggest_boundaries(t, energy_of(pose, t), pose, duration)
    assert out == [(0.0, round(duration, 3))]


def test_long_continuous_movement_is_split_into_teachable_lengths() -> None:
    duration = 29.5
    t = timeline(duration)
    pose = moving_pose(t, np.ones(len(t), bool))
    out = suggest_boundaries(t, energy_of(pose, t), pose, duration)
    assert_tiles(out, duration)
    assert len(out) >= 4
    for s, e in out:
        assert CFG.min_len - 1e-6 <= e - s <= CFG.max_len + 1e-6


def test_clear_pauses_become_boundaries() -> None:
    duration = 18.0
    t = timeline(duration)
    moving = np.ones(len(t), bool)
    pauses = [6.0, 12.0]
    for p in pauses:
        moving[(t > p - 0.5) & (t < p + 0.5)] = False
    pose = moving_pose(t, moving)
    out = suggest_boundaries(t, energy_of(pose, t), pose, duration)
    assert_tiles(out, duration)
    cuts = [e for _, e in out[:-1]]
    assert len(cuts) == 2
    for p, c in zip(pauses, cuts, strict=True):
        assert abs(c - p) <= 0.6, (cuts, pauses)


def test_no_movement_still_tiles_evenly_and_deterministically() -> None:
    duration = 20.0
    t = timeline(duration)
    pose = still_pose(len(t))
    e = energy_of(pose, t)
    a = suggest_boundaries(t, e, pose, duration)
    b = suggest_boundaries(t, e, pose, duration)
    assert a == b
    assert_tiles(a, duration)
    lengths = [y - x for x, y in a]
    assert max(lengths) - min(lengths) <= 1.0


def test_missing_pose_spans_still_cover_the_video() -> None:
    duration = 16.0
    t = timeline(duration)
    pose = moving_pose(t, np.ones(len(t), bool))
    e = energy_of(pose, t)
    gap = (t > 5.0) & (t < 11.0)
    pose[gap] = np.nan
    e[gap] = np.nan
    out = suggest_boundaries(t, e, pose, duration)
    assert_tiles(out, duration)
    scores = cut_scores(t, e, pose)
    deep = (t > 5.5) & (t < 10.5)  # beyond the smoothing window of measured frames
    assert np.all(scores.cost[deep] == pytest.approx(CFG.unknown_cost))
    assert np.all((scores.cost >= 0) & (scores.cost <= 1))


def test_no_frames_or_bad_duration() -> None:
    z = np.zeros(0)
    assert suggest_boundaries(z, z, np.zeros((0, J, 2)), 0.0) == []
    assert suggest_boundaries(z, z, np.zeros((0, J, 2)), 20.0)  # sparse: even split fallback
    assert_tiles(suggest_boundaries(z, z, np.zeros((0, J, 2)), 20.0), 20.0)


def test_pause_scores_lower_than_motion() -> None:
    t = timeline(12.0)
    moving = np.ones(len(t), bool)
    moving[(t > 5.5) & (t < 6.5)] = False
    pose = moving_pose(t, moving)
    s = cut_scores(t, energy_of(pose, t), pose)
    i_pause = int(np.argmin(np.abs(t - 6.0)))
    i_move = int(np.argmin(np.abs(t - 3.1)))
    assert s.cost[i_pause] < s.cost[i_move]


# ---- edits ---------------------------------------------------------------------------------


def test_valid_edit_snaps_to_full_coverage() -> None:
    out = validate_sections([(0.004, 4.0), (4.0, 9.5), (9.5, 14.996)], 15.0)
    assert out == [(0.0, 4.0), (4.0, 9.5), (9.5, 15.0)]


@pytest.mark.parametrize(
    ("sections", "code"),
    [
        ([], "sections_empty"),
        ([(0.5, 15.0)], "sections_gap"),
        ([(0.0, 5.0), (5.5, 15.0)], "sections_gap"),
        ([(0.0, 5.0), (4.0, 15.0)], "sections_overlap"),
        ([(0.0, 5.0), (5.0, 14.0)], "sections_incomplete"),
        ([(0.0, 0.2), (0.2, 15.0)], "section_too_short"),
        ([(0.0, 14.8), (14.8, 15.0)], "section_too_short"),
        ([(0.0, float("nan")), (5.0, 15.0)], "invalid_section_time"),
        ([(i * 0.35, (i + 1) * 0.35) for i in range(43)], "too_many_sections"),
    ],
)
def test_invalid_edits_are_rejected(sections: list[tuple[float, float]], code: str) -> None:
    with pytest.raises(InvalidSections) as exc:
        validate_sections(sections, 15.0)
    assert exc.value.code == code


# ---- instructions --------------------------------------------------------------------------


def section(n: int = 36) -> dict[str, np.ndarray]:
    norm = np.full((n, L.NUM_LANDMARKS, 2), np.nan)
    for j, (x, y) in {
        L.L_SHOULDER: (0.4, -1.0),
        L.R_SHOULDER: (-0.4, -1.0),
        L.L_HIP: (0.2, 0.0),
        L.R_HIP: (-0.2, 0.0),
        L.L_ELBOW: (0.6, -0.5),
        L.R_ELBOW: (-0.6, -0.5),
        L.L_WRIST: (0.6, 0.0),
        L.R_WRIST: (-0.6, 0.0),
    }.items():
        norm[:, j] = (x, y)
    return {
        "norm": norm,
        "travel": np.zeros((n, 2)),
        "lean": np.zeros(n),
        "energy": np.ones(n),
        "valid": np.ones(n, bool),
    }


def make_input(
    d: dict[str, np.ndarray], angles: dict[str, np.ndarray] | None = None
) -> SectionInput:
    n = len(d["valid"])
    a = {name: np.full(n, np.nan) for name in L.ANGLES}
    a.update(angles or {})
    return SectionInput(
        norm=d["norm"],
        angles=a,
        travel=d["travel"],
        lean=d["lean"],
        energy=d["energy"],
        valid=d["valid"],
        clip_energy=1.0,
    )


def test_raising_dancers_left_arm_uses_learner_side_per_perspective() -> None:
    d = section()
    d["norm"][18:, L.L_WRIST, 1] = -1.6  # left wrist above the left shoulder for the 2nd half
    desc = describe_section(make_input(d))
    assert "Raise your left arm above shoulder level" in desc.instruction_mirror
    assert "Raise your right arm above shoulder level" in desc.instruction_direct
    assert desc.facts[0].side == "left"


def test_both_arms_and_travel_direction() -> None:
    d = section()
    d["norm"][:, L.L_WRIST, 1] = -1.6
    d["norm"][:, L.R_WRIST, 1] = -1.6
    d["travel"][:, 0] = np.linspace(0, 1.2, 36)  # toward image right = dancer's left
    desc = describe_section(make_input(d))
    assert desc.instruction_mirror.startswith("Keep both arms above shoulder level")
    assert "Travel to your left" in desc.instruction_mirror
    assert "Travel to your right" in desc.instruction_direct


def test_untracked_legs_are_never_described() -> None:
    d = section()
    knee = np.full(36, 95.0)  # would trigger "bend your knees" if it were trusted
    knee[::2] = np.nan  # but only half of the frames measured it reliably…
    knee[1::4] = np.nan  # …now only a quarter
    desc = describe_section(make_input(d, {"left_knee": knee, "right_knee": knee}))
    assert "knee" not in desc.instruction_mirror.lower()
    assert "left leg" in desc.untracked and "right leg" in desc.untracked


def test_measured_knee_bend_is_described_with_rounded_angle() -> None:
    d = section()
    knee = np.linspace(175, 112, 36)
    desc = describe_section(make_input(d, {"left_knee": knee, "right_knee": knee}))
    assert "Bend your knees (to about 120°)" in desc.instruction_mirror


def test_low_coverage_section_says_so() -> None:
    d = section()
    d["valid"][:24] = False
    desc = describe_section(make_input(d))
    assert desc.instruction_mirror == "Tracking is limited in this section — follow the video."
    assert desc.coverage == pytest.approx(1 / 3)
    assert desc.facts == []


def test_instruction_is_brief_and_deterministic() -> None:
    d = section()
    d["norm"][:, L.L_WRIST, 1] = -1.6
    d["travel"][:, 0] = np.linspace(0, -1.0, 36)
    d["lean"][:] = 20.0
    a = describe_section(make_input(d))
    b = describe_section(make_input(d))
    assert a.as_dict() == b.as_dict()
    assert len(a.facts) <= 3
    assert a.as_dict()["experimental"] is True


def test_both_elbows_bending_are_one_statement_with_sides_swapped_in_direct_view() -> None:
    d = section()
    left = np.r_[np.full(6, 170.0), np.full(30, 78.0)]
    right = np.r_[np.full(6, 170.0), np.full(30, 98.0)]
    desc = describe_section(make_input(d, {"left_elbow": left, "right_elbow": right}))
    assert "Bend both elbows (left about 80°, right about 100°)" in desc.instruction_mirror
    assert "Bend both elbows (left about 100°, right about 80°)" in desc.instruction_direct
    same = describe_section(make_input(d, {"left_elbow": left, "right_elbow": left}))
    assert "Bend both elbows to about 80°" in same.instruction_mirror

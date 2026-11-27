"""Pure tests of "who is in the video" and following a chosen person (spec amendment A2).

Synthetic landmark detections and synthetic colour histograms are allowed here (and only in
pure-math tests): they test the identity rules, not the product's claims about real dancers.
The same rules are checked end to end on real composited footage in test_subject_choice.py.
"""

from __future__ import annotations

import numpy as np

from app.pose import people as P
from tests.test_pose_math import standing_pose

RED = np.zeros(64)
RED[48] = 1.0  # all pixels in one reddish bin
NAVY = np.zeros(64)
NAVY[1] = 1.0
RED_ISH = 0.9 * RED + 0.1 * NAVY


def frames(
    *people: list[tuple[float, np.ndarray | None]],
) -> tuple[list[list[np.ndarray]], list[list[np.ndarray | None]], list[list[int]], np.ndarray]:
    """people[k][t] = (x position or nan for absent, appearance) for person k at frame t."""
    n = len(people[0])
    dets: list[list[np.ndarray]] = []
    looks: list[list[np.ndarray | None]] = []
    for t in range(n):
        d: list[np.ndarray] = []
        a: list[np.ndarray | None] = []
        for person in people:
            x, look = person[t]
            if not np.isnan(x):
                d.append(standing_pose(cx=x, cy=0.55, s=0.05))
                a.append(look)
        dets.append(d)
        looks.append(a)
    distinct, _ = P.distinct_detections(dets)
    return dets, looks, distinct, np.arange(n) / 12.0


def xs(dets: list[list[np.ndarray]], res: P.FollowResult) -> list[float | None]:
    return [
        None if k < 0 else round(float(P.pose_root(dets[t][int(k)])[0]), 3)
        for t, k in enumerate(res.chosen)
    ]


def test_overlapping_second_detection_is_the_same_person() -> None:
    body = standing_pose(cx=0.5, cy=0.55, s=0.05)
    upper = body.copy()
    upper[23:, 3:] = 0.0  # only the upper body reported again (the CI false positive)
    other = standing_pose(cx=0.85, cy=0.55, s=0.05)
    assert P.distinct_people([body, upper]) == [0]
    assert P.distinct_people([upper, body]) == [1]
    assert sorted(P.distinct_people([body, other])) == [0, 1]
    assert P.distinct_people([body, upper, other]) == [0, 2] or set(
        P.distinct_people([body, upper, other])
    ) == {0, 2}


def test_body_box_and_overlap_ratio() -> None:
    b = P.body_box(standing_pose(cx=0.5, cy=0.5, s=0.1))
    assert b is not None and b[0] < 0.5 < b[2] and b[1] < 0.5 < b[3]
    inner = np.asarray([0.4, 0.4, 0.5, 0.5])
    outer = np.asarray([0.0, 0.0, 1.0, 1.0])
    assert P.overlap_ratio(inner, outer) == 1.0
    assert P.overlap_ratio(inner, np.asarray([0.6, 0.6, 0.7, 0.7])) == 0.0
    empty = np.zeros((33, 5))
    assert P.body_box(empty) is None


def test_appearance_histogram_and_distance() -> None:
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img[:, :50] = (150, 30, 40)  # maroon left half
    img[:, 50:] = (25, 30, 60)  # navy right half
    left = P.appearance_of(img, standing_pose(cx=0.25, cy=0.6, s=0.05))
    right = P.appearance_of(img, standing_pose(cx=0.75, cy=0.6, s=0.05))
    assert left is not None and right is not None
    assert abs(left.sum() - 1) < 1e-9
    assert P.appearance_distance(left, left) == 0.0
    d = P.appearance_distance(left, right)
    assert d is not None and d > 0.9
    assert P.appearance_distance(left, None) is None
    # Torso outside the frame → nothing measured.
    assert P.appearance_of(img, standing_pose(cx=1.6, cy=0.6, s=0.05)) is None


def test_survey_numbers_people_left_to_right() -> None:
    n = 24
    a = [(0.7, RED)] * n
    b = [(0.25, NAVY)] * n
    dets, looks, distinct, times = frames(a, b)
    s = P.survey_people(dets, looks, distinct, times)
    assert s is not None and [c.person for c in s.candidates] == [1, 2]
    assert s.candidates[0].root[0] < s.candidates[1].root[0]
    assert [c.position for c in s.candidates] == ["left", "right"]
    assert all(c.share == 1.0 for c in s.candidates)
    # Single person → no survey.
    d1, l1, ds1, t1 = frames(a)
    assert P.survey_people(d1, l1, ds1, t1) is None


def test_follow_keeps_the_chosen_person_through_a_crossing() -> None:
    """Two people swap sides; mid-crossing they overlap. Position alone would hand the follower
    to whoever is nearer; appearance keeps the identity (or masks), never a silent switch."""
    n = 36
    path_a = [0.2 + 0.6 * t / (n - 1) for t in range(n)]  # red walks left → right
    path_b = [0.8 - 0.6 * t / (n - 1) for t in range(n)]  # navy walks right → left
    a = [(x, RED) for x in path_a]
    b = [(x, NAVY) for x in path_b]
    dets, looks, distinct, _ = frames(a, b)
    first = 0
    red = next(i for i, look in enumerate(looks[first]) if look is RED)
    res = P.follow_person(dets, looks, distinct, first, red, max_jump=0.2)
    for t, x in enumerate(xs(dets, res)):
        if x is not None:
            assert abs(x - path_a[t]) < 0.03, (t, x)  # always the red person
    assert res.followed_fraction > 0.8
    navy = next(i for i, look in enumerate(looks[first]) if look is NAVY)
    res_b = P.follow_person(dets, looks, distinct, first, navy, max_jump=0.2)
    for t, x in enumerate(xs(dets, res_b)):
        if x is not None:
            assert abs(x - path_b[t]) < 0.03, (t, x)


def test_follow_masks_when_the_chosen_person_leaves_instead_of_switching() -> None:
    n = 40
    a = [(float("nan"), RED) if 12 <= t < 24 else (0.3, RED) for t in range(n)]
    b = [(0.7, NAVY)] * n
    dets, looks, distinct, times = frames(a, b)
    red = next(i for i, look in enumerate(looks[0]) if look is RED)
    res = P.follow_person(dets, looks, distinct, 0, red)
    got = xs(dets, res)
    assert all(x is None for x in got[12:24])  # masked, not the navy person at 0.7
    assert all(x == 0.3 for x in got[:12] + got[24:])  # comes back after the gap
    assert set(res.status[12:24]) == {"lost"}
    spans = P.status_spans(times, res.status, ("lost",))
    assert spans == [(times[12], times[23])]


def test_follow_marks_lookalikes_overlapping_as_uncertain() -> None:
    n = 20
    a = [(0.5 if 8 <= t < 12 else 0.3, RED) for t in range(n)]
    b = [(0.52 if 8 <= t < 12 else 0.7, RED_ISH) for t in range(n)]  # dressed almost the same
    dets, looks, distinct, _ = frames(a, b)
    first = next(i for i, look in enumerate(looks[0]) if look is RED)
    res = P.follow_person(dets, looks, distinct, 0, first)
    # While they overlap the follower can't tell them apart: never picks the wrong one.
    for t in range(8, 12):
        assert res.status[t] in ("uncertain", "lost") or xs(dets, res)[t] == 0.5
    assert all(x in (None, 0.3, 0.5) for x in xs(dets, res))


def test_follow_without_appearance_needs_an_unambiguous_single_body() -> None:
    n = 12
    a = [(0.3, None)] * n
    dets, looks, distinct, _ = frames(a)
    res = P.follow_person(dets, looks, distinct, 0, 0)
    assert res.followed_fraction == 1.0
    b = [(0.45, None)] * n  # someone unmeasurable right next to them
    dets2, looks2, distinct2, _ = frames(a, b)
    res2 = P.follow_person(dets2, looks2, distinct2, 0, 0)
    assert res2.status[1:] == ["uncertain"] * (n - 1)


def test_locate_choice_finds_the_person_at_the_stored_moment() -> None:
    n = 12
    a = [(0.3, RED)] * n
    b = [(0.7, NAVY)] * n
    dets, _, distinct, times = frames(a, b)
    root_b = P.pose_root(dets[6][1])
    found = P.locate_choice(dets, distinct, times, float(times[6]), (root_b[0], root_b[1]))
    assert found is not None and found[0] == 6
    assert abs(P.pose_root(dets[6][found[1]])[0] - 0.7) < 1e-9
    assert P.locate_choice(dets, distinct, times, float(times[6]), (0.5, 0.1)) is None

"""Who is in the video, and following the person the user chose (spec amendment A2).

Pure functions over real MediaPipe detections. A detection is a (33,5) landmark array
(image-normalized x, y, z, visibility, presence) plus an optional appearance descriptor: a
colour histogram of the torso measured on the real video frame (`appearance_of`).

Identity rules (A2 robustness requirements):
- a second detection that overlaps the main body is the same person seen twice, not another
  person (`distinct_people`);
- the chosen person is followed by position, and by appearance whenever more than one person is
  near; if identity is uncertain (people overlap and look alike) or the person is gone, the
  frame is masked and labelled — the follower never silently switches to someone else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from app.pose import landmarks as L
from app.pose.features import confidence_of

FloatArray = NDArray[np.float64]
UInt8Array = NDArray[np.uint8]

PEOPLE_VERSION = "people-1"
MAX_CANDIDATES = 4

# Two detections whose bodies overlap by more than this (intersection over the smaller box)
# are one person.
SAME_PERSON_OVERLAP = 0.6
# Candidate people offered to the user must be clearly apart in the chosen frame.
CANDIDATE_MAX_OVERLAP = 0.25
# Appearance: Hellinger distance between torso colour histograms (0 = identical, 1 = disjoint).
APPEARANCE_MATCH = 0.45  # at most this far from the chosen person's look to be accepted
APPEARANCE_MARGIN = 0.12  # and this much closer than anyone else nearby

FrameStatus = Literal["followed", "lost", "uncertain"]


# --------------------------------------------------------------------------------------------
# Geometry and appearance of a single detection
# --------------------------------------------------------------------------------------------


def body_box(pose: FloatArray, threshold: float = 0.5) -> FloatArray | None:
    """[x0, y0, x1, y1] (image-normalized, clipped to the frame) of the confident landmarks."""
    conf = confidence_of(pose)
    pts = pose[conf >= threshold, :2]
    pts = pts[np.isfinite(pts).all(axis=1)]
    if len(pts) < 3:
        return None
    lo = np.clip(pts.min(axis=0), 0.0, 1.0)
    hi = np.clip(pts.max(axis=0), 0.0, 1.0)
    if hi[0] - lo[0] <= 1e-3 or hi[1] - lo[1] <= 1e-3:
        return None
    return np.asarray([lo[0], lo[1], hi[0], hi[1]], dtype=np.float64)


def box_area(b: FloatArray) -> float:
    return float(max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1]))


def overlap_ratio(a: FloatArray, b: FloatArray) -> float:
    """Intersection over the smaller box (1.0 when one box sits inside the other)."""
    iw = min(a[2], b[2]) - max(a[0], b[0])
    ih = min(a[3], b[3]) - max(a[1], b[1])
    if iw <= 0 or ih <= 0:
        return 0.0
    small = min(box_area(a), box_area(b))
    return float(iw * ih / small) if small > 0 else 0.0


def pose_root(pose: FloatArray) -> FloatArray:
    """Hip midpoint; shoulder midpoint when the hips are missing (image-normalized)."""
    hips = (pose[L.L_HIP, :2] + pose[L.R_HIP, :2]) / 2
    if np.isfinite(hips).all():
        return np.asarray(hips, dtype=np.float64)
    return np.asarray((pose[L.L_SHOULDER, :2] + pose[L.R_SHOULDER, :2]) / 2, dtype=np.float64)


def appearance_of(rgb: UInt8Array, pose: FloatArray, bins: int = 4) -> FloatArray | None:
    """Colour histogram (bins^3, L1-normalized) of the torso area between shoulders and hips,
    measured on the real frame. None when the torso is too small or off-frame."""
    h, w = rgb.shape[:2]
    pts = pose[[L.L_SHOULDER, L.R_SHOULDER, L.L_HIP, L.R_HIP], :2]
    if not np.isfinite(pts).all():
        return None
    x0, y0 = pts.min(axis=0)
    x1, y1 = pts.max(axis=0)
    # Shrink towards the middle of the torso so arms and background contribute little.
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hw, hh = max((x1 - x0) * 0.35, 0.01), max((y1 - y0) * 0.4, 0.01)
    px0, px1 = int(np.clip((cx - hw) * w, 0, w)), int(np.clip((cx + hw) * w, 0, w))
    py0, py1 = int(np.clip((cy - hh) * h, 0, h)), int(np.clip((cy + hh) * h, 0, h))
    if px1 - px0 < 4 or py1 - py0 < 4:
        return None
    patch = rgb[py0:py1, px0:px1].reshape(-1, 3).astype(np.int64)
    q = (patch * bins) // 256
    idx = q[:, 0] * bins * bins + q[:, 1] * bins + q[:, 2]
    hist = np.bincount(idx, minlength=bins**3).astype(np.float64)
    total = hist.sum()
    return hist / total if total > 0 else None


def appearance_distance(a: FloatArray | None, b: FloatArray | None) -> float | None:
    """Hellinger distance in [0, 1]; None when either side is unmeasured."""
    if a is None or b is None:
        return None
    bc = float(np.sum(np.sqrt(a * b)))
    return float(np.sqrt(max(0.0, 1.0 - min(1.0, bc))))


# --------------------------------------------------------------------------------------------
# Per-frame: distinct people
# --------------------------------------------------------------------------------------------


def distinct_people(poses: list[FloatArray], threshold: float = 0.5) -> list[int]:
    """Indices of detections that are separate people, largest body first. A detection that
    mostly overlaps a bigger one (e.g. the upper and lower half of one dancer reported twice)
    is dropped. Detections without a measurable body are dropped too."""
    boxes = [body_box(p, threshold) for p in poses]
    order = sorted(
        (i for i, b in enumerate(boxes) if b is not None),
        key=lambda i: -box_area(boxes[i]),  # type: ignore[arg-type]
    )
    kept: list[int] = []
    for i in order:
        bi = boxes[i]
        assert bi is not None
        if all(overlap_ratio(bi, boxes[k]) <= SAME_PERSON_OVERLAP for k in kept):  # type: ignore[arg-type]
            kept.append(i)
    return kept


def distinct_detections(
    detections: list[list[FloatArray]], threshold: float = 0.5
) -> tuple[list[list[int]], NDArray[np.int64]]:
    """Per frame: indices of distinct people, and how many there are."""
    kept = [distinct_people(poses, threshold) for poses in detections]
    counts = np.asarray([len(k) for k in kept], dtype=np.int64)
    return kept, counts


# --------------------------------------------------------------------------------------------
# Following one chosen person
# --------------------------------------------------------------------------------------------


@dataclass
class FollowResult:
    chosen: NDArray[np.int64]  # detection index per frame (-1 = not followed)
    status: list[FrameStatus]  # why a frame has / hasn't got the chosen person
    seed_frame: int

    @property
    def followed_fraction(self) -> float:
        n = len(self.status)
        return sum(s == "followed" for s in self.status) / n if n else 0.0


def _follow_pass(
    detections: list[list[FloatArray]],
    appearances: list[list[FloatArray | None]],
    distinct: list[list[int]],
    frames: range,
    start_root: FloatArray,
    ref_look: FloatArray | None,
    chosen: NDArray[np.int64],
    status: list[FrameStatus],
    *,
    max_jump: float,
    reacquire_after: int,
) -> None:
    last_root = start_root
    look = ref_look
    missing = 0
    for t in frames:
        people = distinct[t]
        if not people:
            status[t] = "lost"
            missing += 1
            continue
        dists = {i: float(np.linalg.norm(pose_root(detections[t][i]) - last_root)) for i in people}
        looks = {
            i: appearance_distance(appearances[t][i] if i < len(appearances[t]) else None, look)
            for i in people
        }
        # The search radius grows a little during a short gap; after a long gap the person may
        # come back anywhere, but then only an appearance match can bring them back.
        radius = max_jump * (1.0 + 0.5 * min(missing, 4))
        near = (
            list(people)
            if missing >= reacquire_after
            else [i for i in people if dists[i] <= radius]
        )
        pick: int | None = None
        uncertain = False
        if look is None:
            # Nothing to recognise them by: accept only an unambiguous, nearby single body.
            if len(near) == 1 and len(people) == 1 and dists[near[0]] <= max_jump:
                pick = near[0]
            elif len(near) > 1:
                uncertain = True
        else:
            measured = sorted(
                ((d, i) for i in near if (d := looks[i]) is not None), key=lambda x: x[0]
            )
            unmeasured = [i for i in near if looks[i] is None]
            matches = [(d, i) for d, i in measured if d <= APPEARANCE_MATCH]
            if matches:
                best_d, best_i = matches[0]
                rivals = [d for d, i in measured if i != best_i]
                if unmeasured or (rivals and rivals[0] - best_d < APPEARANCE_MARGIN):
                    uncertain = True  # someone nearby could be them too
                else:
                    pick = best_i
            elif (
                len(unmeasured) == 1
                and not measured
                and len(people) == 1
                and dists[unmeasured[0]] <= max_jump
            ):
                pick = unmeasured[0]  # torso not measurable (e.g. off-frame) but nobody else here
        if pick is None:
            status[t] = "uncertain" if uncertain else "lost"
            missing += 1
            continue
        chosen[t] = pick
        status[t] = "followed"
        missing = 0
        last_root = pose_root(detections[t][pick])
        new_look = appearances[t][pick] if pick < len(appearances[t]) else None
        # Update the remembered look slowly, and only when nobody else is close by.
        others_close = any(i != pick and dists[i] <= max_jump * 1.5 for i in people)
        if new_look is not None and not others_close:
            look = new_look if look is None else 0.9 * look + 0.1 * new_look


def follow_person(
    detections: list[list[FloatArray]],
    appearances: list[list[FloatArray | None]],
    distinct: list[list[int]],
    seed_frame: int,
    seed_index: int,
    *,
    max_jump: float = 0.2,
    reacquire_after: int = 6,
) -> FollowResult:
    """Follow the person `seed_index` of frame `seed_frame` forwards and backwards in time."""
    n = len(detections)
    chosen = np.full(n, -1, dtype=np.int64)
    status: list[FrameStatus] = ["lost"] * n
    seed_pose = detections[seed_frame][seed_index]
    root = pose_root(seed_pose)
    look = (
        appearances[seed_frame][seed_index] if seed_index < len(appearances[seed_frame]) else None
    )
    chosen[seed_frame] = seed_index
    status[seed_frame] = "followed"
    kw = {"max_jump": max_jump, "reacquire_after": reacquire_after}
    _follow_pass(
        detections,
        appearances,
        distinct,
        range(seed_frame + 1, n),
        root,
        look,
        chosen,
        status,
        **kw,  # type: ignore[arg-type]
    )
    _follow_pass(
        detections,
        appearances,
        distinct,
        range(seed_frame - 1, -1, -1),
        root,
        look,
        chosen,
        status,
        **kw,  # type: ignore[arg-type]
    )
    return FollowResult(chosen=chosen, status=status, seed_frame=seed_frame)


def track_from_follow(detections: list[list[FloatArray]], result: FollowResult) -> FloatArray:
    out = np.full((len(detections), L.NUM_LANDMARKS, 5), np.nan)
    for t, k in enumerate(result.chosen):
        if k >= 0:
            out[t] = detections[t][int(k)]
    return out


def status_spans(
    times: FloatArray, status: list[FrameStatus], wanted: tuple[FrameStatus, ...]
) -> list[tuple[float, float]]:
    """Merged [start, end] time spans of frames whose status is in `wanted`."""
    spans: list[tuple[float, float]] = []
    start: int | None = None
    for t, s in enumerate([*status, "followed"]):
        if t < len(status) and s in wanted:
            if start is None:
                start = t
        elif start is not None:
            end = t - 1
            spans.append((float(times[start]), float(times[end])))
            start = None
    return spans


# --------------------------------------------------------------------------------------------
# Who is in the video: candidates for "Who should we follow?"
# --------------------------------------------------------------------------------------------


@dataclass
class Candidate:
    person: int  # 1-based, numbered left to right in the chosen frame
    detection: int  # detection index in that frame
    box: list[float]
    root: list[float]
    position: str  # "left" / "centre" / "right" / "left of centre" ...
    share: float  # fraction of analysed frames in which this person is followed

    def as_dict(self) -> dict[str, object]:
        return {
            "person": self.person,
            "box": [round(v, 4) for v in self.box],
            "root": [round(v, 4) for v in self.root],
            "position": self.position,
            "share": round(self.share, 3),
        }


@dataclass
class PeopleSurvey:
    frame: int  # analysed frame index the candidates were taken from
    time: float
    candidates: list[Candidate] = field(default_factory=list)


def _position_label(rank: int, count: int, x: float) -> str:
    if count == 2:
        return ("left", "right")[rank]
    if count == 3:
        return ("left", "centre", "right")[rank]
    if x < 0.4:
        return "left"
    if x > 0.6:
        return "right"
    return "centre-left" if x < 0.5 else "centre-right"


def survey_people(
    detections: list[list[FloatArray]],
    appearances: list[list[FloatArray | None]],
    distinct: list[list[int]],
    times: FloatArray,
    threshold: float = 0.5,
) -> PeopleSurvey | None:
    """Pick the clearest frame showing the most people (clearly apart) and offer each of them.

    Returns None when the video never shows two separate people at once."""
    best: tuple[int, float, int] | None = None  # (people, min confidence, -distance to middle)
    best_frame = -1
    best_people: list[int] = []
    n = len(detections)
    for t in range(n):
        people = distinct[t][:MAX_CANDIDATES]
        if len(people) < 2:
            continue
        boxes = [body_box(detections[t][i], threshold) for i in people]
        if any(b is None for b in boxes):
            continue
        apart = all(
            overlap_ratio(boxes[a], boxes[b]) <= CANDIDATE_MAX_OVERLAP  # type: ignore[arg-type]
            for a in range(len(boxes))
            for b in range(a + 1, len(boxes))
        )
        if not apart:
            continue
        min_conf = min(float(np.nanmean(confidence_of(detections[t][i]))) for i in people)
        key = (len(people), round(min_conf, 2), -abs(t - n // 2))
        if best is None or key > best:
            best, best_frame, best_people = key, t, list(people)
    if best is None:
        return None
    ordered = sorted(best_people, key=lambda i: float(pose_root(detections[best_frame][i])[0]))
    survey = PeopleSurvey(frame=best_frame, time=float(times[best_frame]))
    for rank, i in enumerate(ordered):
        pose = detections[best_frame][i]
        box = body_box(pose, threshold)
        assert box is not None
        root = pose_root(pose)
        share = follow_person(detections, appearances, distinct, best_frame, i).followed_fraction
        survey.candidates.append(
            Candidate(
                person=rank + 1,
                detection=i,
                box=[float(v) for v in box],
                root=[float(v) for v in root],
                position=_position_label(rank, len(ordered), float(root[0])),
                share=share,
            )
        )
    return survey


def locate_choice(
    detections: list[list[FloatArray]],
    distinct: list[list[int]],
    times: FloatArray,
    choice_time: float,
    choice_root: tuple[float, float],
    *,
    tolerance: float = 0.12,
    search_frames: int = 3,
) -> tuple[int, int] | None:
    """(frame, detection) of the chosen person: the detection nearest the stored hip point at the
    stored moment (or a few frames around it). None when nobody is there any more."""
    if len(times) == 0:
        return None
    t0 = int(np.argmin(np.abs(times - choice_time)))
    target = np.asarray(choice_root, dtype=np.float64)
    for off in sorted(range(-search_frames, search_frames + 1), key=abs):
        t = t0 + off
        if t < 0 or t >= len(detections) or not distinct[t]:
            continue
        best = min(
            distinct[t], key=lambda i: float(np.linalg.norm(pose_root(detections[t][i]) - target))
        )
        if float(np.linalg.norm(pose_root(detections[t][best]) - target)) <= tolerance:
            return t, best
    return None

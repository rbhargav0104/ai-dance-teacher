"""Spec amendment A2 exit gate (backend): choose the dancer in multi-person videos.

Real footage only: fixtures/multi/*.mp4 are FFmpeg composites of the two committed Mixkit clips
(scripts/make_multi_person_fixtures.py). Identity is checked against the video's own pixels:
the girl wears a maroon top, the boy a navy T-shirt, so the colour under the followed person's
torso says who was followed in every frame.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import REPO_ROOT
from tests.test_reference_analysis import (  # noqa: F401 - fixtures
    analyze,
    auth,
    frame_rgb,
    real,
    run_jobs,
    upload,
)

MULTI = REPO_ROOT / "fixtures" / "multi"
pytestmark = pytest.mark.skipif(not MULTI.is_dir(), reason="multi-person fixtures missing")


def who(px: np.ndarray) -> str:
    """'girl' (maroon top), 'boy' (navy shirt) or '?' for the colour under a torso point."""
    r, g, b = (int(v) for v in px)
    if r > 80 and r > 2 * g and r > 1.5 * b:  # maroon; skin (r ≈ 1.5 g) doesn't qualify
        return "girl"
    if r < 80 and g < 80 and b < 100 and b >= r:
        return "boy"
    return "?"


def canonical_path(project_id: str) -> Path:
    from app.db.session import get_sessionmaker
    from app.models import ReferenceVideo
    from app.storage import get_storage

    with get_sessionmaker()() as db:
        ref = db.query(ReferenceVideo).filter_by(project_id=project_id).one()
        key = ref.canonical_object_key
    assert key
    return get_storage().local_path(key)


def followed_identities(
    c: TestClient, headers: dict[str, str], pid: str, every: int = 3
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    poses = c.get(f"/api/projects/{pid}/poses", headers=headers).json()
    w, h = poses["width"], poses["height"]
    video = canonical_path(pid)
    seen: dict[str, int] = {"girl": 0, "boy": 0, "?": 0}
    valid = [f for f in poses["frames"] if f["valid"]]
    for f in valid[::every]:
        lm = f["data"]["landmarks"]
        x = (lm[11][0] + lm[12][0] + lm[23][0] + lm[24][0]) / 4
        y = (lm[11][1] + lm[12][1] + lm[23][1] + lm[24][1]) / 4
        img = frame_rgb(video, f["t"], w, h)
        seen[who(img[min(h - 1, int(y * h)), min(w - 1, int(x * w))])] += 1
    return seen, poses["frames"]


def choose(c: TestClient, headers: dict[str, str], pid: str, person: int) -> dict[str, Any]:
    res = c.post(f"/api/projects/{pid}/subject", headers=headers, json={"person": person})
    assert res.status_code == 202, res.text
    assert run_jobs() == 1
    body: dict[str, Any] = c.get(f"/api/projects/{pid}", headers=headers).json()
    return body


def test_pick_left_then_right_dancer_follows_each(
    real: TestClient,  # noqa: F811
    auth: dict[str, str],  # noqa: F811
) -> None:
    pid = upload(real, auth, MULTI / "duo_girl_left.mp4")
    p = analyze(real, auth, pid)
    assert p["status"] == "needs_subject" and p["error_code"] == "choose_dancer"
    subject = p["reference"]["subject"]  # type: ignore[index]
    cands = subject["candidates"]
    assert [c["person"] for c in cands] == [1, 2]
    assert [c["position"] for c in cands] == ["left", "right"]
    assert cands[0]["box"][2] <= cands[1]["box"][0] + 0.05  # clearly apart, left to right
    assert all(c["share"] > 0.8 for c in cands)
    # The frame used for choosing is a real private JPEG.
    media = real.get(f"/api/projects/{pid}/media/people", headers=auth).json()
    assert real.get(media["url"]).content[:2] == b"\xff\xd8"
    # Nothing downstream is available until a person is chosen.
    assert real.get(f"/api/projects/{pid}/segments", headers=auth).status_code == 409

    left = choose(real, auth, pid, 1)
    assert left["status"] == "analyzed", left
    ref = left["reference"]
    assert ref["subject"]["choice"]["person"] == 1
    assert ref["subject"]["choice"]["position"] == "left"
    assert "other_people_ignored" in ref["warnings"]
    seen, frames = followed_identities(real, auth, pid)
    assert seen["girl"] >= 10 and seen["boy"] == 0, seen
    assert {f["data"]["subject"] for f in frames} <= {"followed", "lost", "uncertain"}
    sections = real.get(f"/api/projects/{pid}/segments", headers=auth).json()["sections"]
    assert sections and sections[-1]["end"] == pytest.approx(8.0, abs=0.1)

    # Choosing the same person again is idempotent: no new job.
    again = real.post(f"/api/projects/{pid}/subject", headers=auth, json={"person": 1})
    assert again.status_code == 200 and again.json()["id"] == left["latest_job"]["id"]
    assert run_jobs() == 0

    right = choose(real, auth, pid, 2)
    assert right["status"] == "analyzed"
    assert right["reference"]["subject"]["choice"]["person"] == 2
    # The candidates offered stay the same people after a choice ("Follow someone else").
    assert right["reference"]["subject"]["candidates"] == cands
    seen, _ = followed_identities(real, auth, pid)
    assert seen["boy"] >= 10 and seen["girl"] == 0, seen


def test_swapped_positions_follow_the_person_not_the_side(
    real: TestClient,  # noqa: F811
    auth: dict[str, str],  # noqa: F811
) -> None:
    pid = upload(real, auth, MULTI / "duo_boy_left.mp4")
    assert analyze(real, auth, pid)["status"] == "needs_subject"
    left = choose(real, auth, pid, 1)
    assert left["status"] == "analyzed"
    seen, _ = followed_identities(real, auth, pid)
    assert seen["boy"] >= 10 and seen["girl"] == 0, seen


def test_chosen_dancer_leaving_is_masked_never_switched(
    real: TestClient,  # noqa: F811
    auth: dict[str, str],  # noqa: F811
) -> None:
    pid = upload(real, auth, MULTI / "duo_girl_leaves.mp4")
    assert analyze(real, auth, pid)["status"] == "needs_subject"
    p = choose(real, auth, pid, 1)  # the girl, who vanishes from 3 s to 5.5 s
    ref = p["reference"]
    assert p["status"] == "analyzed", p  # 2.5 s of 8 s lost: partial, still usable
    assert "chosen_dancer_lost" in ref["warnings"]
    followed = ref["subject"]["followed"]
    lost = followed["lost_spans"] + followed["uncertain_spans"]
    assert any(a <= 3.3 and b >= 5.2 for a, b in lost), lost
    seen, frames = followed_identities(real, auth, pid, every=1)
    assert seen["boy"] == 0 and seen["girl"] >= 30, seen
    gone = [f for f in frames if 3.2 <= f["t"] <= 5.3]
    assert gone and all(not f["valid"] for f in gone)
    assert all(f["data"]["subject"] in ("lost", "uncertain") for f in gone)


def test_crossing_never_switches_silently(
    real: TestClient,  # noqa: F811
    auth: dict[str, str],  # noqa: F811
) -> None:
    """The boy walks across the girl and hides her. A brief overlap (< 20% of frames with two
    people) keeps the single-dancer flow, but "Follow someone else" is offered; whichever person
    is followed, every measured frame is that person."""
    pid = upload(real, auth, MULTI / "crossing.mp4")
    p = analyze(real, auth, pid)
    subject = p["reference"]["subject"]  # type: ignore[index]
    assert subject is not None and len(subject["candidates"]) == 2
    first, _ = followed_identities(real, auth, pid, every=1)
    main = "girl" if first["girl"] > first["boy"] else "boy"
    other = "boy" if main == "girl" else "girl"
    assert first[other] == 0, first

    for c in subject["candidates"]:
        res = real.post(f"/api/projects/{pid}/subject", headers=auth, json={"person": c["person"]})
        assert res.status_code in (200, 202), res.text
        run_jobs()
        after = real.get(f"/api/projects/{pid}", headers=auth).json()
        # Hidden for much of the clip, the girl may honestly fail the coverage gate; frames
        # stay inspectable either way.
        assert after["status"] in ("analyzed", "failed"), after
        seen, _ = followed_identities(real, auth, pid, every=1)
        assert min(seen["girl"], seen["boy"]) == 0, (c, seen)
        assert max(seen["girl"], seen["boy"]) >= 10, (c, seen)

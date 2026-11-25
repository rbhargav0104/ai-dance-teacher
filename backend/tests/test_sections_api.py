"""Teachable sections end to end on REAL footage: the committed Mixkit clip goes through the real
worker + MediaPipe, then sections are suggested, edited, validated and regenerated via the API."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.test_reference_analysis import (  # noqa: F401  (pytest fixtures)
    GIRL,
    analyze,
    auth,
    real,
    upload,
)

pytest.importorskip("mediapipe")


@pytest.fixture
def analysed(real: TestClient, auth: dict[str, str]) -> str:  # noqa: F811
    pid = upload(real, auth, GIRL)
    assert analyze(real, auth, pid)["status"] == "analyzed"
    return pid


def sections(c: TestClient, auth: dict[str, str], pid: str) -> dict[str, object]:  # noqa: F811
    res = c.get(f"/api/projects/{pid}/segments", headers=auth)
    assert res.status_code == 200, res.text
    return dict(res.json())


def tiles(secs: list[dict[str, object]], duration: float) -> None:
    assert secs[0]["start"] == 0.0
    assert secs[-1]["end"] == pytest.approx(duration, abs=1e-3)
    for a, b in zip(secs[:-1], secs[1:], strict=True):
        assert a["end"] == b["start"]
    assert [s["position"] for s in secs] == list(range(len(secs)))


def test_analysis_suggests_full_coverage_sections_with_thumbnails(
    real: TestClient,  # noqa: F811
    auth: dict[str, str],  # noqa: F811
    analysed: str,
) -> None:
    data = sections(real, auth, analysed)
    secs = list(data["sections"])  # type: ignore[call-overload]
    duration = float(data["duration"])  # type: ignore[arg-type]
    assert 13.5 < duration < 14.5
    assert 2 <= len(secs) <= 4
    tiles(secs, duration)
    for i, s in enumerate(secs):
        assert s["boundary_source"] == "automatic"
        assert s["title"] == f"Section {i + 1:02d}"
        assert s["completed"] is False
        assert 2.0 - 1e-6 <= s["end"] - s["start"] <= 8.0 + 1e-6
        assert s["instruction"] and s["instruction_direct"]
        assert s["instruction_experimental"] is True
        assert 0.0 <= s["coverage"] <= 1.0
        # Feet are out of frame in this clip: the legs must never be described.
        assert "knee" not in s["instruction"].lower()
        assert "left leg" in s["untracked"] or s["coverage"] < 0.5
        img = real.get(s["thumbnail_url"])
        assert img.status_code == 200
        assert img.headers["content-type"] == "image/jpeg"
        assert img.content[:2] == b"\xff\xd8"
    # Thumbnails are private: no session → no image token; signed URL leaks no object key.
    assert "sections/" not in secs[0]["thumbnail_url"]


def test_edits_persist_and_change_only_what_moved(
    real: TestClient,  # noqa: F811
    auth: dict[str, str],  # noqa: F811
    analysed: str,
) -> None:
    data = sections(real, auth, analysed)
    secs = list(data["sections"])  # type: ignore[call-overload]
    duration = float(data["duration"])  # type: ignore[arg-type]
    first = secs[0]
    real.patch(
        f"/api/projects/{analysed}/segments/{first['id']}",
        headers=auth,
        json={"completed": True, "title": "Arms intro"},
    ).raise_for_status()

    # Split the last section in two and keep the others untouched.
    last = secs[-1]
    mid = round((last["start"] + last["end"]) / 2, 3)
    body = [{"id": s["id"], "start": s["start"], "end": s["end"]} for s in secs[:-1]] + [
        {"id": last["id"], "start": last["start"], "end": mid},
        {"start": mid, "end": duration},
    ]
    res = real.patch(f"/api/projects/{analysed}/segments", headers=auth, json={"sections": body})
    assert res.status_code == 200, res.text
    after = list(res.json()["sections"])
    assert len(after) == len(secs) + 1
    tiles(after, duration)
    assert after[0]["id"] == first["id"] and after[0]["completed"] is True
    assert after[0]["title"] == "Arms intro"
    assert after[0]["boundary_source"] == "automatic"
    assert after[0]["thumbnail_url"] is not None
    assert after[-2]["id"] == last["id"] and after[-2]["boundary_source"] == "manual"
    assert after[-1]["boundary_source"] == "manual"
    assert after[-1]["title"] == f"Section {len(after):02d}"
    assert after[-1]["thumbnail_url"] and after[-2]["thumbnail_url"]

    # Persisted: a fresh read returns the same boundaries.
    again = list(sections(real, auth, analysed)["sections"])  # type: ignore[call-overload]
    assert [(s["start"], s["end"]) for s in again] == [(s["start"], s["end"]) for s in after]

    # Merge everything back into one section.
    res = real.patch(
        f"/api/projects/{analysed}/segments",
        headers=auth,
        json={"sections": [{"id": first["id"], "start": 0, "end": duration}]},
    )
    assert res.status_code == 200, res.text
    one = res.json()["sections"]
    assert len(one) == 1 and one[0]["completed"] is False  # boundaries changed → not complete


@pytest.mark.parametrize(
    ("make", "code"),
    [
        (lambda d: [{"start": 0, "end": 5}, {"start": 6, "end": d}], "sections_gap"),
        (lambda d: [{"start": 0, "end": 5}, {"start": 4, "end": d}], "sections_overlap"),
        (lambda d: [{"start": 0, "end": d - 1}], "sections_incomplete"),
        (lambda d: [{"start": 0, "end": 0.1}, {"start": 0.1, "end": d}], "section_too_short"),
        (lambda d: [{"id": "nope", "start": 0, "end": d}], "unknown_section"),
    ],
)
def test_invalid_edits_are_rejected_without_changes(
    real: TestClient,  # noqa: F811
    auth: dict[str, str],  # noqa: F811
    analysed: str,
    make: object,
    code: str,
) -> None:
    before = sections(real, auth, analysed)
    duration = float(before["duration"])  # type: ignore[arg-type]
    res = real.patch(
        f"/api/projects/{analysed}/segments",
        headers=auth,
        json={"sections": make(duration)},  # type: ignore[operator]
    )
    assert res.status_code == 422, res.text
    assert res.json()["error"]["code"] == code
    after = sections(real, auth, analysed)
    assert [s["id"] for s in after["sections"]] == [s["id"] for s in before["sections"]]  # type: ignore[union-attr]


def test_regenerate_restores_automatic_sections(
    real: TestClient,  # noqa: F811
    auth: dict[str, str],  # noqa: F811
    analysed: str,
) -> None:
    auto = list(sections(real, auth, analysed)["sections"])  # type: ignore[call-overload]
    duration = auto[-1]["end"]
    real.patch(
        f"/api/projects/{analysed}/segments",
        headers=auth,
        json={"sections": [{"start": 0, "end": duration}]},
    ).raise_for_status()
    res = real.post(f"/api/projects/{analysed}/segments/regenerate", headers=auth)
    assert res.status_code == 200, res.text
    regen = res.json()["sections"]
    assert [(s["start"], s["end"]) for s in regen] == [(s["start"], s["end"]) for s in auto]
    assert all(s["boundary_source"] == "automatic" and not s["completed"] for s in regen)


def test_sections_are_owner_only_and_need_analysis(
    real: TestClient,  # noqa: F811
    auth: dict[str, str],  # noqa: F811
    analysed: str,
) -> None:
    other = {"Authorization": f"Bearer {real.post('/api/session').json()['token']}"}
    assert real.get(f"/api/projects/{analysed}/segments", headers=other).status_code == 404
    assert (
        real.patch(
            f"/api/projects/{analysed}/segments",
            headers=other,
            json={"sections": [{"start": 0, "end": 1}]},
        ).status_code
        == 404
    )
    pid = upload(real, auth, GIRL)  # uploaded, not analysed
    res = real.get(f"/api/projects/{pid}/segments", headers=auth)
    assert res.status_code == 409 and res.json()["error"]["code"] == "not_analyzed"


def test_deleting_project_removes_section_thumbnails(
    real: TestClient,  # noqa: F811
    auth: dict[str, str],  # noqa: F811
    analysed: str,
) -> None:
    from app.config import get_settings

    root = Path(get_settings().objects_dir)
    assert list(root.rglob("sections/*.jpg"))
    assert real.delete(f"/api/projects/{analysed}", headers=auth).status_code == 204
    assert not list(root.rglob("sections/*.jpg"))

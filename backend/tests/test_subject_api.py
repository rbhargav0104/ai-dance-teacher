"""Subject-choice API contract (spec amendment A2) without the vision stack: validation,
ownership, idempotency, "analysis in progress", and LIMITED behaviour (the choice is stored, the
analysis is refused honestly with 503 — never simulated).

The "who is in the video" record is written into the database directly here (API-contract setup
only). The real record comes from MediaPipe in test_subject_choice.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from tests.test_practice_api import _new_user, analysed_project

RECORD: dict[str, Any] = {
    "version": "people-1",
    "frame_time": 1.0,
    "frame_key": None,
    "candidates": [
        {"person": 1, "box": [0.1, 0.2, 0.4, 1.0], "root": [0.25, 0.7], "position": "left",
         "share": 1.0},
        {"person": 2, "box": [0.6, 0.2, 0.9, 1.0], "root": [0.75, 0.7], "position": "right",
         "share": 0.9},
    ],
    "choice": None,
    "followed": None,
}  # fmt: skip


def _set_reference_subject(pid: str, record: dict[str, Any] | None, status: str) -> None:
    from app.db.session import get_sessionmaker
    from app.models import DanceProject

    with get_sessionmaker()() as db:
        project = db.get(DanceProject, pid)
        assert project is not None and project.reference_video is not None
        project.reference_video.subject = record
        project.status = status
        db.commit()


def _reference_subject(pid: str) -> dict[str, Any] | None:
    from app.db.session import get_sessionmaker
    from app.models import DanceProject

    with get_sessionmaker()() as db:
        project = db.get(DanceProject, pid)
        assert project is not None and project.reference_video is not None
        return project.reference_video.subject


def test_choice_validation_ownership_and_limited(
    client: TestClient, auth_headers: dict[str, str], media: dict[str, Path]
) -> None:
    pid, _ = analysed_project(client, auth_headers, media["valid.mp4"])
    url = f"/api/projects/{pid}/subject"

    # One person only → nothing to choose.
    res = client.post(url, headers=auth_headers, json={"person": 1})
    assert res.status_code == 409 and res.json()["error"]["code"] == "no_people_to_choose"

    _set_reference_subject(pid, dict(RECORD), "needs_subject")
    project = client.get(f"/api/projects/{pid}", headers=auth_headers).json()
    assert project["status"] == "needs_subject"
    subject = project["reference"]["subject"]
    assert [c["person"] for c in subject["candidates"]] == [1, 2]
    assert subject["choice"] is None and subject["has_frame"] is False
    assert client.get(f"/api/projects/{pid}/media/people", headers=auth_headers).status_code == 404

    for bad in ({"person": 3}, {"person": 0}):
        res = client.post(url, headers=auth_headers, json=bad)
        assert res.status_code == 422 and res.json()["error"]["code"] == "unknown_person"
    assert client.post(url, headers=auth_headers, json={}).status_code == 422
    assert client.post(url, headers=auth_headers, json={"person": "x"}).status_code == 422
    assert _reference_subject(pid)["choice"] is None  # type: ignore[index]

    # Someone else's dance: same 404 as a missing one, nothing stored.
    other = _new_user(client)
    res = client.post(url, headers=other, json={"person": 1})
    assert res.status_code == 404 and res.json()["error"]["code"] == "project_not_found"
    assert _reference_subject(pid)["choice"] is None  # type: ignore[index]

    # LIMITED (no pose model in this test env): the choice is saved, analysis refused honestly.
    res = client.post(url, headers=auth_headers, json={"person": 2})
    assert res.status_code == 503 and res.json()["error"]["code"] == "analysis_unavailable"
    assert "saved" in res.json()["error"]["message"]
    stored = _reference_subject(pid)
    assert stored is not None and stored["choice"]["person"] == 2
    assert stored["choice"]["root"] == [0.75, 0.7] and stored["choice"]["t"] == 1.0
    project = client.get(f"/api/projects/{pid}", headers=auth_headers).json()
    assert project["reference"]["subject"]["choice"]["position"] == "right"
    assert "root" not in project["reference"]["subject"]["choice"]
    assert project["status"] == "needs_subject"  # nothing pretended to run


def test_choice_queues_analysis_and_is_idempotent(
    client: TestClient,
    auth_headers: dict[str, str],
    media: dict[str, Path],
    monkeypatch: Any,
) -> None:
    from app.api import subjects
    from app.api.health import Capability

    pid, _ = analysed_project(client, auth_headers, media["valid.mp4"])
    _set_reference_subject(pid, dict(RECORD), "needs_subject")
    monkeypatch.setattr(
        subjects,
        "analysis_capability",
        lambda _s: Capability(available=True, reason=None, runtime_ok=True, worker_ok=True),
    )
    url = f"/api/projects/{pid}/subject"
    first = client.post(url, headers=auth_headers, json={"person": 1})
    assert first.status_code == 202, first.text
    job = first.json()
    assert job["kind"] == "reference_analysis" and job["status"] == "queued"
    assert client.get(f"/api/projects/{pid}", headers=auth_headers).json()["status"] == "queued"
    # Same choice while it runs → the same job.
    again = client.post(url, headers=auth_headers, json={"person": 1})
    assert again.status_code == 200 and again.json()["id"] == job["id"]
    # A different choice while it runs → 409, choice unchanged.
    clash = client.post(url, headers=auth_headers, json={"person": 2})
    assert clash.status_code == 409 and clash.json()["error"]["code"] == "analysis_in_progress"
    assert _reference_subject(pid)["choice"]["person"] == 1  # type: ignore[index]

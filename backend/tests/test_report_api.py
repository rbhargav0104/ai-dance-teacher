"""`GET /api/practice-sessions/{id}/report` contract (Outcome 7) on real footage: honest
refusals, owner isolation, stored + invalidated scores, section attempts, score summary on the
attempt, delete cascade and the no-numpy refusal."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tests.test_practice_analysis import ATTEMPTS, analysed_girl, attempt
from tests.test_reference_analysis import auth, ffmpeg, real, run_jobs  # noqa: F401

pytestmark = pytest.mark.skipif(not ATTEMPTS.is_dir(), reason="attempt fixtures missing")


def report(c: TestClient, h: dict[str, str], sid: str) -> dict[str, Any]:
    res = c.get(f"/api/practice-sessions/{sid}/report", headers=h)
    assert res.status_code == 200, res.text
    body: dict[str, Any] = res.json()
    return body


def score_rows(sid: str) -> int:
    from app.config import get_settings

    eng = create_engine(get_settings().resolved_database_url)
    with eng.connect() as conn:
        n = conn.execute(
            text("SELECT COUNT(*) FROM performance_scores WHERE practice_session_id = :s"),
            {"s": sid},
        ).scalar_one()
    eng.dispose()
    return int(n)


def test_report_contract(
    real: TestClient,  # noqa: F811
    auth: dict[str, str],  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = analysed_girl(real, auth)
    pid = project["id"]
    full = attempt(real, auth, pid, "girl_good")["id"]

    # Not analysed yet → honest 409; someone else's attempt → the same 404 as a missing one.
    res = real.get(f"/api/practice-sessions/{full}/report", headers=auth)
    assert res.status_code == 409 and res.json()["error"]["code"] == "not_analyzed"
    other = {"Authorization": f"Bearer {real.post('/api/session').json()['token']}"}
    assert real.get(f"/api/practice-sessions/{full}/report", headers=other).status_code == 404
    assert real.get("/api/practice-sessions/nope/report", headers=auth).status_code == 404

    sections = real.get(f"/api/projects/{pid}/segments", headers=auth).json()["sections"]
    s2 = sections[1]
    cut = tmp_path / "girl_section2.mp4"
    ffmpeg("-ss", f"{s2['start']:.3f}", "-i", str(ATTEMPTS / "girl_good.mp4"), "-t",
           f"{s2['end'] - s2['start']:.3f}", "-an", "-c:v", "libx264", "-preset", "veryfast",
           "-pix_fmt", "yuv420p", str(cut))  # fmt: skip
    with cut.open("rb") as fh:
        res = real.post(
            f"/api/projects/{pid}/practice-sessions",
            headers=auth,
            files={"file": (cut.name, fh, "video/mp4")},
            data={"segment_id": s2["id"]},
        )
    assert res.status_code == 201, res.text
    sec = res.json()["id"]
    assert run_jobs() == 2

    # Before the report is computed the attempt carries no score.
    att = real.get(f"/api/practice-sessions/{full}", headers=auth).json()
    assert att["scored"] is False and att["score"] is None

    first = report(real, auth, full)
    r = first["report"]
    assert first["cached"] is False
    assert r["status"] in {"scored", "qualified"} and isinstance(r["overall"], float)
    assert r["window"] == {"start": 0.0, "end": pytest.approx(14.0, abs=0.1), "segment_id": None}
    assert [s["id"] for s in r["sections"]] == [s["id"] for s in sections]
    assert r["sections"][1]["start"] == pytest.approx(s2["start"], abs=1e-3)
    assert score_rows(full) == 1
    att = real.get(f"/api/practice-sessions/{full}", headers=auth).json()
    assert att["scored"] is True and att["score"]["overall"] == r["overall"]
    assert att["score"]["version"] == "score-1"
    listed = real.get(f"/api/projects/{pid}/practice-sessions", headers=auth).json()["sessions"]
    assert {s["id"]: s["score"] for s in listed}[full]["overall"] == r["overall"]
    again = report(real, auth, full)
    assert again["cached"] is True and again["report"] == r
    assert score_rows(full) == 1

    # Section attempt: scored against its own window, no per-section breakdown.
    rs = report(real, auth, sec)["report"]
    assert rs["status"] in {"scored", "qualified"}, rs.get("reason")
    assert rs["window"]["segment_id"] == s2["id"] and rs["sections"] == []
    assert rs["overall"] >= 85  # the good performance, cut to the section

    # Moving a section boundary changes the breakdown → stored score is stale and recomputed.
    mid = round((sections[0]["start"] + sections[0]["end"]) / 2 + 0.5, 3)
    edit = [
        {"id": sections[0]["id"], "start": sections[0]["start"], "end": mid},
        {"id": s2["id"], "start": mid, "end": s2["end"]},
        *[{"id": s["id"], "start": s["start"], "end": s["end"]} for s in sections[2:]],
    ]
    res = real.patch(f"/api/projects/{pid}/segments", headers=auth, json={"sections": edit})
    assert res.status_code == 200, res.text
    assert real.get(f"/api/practice-sessions/{full}", headers=auth).json()["score"] is None

    # Without numpy a stale score is not approximated: 503, nothing stored changes.
    monkeypatch.setitem(sys.modules, "app.pose.scoring", None)
    res = real.get(f"/api/practice-sessions/{full}/report", headers=auth)
    assert res.status_code == 503 and res.json()["error"]["code"] == "analysis_unavailable"
    monkeypatch.delitem(sys.modules, "app.pose.scoring")

    fresh = report(real, auth, full)
    assert fresh["cached"] is False
    assert fresh["report"]["sections"][0]["end"] == pytest.approx(mid, abs=1e-3)
    assert score_rows(full) == 1

    # Deleting the attempt removes its stored score.
    assert real.delete(f"/api/practice-sessions/{full}", headers=auth).status_code == 204
    assert score_rows(full) == 0
    assert real.get(f"/api/practice-sessions/{full}/report", headers=auth).status_code == 404

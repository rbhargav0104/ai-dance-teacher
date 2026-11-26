"""Practice-attempt API (Outcome 5) without the vision stack: intake, ownership, idempotency,
quota, no-residue rejections, WebM recording repair, LIMITED behaviour and deletion.

The dance is marked analysed directly in the database here so the API contract can be tested
without MediaPipe; real end-to-end learner analysis lives in test_practice_analysis.py.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from tests.conftest import _clear_caches
from tests.media_factory import FFMPEG


@pytest.fixture
def client(migrated: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MAX_DURATION_SECONDS", "20")
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    monkeypatch.setenv("MAX_SESSIONS_PER_PROJECT", "3")
    _clear_caches()
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


def _new_user(client: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {client.post('/api/session').json()['token']}"}


def analysed_project(client: TestClient, auth: dict[str, str], video: Path) -> tuple[str, str]:
    """Upload a reference, then mark it analysed with one section (API-contract setup only)."""
    from app.db.base import utcnow
    from app.db.session import get_sessionmaker
    from app.models import DanceProject, DanceSegment

    with video.open("rb") as fh:
        res = client.post("/api/projects", headers=auth, files={"file": ("ref.mp4", fh)})
    assert res.status_code == 201, res.text
    pid = str(res.json()["id"])
    with get_sessionmaker()() as db:
        project = db.get(DanceProject, pid)
        assert project is not None and project.reference_video is not None
        project.status = "analyzed"
        project.reference_video.analyzed_at = utcnow()
        project.reference_video.canonical_duration = 2.0
        seg = DanceSegment(
            project_id=pid, position=0, start_time=0.0, end_time=2.0, title="Section 1"
        )
        db.add(seg)
        db.commit()
        sid = seg.id
    return pid, sid


def post_attempt(
    client: TestClient,
    auth: dict[str, str],
    pid: str,
    path: Path,
    *,
    name: str | None = None,
    key: str | None = None,
    fields: dict[str, str] | None = None,
) -> tuple[int, dict[str, object]]:
    h = dict(auth)
    if key:
        h["Idempotency-Key"] = key
    with path.open("rb") as fh:
        res = client.post(
            f"/api/projects/{pid}/practice-sessions",
            headers=h,
            files={"file": (name or path.name, fh, "video/webm")},
            data=fields or {},
        )
    return res.status_code, res.json()


def _practice_count() -> int:
    from app.db.session import get_sessionmaker
    from app.models import PracticeSession

    with get_sessionmaker()() as db:
        return int(db.scalar(select(func.count()).select_from(PracticeSession)) or 0)


def _practice_files(data: Path) -> list[Path]:
    root = data / "objects"
    return [p for p in root.rglob("*") if p.is_file() and "/practice/" in p.as_posix()]


def _tmp_files(data: Path) -> list[Path]:
    root = data / "tmp"
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


def test_attempt_needs_an_analysed_dance(
    client: TestClient, auth_headers: dict[str, str], media: dict[str, Path], migrated: Path
) -> None:
    with media["valid.mp4"].open("rb") as fh:
        pid = client.post("/api/projects", headers=auth_headers, files={"file": ("r.mp4", fh)})
    status, body = post_attempt(client, auth_headers, pid.json()["id"], media["valid.mp4"])
    assert status == 409 and body["error"]["code"] == "reference_not_ready"  # type: ignore[index]
    assert _practice_count() == 0 and _practice_files(migrated / "data") == []


def test_webcam_section_attempt_persists_privately_and_stays_honest_in_limited(
    client: TestClient, auth_headers: dict[str, str], media: dict[str, Path], migrated: Path
) -> None:
    pid, sid = analysed_project(client, auth_headers, media["valid.mp4"])
    status, body = post_attempt(
        client,
        auth_headers,
        pid,
        media["valid.webm"],
        fields={"segment_id": sid, "capture_source": "webcam", "mirrored": "false"},
    )
    assert status == 201, body
    assert body["status"] == "uploaded"  # LIMITED test server: stored, never simulated
    assert body["latest_job"] is None and body["analyzed_at"] is None
    assert body["capture_source"] == "webcam" and body["declared_mirrored"] is False
    assert body["target"] == {"segment_id": sid, "title": "Section 1", "start": 0.0, "end": 2.0}
    assert body["scored"] is False
    text = str(body)
    assert "users/" not in text and str(migrated) not in text  # no keys or paths leak

    files = _practice_files(migrated / "data")
    assert len(files) == 1 and files[0].read_bytes() == media["valid.webm"].read_bytes()
    assert oct(files[0].stat().st_mode & 0o777) == "0o600"

    res = client.post(f"/api/practice-sessions/{body['id']}/analysis", headers=auth_headers)
    assert res.status_code == 503 and res.json()["error"]["code"] == "analysis_unavailable"
    res = client.get(f"/api/practice-sessions/{body['id']}/poses", headers=auth_headers)
    assert res.status_code == 409 and res.json()["error"]["code"] == "not_analyzed"

    listed = client.get(f"/api/projects/{pid}/practice-sessions", headers=auth_headers).json()
    assert [s["id"] for s in listed["sessions"]] == [body["id"]] and listed["limit"] == 3
    media_url = client.get(
        f"/api/practice-sessions/{body['id']}/media/source", headers=auth_headers
    ).json()
    got = client.get(media_url["url"], headers={"Range": "bytes=0-99"})
    assert got.status_code == 206 and got.headers["content-type"] == "video/webm"
    missing = client.get(
        f"/api/practice-sessions/{body['id']}/media/canonical", headers=auth_headers
    )
    assert missing.status_code == 404

    # The dance itself is untouched by an attempt.
    project = client.get(f"/api/projects/{pid}", headers=auth_headers).json()
    assert project["status"] == "analyzed"


def test_full_dance_upload_and_short_attempt_warning(
    client: TestClient, auth_headers: dict[str, str], media: dict[str, Path], tmp_path: Path
) -> None:
    pid, _ = analysed_project(client, auth_headers, media["valid.mp4"])
    status, body = post_attempt(client, auth_headers, pid, media["valid.mov"], fields={})
    assert status == 201
    assert body["capture_source"] == "upload" and body["target"]["segment_id"] is None  # type: ignore[index]
    assert body["target"]["title"] == "Full dance"  # type: ignore[index]
    assert "shorter_than_target" not in body["warnings"]  # type: ignore[operator]

    short = tmp_path / "short.mp4"
    subprocess.run(  # noqa: S603
        [str(FFMPEG), "-loglevel", "error", "-y", "-f", "lavfi", "-i",
         "testsrc2=size=320x240:rate=24:duration=1.2", "-pix_fmt", "yuv420p", str(short)],
        check=True,
    )  # fmt: skip
    status, body = post_attempt(client, auth_headers, pid, short, fields={"mirrored": "true"})
    assert status == 201 and body["declared_mirrored"] is True
    assert "shorter_than_target" in body["warnings"]  # type: ignore[operator]


def test_browser_webm_without_duration_is_repaired_by_remux(
    client: TestClient,
    auth_headers: dict[str, str],
    media: dict[str, Path],
    tmp_path: Path,
    migrated: Path,
) -> None:
    """MediaRecorder WebM has no container duration (like FFmpeg writing to a pipe)."""
    rec = tmp_path / "recording.webm"
    with rec.open("wb") as out:
        subprocess.run(  # noqa: S603
            [str(FFMPEG), "-loglevel", "error", "-f", "lavfi", "-i",
             "testsrc2=size=320x240:rate=24:duration=2", "-c:v", "libvpx-vp9", "-b:v", "200k",
             "-deadline", "realtime", "-f", "webm", "pipe:1"],
            check=True, stdout=out,
        )  # fmt: skip
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(rec)],
        check=True, capture_output=True, text=True,
    ).stdout.strip()  # fmt: skip
    assert probe in {"", "N/A"}, probe  # the problem this test is about

    pid, sid = analysed_project(client, auth_headers, media["valid.mp4"])
    status, body = post_attempt(
        client, auth_headers, pid, rec, fields={"segment_id": sid, "capture_source": "webcam"}
    )
    assert status == 201, body
    assert abs(float(body["duration"]) - 2.0) < 0.15  # type: ignore[arg-type]
    assert _tmp_files(migrated / "data") == []


@pytest.mark.parametrize(
    ("fixture", "code"),
    [("notes.txt", "unsupported_type"), ("corrupt.mp4", "unreadable_media"),
     ("audio_only.mp4", "audio_only"), ("empty.mp4", "empty_file"), ("long.mp4", "too_long")],
)  # fmt: skip
def test_rejected_attempts_leave_no_residue(
    client: TestClient,
    auth_headers: dict[str, str],
    media: dict[str, Path],
    migrated: Path,
    fixture: str,
    code: str,
) -> None:
    pid, _ = analysed_project(client, auth_headers, media["valid.mp4"])
    status, body = post_attempt(client, auth_headers, pid, media[fixture])
    assert status in (415, 422), body
    assert body["error"]["code"] == code  # type: ignore[index]
    assert _practice_count() == 0
    assert _practice_files(migrated / "data") == [] and _tmp_files(migrated / "data") == []


def test_bad_segment_and_capture_source_rejected_without_residue(
    client: TestClient, auth_headers: dict[str, str], media: dict[str, Path], migrated: Path
) -> None:
    pid, _ = analysed_project(client, auth_headers, media["valid.mp4"])
    other_pid, other_sid = analysed_project(client, auth_headers, media["valid.mov"])
    assert other_pid != pid
    status, body = post_attempt(
        client, auth_headers, pid, media["valid.mp4"], fields={"segment_id": other_sid}
    )
    assert status == 404 and body["error"]["code"] == "section_not_found"  # type: ignore[index]
    status, body = post_attempt(
        client, auth_headers, pid, media["valid.mp4"], fields={"capture_source": "drone"}
    )
    assert status == 422 and body["error"]["code"] == "invalid_capture_source"  # type: ignore[index]
    assert _practice_count() == 0 and _practice_files(migrated / "data") == []
    assert _tmp_files(migrated / "data") == []


def test_idempotent_retry_quota_and_ownership(
    client: TestClient, auth_headers: dict[str, str], media: dict[str, Path]
) -> None:
    pid, _ = analysed_project(client, auth_headers, media["valid.mp4"])
    s1, first = post_attempt(client, auth_headers, pid, media["valid.mp4"], key="attempt-key-1")
    s2, again = post_attempt(client, auth_headers, pid, media["valid.mp4"], key="attempt-key-1")
    assert (s1, s2) == (201, 200) and first["id"] == again["id"]
    for i in range(2):
        assert (
            post_attempt(client, auth_headers, pid, media["valid.mp4"], key=f"k-{i}-xxxx")[0] == 201
        )
    status, body = post_attempt(client, auth_headers, pid, media["valid.mp4"])
    assert status == 409 and body["error"]["code"] == "practice_limit"  # type: ignore[index]

    stranger = _new_user(client)
    aid = first["id"]
    for method, path in [
        ("get", f"/api/practice-sessions/{aid}"),
        ("get", f"/api/practice-sessions/{aid}/poses"),
        ("get", f"/api/practice-sessions/{aid}/media/source"),
        ("post", f"/api/practice-sessions/{aid}/analysis"),
        ("delete", f"/api/practice-sessions/{aid}"),
        ("get", f"/api/projects/{pid}/practice-sessions"),
    ]:
        res = getattr(client, method)(path, headers=stranger)
        assert res.status_code == 404, (path, res.text)
    status, body = post_attempt(client, stranger, pid, media["valid.mp4"])
    assert status == 404 and body["error"]["code"] == "project_not_found"  # type: ignore[index]
    assert client.get(f"/api/practice-sessions/{aid}", headers=auth_headers).status_code == 200


def test_delete_attempt_and_dance_cascade(
    client: TestClient, auth_headers: dict[str, str], media: dict[str, Path], migrated: Path
) -> None:
    pid, sid = analysed_project(client, auth_headers, media["valid.mp4"])
    _, a = post_attempt(client, auth_headers, pid, media["valid.mp4"], fields={"segment_id": sid})
    _, b = post_attempt(client, auth_headers, pid, media["valid.mov"])
    assert len(_practice_files(migrated / "data")) == 2
    res = client.delete(f"/api/practice-sessions/{a['id']}", headers=auth_headers)
    assert res.status_code == 204
    assert client.get(f"/api/practice-sessions/{a['id']}", headers=auth_headers).status_code == 404
    assert len(_practice_files(migrated / "data")) == 1 and _practice_count() == 1

    assert client.delete(f"/api/projects/{pid}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/practice-sessions/{b['id']}", headers=auth_headers).status_code == 404
    assert _practice_count() == 0 and _practice_files(migrated / "data") == []


def test_section_deleted_by_edit_keeps_attempt_as_full_dance(
    client: TestClient, auth_headers: dict[str, str], media: dict[str, Path]
) -> None:
    """Sections stay editable (spec rule 9); an attempt whose section disappears is kept."""
    from app.db.session import get_sessionmaker
    from app.models import DanceSegment

    pid, sid = analysed_project(client, auth_headers, media["valid.mp4"])
    _, a = post_attempt(client, auth_headers, pid, media["valid.mp4"], fields={"segment_id": sid})
    with get_sessionmaker()() as db:
        seg = db.get(DanceSegment, sid)
        db.delete(seg)
        db.commit()
    body = client.get(f"/api/practice-sessions/{a['id']}", headers=auth_headers).json()
    assert body["target"]["segment_id"] is None and body["target"]["title"] == "Full dance"

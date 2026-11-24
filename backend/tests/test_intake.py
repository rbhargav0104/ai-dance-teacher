"""Reference intake API: valid uploads persist privately; every rejection leaves no residue."""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from tests.conftest import _clear_caches

MAX_DURATION = 20


@pytest.fixture
def client(migrated: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MAX_DURATION_SECONDS", str(MAX_DURATION))
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    monkeypatch.setenv("MAX_PROJECTS_PER_USER", "3")
    _clear_caches()
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


def _counts() -> dict[str, int]:
    from app.db.session import get_sessionmaker
    from app.models import AnalysisJob, DanceProject, ReferenceVideo

    with get_sessionmaker()() as db:
        return {
            m.__tablename__: int(db.scalar(select(func.count()).select_from(m)) or 0)
            for m in (DanceProject, ReferenceVideo, AnalysisJob)
        }


def _files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


def assert_no_residue(data_dir: Path) -> None:
    assert _counts() == {"dance_projects": 0, "reference_videos": 0, "analysis_jobs": 0}
    objects = [p for p in _files(data_dir / "objects") if not p.name.startswith(".probe")]
    assert objects == [], objects
    assert _files(data_dir / "tmp") == []


def upload(
    client: TestClient,
    headers: dict[str, str],
    path: Path,
    *,
    name: str | None = None,
    key: str | None = None,
    title: str | None = None,
) -> tuple[int, dict[str, object]]:
    h = dict(headers)
    if key:
        h["Idempotency-Key"] = key
    data = {"title": title} if title else None
    with path.open("rb") as fh:
        res = client.post(
            "/api/projects",
            headers=h,
            files={"file": (name or path.name, fh, "video/mp4")},
            data=data,
        )
    return res.status_code, res.json()


def test_valid_upload_persists_privately(
    client: TestClient, auth_headers: dict[str, str], media: dict[str, Path], migrated: Path
) -> None:
    code, body = upload(client, auth_headers, media["with_audio.mp4"], title="  My   groove ")
    assert code == 201, body
    assert body["title"] == "My groove"
    assert body["status"] == "uploaded"
    ref = body["reference"]
    assert isinstance(ref, dict)
    assert ref["width"] == 320 and ref["height"] == 240
    assert abs(float(ref["duration"]) - 2.0) < 0.2
    assert ref["source_fps"] == 24
    assert ref["has_audio"] is True and ref["codec"] == "h264"
    job = body["latest_job"]
    assert (
        isinstance(job, dict) and job["status"] == "succeeded" and job["kind"] == "reference_intake"
    )

    objects = _files(migrated / "data" / "objects" / "users")
    assert len(objects) == 1
    assert stat.S_IMODE(objects[0].stat().st_mode) == 0o600
    assert objects[0].read_bytes() == media["with_audio.mp4"].read_bytes()
    # Object keys and paths never leak to the client.
    assert "users/" not in str(body) and "objects" not in str(body)
    assert _files(migrated / "data" / "tmp") == []


@pytest.mark.parametrize("name", ["valid.mp4", "valid.mov", "valid.webm"])
def test_each_accepted_container(
    client: TestClient, auth_headers: dict[str, str], media: dict[str, Path], name: str
) -> None:
    code, body = upload(client, auth_headers, media[name])
    assert code == 201, body


def test_portrait_is_accepted_with_warning(
    client: TestClient, auth_headers: dict[str, str], media: dict[str, Path]
) -> None:
    code, body = upload(client, auth_headers, media["portrait.mp4"])
    assert code == 201
    ref = body["reference"]
    assert isinstance(ref, dict) and "portrait" in ref["warnings"]  # type: ignore[operator]


REJECTIONS = [
    ("notes.txt", None, 415, "unsupported_type"),
    ("valid.mp4", "dance.avi", 415, "unsupported_type"),
    ("valid.mp4", "noext", 415, "unsupported_type"),
    ("corrupt.mp4", None, 422, "unreadable_media"),
    ("truncated.mp4", None, 422, "unreadable_media"),
    ("audio_only.mp4", None, 422, "audio_only"),
    ("image_as.mp4", None, 422, "no_video_stream"),
    ("empty.mp4", None, 422, "empty_file"),
    ("tiny.mp4", None, 422, "dimensions_too_small"),
    ("short.mp4", None, 422, "too_short"),
    ("long.mp4", None, 422, "too_long"),
]


@pytest.mark.parametrize(("fixture", "name", "status", "code"), REJECTIONS)
def test_rejections_leave_no_residue(
    client: TestClient,
    auth_headers: dict[str, str],
    media: dict[str, Path],
    migrated: Path,
    fixture: str,
    name: str | None,
    status: int,
    code: str,
) -> None:
    res_status, body = upload(client, auth_headers, media[fixture], name=name, key=f"k-{fixture}")
    assert res_status == status, body
    err = body["error"]
    assert isinstance(err, dict) and err["code"] == code and err["message"]
    assert_no_residue(migrated / "data")


def test_oversized_upload_is_rejected_while_streaming(
    client: TestClient, auth_headers: dict[str, str], migrated: Path, tmp_path: Path
) -> None:
    big = tmp_path / "big.mp4"
    big.write_bytes(os.urandom(1024 * 1024 + 10))
    status, body = upload(client, auth_headers, big)
    assert status == 413 and body["error"]["code"] == "file_too_large"  # type: ignore[index]
    assert_no_residue(migrated / "data")


def test_declared_content_length_over_limit_is_rejected_early(
    client: TestClient, auth_headers: dict[str, str], migrated: Path
) -> None:
    res = client.post(
        "/api/projects",
        headers={
            **auth_headers,
            "Content-Type": "multipart/form-data; boundary=x",
            "Content-Length": str(50 * 1024 * 1024),
        },
        content=b"--x--\r\n",
    )
    assert res.status_code == 413
    assert_no_residue(migrated / "data")


def test_missing_file_and_bad_content_type(
    client: TestClient, auth_headers: dict[str, str], migrated: Path
) -> None:
    res = client.post("/api/projects", headers=auth_headers, files={"title": (None, "x")})
    assert res.status_code == 400 and res.json()["error"]["code"] == "missing_file"
    res = client.post(
        "/api/projects",
        headers={**auth_headers, "Content-Type": "application/json"},
        content=b"{}",
    )
    assert res.status_code == 400
    assert_no_residue(migrated / "data")


def test_two_files_rejected(
    client: TestClient, auth_headers: dict[str, str], media: dict[str, Path], migrated: Path
) -> None:
    p = media["valid.mp4"]
    res = client.post(
        "/api/projects",
        headers=auth_headers,
        files=[("file", ("a.mp4", p.read_bytes())), ("file", ("b.mp4", p.read_bytes()))],
    )
    assert res.status_code == 400 and res.json()["error"]["code"] == "too_many_files"
    assert_no_residue(migrated / "data")


def test_unauthenticated_upload_rejected(
    client: TestClient, media: dict[str, Path], migrated: Path
) -> None:
    status, body = upload(client, {}, media["valid.mp4"])
    assert status == 401
    assert_no_residue(migrated / "data")


def test_storage_or_db_failure_mid_persist_cleans_up(
    client: TestClient,
    auth_headers: dict[str, str],
    media: dict[str, Path],
    migrated: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.orm import Session

    def boom(self: Session) -> None:
        raise RuntimeError("db went away")

    monkeypatch.setattr(Session, "commit", boom)
    with pytest.raises(RuntimeError):
        upload(client, auth_headers, media["valid.mp4"])
    monkeypatch.undo()
    assert_no_residue(migrated / "data")


def test_probe_timeout_is_actionable(
    client: TestClient,
    auth_headers: dict[str, str],
    media: dict[str, Path],
    migrated: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess

    def slow(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=0.01)

    monkeypatch.setattr("app.media.probe.subprocess.run", slow)
    status, body = upload(client, auth_headers, media["valid.mp4"])
    assert status == 422 and body["error"]["code"] == "probe_timeout"  # type: ignore[index]
    assert_no_residue(migrated / "data")


def test_idempotent_retry_returns_same_project(
    client: TestClient, auth_headers: dict[str, str], media: dict[str, Path], migrated: Path
) -> None:
    s1, b1 = upload(client, auth_headers, media["valid.mp4"], key="retry-key-0001")
    s2, b2 = upload(client, auth_headers, media["valid.mp4"], key="retry-key-0001")
    assert (s1, s2) == (201, 200)
    assert b1["id"] == b2["id"]
    assert _counts()["dance_projects"] == 1
    assert len(_files(migrated / "data" / "objects" / "users")) == 1


def test_invalid_idempotency_key(
    client: TestClient, auth_headers: dict[str, str], media: dict[str, Path]
) -> None:
    status, body = upload(client, auth_headers, media["valid.mp4"], key="bad key!")
    assert status == 400


def test_project_quota(
    client: TestClient, auth_headers: dict[str, str], media: dict[str, Path]
) -> None:
    for i in range(3):
        assert upload(client, auth_headers, media["valid.mp4"], key=f"quota-{i:04d}")[0] == 201
    status, body = upload(client, auth_headers, media["valid.mp4"], key="quota-9999")
    assert status == 409 and body["error"]["code"] == "project_limit"  # type: ignore[index]


def test_list_get_refresh_and_delete_cascade(
    client: TestClient, auth_headers: dict[str, str], media: dict[str, Path], migrated: Path
) -> None:
    _, body = upload(client, auth_headers, media["valid.mp4"])
    pid = body["id"]
    # "Refresh": a fresh request (and a fresh app) sees the same persisted project + job state.
    listed = client.get("/api/projects", headers=auth_headers).json()
    assert [p["id"] for p in listed["projects"]] == [pid]
    from app.main import create_app

    with TestClient(create_app()) as c2:
        again = c2.get(f"/api/projects/{pid}", headers=auth_headers).json()
    assert again["latest_job"]["status"] == "succeeded"
    assert again["reference"] == body["reference"]

    assert client.delete(f"/api/projects/{pid}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/projects/{pid}", headers=auth_headers).status_code == 404
    assert_no_residue(migrated / "data")


def test_ownership_isolation(
    client: TestClient, auth_headers: dict[str, str], media: dict[str, Path]
) -> None:
    _, body = upload(client, auth_headers, media["valid.mp4"])
    pid = body["id"]
    other = {"Authorization": f"Bearer {client.post('/api/session').json()['token']}"}
    assert client.get("/api/projects", headers=other).json()["projects"] == []
    for method, path in [
        ("GET", f"/api/projects/{pid}"),
        ("DELETE", f"/api/projects/{pid}"),
        ("GET", f"/api/projects/{pid}/media/source"),
        ("POST", f"/api/projects/{pid}/analysis"),
    ]:
        res = client.request(method, path, headers=other)
        assert res.status_code == 404, (method, path)
        assert res.json()["error"]["code"] == "project_not_found"
    assert client.get(f"/api/projects/{pid}", headers=auth_headers).status_code == 200


def test_analysis_is_refused_with_503_in_limited_mode(
    client: TestClient, auth_headers: dict[str, str], media: dict[str, Path]
) -> None:
    _, body = upload(client, auth_headers, media["valid.mp4"])
    res = client.post(f"/api/projects/{body['id']}/analysis", headers=auth_headers)
    assert res.status_code == 503 and res.json()["error"]["code"] == "analysis_unavailable"


def test_samples_go_through_the_same_intake(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    samples = client.get("/api/samples").json()
    assert len(samples) >= 2 and all(s["license"] for s in samples)
    res = client.post(
        "/api/projects/sample", headers=auth_headers, json={"sample_id": samples[0]["id"]}
    )
    assert res.status_code == 201, res.json()
    body = res.json()
    assert body["is_demo"] is True and body["reference"]["width"] == 1280
    again = client.post(
        "/api/projects/sample", headers=auth_headers, json={"sample_id": samples[0]["id"]}
    )
    assert again.status_code == 200 and again.json()["id"] == body["id"]
    missing = client.post("/api/projects/sample", headers=auth_headers, json={"sample_id": "nope"})
    assert missing.status_code == 404

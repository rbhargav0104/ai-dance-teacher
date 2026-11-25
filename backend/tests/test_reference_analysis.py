"""End-to-end reference analysis on REAL footage (committed Mixkit fixtures + FFmpeg variants).

No landmarks are fabricated here: every pose comes from MediaPipe running on video frames.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.config import REPO_ROOT

pytest.importorskip("mediapipe")
MODEL = REPO_ROOT / "models" / "pose_landmarker_full.task"
REFS = REPO_ROOT / "fixtures" / "references"
GIRL = REFS / "mixkit_girl_earphones_28306.mp4"
BOY = REFS / "mixkit_boy_funny_28289.mp4"
pytestmark = pytest.mark.skipif(
    not MODEL.is_file() or not shutil.which("ffmpeg"), reason="pose model / ffmpeg missing"
)


def ffmpeg(*args: str) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True, timeout=120
    )


@pytest.fixture
def real(env: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    from app.config import get_settings
    from app.main import create_app
    from tests.conftest import _clear_caches, migrate

    monkeypatch.setenv("MODEL_PATH", str(MODEL))
    _clear_caches()
    migrate(get_settings().resolved_database_url)
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def auth(real: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {real.post('/api/session').json()['token']}"}


def run_jobs() -> int:
    from app.jobs.worker import get_worker

    n = 0
    while get_worker().run_once():
        n += 1
    return n


def upload(c: TestClient, auth: dict[str, str], path: Path) -> str:
    with path.open("rb") as fh:
        res = c.post("/api/projects", headers=auth, files={"file": (path.name, fh, "video/mp4")})
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


def analyze(c: TestClient, auth: dict[str, str], pid: str) -> dict[str, object]:
    res = c.post(f"/api/projects/{pid}/analysis", headers=auth)
    assert res.status_code == 202, res.text
    assert run_jobs() == 1
    return dict(c.get(f"/api/projects/{pid}", headers=auth).json())


def frame_rgb(video: Path, t: float, w: int, h: int) -> np.ndarray:
    out = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True, timeout=60,
    ).stdout  # fmt: skip
    return np.frombuffer(out, dtype=np.uint8).reshape(h, w, 3)


def is_green(px: np.ndarray) -> bool:
    r, g, b = (int(v) for v in px)
    return g > r + 40 and g > b + 40


def test_sample_reference_yields_aligned_skeleton_and_features(
    real: TestClient, auth: dict[str, str], env: Path
) -> None:
    res = real.post(
        "/api/projects/sample", headers=auth, json={"sample_id": "mixkit_girl_earphones_28306"}
    )
    assert res.status_code == 201, res.text
    pid_s = res.json()["id"]

    # A sample starts real analysis immediately (READY server); re-requests are idempotent.
    assert res.json()["status"] == "queued"
    queued_job = res.json()["latest_job"]
    assert queued_job["kind"] == "reference_analysis" and queued_job["status"] == "queued"
    again = real.post(f"/api/projects/{pid_s}/analysis", headers=auth)
    assert again.status_code == 200 and again.json()["id"] == queued_job["id"]
    assert run_jobs() == 1

    p = real.get(f"/api/projects/{pid_s}", headers=auth).json()
    assert p["status"] == "analyzed", p
    assert p["latest_job"]["status"] == "succeeded"
    ref = p["reference"]
    assert (ref["canonical_width"], ref["canonical_height"]) == (1280, 720)
    assert ref["canonical_fps"] == pytest.approx(24.0)
    assert ref["analysis_fps"] == 12.0
    assert ref["pose_coverage"] > 0.85
    assert "cropped_body" in ref["warnings"]  # feet are out of frame in this clip: honest warning
    assert ref["pipeline_version"] == "ref-pose-1"
    assert ref["model_version"].startswith("pose_landmarker_full@sha256:4eaa5eb7a983")

    poses = real.get(f"/api/projects/{pid_s}/poses", headers=auth).json()
    frames = poses["frames"]
    assert len(frames) == pytest.approx(14.0 * 12, abs=2)
    ts = [f["t"] for f in frames]
    assert ts == sorted(ts) and ts[0] == 0.0
    assert all(f["frame"] == round(f["t"] * 24) for f in frames)
    assert len(poses["landmark_names"]) == 33

    # Anatomy sanity on every valid frame: nose above shoulders above hips; angles in range.
    valid = [f for f in frames if f["valid"]]
    for f in valid:
        lm = f["data"]["landmarks"]
        sh_y = (lm[11][1] + lm[12][1]) / 2
        hip_y = (lm[23][1] + lm[24][1]) / 2
        assert lm[0][1] < sh_y < hip_y
        for v in f["data"]["angles"].values():
            assert v is None or 0.0 <= v <= 180.0
        assert f["data"]["yaw_experimental"] is None or -90 <= f["data"]["yaw_experimental"] <= 90
    # Feet hidden → ankle angles masked (null), never guessed.
    assert sum(f["data"]["angles"]["left_ankle"] is None for f in valid) > 0.8 * len(valid)

    # Skeleton is aligned with the real dancer: torso points land on the dancer, not on the
    # green-screen background; a far-left background point stays green.
    from app.storage import get_storage

    canon_url = real.get(f"/api/projects/{pid_s}/media/canonical", headers=auth).json()["url"]
    assert real.get(canon_url, headers={"Range": "bytes=0-99"}).status_code == 206
    from app.db.session import get_sessionmaker
    from app.models import ReferenceVideo

    with get_sessionmaker()() as db:
        key = db.query(ReferenceVideo).one().canonical_object_key
    canonical = get_storage().local_path(key)
    assert "low_tracking_confidence" not in ref["warnings"]
    assert poses["quality"]["measured_joint_confidence"] > 0.9
    for f in valid[:: max(1, len(valid) // 6)]:
        img = frame_rgb(canonical, f["t"], 1280, 720)
        lm = f["data"]["landmarks"]
        for a, b in ((11, 23), (12, 24)):  # shoulder→hip midline of each side of the torso
            x = (lm[a][0] + lm[b][0]) / 2
            y = (lm[a][1] + lm[b][1]) / 2
            assert not is_green(img[int(y * 720), int(x * 1280)]), (f["t"], x, y)
        assert is_green(img[360, 20])

    poster = real.get(f"/api/projects/{pid_s}/media/poster", headers=auth).json()
    assert poster["content_type"] == "image/jpeg"
    assert real.get(poster["url"]).content[:2] == b"\xff\xd8"


def test_multi_person_clip_fails_honestly(
    real: TestClient, auth: dict[str, str], tmp_path: Path
) -> None:
    duo = tmp_path / "duo.mp4"
    ffmpeg(
        "-i", str(GIRL), "-i", str(BOY), "-filter_complex",
        "[0:v]crop=640:720[a];[1:v]crop=640:720[b];[a][b]hstack", "-t", "8", "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(duo),
    )  # fmt: skip
    pid = upload(real, auth, duo)
    p = analyze(real, auth, pid)
    assert p["status"] == "failed"
    assert p["error_code"] == "multiple_people"
    job = p["latest_job"]
    assert isinstance(job, dict) and job["status"] == "failed" and job["retryable"] is False
    # The failed analysis is still inspectable in the debugger.
    q = real.get(f"/api/projects/{pid}/poses", headers=auth).json()
    assert q["quality"]["multi_person_fraction"] > 0.2


def test_occluded_clip_fails_on_coverage(
    real: TestClient, auth: dict[str, str], tmp_path: Path
) -> None:
    occluded = tmp_path / "occluded.mp4"
    ffmpeg(
        "-i", str(GIRL), "-vf",
        "drawbox=x=0:y=0:w=iw:h=ih:color=0x22aa33:t=fill:enable='between(t,3,13)'",
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(occluded),
    )  # fmt: skip
    pid = upload(real, auth, occluded)
    p = analyze(real, auth, pid)
    assert p["status"] == "failed" and p["error_code"] == "low_coverage", p
    assert "%" in str(p["error_message"])
    assert p["reference"]["pose_coverage"] < 0.55  # type: ignore[index]


def test_empty_scene_reports_no_dancer(
    real: TestClient, auth: dict[str, str], tmp_path: Path
) -> None:
    empty = tmp_path / "empty.mp4"
    ffmpeg(
        "-f", "lavfi", "-i", "color=c=0x22aa33:s=640x360:r=24:d=3",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(empty),
    )  # fmt: skip
    pid = upload(real, auth, empty)
    p = analyze(real, auth, pid)
    assert p["status"] == "failed" and p["error_code"] == "no_dancer_detected"


def test_poses_require_ownership_and_analysis(real: TestClient, auth: dict[str, str]) -> None:
    pid = upload(real, auth, BOY)
    assert real.get(f"/api/projects/{pid}/poses", headers=auth).status_code == 409
    assert real.get(f"/api/projects/{pid}/media/canonical", headers=auth).status_code == 404
    other = {"Authorization": f"Bearer {real.post('/api/session').json()['token']}"}
    assert real.get(f"/api/projects/{pid}/poses", headers=other).status_code == 404
    assert real.post(f"/api/projects/{pid}/analysis", headers=other).status_code == 404


def test_interrupted_job_is_recovered_then_failed_after_max_attempts(
    real: TestClient, auth: dict[str, str]
) -> None:
    from app.db.base import utcnow
    from app.db.session import get_sessionmaker
    from app.jobs import queue
    from app.models import AnalysisJob

    pid = upload(real, auth, BOY)
    job_id = real.post(f"/api/projects/{pid}/analysis", headers=auth).json()["id"]
    sm = get_sessionmaker()
    for attempt in (1, 2, 3):
        with sm() as db:
            assert queue.claim_next(db, "dead-worker") == job_id
            # Simulate the worker dying: heartbeat stops.
            db.execute(
                update(AnalysisJob)
                .where(AnalysisJob.id == job_id)
                .values(heartbeat_at=utcnow() - timedelta(minutes=10))
            )
            db.commit()
            queue.recover(db, lease_seconds=60, max_attempts=3)
            job = db.get(AnalysisJob, job_id)
            assert job is not None and job.attempts == attempt
            expected = "queued" if attempt < 3 else "failed"
            assert job.status == expected
    p = real.get(f"/api/projects/{pid}", headers=auth).json()
    assert p["status"] == "failed" and p["error_code"] == "interrupted"
    assert p["latest_job"]["retryable"] is True
    # A retry is allowed after a retryable failure and creates a fresh job.
    res = real.post(f"/api/projects/{pid}/analysis", headers=auth)
    assert res.status_code == 202 and res.json()["id"] != job_id


def test_deleting_during_a_job_stops_it_and_leaves_no_residue(
    real: TestClient, auth: dict[str, str], env: Path
) -> None:
    from app.db.session import get_sessionmaker
    from app.jobs import queue
    from app.jobs.worker import get_worker

    pid = upload(real, auth, BOY)
    job_id = real.post(f"/api/projects/{pid}/analysis", headers=auth).json()["id"]
    worker = get_worker()
    with get_sessionmaker()() as db:
        assert queue.claim_next(db, worker.worker_id) == job_id
    assert real.delete(f"/api/projects/{pid}", headers=auth).status_code == 204
    with get_sessionmaker()() as db, pytest.raises(queue.JobLost):
        queue.heartbeat(db, job_id, worker.worker_id, stage="tracking", progress=0.5)
    worker._run(job_id)  # returns quietly: the job row is gone
    objects = env / "data" / "objects"
    assert not [p for p in objects.rglob("*") if p.is_file()]


def test_stuck_project_without_job_is_repaired(real: TestClient, auth: dict[str, str]) -> None:
    from app.db.session import get_sessionmaker
    from app.jobs import queue
    from app.models import DanceProject

    pid = upload(real, auth, BOY)
    with get_sessionmaker()() as db:
        db.execute(update(DanceProject).where(DanceProject.id == pid).values(status="processing"))
        db.commit()
        assert queue.recover(db, lease_seconds=60, max_attempts=3) == 1
    p = real.get(f"/api/projects/{pid}", headers=auth).json()
    assert p["status"] == "failed" and p["error_code"] == "interrupted"

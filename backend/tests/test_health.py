from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import health as health_module


def test_health_limited_without_model(client: TestClient) -> None:
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "limited"
    assert body["database"]["ok"] is True
    assert body["database"]["detail"] == "0006"
    assert body["storage"]["ok"] is True
    assert body["analysis"]["available"] is False
    assert body["analysis"]["model_present"] is False
    assert "model" in body["analysis"]["reason"].lower()
    assert body["limits"]["accepted_extensions"] == [".mp4", ".mov", ".webm"]
    assert res.headers["cache-control"] == "no-store"
    assert res.headers["x-request-id"]


def test_health_offline_when_not_migrated(env: Path) -> None:
    from app.main import create_app

    with TestClient(create_app()) as c:
        body = c.get("/api/health").json()
    assert body["status"] == "offline"
    assert "migrated" in body["message"]


def test_corrupt_model_is_not_verified(
    client: TestClient, env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = env / "models" / "missing.task"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"not a model")
    body = client.get("/api/health").json()
    assert body["analysis"]["model_present"] is True
    assert body["analysis"]["model_verified"] is False
    assert body["status"] == "limited"


def test_hash_ok_but_unloadable_model_stays_limited(
    client: TestClient, env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file that passes the SHA check but can't actually load must not flip READY."""
    pytest.importorskip("mediapipe")
    from app.config import get_settings

    model = env / "models" / "missing.task"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"pretend-bytes-for-hash-check")
    monkeypatch.setattr(
        get_settings(), "model_sha256", hashlib.sha256(model.read_bytes()).hexdigest()
    )
    body = client.get("/api/health").json()
    assert body["analysis"]["model_verified"] is True
    assert body["analysis"]["runtime_selftest"] is False
    assert body["status"] == "limited"
    assert "failed to load" in body["analysis"]["reason"]


def test_ready_with_real_model_and_worker(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("mediapipe")
    from app.config import REPO_ROOT, get_settings

    real = REPO_ROOT / "models" / "pose_landmarker_full.task"
    if not real.is_file():
        pytest.skip("pose model not downloaded")
    monkeypatch.setattr(get_settings(), "model_path", real)
    body = client.get("/api/health").json()
    assert body["status"] == "ready", body
    assert body["analysis"]["runtime_selftest"] is True
    assert body["analysis"]["worker_running"] is True

    # Without a worker, the same server must say LIMITED.
    monkeypatch.setattr(get_settings(), "worker_mode", "off")
    body = client.get("/api/health").json()
    assert body["status"] == "limited"
    assert "worker" in body["analysis"]["reason"]
    monkeypatch.setattr(get_settings(), "worker_mode", "manual")
    monkeypatch.setattr(health_module, "ANALYSIS_PIPELINE_IMPLEMENTED", False)
    assert client.get("/api/health").json()["status"] == "limited"


def test_liveness_and_openapi(client: TestClient) -> None:
    assert client.get("/api/health/live").json() == {"status": "alive"}
    paths = client.get("/api/openapi.json").json()["paths"]
    assert {"/api/health", "/api/session", "/api/me"} <= set(paths)


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    res = client.get("/api/nope")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"

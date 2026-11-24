from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from app.config import REPO_ROOT, Settings
from app.pose.runtime import probe

MODEL = Path(os.environ.get("ADT_TEST_MODEL_PATH", REPO_ROOT / "models/pose_landmarker_full.task"))
HAVE_RUNTIME = MODEL.is_file() and importlib.util.find_spec("mediapipe") is not None


def test_probe_missing_model(tmp_path: Path) -> None:
    status = probe(tmp_path / "nope.task", "0" * 64)
    assert not status.model_present
    assert not status.available
    assert status.problem


@pytest.mark.skipif(not HAVE_RUNTIME, reason="pose model or mediapipe not installed")
def test_real_model_loads_and_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings
    from app.pose import verify

    monkeypatch.setenv("MODEL_PATH", str(MODEL))
    get_settings.cache_clear()
    try:
        assert probe(MODEL, Settings().model_sha256).model_verified
        out = verify.run()
        assert out["ok"] is True
        assert out["poses_on_blank_frame"] == 0
    finally:
        get_settings.cache_clear()

"""Smoke-check that MediaPipe can load the pinned model and run VIDEO-mode inference.

Usage: `uv run python -m app.pose.verify`. Runs on a blank frame, so 0 poses is the
expected, honest result; this checks the runtime, not accuracy.
"""

from __future__ import annotations

import json
import sys

from app.config import get_settings
from app.pose.runtime import probe


def run() -> dict[str, object]:
    settings = get_settings()
    status = probe(settings.model_path, settings.model_sha256)
    if not status.available:
        return {"ok": False, "problem": status.problem}

    import mediapipe as mp
    import numpy as np
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions, RunningMode

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(settings.model_path)),
        running_mode=RunningMode.VIDEO,
        num_poses=2,
    )
    frame = np.zeros((256, 256, 3), dtype=np.uint8)
    with PoseLandmarker.create_from_options(options) as landmarker:
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
        result = landmarker.detect_for_video(image, 0)
    return {
        "ok": True,
        "mediapipe": status.runtime_version,
        "model": status.model_version,
        "poses_on_blank_frame": len(result.pose_landmarks),
    }


if __name__ == "__main__":
    out = run()
    print(json.dumps(out))
    sys.exit(0 if out["ok"] else 1)

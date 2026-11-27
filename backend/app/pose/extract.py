"""Real MediaPipe Pose Landmarker inference over a canonical video (spec section 12).

Frames are decoded by FFmpeg at the analysis rate (default 12 fps from the 24 fps canonical
copy) and fed to the landmarker in VIDEO mode with their real timestamps. Up to four poses are
requested per frame so that other people are *detected* (and the user can choose whom to follow,
spec amendment A2) instead of being silently ignored. For each detection a torso colour
histogram is measured on the same frame, so the chosen person can be told apart from others.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from app.media.transcode import CANONICAL_FPS
from app.pose import landmarks as L
from app.pose.people import appearance_of

FloatArray = NDArray[np.float64]

ProgressFn = Callable[[float], None]

MAX_POSES = 4


class ExtractionFailed(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class RawExtraction:
    times: FloatArray  # seconds on the canonical timeline
    frame_numbers: NDArray[np.int64]  # canonical (24 fps) frame index
    detections: list[list[FloatArray]]  # per frame: list of (33,5) arrays
    world: list[list[FloatArray]]  # per frame: list of (33,3) world landmarks (metres, hip-origin)
    appearances: list[list[FloatArray | None]]  # per frame/detection: torso colour histogram
    analysis_fps: float


def _pose_array(landmarks: Any) -> FloatArray:
    arr = np.empty((L.NUM_LANDMARKS, 5), dtype=np.float64)
    for j, p in enumerate(landmarks[: L.NUM_LANDMARKS]):
        arr[j] = (
            p.x,
            p.y,
            p.z,
            p.visibility if p.visibility is not None else 0.0,
            p.presence if p.presence is not None else 0.0,
        )
    return arr


def _world_array(landmarks: Any) -> FloatArray:
    arr = np.empty((L.NUM_LANDMARKS, 3), dtype=np.float64)
    for j, p in enumerate(landmarks[: L.NUM_LANDMARKS]):
        arr[j] = (p.x, p.y, p.z)
    return arr


def extract(
    video: Path,
    *,
    width: int,
    height: int,
    duration: float,
    model_path: Path,
    analysis_fps: float,
    timeout_s: float,
    progress: ProgressFn | None = None,
    check_cancelled: Callable[[], None] | None = None,
) -> RawExtraction:
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import (
        PoseLandmarker,
        PoseLandmarkerOptions,
        RunningMode,
    )

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model_path)),
        running_mode=RunningMode.VIDEO,
        num_poses=MAX_POSES,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    args = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video),
        "-vf",
        f"fps={analysis_fps:g}",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ]
    frame_bytes = width * height * 3
    expected = max(1, int(round(duration * analysis_fps)))
    times: list[float] = []
    frames: list[int] = []
    detections: list[list[FloatArray]] = []
    world: list[list[FloatArray]] = []
    appearances: list[list[FloatArray | None]] = []

    proc = subprocess.Popen(  # noqa: S603 - fixed argv; path is server-generated
        args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    assert proc.stdout is not None
    try:
        with PoseLandmarker.create_from_options(options) as landmarker:
            i = 0
            while True:
                buf = proc.stdout.read(frame_bytes)
                if len(buf) < frame_bytes:
                    break
                t = i / analysis_fps
                rgb = np.frombuffer(buf, dtype=np.uint8).reshape(height, width, 3)
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
                result = landmarker.detect_for_video(image, int(round(t * 1000)))
                poses = [_pose_array(p) for p in result.pose_landmarks]
                detections.append(poses)
                appearances.append([appearance_of(rgb, p) for p in poses])
                world.append([_world_array(p) for p in (result.pose_world_landmarks or [])])
                times.append(t)
                frames.append(int(round(t * CANONICAL_FPS)))
                i += 1
                if progress and i % 6 == 0:
                    progress(min(1.0, i / expected))
                if check_cancelled and i % 12 == 0:
                    check_cancelled()
        proc.wait(timeout=timeout_s)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    if proc.returncode not in (0, None):
        raise ExtractionFailed("decode_failed", "We couldn't read frames from this video.")
    if not times:
        raise ExtractionFailed("decode_failed", "We couldn't read frames from this video.")
    return RawExtraction(
        times=np.asarray(times, dtype=np.float64),
        frame_numbers=np.asarray(frames, dtype=np.int64),
        detections=detections,
        world=world,
        appearances=appearances,
        analysis_fps=analysis_fps,
    )

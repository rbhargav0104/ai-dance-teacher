"""FFprobe inspection + metadata validation for reference/practice uploads (spec section 11).

Extension and MIME type are only hints; the real check is what FFprobe finds in the bytes.
`validate_probe` is pure so every rejection rule is unit-testable without media files.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

from pydantic import BaseModel

ACCEPTED_EXTENSIONS = (".mp4", ".mov", ".webm")
MIN_DURATION_S = 1.0
MIN_DIMENSION_PX = 128
MAX_DIMENSION_PX = 7680
MIN_FPS = 1.0
MAX_FPS = 240.0
# Container formats FFprobe may report for our accepted extensions.
ACCEPTED_FORMATS = {"mov", "mp4", "m4a", "3gp", "3g2", "mj2", "matroska", "webm"}


class MediaRejected(Exception):
    """A user-facing, actionable rejection. `code` is stable for clients and tests."""

    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ProbeResult(BaseModel):
    format_name: str
    duration: float
    width: int
    height: int
    fps: float
    video_codec: str
    has_audio: bool
    rotation: int = 0

    @property
    def display_width(self) -> int:
        return self.height if self.rotation in (90, 270) else self.width

    @property
    def display_height(self) -> int:
        return self.width if self.rotation in (90, 270) else self.height


def check_extension(filename: str | None) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext not in ACCEPTED_EXTENSIONS:
        raise MediaRejected(
            "unsupported_type",
            "Upload an MP4, MOV or WebM video.",
            status_code=415,
        )
    return ext


def parse_rate(value: object) -> float | None:
    """Parse an FFprobe rational like '30000/1001'. Returns None for 0/0, junk or non-finite."""
    if not isinstance(value, str) or not value:
        return None
    try:
        rate = float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return None
    return rate if math.isfinite(rate) and rate > 0 else None


def _float(value: object) -> float | None:
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _rotation(stream: dict[str, Any]) -> int:
    raw: object = (stream.get("tags") or {}).get("rotate")
    for side in stream.get("side_data_list") or []:
        if isinstance(side, dict) and "rotation" in side:
            raw = side["rotation"]
    rot = _float(raw)
    return int(round(rot)) % 360 if rot is not None else 0


def validate_probe(data: dict[str, Any], *, max_duration: float) -> ProbeResult:
    """Turn raw `ffprobe -show_format -show_streams` JSON into a validated ProbeResult."""
    streams = [s for s in data.get("streams") or [] if isinstance(s, dict)]
    fmt = data.get("format") or {}
    format_names = set(str(fmt.get("format_name", "")).split(","))
    if not streams and not fmt:
        raise MediaRejected("unreadable_media", "We couldn't read this file as a video.")

    video = [
        s
        for s in streams
        if s.get("codec_type") == "video"
        and not (s.get("disposition") or {}).get("attached_pic")
        and s.get("codec_name") not in {"mjpeg", "png", "bmp"}
    ]
    if not video:
        if any(s.get("codec_type") == "audio" for s in streams):
            raise MediaRejected(
                "audio_only", "This file only contains audio. Upload a video of the dance."
            )
        raise MediaRejected("no_video_stream", "This file has no video track.")
    if not format_names & ACCEPTED_FORMATS:
        raise MediaRejected("unsupported_type", "Upload an MP4, MOV or WebM video.", 415)

    stream = video[0]
    width, height = int(stream.get("width") or 0), int(stream.get("height") or 0)
    if width <= 0 or height <= 0:
        raise MediaRejected(
            "unreadable_media",
            "We couldn't read the video frames. It may be corrupt or incomplete — re-export it.",
        )
    if width < MIN_DIMENSION_PX or height < MIN_DIMENSION_PX:
        raise MediaRejected(
            "dimensions_too_small",
            f"The video is {width}×{height}. Use at least {MIN_DIMENSION_PX}px on each side.",
        )
    if width > MAX_DIMENSION_PX or height > MAX_DIMENSION_PX:
        raise MediaRejected(
            "dimensions_too_large",
            f"The video is {width}×{height}. Use at most {MAX_DIMENSION_PX}px on each side.",
        )

    fps = parse_rate(stream.get("avg_frame_rate")) or parse_rate(stream.get("r_frame_rate"))
    if fps is None or not (MIN_FPS <= fps <= MAX_FPS):
        raise MediaRejected(
            "invalid_frame_rate", "We couldn't read a sensible frame rate from this video."
        )

    duration = _float(fmt.get("duration")) or _float(stream.get("duration"))
    if duration is None or duration <= 0:
        raise MediaRejected("invalid_timing", "We couldn't read this video's length.")
    if duration < MIN_DURATION_S:
        raise MediaRejected("too_short", "The video is shorter than 1 second.")
    if duration > max_duration:
        raise MediaRejected(
            "too_long",
            f"The video is {duration:.0f} s long. Trim it to {max_duration:.0f} s or less.",
        )

    return ProbeResult(
        format_name=str(fmt.get("format_name", "")),
        duration=round(duration, 3),
        width=width,
        height=height,
        fps=round(fps, 3),
        video_codec=str(stream.get("codec_name", "")),
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
        rotation=_rotation(stream),
    )


def ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


def run_ffprobe(path: Path, *, timeout_s: float, binary: str = "ffprobe") -> dict[str, Any]:
    """Run FFprobe with an argument list (never a shell) and a hard timeout."""
    cmd = [
        binary,
        "-v",
        "error",
        "-hide_banner",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        "--",
        str(path),
    ]
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, path is server-generated
            cmd, capture_output=True, timeout=timeout_s, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaRejected(
            "probe_timeout",
            "Inspecting this video took too long. Try a shorter or re-exported MP4.",
        ) from exc
    except FileNotFoundError as exc:
        raise MediaRejected(
            "inspection_unavailable", "Video inspection is unavailable on this server.", 503
        ) from exc
    try:
        data = json.loads(proc.stdout or b"{}")
    except json.JSONDecodeError:
        data = {}
    if proc.returncode != 0 or not isinstance(data, dict) or not data.get("streams"):
        raise MediaRejected(
            "unreadable_media",
            "We couldn't read this file as a video. It may be corrupt — try re-exporting it.",
        )
    return data


def probe_file(path: Path, *, max_duration: float, timeout_s: float) -> ProbeResult:
    return validate_probe(run_ffprobe(path, timeout_s=timeout_s), max_duration=max_duration)

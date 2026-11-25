"""Canonical analysis/playback copy + poster frame (spec section 11 'Canonical representation').

Deterministic: ≤1280 px on the long side, aspect ratio preserved, even dimensions, 24 fps
constant frame rate, H.264 yuv420p with fast start, optional AAC audio. FFmpeg always runs with
an argument list and a timeout; partial output is deleted on any failure and the final file is
re-probed before anyone uses it.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.media.probe import MediaRejected, ProbeResult, probe_file

CANONICAL_FPS = 24
MAX_LONG_SIDE = 1280


class TranscodeFailed(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def canonical_size(
    display_w: int, display_h: int, max_long: int = MAX_LONG_SIDE
) -> tuple[int, int]:
    """Scale so the long side is ≤ max_long (never upscale) and both sides are even."""
    scale = min(1.0, max_long / max(display_w, display_h))
    w = max(2, int(round(display_w * scale / 2)) * 2)
    h = max(2, int(round(display_h * scale / 2)) * 2)
    return w, h


def transcode_args(
    src: Path, dest: Path, *, width: int, height: int, has_audio: bool, max_duration: float
) -> list[str]:
    args = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(src),
        "-map",
        "0:v:0",
    ]
    if has_audio:
        args += ["-map", "0:a:0?"]
    args += [
        "-t",
        f"{max_duration:.3f}",
        "-vf",
        f"scale={width}:{height}:flags=bicubic,setsar=1,fps={CANONICAL_FPS},format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-map_metadata",
        "-1",
    ]
    args += ["-c:a", "aac", "-b:a", "128k", "-ac", "2"] if has_audio else ["-an"]
    args += ["-f", "mp4", str(dest)]
    return args


def _run(args: list[str], timeout_s: float, dest: Path) -> None:
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv; paths are server-generated
            args, capture_output=True, timeout=timeout_s, check=False
        )
    except subprocess.TimeoutExpired as exc:
        dest.unlink(missing_ok=True)
        raise TranscodeFailed(
            "transcode_timeout", "Preparing this video took too long. Try a shorter clip."
        ) from exc
    except FileNotFoundError as exc:
        dest.unlink(missing_ok=True)
        raise TranscodeFailed("transcode_unavailable", "Video conversion is unavailable.") from exc
    if proc.returncode != 0:
        dest.unlink(missing_ok=True)
        raise TranscodeFailed(
            "transcode_failed", "We couldn't convert this video. Try re-exporting it as MP4."
        )
    if not dest.is_file() or dest.stat().st_size == 0:
        dest.unlink(missing_ok=True)
        raise TranscodeFailed("transcode_empty", "Converting this video produced no output.")


@dataclass(frozen=True)
class CanonicalResult:
    path: Path
    probe: ProbeResult


def make_canonical(
    src: Path,
    dest: Path,
    source_probe: ProbeResult,
    *,
    max_duration: float,
    timeout_s: float,
    probe_timeout_s: float,
) -> CanonicalResult:
    width, height = canonical_size(source_probe.display_width, source_probe.display_height)
    args = transcode_args(
        src,
        dest,
        width=width,
        height=height,
        has_audio=source_probe.has_audio,
        max_duration=max_duration,
    )
    _run(args, timeout_s, dest)
    try:
        out = probe_file(dest, max_duration=max_duration + 1, timeout_s=probe_timeout_s)
    except MediaRejected as exc:
        dest.unlink(missing_ok=True)
        raise TranscodeFailed(
            "transcode_invalid", "The converted video failed inspection."
        ) from exc
    if (
        out.video_codec != "h264"
        or (out.display_width, out.display_height) != (width, height)
        or abs(out.fps - CANONICAL_FPS) > 0.5
    ):
        dest.unlink(missing_ok=True)
        raise TranscodeFailed("transcode_invalid", "The converted video failed inspection.")
    return CanonicalResult(dest, out)


def make_poster(src: Path, dest: Path, *, at_seconds: float, timeout_s: float) -> None:
    args = [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{max(0.0, at_seconds):.3f}",
        "-i",
        str(src),
        "-frames:v",
        "1",
        "-vf",
        "scale='min(640,iw)':-2",
        "-q:v",
        "4",
        str(dest),
    ]
    _run(args, timeout_s, dest)

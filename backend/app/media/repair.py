"""Browser recordings: MediaRecorder WebM files carry no container duration (Chrome writes the
clusters as it records and never seeks back). FFprobe then can't read the length, so a
stream-copy remux (no re-encode, nothing about the picture changes) writes the missing
duration. Anything else that fails inspection is rejected exactly as before.
"""

from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

from app.config import Settings
from app.media.probe import MediaRejected, ProbeResult, probe_file

REPAIRABLE = {"invalid_timing"}
REPAIRABLE_EXTENSIONS = {".webm"}


def remux(src: Path, dest: Path, *, timeout_s: float) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return False
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv; paths are server-generated
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-i",
                str(src),
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c",
                "copy",
                str(dest),
            ],
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        dest.unlink(missing_ok=True)
        return False
    if proc.returncode != 0 or not dest.is_file() or dest.stat().st_size == 0:
        dest.unlink(missing_ok=True)
        return False
    return True


def probe_or_repair(
    path: Path, extension: str, settings: Settings
) -> tuple[Path, ProbeResult, Path | None]:
    """(path to store, probe, temp file the caller must delete or None)."""
    try:
        return (
            path,
            probe_file(
                path,
                max_duration=settings.max_duration_seconds,
                timeout_s=settings.ffprobe_timeout_seconds,
            ),
            None,
        )
    except MediaRejected as exc:
        if exc.code not in REPAIRABLE or extension not in REPAIRABLE_EXTENSIONS:
            raise
        fixed = path.with_name(f"remux-{uuid.uuid4().hex}{extension}")
        if not remux(path, fixed, timeout_s=settings.transcode_timeout_seconds):
            raise
        try:
            probe = probe_file(
                fixed,
                max_duration=settings.max_duration_seconds,
                timeout_s=settings.ffprobe_timeout_seconds,
            )
        except MediaRejected:
            fixed.unlink(missing_ok=True)
            raise
        return fixed, probe, fixed

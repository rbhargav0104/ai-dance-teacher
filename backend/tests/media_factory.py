"""Generate small real media files with FFmpeg for intake tests (no binaries committed).

These are container/metadata fixtures (test patterns, tones), not movement data: they exercise
validation only and are never used for pose or scoring tests.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

FFMPEG = shutil.which("ffmpeg")


def _ffmpeg(*args: str) -> None:
    assert FFMPEG, "ffmpeg required"
    subprocess.run(  # noqa: S603
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], check=True, timeout=60
    )


def make_media(out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    m: dict[str, Path] = {}

    def video(name: str, *, size: str = "320x240", dur: float = 2.0, rate: int = 24,
              extra: tuple[str, ...] = (), codec: tuple[str, ...] = ("-c:v", "libx264",
              "-pix_fmt", "yuv420p")) -> None:  # fmt: skip
        path = out_dir / name
        _ffmpeg(
            "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}:duration={dur}",
            *extra, *codec, str(path),
        )  # fmt: skip
        m[name] = path

    video("valid.mp4")
    video("valid.mov")
    video("valid.webm", codec=("-c:v", "libvpx-vp9", "-b:v", "200k", "-deadline", "realtime"))
    video("portrait.mp4", size="240x320")
    video("tiny.mp4", size="64x64")
    video("short.mp4", dur=0.4)
    video("long.mp4", dur=25.0, rate=4)
    # Valid video + an audio track.
    path = out_dir / "with_audio.mp4"
    _ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=24:duration=2",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
    )  # fmt: skip
    m["with_audio.mp4"] = path
    # Audio only, but named .mp4.
    path = out_dir / "audio_only.mp4"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:a", "aac", str(path))
    m["audio_only.mp4"] = path
    # A still image inside an .mp4-named file (image2 container → not a video format).
    path = out_dir / "still.png"
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x240", "-frames:v", "1", str(path))
    image_as_mp4 = out_dir / "image_as.mp4"
    image_as_mp4.write_bytes(path.read_bytes())
    m["image_as.mp4"] = image_as_mp4
    # Corrupt bytes with a valid extension.
    corrupt = out_dir / "corrupt.mp4"
    corrupt.write_bytes(b"\x00\x00\x00\x18ftypmp42" + bytes(range(256)) * 64)
    m["corrupt.mp4"] = corrupt
    # Truncated real file: header present, payload cut off.
    truncated = out_dir / "truncated.mp4"
    truncated.write_bytes(m["valid.mov"].read_bytes()[:400])
    m["truncated.mp4"] = truncated
    text = out_dir / "notes.txt"
    text.write_text("not a video")
    m["notes.txt"] = text
    empty = out_dir / "empty.mp4"
    empty.write_bytes(b"")
    m["empty.mp4"] = empty
    return m


@pytest.fixture(scope="session")
def media(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    if FFMPEG is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg/ffprobe not installed")
    return make_media(tmp_path_factory.mktemp("media"))

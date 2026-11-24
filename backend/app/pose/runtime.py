"""Capability probe for the pose runtime. Never fabricates availability.

`probe()` is cheap enough for /api/health: it checks the model file's SHA-256 (cached by
size+mtime) and whether the `mediapipe` package is importable, without loading the model.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import threading
from dataclasses import dataclass
from pathlib import Path

MODEL_NAME = "pose_landmarker_full"

_lock = threading.Lock()
_hash_cache: dict[tuple[str, int, int], str] = {}


@dataclass(frozen=True)
class PoseRuntimeStatus:
    model_present: bool
    model_verified: bool
    runtime_installed: bool
    runtime_version: str | None
    model_version: str
    problem: str | None

    @property
    def available(self) -> bool:
        return self.model_verified and self.runtime_installed


def _sha256(path: Path) -> str:
    st = path.stat()
    cache_key = (str(path), st.st_size, st.st_mtime_ns)
    with _lock:
        if cache_key in _hash_cache:
            return _hash_cache[cache_key]
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    with _lock:
        _hash_cache[cache_key] = value
    return value


def probe(model_path: Path, expected_sha256: str) -> PoseRuntimeStatus:
    model_version = f"{MODEL_NAME}@sha256:{expected_sha256[:12]}"
    present = model_path.is_file()
    verified = present and _sha256(model_path) == expected_sha256.lower()
    installed = importlib.util.find_spec("mediapipe") is not None
    version: str | None = None
    if installed:
        try:
            version = importlib.metadata.version("mediapipe")
        except importlib.metadata.PackageNotFoundError:
            version = None

    problem: str | None = None
    if not installed:
        problem = "The movement-analysis runtime is not installed on this server."
    elif not present:
        problem = "The pose model has not been downloaded (run scripts/download_model.sh)."
    elif not verified:
        problem = "The pose model file failed its integrity check."
    return PoseRuntimeStatus(present, verified, installed, version, model_version, problem)

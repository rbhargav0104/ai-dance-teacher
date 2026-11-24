"""Private object storage interface. Keys are generated server-side; never user-supplied."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol

_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*$")


class InvalidObjectKey(ValueError):
    pass


def validate_key(key: str) -> str:
    """Reject anything that could escape the bucket root (.., absolute paths, odd chars)."""
    if not key or len(key) > 512 or not _KEY_RE.fullmatch(key):
        raise InvalidObjectKey("invalid object key")
    if any(part in {".", ".."} for part in key.split("/")):
        raise InvalidObjectKey("invalid object key")
    return key


class ObjectStorage(Protocol):
    provider: str

    def put_file(self, key: str, source: Path) -> int:
        """Copy a local file into storage under `key`; returns stored size in bytes."""

    def local_path(self, key: str) -> Path:
        """Path for streaming/inspection (local adapter) or a downloaded temp copy."""

    def exists(self, key: str) -> bool: ...

    def size(self, key: str) -> int: ...

    def delete(self, key: str) -> None: ...

    def delete_prefix(self, prefix: str) -> int: ...

    def healthy(self) -> bool: ...

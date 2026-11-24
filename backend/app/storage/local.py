"""Local private object directory for development. Files are never served statically."""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from app.storage.base import InvalidObjectKey, validate_key


class LocalObjectStorage:
    provider = "local"

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)

    def _path(self, key: str) -> Path:
        validate_key(key)
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise InvalidObjectKey("invalid object key")
        return path

    def put_file(self, key: str, source: Path) -> int:
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(f".{dest.name}.{uuid.uuid4().hex}.part")
        try:
            shutil.copyfile(source, tmp)
            os.chmod(tmp, 0o600)
            os.replace(tmp, dest)
        finally:
            tmp.unlink(missing_ok=True)
        return dest.stat().st_size

    def local_path(self, key: str) -> Path:
        path = self._path(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        return path

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def size(self, key: str) -> int:
        return self.local_path(key).stat().st_size

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def delete_prefix(self, prefix: str) -> int:
        base = self._path(prefix.rstrip("/"))
        if not base.exists():
            return 0
        if base.is_file():
            base.unlink()
            return 1
        count = sum(1 for p in base.rglob("*") if p.is_file())
        shutil.rmtree(base)
        return count

    def healthy(self) -> bool:
        probe = self.root / f".probe-{uuid.uuid4().hex}"
        try:
            probe.write_bytes(b"ok")
            probe.unlink()
            return True
        except OSError:
            return False

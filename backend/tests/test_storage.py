from __future__ import annotations

from pathlib import Path

import pytest

from app.storage.base import InvalidObjectKey, validate_key
from app.storage.local import LocalObjectStorage


@pytest.mark.parametrize(
    "key",
    ["", "../etc/passwd", "a/../../b", "/abs/path", "a//b", "a/./b", ".hidden", "a\\b", "a b"],
)
def test_rejects_unsafe_keys(key: str) -> None:
    with pytest.raises(InvalidObjectKey):
        validate_key(key)


def test_roundtrip_and_prefix_delete(tmp_path: Path) -> None:
    store = LocalObjectStorage(tmp_path / "objects")
    src = tmp_path / "in.bin"
    src.write_bytes(b"hello")
    assert store.put_file("u1/p1/source/abc.mp4", src) == 5
    assert store.put_file("u1/p1/thumb/t.jpg", src) == 5
    assert store.exists("u1/p1/source/abc.mp4")
    assert store.local_path("u1/p1/source/abc.mp4").read_bytes() == b"hello"
    assert (store.local_path("u1/p1/source/abc.mp4").stat().st_mode & 0o777) == 0o600
    assert store.delete_prefix("u1/p1") == 2
    assert not store.exists("u1/p1/source/abc.mp4")
    assert store.delete_prefix("u1/p1") == 0
    assert store.healthy()


def test_symlink_escape_blocked(tmp_path: Path) -> None:
    store = LocalObjectStorage(tmp_path / "objects")
    outside = tmp_path / "outside"
    outside.mkdir()
    (store.root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(InvalidObjectKey):
        store.local_path("link/secret")

"""Signed private media: ownership, expiry, tampering, range requests, no-store headers."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.media import parse_range


def _upload(client: TestClient, headers: dict[str, str], path: Path) -> str:
    with path.open("rb") as fh:
        res = client.post("/api/projects", headers=headers, files={"file": (path.name, fh)})
    assert res.status_code == 201, res.json()
    return str(res.json()["id"])


def test_signed_source_streams_with_ranges(
    client: TestClient, auth_headers: dict[str, str], media: dict[str, Path]
) -> None:
    src = media["valid.mp4"]
    pid = _upload(client, auth_headers, src)
    info = client.get(f"/api/projects/{pid}/media/source", headers=auth_headers).json()
    assert info["url"].startswith("/api/media/") and info["content_type"] == "video/mp4"
    assert "users/" not in info["url"]

    full = client.get(info["url"])  # no bearer needed: the URL itself is the short-lived grant
    assert full.status_code == 200 and full.content == src.read_bytes()
    assert "no-store" in full.headers["cache-control"]
    assert full.headers["accept-ranges"] == "bytes"

    part = client.get(info["url"], headers={"Range": "bytes=10-19"})
    assert part.status_code == 206 and part.content == src.read_bytes()[10:20]
    size = src.stat().st_size
    assert part.headers["content-range"] == f"bytes 10-19/{size}"
    tail = client.get(info["url"], headers={"Range": "bytes=-5"})
    assert tail.content == src.read_bytes()[-5:]
    bad = client.get(info["url"], headers={"Range": f"bytes={size + 10}-"})
    assert bad.status_code == 416

    # After deletion the link stops working.
    client.delete(f"/api/projects/{pid}", headers=auth_headers)
    assert client.get(info["url"]).status_code == 404


def test_tampered_and_expired_links(
    client: TestClient,
    auth_headers: dict[str, str],
    media: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid = _upload(client, auth_headers, media["valid.mp4"])
    url = client.get(f"/api/projects/{pid}/media/source", headers=auth_headers).json()["url"]
    assert client.get(url[:-2] + "xx").status_code == 403
    monkeypatch.setattr("app.media.signing.MEDIA_TOKEN_TTL_SECONDS", -1)
    res = client.get(url)
    assert res.status_code == 403 and res.json()["error"]["code"] == "media_link_expired"


def test_forged_grant_for_another_users_key_is_refused(
    client: TestClient, auth_headers: dict[str, str], media: dict[str, Path]
) -> None:
    from app.config import get_settings
    from app.media.signing import MediaGrant, sign_media

    _upload(client, auth_headers, media["valid.mp4"])
    me = client.get("/api/me", headers=auth_headers).json()["user_id"]
    token = sign_media(
        get_settings(), MediaGrant(f"users/{me}/x/source.mp4", "someone", "video/mp4")
    )
    assert client.get(f"/api/media/{token}").status_code == 403


@pytest.mark.parametrize(
    ("header", "expected"),
    [(None, None), ("bytes=0-0", (0, 0)), ("bytes=5-", (5, 99)), ("bytes=-10", (90, 99)),
     ("bytes=90-500", (90, 99)), ("bytes=0-1,5-6", None), ("items=0-1", None)],
)  # fmt: skip
def test_parse_range(header: str | None, expected: tuple[int, int] | None) -> None:
    assert parse_range(header, 100) == expected


@pytest.mark.parametrize("header", ["bytes=100-", "bytes=50-10", "bytes=-0"])
def test_unsatisfiable_ranges(header: str) -> None:
    with pytest.raises(ValueError):
        parse_range(header, 100)

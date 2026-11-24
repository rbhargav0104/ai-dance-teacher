"""Signed, short-lived private media streaming with HTTP range support (spec section 23)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.session import get_db
from app.errors import ApiError
from app.media.signing import InvalidMediaToken, verify_media
from app.models import User
from app.storage import get_storage

router = APIRouter(tags=["media"])

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")
CHUNK = 256 * 1024
PRIVATE_HEADERS = {
    "Cache-Control": "private, no-store",
    "Accept-Ranges": "bytes",
    "X-Content-Type-Options": "nosniff",
    "Content-Disposition": "inline",
    "Cross-Origin-Resource-Policy": "same-site",
}


def _iter_file(path: Path, start: int, length: int) -> Iterator[bytes]:
    with path.open("rb") as fh:
        fh.seek(start)
        remaining = length
        while remaining > 0:
            chunk = fh.read(min(CHUNK, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Return inclusive (start, end) or None for a full response. Raises on unsatisfiable."""
    if not header:
        return None
    m = _RANGE_RE.fullmatch(header.strip())
    if not m or (not m.group(1) and not m.group(2)):
        return None  # multi-range / malformed: serve the whole file (allowed by RFC 9110)
    if m.group(1):
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else size - 1
    else:
        suffix = int(m.group(2))
        if suffix == 0:
            raise ValueError("unsatisfiable")
        start, end = max(0, size - suffix), size - 1
    if start >= size or start > end:
        raise ValueError("unsatisfiable")
    return start, min(end, size - 1)


@router.get("/api/media/{token}", include_in_schema=True)
def stream_media(
    token: str,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    range_header: Annotated[str | None, Header(alias="Range")] = None,
) -> StreamingResponse:
    try:
        grant = verify_media(settings, token)
    except InvalidMediaToken as exc:
        if exc.expired:
            raise ApiError(403, "media_link_expired", "This video link expired. Reload.") from exc
        raise ApiError(403, "media_link_invalid", "This video link isn't valid.") from exc
    # Defence in depth: the key must sit under the grantee's prefix and the user must exist.
    if (
        not grant.object_key.startswith(f"users/{grant.user_id}/")
        or db.get(User, grant.user_id) is None
    ):
        raise ApiError(403, "media_link_invalid", "This video link isn't valid.")
    storage = get_storage()
    try:
        path = storage.local_path(grant.object_key)
    except (FileNotFoundError, ValueError) as exc:
        raise ApiError(404, "media_not_found", "This video was deleted.") from exc
    size = path.stat().st_size
    try:
        rng = parse_range(range_header, size)
    except ValueError as exc:
        raise ApiError(416, "range_not_satisfiable", "Requested range is invalid.") from exc
    headers = dict(PRIVATE_HEADERS)
    if rng is None:
        headers["Content-Length"] = str(size)
        return StreamingResponse(
            _iter_file(path, 0, size), media_type=grant.content_type, headers=headers
        )
    start, end = rng
    length = end - start + 1
    headers["Content-Length"] = str(length)
    headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(
        _iter_file(path, start, length),
        status_code=206,
        media_type=grant.content_type,
        headers=headers,
    )

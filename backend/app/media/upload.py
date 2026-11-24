"""Streaming multipart receiver: writes the single `file` part straight to a temp file.

FastAPI's UploadFile would buffer the whole body before our size check runs. This parser
enforces the byte limit *while* streaming, rejects bad extensions as soon as the part headers
arrive, and never holds more than one network chunk in memory.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from python_multipart.multipart import MultipartParser, parse_options_header

from app.media.probe import MediaRejected, check_extension

MAX_TEXT_FIELD_BYTES = 1024
# Multipart framing + small text fields on top of the file itself.
MULTIPART_OVERHEAD_BYTES = 64 * 1024


@dataclass
class ReceivedUpload:
    path: Path
    filename: str
    extension: str
    size: int
    fields: dict[str, str] = field(default_factory=dict)


class _State:
    def __init__(self, tmp_dir: Path, max_bytes: int) -> None:
        self.tmp_dir = tmp_dir
        self.max_bytes = max_bytes
        self.header_field = b""
        self.header_value = b""
        self.headers: dict[bytes, bytes] = {}
        self.part_name: str | None = None
        self.part_filename: str | None = None
        self.text = bytearray()
        self.fh: BinaryIO | None = None
        self.path: Path | None = None
        self.filename = ""
        self.extension = ""
        self.size = 0
        self.file_parts = 0
        self.fields: dict[str, str] = {}
        self.error: MediaRejected | None = None

    # --- parser callbacks -------------------------------------------------------------------
    def on_part_begin(self) -> None:
        self.headers = {}
        self.part_name = None
        self.part_filename = None
        self.text = bytearray()

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self.header_field += data[start:end]

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self.header_value += data[start:end]

    def on_header_end(self) -> None:
        self.headers[self.header_field.lower()] = self.header_value
        self.header_field = b""
        self.header_value = b""

    def on_headers_finished(self) -> None:
        _, opts = parse_options_header(self.headers.get(b"content-disposition", b""))
        name = opts.get(b"name")
        fname = opts.get(b"filename")
        self.part_name = name.decode("utf-8", "replace") if name else None
        self.part_filename = fname.decode("utf-8", "replace") if fname is not None else None
        if self.part_name == "file":
            self.file_parts += 1
            if self.file_parts > 1:
                raise MediaRejected("too_many_files", "Upload one video at a time.", 400)
            self.extension = check_extension(self.part_filename)
            self.filename = self.part_filename or ""
            self.tmp_dir.mkdir(parents=True, exist_ok=True)
            self.path = self.tmp_dir / f"upload-{uuid.uuid4().hex}{self.extension}"
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            self.fh = os.fdopen(fd, "wb")

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        chunk = data[start:end]
        if self.part_name == "file" and self.fh is not None:
            self.size += len(chunk)
            if self.size > self.max_bytes:
                raise MediaRejected(
                    "file_too_large",
                    f"Videos must be {self.max_bytes // (1024 * 1024)} MB or smaller.",
                    413,
                )
            self.fh.write(chunk)
        elif self.part_name is not None:
            self.text += chunk
            if len(self.text) > MAX_TEXT_FIELD_BYTES:
                raise MediaRejected("invalid_request", "A form field was too long.", 400)

    def on_part_end(self) -> None:
        if self.part_name == "file" and self.fh is not None:
            self.fh.close()
            self.fh = None
        elif self.part_name:
            self.fields[self.part_name] = self.text.decode("utf-8", "replace")

    def cleanup(self) -> None:
        if self.fh is not None:
            self.fh.close()
            self.fh = None
        if self.path is not None:
            self.path.unlink(missing_ok=True)


def boundary_from_content_type(content_type: str | None) -> bytes:
    ctype, opts = parse_options_header(content_type or "")
    boundary = opts.get(b"boundary")
    if ctype != b"multipart/form-data" or not boundary:
        raise MediaRejected("invalid_request", "Send the video as multipart/form-data.", 400)
    return boundary


async def receive_upload(
    stream: AsyncIterator[bytes], content_type: str | None, *, tmp_dir: Path, max_bytes: int
) -> ReceivedUpload:
    """Stream the request body to disk. On any failure the temp file is removed."""
    boundary = boundary_from_content_type(content_type)
    state = _State(tmp_dir, max_bytes)
    parser = MultipartParser(
        boundary,
        {
            "on_part_begin": state.on_part_begin,
            "on_header_field": state.on_header_field,
            "on_header_value": state.on_header_value,
            "on_header_end": state.on_header_end,
            "on_headers_finished": state.on_headers_finished,
            "on_part_data": state.on_part_data,
            "on_part_end": state.on_part_end,
        },
    )
    try:
        async for chunk in stream:
            parser.write(chunk)
        parser.finalize()
        if state.path is None or state.file_parts == 0:
            raise MediaRejected("missing_file", "Choose a video to upload.", 400)
        if state.fh is not None:
            raise MediaRejected("invalid_request", "The upload was incomplete.", 400)
        if state.size == 0:
            raise MediaRejected("empty_file", "This file is empty.", 422)
    except MediaRejected:
        state.cleanup()
        raise
    except Exception as exc:
        state.cleanup()
        raise MediaRejected("invalid_request", "The upload could not be read.", 400) from exc
    return ReceivedUpload(
        path=state.path,
        filename=state.filename,
        extension=state.extension,
        size=state.size,
        fields=state.fields,
    )

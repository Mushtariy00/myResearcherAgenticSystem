"""File downloads: bytes or stored files streamed with the headers docs/PLAN.md asks for
(browser hardening).

Every file response is ``nosniff`` and private. Attachments make the browser save rather than
render what was generated from model output. PDFs too: the viewer fetches them itself.
"""

import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any, BinaryIO, Literal
from urllib.parse import quote

from fastapi.responses import StreamingResponse

CHUNK_BYTES = 64 * 1024
MAX_FILENAME = 120
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def binary_response(*media_types: str) -> dict[int | str, dict[str, Any]]:
    """OpenAPI ``responses`` for a binary body of these types (generated clients read a Blob)."""
    return {
        200: {
            "description": "The file",
            "content": {
                media_type: {"schema": {"type": "string", "format": "binary"}}
                for media_type in media_types
            },
        }
    }


def safe_filename(name: str, fallback: str = "download") -> str:
    """An ASCII file name: runs of anything but letters, digits, dots, dashes and underscores
    become one dash, and leading or trailing dots and dashes go."""
    cleaned = _UNSAFE.sub("-", name).strip(".-")[:MAX_FILENAME].rstrip(".-")
    return cleaned or fallback


def content_disposition(disposition: Literal["inline", "attachment"], filename: str) -> str:
    """A Content-Disposition value with an ASCII ``filename`` and, when the real name differs,
    the RFC 6266 ``filename*`` form of it (percent-encoded, so it can never break the header)."""
    ascii_name = safe_filename(filename)
    value = f'{disposition}; filename="{ascii_name}"'
    if ascii_name != filename:
        value += f"; filename*=UTF-8''{quote(filename[:MAX_FILENAME], safe='')}"
    return value


def _chunks(content: bytes) -> Iterator[bytes]:
    for start in range(0, len(content), CHUNK_BYTES):
        yield content[start : start + CHUNK_BYTES]


def _file_chunks(handle: BinaryIO) -> Iterator[bytes]:
    with handle:
        while chunk := handle.read(CHUNK_BYTES):
            yield chunk


def _headers(
    disposition: Literal["inline", "attachment"], filename: str, length: int
) -> dict[str, str]:
    return {
        "Content-Disposition": content_disposition(disposition, filename),
        "Content-Length": str(length),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private",
    }


def file_response(
    content: bytes,
    *,
    media_type: str,
    filename: str,
    disposition: Literal["inline", "attachment"] = "attachment",
) -> StreamingResponse:
    return StreamingResponse(
        _chunks(content),
        media_type=media_type,
        headers=_headers(disposition, filename, len(content)),
    )


def path_response(
    path: Path,
    *,
    media_type: str,
    filename: str,
    disposition: Literal["inline", "attachment"] = "attachment",
) -> StreamingResponse:
    """``file_response`` for a file on disk, read a chunk at a time while it is sent.

    The file is opened here, so a missing one raises FileNotFoundError before the response
    starts, and its length is the open file's, so it matches the bytes sent even if the path
    is replaced meanwhile.
    """
    handle = path.open("rb")  # closed by _file_chunks once the body is sent
    length = os.fstat(handle.fileno()).st_size
    return StreamingResponse(
        _file_chunks(handle),
        media_type=media_type,
        headers=_headers(disposition, filename, length),
    )

"""Content-addressed PDF files: ``<root>/papers/<sha256[:2]>/<sha256>.pdf``.

The same PDF reached through several papers or runs is stored once, and a file is complete
whenever its name exists, because it is written to a temporary file and renamed into place.
"""

import contextlib
import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Final

_SHA256: Final = re.compile(r"^[0-9a-f]{64}$")
# Readable by the API process, which streams files to lab members; the data directory itself
# is what keeps them private.
_FILE_MODE: Final = 0o644


def pdf_path(root: Path, sha256: str) -> Path:
    """Where the PDF with this SHA-256 lives under root."""
    if not _SHA256.match(sha256):
        raise ValueError(f"not a lowercase hex SHA-256: {sha256!r}")
    return root / "papers" / sha256[:2] / f"{sha256}.pdf"


def write_atomic(path: Path, data: bytes) -> None:
    """Write data to path so that readers see the old file or the whole new one, never part."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, _FILE_MODE)
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
        raise
    _sync_directory(path.parent)


def store_pdf(root: Path, data: bytes) -> tuple[str, Path]:
    """Store a PDF under its SHA-256 unless that file exists; returns (sha256, path)."""
    sha256 = hashlib.sha256(data).hexdigest()
    path = pdf_path(root, sha256)
    if not path.exists():
        write_atomic(path, data)
    return sha256, path


def _sync_directory(directory: Path) -> None:
    # Makes the rename itself durable; directories cannot be opened like this on Windows.
    if os.name != "posix":
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

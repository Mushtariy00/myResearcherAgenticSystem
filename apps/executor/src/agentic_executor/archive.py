"""Copying a job's outputs out of the tar Docker returns for its output folder.

The tar comes from the job's container, so it is untrusted. Only the regular files named in
agentic_core.gpu_jobs.OUTPUT_FILES are written, each within its size cap. Every other member is
ignored, so nothing in the tar can write outside the job's out/ folder: no links, devices,
absolute paths or "..".

Each file is hashed as it is copied. The job's provenance keeps the hashes, so the API lists the
outputs with their sha256 without reading a checkpoint of up to 200 MB again on every request.
"""

from __future__ import annotations

import hashlib
import os
import tarfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import IO

from agentic_core.gpu_jobs import OUTPUT_FILES

CHUNK_BYTES = 1024 * 1024


class ArchiveError(Exception):
    """The tar could not be read (truncated or not a tar)."""


@dataclass
class ExtractReport:
    copied: dict[str, int] = field(default_factory=dict)  # path under out/ to bytes written
    sha256: dict[str, str] = field(default_factory=dict)  # path under out/ to its sha256
    skipped: dict[str, str] = field(default_factory=dict)  # output file left behind, and why


def extract_outputs(
    tar_path: Path, out_dir: Path, allowed: Mapping[str, int] = OUTPUT_FILES
) -> ExtractReport:
    """Write the files of ``allowed`` (path under the output folder to its size cap) found in
    ``tar_path``, the archive of the container's output folder, under ``out_dir``."""
    report = ExtractReport()
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(tar_path, mode="r:") as tar:
            for member in tar:
                relative = _relative(member.name)
                if relative is None or relative not in allowed:
                    continue
                if relative in report.copied or relative in report.skipped:
                    continue  # the first member of a name wins
                if not member.isfile():
                    report.skipped[relative] = "not a regular file"
                    continue
                cap = allowed[relative]
                if member.size > cap:
                    report.skipped[relative] = f"{member.size} bytes, over the {cap}-byte cap"
                    continue
                source = tar.extractfile(member)
                if source is None:
                    report.skipped[relative] = "unreadable"
                    continue
                written, sha256 = _write(source, out_dir / relative, cap)
                report.copied[relative] = written
                report.sha256[relative] = sha256
    except (tarfile.TarError, EOFError) as exc:
        raise ArchiveError(f"Cannot read the output archive: {exc}") from exc
    return report


def _relative(name: str) -> str | None:
    """A member's path under the archived folder ("out/results.json" -> "results.json"), or None
    for the folder itself and for any path that is absolute or climbs out with ".."."""
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        return None
    parts = [part for part in path.parts if part not in ("", ".")]
    if len(parts) < 2:
        return None
    return "/".join(parts[1:])


def _write(source: IO[bytes], target: Path, cap: int) -> tuple[int, str]:
    """Copy ``source`` to ``target``: the bytes written and their sha256."""
    target.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
    digest = hashlib.sha256()
    written = 0
    with os.fdopen(os.open(target, flags, 0o644), "wb") as sink:
        while chunk := source.read(CHUNK_BYTES):
            written += len(chunk)
            if written > cap:
                break
            digest.update(chunk)
            sink.write(chunk)
    if written > cap:  # a member larger than its header said
        target.unlink()
        raise ArchiveError(f"{target.name} is larger than its {cap}-byte cap")
    return written, digest.hexdigest()

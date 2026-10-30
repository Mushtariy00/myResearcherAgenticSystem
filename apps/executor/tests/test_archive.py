"""Copying outputs out of the container's tar: only the listed regular files, within their caps."""

import hashlib
import io
import tarfile
from pathlib import Path

import pytest

from agentic_executor import archive as archive_module
from agentic_executor.archive import ArchiveError, extract_outputs

ALLOWED = {"results.json": 100, "metrics.jsonl": 100, "checkpoints/best.pt": 10}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tar(path: Path, members: list[tuple[str, bytes | None, bytes]]) -> Path:
    """members: (name, file content or None for a directory, tarfile type)."""
    with tarfile.open(path, mode="w") as tar:
        for name, content, kind in members:
            info = tarfile.TarInfo(name)
            info.type = kind
            if kind == tarfile.SYMTYPE or kind == tarfile.LNKTYPE:
                info.linkname = "/etc/passwd"
                tar.addfile(info)
            elif content is None:
                tar.addfile(info)
            else:
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))
    return path


def test_the_listed_files_are_copied_and_nothing_else(tmp_path: Path) -> None:
    archive = _tar(
        tmp_path / "out.tar",
        [
            ("out/", None, tarfile.DIRTYPE),
            ("out/results.json", b'{"status": "ok"}', tarfile.REGTYPE),
            ("out/metrics.jsonl", b"{}\n", tarfile.REGTYPE),
            ("out/checkpoints/", None, tarfile.DIRTYPE),
            ("out/checkpoints/best.pt", b"weights", tarfile.REGTYPE),
            ("out/checkpoints/last.pt", b"weights", tarfile.REGTYPE),
            ("out/notes.txt", b"hello", tarfile.REGTYPE),
        ],
    )
    out = tmp_path / "job" / "out"
    report = extract_outputs(archive, out, ALLOWED)
    assert report.copied == {"results.json": 16, "metrics.jsonl": 3, "checkpoints/best.pt": 7}
    # Hashed as they are copied: the job's provenance lists them with these.
    assert report.sha256 == {
        "results.json": _sha256(b'{"status": "ok"}'),
        "metrics.jsonl": _sha256(b"{}\n"),
        "checkpoints/best.pt": _sha256(b"weights"),
    }
    assert report.skipped == {}
    assert sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file()) == [
        "checkpoints/best.pt",
        "metrics.jsonl",
        "results.json",
    ]
    assert (out / "results.json").read_bytes() == b'{"status": "ok"}'


def test_a_file_over_its_cap_is_left_behind(tmp_path: Path) -> None:
    archive = _tar(tmp_path / "out.tar", [("out/checkpoints/best.pt", b"x" * 11, tarfile.REGTYPE)])
    report = extract_outputs(archive, tmp_path / "out", ALLOWED)
    assert report.copied == {} and report.sha256 == {}
    assert "over the 10-byte cap" in report.skipped["checkpoints/best.pt"]
    assert not (tmp_path / "out" / "checkpoints" / "best.pt").exists()


def test_a_file_is_copied_and_hashed_a_chunk_at_a_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(archive_module, "CHUNK_BYTES", 4)
    weights = bytes(range(10))
    archive = _tar(tmp_path / "out.tar", [("out/checkpoints/best.pt", weights, tarfile.REGTYPE)])
    report = extract_outputs(archive, tmp_path / "out", ALLOWED)
    assert report.copied == {"checkpoints/best.pt": 10}
    assert report.sha256 == {"checkpoints/best.pt": _sha256(weights)}
    assert (tmp_path / "out" / "checkpoints" / "best.pt").read_bytes() == weights


def test_a_member_longer_than_its_header_said_is_removed(tmp_path: Path) -> None:
    target = tmp_path / "out" / "results.json"
    with pytest.raises(ArchiveError, match="larger than its 10-byte cap"):
        archive_module._write(io.BytesIO(b"x" * 11), target, 10)
    assert not target.exists()


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE])
def test_links_and_special_files_are_never_written(tmp_path: Path, kind: bytes) -> None:
    archive = _tar(tmp_path / "out.tar", [("out/results.json", b"", kind)])
    report = extract_outputs(archive, tmp_path / "out", ALLOWED)
    assert report.skipped == {"results.json": "not a regular file"}
    assert not (tmp_path / "out" / "results.json").exists()


@pytest.mark.parametrize(
    "name", ["/out/results.json", "out/../results.json", "../out/results.json", "results.json"]
)
def test_paths_that_leave_the_folder_or_name_it_are_ignored(tmp_path: Path, name: str) -> None:
    archive = _tar(tmp_path / "out.tar", [(name, b"{}", tarfile.REGTYPE)])
    report = extract_outputs(archive, tmp_path / "job" / "out", ALLOWED)
    assert report.copied == {}
    assert not any((tmp_path / "job").rglob("results.json"))


def test_the_first_member_of_a_name_wins(tmp_path: Path) -> None:
    archive = _tar(
        tmp_path / "out.tar",
        [
            ("out/results.json", b"first", tarfile.REGTYPE),
            ("out/results.json", b"second", tarfile.REGTYPE),
        ],
    )
    extract_outputs(archive, tmp_path / "out", ALLOWED)
    assert (tmp_path / "out" / "results.json").read_bytes() == b"first"


def test_a_truncated_archive_is_an_error(tmp_path: Path) -> None:
    archive = _tar(tmp_path / "out.tar", [("out/results.json", b"x" * 90, tarfile.REGTYPE)])
    archive.write_bytes(archive.read_bytes()[:600])
    with pytest.raises(ArchiveError):
        extract_outputs(archive, tmp_path / "out", ALLOWED)

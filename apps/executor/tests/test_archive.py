"""Copying outputs out of the container's tar: only the listed regular files, within their caps."""

import io
import tarfile
from pathlib import Path

import pytest

from agentic_executor.archive import ArchiveError, extract_outputs

ALLOWED = {"results.json": 100, "metrics.jsonl": 100, "checkpoints/best.pt": 10}


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
    assert report.copied == {}
    assert "over the 10-byte cap" in report.skipped["checkpoints/best.pt"]
    assert not (tmp_path / "out" / "checkpoints" / "best.pt").exists()


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

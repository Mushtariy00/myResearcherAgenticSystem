import hashlib
import os
import stat
from pathlib import Path

import pytest

from agentic_scholarly import storage
from agentic_scholarly.storage import pdf_path, store_pdf, write_atomic

SHA = hashlib.sha256(b"paper").hexdigest()


def test_paths_are_content_addressed(tmp_path: Path) -> None:
    assert pdf_path(tmp_path, SHA) == tmp_path / "papers" / SHA[:2] / f"{SHA}.pdf"


@pytest.mark.parametrize("bad", ["../../etc/passwd", SHA.upper(), SHA[:-1], ""])
def test_only_sha256_digests_name_files(tmp_path: Path, bad: str) -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        pdf_path(tmp_path, bad)


def test_atomic_writes_leave_no_temporary_files(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "file.pdf"
    write_atomic(target, b"first")
    write_atomic(target, b"second")
    assert target.read_bytes() == b"second"
    assert [p.name for p in target.parent.iterdir()] == ["file.pdf"]
    if os.name == "posix":
        assert stat.S_IMODE(target.stat().st_mode) == 0o644


def test_a_failed_write_keeps_the_old_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "file.pdf"
    write_atomic(target, b"old")

    def broken_replace(source: str, destination: Path) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(storage.os, "replace", broken_replace)
    with pytest.raises(OSError, match="disk full"):
        write_atomic(target, b"new")
    assert target.read_bytes() == b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["file.pdf"]


def test_store_pdf_writes_each_file_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sha256, path = store_pdf(tmp_path, b"paper")
    assert sha256 == SHA
    assert path.read_bytes() == b"paper"

    def no_second_write(path: Path, data: bytes) -> None:
        raise AssertionError("an existing file was written again")

    monkeypatch.setattr(storage, "write_atomic", no_second_write)
    assert store_pdf(tmp_path, b"paper") == (SHA, path)

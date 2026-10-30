"""Executor entry point: `python -m harness.job [harness.train arguments]`.

The executor runs every job through this wrapper (docs/design/experiments.md). It starts
harness.train in a child process and is the only writer of the container's output:
  - the training's metric records reach it on a pipe of their own (ARP_METRIC_FD) and go out as
    `ARP-METRIC <json>` lines;
  - everything the training prints goes out as it came, in lines of at most MAX_LINE characters,
    except that a line starting with "ARP-" is indented, so generated code can't fake a metric
    record or the end of the job;
  - when training ends: `ARP-DONE {"exit_code": n}`, n being negative when a signal ended it.

Then it waits, up to HOLD_SECONDS, for the executor to copy /workspace/out and stop the
container. The output folder is a tmpfs volume, and its contents are gone once the container
stops. SIGTERM stops the training (and its DataLoader workers) and ends the wait.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from types import FrameType
from typing import IO

HOLD_SECONDS = 900
MAX_LINE = 64 * 1024
# DataLoader workers can hold the pipes open for a moment after the training process has died.
READER_GRACE_SECONDS = 10
METRIC_FD_ENV = "ARP_METRIC_FD"
PROTOCOL_PREFIX = "ARP-"
METRIC_PREFIX = "ARP-METRIC "

_write_lock = threading.Lock()


def _write_line(text: str) -> None:
    with _write_lock:
        sys.stdout.write(text + "\n")
        sys.stdout.flush()


def _relay_output(pipe: IO[str]) -> None:
    """The training's own stdout and stderr, with protocol-like lines indented."""
    for piece in iter(lambda: pipe.readline(MAX_LINE), ""):
        text = piece.removesuffix("\n")
        if text.startswith(PROTOCOL_PREFIX):
            text = "  " + text
        _write_line(text)


def _relay_metrics(pipe: IO[str]) -> None:
    """harness.train's metric records. Only whole ARP-METRIC lines go out."""
    for piece in iter(lambda: pipe.readline(MAX_LINE), ""):
        if piece.endswith("\n") and piece.startswith(METRIC_PREFIX):
            _write_line(piece.removesuffix("\n"))


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    read_fd, write_fd = os.pipe()
    child = subprocess.Popen(
        [sys.executable, "-m", "harness.train", *args],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        pass_fds=(write_fd,),
        env={**os.environ, METRIC_FD_ENV: str(write_fd)},
        start_new_session=True,  # its own process group, with its DataLoader workers
    )
    os.close(write_fd)
    assert child.stdout is not None
    readers = [
        threading.Thread(target=_relay_output, args=(child.stdout,), daemon=True),
        threading.Thread(
            target=_relay_metrics,
            args=(os.fdopen(read_fd, encoding="utf-8", errors="replace"),),
            daemon=True,
        ),
    ]
    for reader in readers:
        reader.start()

    stopping = threading.Event()

    def stop(signum: int, _frame: FrameType | None) -> None:
        stopping.set()
        try:
            os.killpg(child.pid, signum)
        except ProcessLookupError:
            pass

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    exit_code = child.wait()
    for reader in readers:
        reader.join(READER_GRACE_SECONDS)
    if stopping.is_set():
        return 128 + signal.SIGTERM
    _write_line("ARP-DONE " + json.dumps({"exit_code": exit_code}))
    deadline = time.monotonic() + HOLD_SECONDS
    while not stopping.is_set() and time.monotonic() < deadline:
        stopping.wait(1.0)
    return 0


if __name__ == "__main__":
    sys.exit(main())

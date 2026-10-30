"""Following a job's output: the container's lines become log.txt, the log tail and harness.job's
protocol records.

Only harness.job writes protocol lines (sandbox/pytorch/harness/job.py), on stdout: an exact
``ARP-METRIC <json>`` line is a metric record and an exact ``ARP-DONE <json>`` line says training
ended. It indents every line of the training's own output that starts with "ARP-", so only lines
that start with a prefix count, and generated code can't fake a record or the end of the job.

The container's output is untrusted, so what comes out of here is safe to store: records and the
tail hold no NUL characters, and a record's NaN or infinity becomes null (Postgres refuses both).
"""

from __future__ import annotations

import json
import math
import os
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_core.gpu_jobs import DONE_PREFIX, METRIC_PREFIX
from agentic_executor.ports import LogLine

MAX_LOG_BYTES = 32 * 1024**2  # log.txt; later lines are dropped
TAIL_LINES = 200  # gpu_jobs.log_tail: the output's last lines,
TAIL_BYTES = 32 * 1024  # within this many bytes


@dataclass(frozen=True)
class Epoch:
    """An epoch record ({"kind": "epoch", "epoch", "train", "val", "ts"}). ``ordinal`` is its
    epoch counted from 1 (the record's own "epoch" plus 1), not its place in the output: should
    Docker rotate a long output's first lines away before an executor adopts the container, the
    later epochs still count as new."""

    ordinal: int
    record: dict[str, Any]


@dataclass(frozen=True)
class Step:
    """A training step record ({"kind": "train_step", "epoch", "step", "loss", "ts"})."""

    record: dict[str, Any]


@dataclass(frozen=True)
class Done:
    """ARP-DONE: training ended with this exit code (negative when a signal ended it)."""

    exit_code: int


type Record = Epoch | Step | Done


class JobOutput:
    """A job's output, line by line, from the container's start.

    Writes log.txt from scratch (Docker replays a container's output from its start, so an
    executor that adopts a container writes it again), keeps the tail, and returns the protocol
    record a line holds.
    """

    def __init__(
        self,
        log_path: Path,
        *,
        max_log_bytes: int = MAX_LOG_BYTES,
        tail_lines: int = TAIL_LINES,
        tail_bytes: int = TAIL_BYTES,
    ) -> None:
        fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
        os.fchmod(fd, 0o644)
        self._log = os.fdopen(fd, "wb", buffering=0)  # unbuffered: the log is read while it grows
        self._max_log_bytes = max_log_bytes
        self._log_bytes = 0
        self._truncated = False
        self._tail_lines = tail_lines
        self._tail_bytes = tail_bytes
        self._tail: deque[str] = deque()
        self._tail_size = 0
        self.epochs = 0  # epoch records seen
        self.exit_code: int | None = None  # from ARP-DONE

    def feed(self, line: LogLine) -> Record | None:
        """Take the next line; the protocol record it holds, if any."""
        data = line.text.encode("utf-8", "replace")
        self._write(data)
        self._keep(data)
        if line.stream != "stdout":
            return None  # harness.job writes its protocol lines to stdout only
        return self._record(line.text)

    @property
    def tail(self) -> str:
        """The last lines, at most tail_lines of them within tail_bytes."""
        return "\n".join(self._tail)

    def close(self) -> None:
        self._log.close()

    def _write(self, data: bytes) -> None:
        if self._truncated:
            return
        if self._log_bytes + len(data) + 1 > self._max_log_bytes:
            self._truncated = True
            note = f"[log.txt ends here: the output passed {self._max_log_bytes} bytes]\n"
            self._log.write(note.encode())
            return
        self._log.write(data + b"\n")
        self._log_bytes += len(data) + 1

    def _keep(self, data: bytes) -> None:
        # A line counts its line break; one longer than the whole tail keeps its start.
        data = data.replace(b"\0", b"")[: self._tail_bytes - 1]
        text = data.decode("utf-8", "ignore")
        self._tail.append(text)
        self._tail_size += len(text.encode()) + 1
        while len(self._tail) > self._tail_lines or self._tail_size > self._tail_bytes:
            self._tail_size -= len(self._tail.popleft().encode()) + 1

    def _record(self, text: str) -> Record | None:
        if text.startswith(METRIC_PREFIX):
            record = _json_object(text.removeprefix(METRIC_PREFIX))
            if record is None:
                return None
            if record.get("kind") == "epoch":
                epoch = record.get("epoch")
                if not isinstance(epoch, int) or isinstance(epoch, bool) or epoch < 0:
                    return None
                self.epochs += 1
                return Epoch(epoch + 1, record)
            if record.get("kind") == "train_step":
                return Step(record)
            return None
        if text.startswith(DONE_PREFIX) and self.exit_code is None:
            record = _json_object(text.removeprefix(DONE_PREFIX))
            exit_code = record.get("exit_code") if record is not None else None
            if isinstance(exit_code, int) and not isinstance(exit_code, bool):
                self.exit_code = exit_code
                return Done(exit_code)
        return None


def jsonable(value: Any) -> Any:
    """Parsed JSON from a job, as Postgres stores it: strings without NUL characters or lone
    surrogates, and null for NaN and the infinities."""
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {clean_text(str(key)): jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    return value


def clean_text(text: str) -> str:
    """``text`` as a Postgres text column takes it."""
    return text.encode("utf-8", "replace").decode("utf-8").replace("\0", "")


def _json_object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except (ValueError, RecursionError):
        return None
    return jsonable(value) if isinstance(value, dict) else None

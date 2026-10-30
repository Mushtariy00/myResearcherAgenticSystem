"""The Docker Engine API client the executor uses, over the socket proxy's Unix socket.

It makes the calls of agentic_executor.ports.DockerApi and no others. The proxy
(infra/compose/compose.yaml) refuses every other method and path, so a call added here needs a
rule there too; `make docker-proxy-check` shows what gets through.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from agentic_executor.ports import (
    Conflict,
    ContainerState,
    ContainerSummary,
    DockerError,
    LogLine,
    NotFound,
)

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30.0
# Following the logs and waiting for the exit last as long as the job does.
NO_READ_TIMEOUT = httpx.Timeout(TIMEOUT_SECONDS, read=None)
MAX_LINE_BYTES = 64 * 1024
# The log stream's frames from the Docker daemon itself, such as a log file it could not read.
SYSTEM_ERROR_STREAM = 3
_NEW_FILE = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW
_TIME = re.compile(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)")


class DockerClient:
    """agentic_executor.ports.DockerApi over ``socket_path`` (httpx, API ``api_version``)."""

    def __init__(
        self,
        socket_path: Path,
        *,
        api_version: str = "v1.47",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.socket_path = socket_path
        self.api_version = api_version
        self._client = httpx.AsyncClient(
            transport=transport or httpx.AsyncHTTPTransport(uds=str(socket_path)),
            base_url=f"http://docker/{api_version}",
            timeout=TIMEOUT_SECONDS,
            trust_env=False,
        )

    async def create_container(self, name: str, spec: dict[str, Any]) -> str:
        response = await self._call("POST", "/containers/create", params={"name": name}, body=spec)
        answer = _json_object(response)
        # Docker drops a limit this kernel can't enforce with only a warning, so say so.
        for warning in answer.get("Warnings") or []:
            logger.warning("Docker, creating %s: %s", name, warning)
        container_id = answer.get("Id")
        if not isinstance(container_id, str) or not container_id:
            raise DockerError(response.status_code, f"no container id in {answer!r:.200}")
        return container_id

    async def start_container(self, container_id: str) -> None:
        await self._call("POST", f"/containers/{_ref(container_id)}/start", ok=(304,))

    async def inspect_container(self, container_id: str) -> ContainerState:
        answer = _json_object(await self._call("GET", f"/containers/{_ref(container_id)}/json"))
        state = _mapping(answer.get("State"))
        status = str(state.get("Status") or "")
        exit_code = state.get("ExitCode")  # Docker reports 0 for a container still running
        stopped = status in ("exited", "dead") and isinstance(exit_code, int)
        return ContainerState(
            id=str(answer.get("Id") or ""),
            name=str(answer.get("Name") or "").removeprefix("/"),
            image_id=str(answer.get("Image") or ""),
            labels=_labels(_mapping(answer.get("Config")).get("Labels")),
            state=status,
            exit_code=exit_code if stopped else None,
            oom_killed=state.get("OOMKilled") is True,
            started_at=_time(state.get("StartedAt")),
            finished_at=_time(state.get("FinishedAt")),
        )

    async def list_containers(self, label: str) -> list[ContainerSummary]:
        filters = json.dumps({"label": [label]}, separators=(",", ":"))
        response = await self._call(
            "GET", "/containers/json", params={"all": "1", "filters": filters}
        )
        answer = _json(response)
        if not isinstance(answer, list):
            raise DockerError(response.status_code, f"not a container list: {answer!r:.200}")
        return [_summary(item) for item in answer if isinstance(item, dict)]

    async def follow_logs(self, container_id: str) -> AsyncIterator[LogLine]:
        frames = _LogFrames()
        async with self._stream(
            f"/containers/{_ref(container_id)}/logs",
            params={"follow": "1", "stdout": "1", "stderr": "1"},
            http_timeout=NO_READ_TIMEOUT,
        ) as response:
            async for chunk in response.aiter_bytes():
                for line in _log_lines(container_id, frames.feed(chunk)):
                    yield line
        for line in _log_lines(container_id, frames.close()):
            yield line

    async def stop_container(self, container_id: str, *, grace_seconds: int) -> None:
        # Docker answers once the container has stopped, which takes up to the grace period.
        await self._call(
            "POST",
            f"/containers/{_ref(container_id)}/stop",
            params={"t": str(grace_seconds)},
            ok=(304, 404),
            http_timeout=TIMEOUT_SECONDS + grace_seconds,
        )

    async def kill_container(self, container_id: str) -> None:
        try:
            await self._call("POST", f"/containers/{_ref(container_id)}/kill", ok=(404,))
        except Conflict as exc:
            if "not running" not in exc.message:
                raise

    async def wait_container(self, container_id: str) -> int:
        response = await self._call(
            "POST",
            f"/containers/{_ref(container_id)}/wait",
            params={"condition": "not-running"},
            http_timeout=NO_READ_TIMEOUT,
        )
        answer = _json_object(response)
        exit_code = answer.get("StatusCode")
        if not isinstance(exit_code, int):
            raise DockerError(response.status_code, f"no exit code in {answer!r:.200}")
        return exit_code

    async def remove_container(self, container_id: str) -> None:
        await self._call(
            "DELETE",
            f"/containers/{_ref(container_id)}",
            params={"force": "1", "v": "1"},
            ok=(404,),
        )

    async def download_archive(
        self, container_id: str, path: str, destination: Path, *, max_bytes: int
    ) -> int:
        written = 0
        async with self._stream(
            f"/containers/{_ref(container_id)}/archive", params={"path": path}
        ) as response:
            sink = os.fdopen(os.open(destination, _NEW_FILE, 0o600), "wb")
            try:
                with sink:
                    async for chunk in response.aiter_bytes():
                        written += len(chunk)
                        if written > max_bytes:
                            raise DockerError(
                                413, f"the archive of {path} is over {max_bytes} bytes"
                            )
                        sink.write(chunk)
            except BaseException:  # the cap, a broken connection or a cancel: no partial tar
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(destination)
                raise
        return written

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _call(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        ok: tuple[int, ...] = (),
        http_timeout: httpx.Timeout | float = TIMEOUT_SECONDS,
    ) -> httpx.Response:
        """One call. ``ok`` lists the statuses besides 2xx that are answers, not errors."""
        try:
            response = await self._client.request(
                method, path, params=params, json=body, timeout=http_timeout
            )
        except httpx.HTTPError as exc:
            raise self._unreachable(method, path, exc) from exc
        if not (response.is_success or response.status_code in ok):
            raise _error(response)
        return response

    @asynccontextmanager
    async def _stream(
        self,
        path: str,
        *,
        params: dict[str, str],
        http_timeout: httpx.Timeout | float = TIMEOUT_SECONDS,
    ) -> AsyncIterator[httpx.Response]:
        """A GET whose answer is read as it arrives: a log stream or an archive."""
        request = self._client.build_request("GET", path, params=params, timeout=http_timeout)
        try:
            response = await self._client.send(request, stream=True)
        except httpx.HTTPError as exc:
            raise self._unreachable("GET", path, exc) from exc
        try:
            if not response.is_success:
                await response.aread()
                raise _error(response)
            yield response
        except httpx.HTTPError as exc:  # the connection broke while the answer was arriving
            raise self._unreachable("GET", path, exc) from exc
        finally:
            await response.aclose()

    def _unreachable(self, method: str, path: str, exc: httpx.HTTPError) -> DockerError:
        return DockerError(0, f"{method} {path} through {self.socket_path}: {exc!r}")


class _LogFrames:
    """Docker's multiplexed stream, the log stream of a container without a TTY, as lines.

    Each frame is an 8-byte header (the stream: 1 stdout, 2 stderr, 3 the daemon's own errors;
    three zero bytes; the payload's size as a big-endian uint32) and then the payload. Frames
    don't follow lines: one frame may hold part of a line or many lines, and the socket's chunks
    split frames and headers anywhere.
    """

    def __init__(self) -> None:
        self._header = bytearray()
        self._stream = 0
        self._remaining = 0  # payload bytes of the current frame still to come
        self._partial: dict[int, bytearray] = {}  # per stream, a line begun but not ended

    def feed(self, data: bytes) -> list[tuple[int, bytes]]:
        """The lines that ``data`` completes, as (stream, line without its line break)."""
        lines: list[tuple[int, bytes]] = []
        view = memoryview(data)
        while view:
            if self._remaining:
                payload = view[: self._remaining]
                view = view[len(payload) :]
                self._remaining -= len(payload)
                self._add(self._stream, payload, lines)
                continue
            missing = 8 - len(self._header)
            self._header += view[:missing]
            view = view[missing:]
            if len(self._header) == 8:
                if self._header[0] > SYSTEM_ERROR_STREAM:
                    raise DockerError(
                        0, f"not a multiplexed log stream (frame header {self._header.hex()})"
                    )
                self._stream = self._header[0]
                self._remaining = int.from_bytes(self._header[4:], "big")
                self._header.clear()
        return lines

    def close(self) -> list[tuple[int, bytes]]:
        """The last line of each stream, when the output ended without a line break."""
        last = [(stream, bytes(rest)) for stream, rest in sorted(self._partial.items()) if rest]
        self._partial.clear()
        return last

    def _add(self, stream: int, data: memoryview, lines: list[tuple[int, bytes]]) -> None:
        partial = self._partial.setdefault(stream, bytearray())
        partial += data
        while True:
            end = partial.find(b"\n", 0, MAX_LINE_BYTES + 1)
            if end >= 0:
                lines.append((stream, bytes(partial[:end])))
                del partial[: end + 1]
            elif len(partial) > MAX_LINE_BYTES:  # a long line: send what fits, keep the rest
                cut = _character_boundary(partial, MAX_LINE_BYTES)
                lines.append((stream, bytes(partial[:cut])))
                del partial[:cut]
            else:
                return


def _character_boundary(data: bytearray, limit: int) -> int:
    """Where to cut ``data`` (longer than ``limit``) at most ``limit`` bytes in, so that a UTF-8
    character isn't split between two pieces. Invalid UTF-8 is cut at ``limit``."""
    for cut in range(limit, limit - 4, -1):  # a character has at most 3 continuation bytes
        if data[cut] & 0xC0 != 0x80:
            return cut
    return limit


def _log_lines(container_id: str, lines: list[tuple[int, bytes]]) -> list[LogLine]:
    result: list[LogLine] = []
    for stream, raw in lines:
        text = raw.decode("utf-8", errors="replace")
        if stream == SYSTEM_ERROR_STREAM:  # Docker carries on after it
            logger.warning("Docker, reading the logs of %s: %s", container_id, text)
        else:
            result.append(LogLine("stderr" if stream == 2 else "stdout", text))
    return result


def _ref(container_id: str) -> str:
    """A container id or name as one path segment, so that it can't name another endpoint."""
    return quote(container_id, safe="")


def _error(response: httpx.Response) -> DockerError:
    """The error for a refused call. Docker explains it in a JSON ``message``; the socket
    proxy's refusals (403 for a path or bind mount, 405 for a method) are plain text."""
    try:
        answer = response.json()
    except ValueError:
        answer = None
    message = answer.get("message") if isinstance(answer, dict) else None
    if not isinstance(message, str) or not message:
        message = response.text.strip()[:500] or response.reason_phrase
    status = response.status_code
    if status == 404:
        return NotFound(status, message)
    if status == 409:
        return Conflict(status, message)
    return DockerError(status, message)


def _json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise DockerError(
            response.status_code, f"unreadable answer {response.text!r:.200}"
        ) from exc


def _json_object(response: httpx.Response) -> dict[str, Any]:
    answer = _json(response)
    if not isinstance(answer, dict):
        raise DockerError(response.status_code, f"unexpected answer {answer!r:.200}")
    return answer


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _labels(value: object) -> dict[str, str]:
    """A container's labels; Docker sends null for none."""
    return {str(key): str(item) for key, item in value.items()} if isinstance(value, dict) else {}


def _summary(item: dict[str, Any]) -> ContainerSummary:
    names = item.get("Names")
    name = names[0] if isinstance(names, list) and names and isinstance(names[0], str) else ""
    return ContainerSummary(
        id=str(item.get("Id") or ""),
        name=name.removeprefix("/"),
        labels=_labels(item.get("Labels")),
        state=str(item.get("State") or ""),
    )


def _time(value: object) -> datetime | None:
    """A time from Docker, in UTC. Docker's RFC 3339 times have nanoseconds, of which Python
    keeps the microseconds, and the year 1 for a time that hasn't happened yet."""
    if not isinstance(value, str) or value.startswith("0001-01-01"):
        return None
    match = _TIME.fullmatch(value)
    if match is None:
        return None
    seconds, fraction, zone = match.groups()
    micros = (fraction or "")[:6].ljust(6, "0")
    offset = "+00:00" if zone == "Z" else zone
    return datetime.fromisoformat(f"{seconds}.{micros}{offset}").astimezone(UTC)

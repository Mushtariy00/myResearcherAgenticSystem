"""The Docker client against canned Engine API answers: what each call sends, how the log
stream's frames become lines, the archive's cap, and how failures become DockerErrors."""

import asyncio
import json
import logging
import struct
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from agentic_executor.docker import DockerClient
from agentic_executor.ports import (
    Conflict,
    ContainerState,
    ContainerSummary,
    DockerError,
    LogLine,
    NotFound,
)

KIB = 1024
STDOUT, STDERR, SYSTEM_ERROR = 1, 2, 3


class FakeDocker:
    """Answers each request with the next queued answer, and keeps the requests."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.answers: list[httpx.Response | Exception] = []

    def answer(self, *answers: httpx.Response | Exception) -> None:
        self.answers.extend(answers)

    async def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]


@pytest.fixture
def docker() -> FakeDocker:
    return FakeDocker()


@pytest.fixture
async def client(docker: FakeDocker) -> AsyncIterator[DockerClient]:
    client = DockerClient(
        Path("/run/arp/docker.sock"), transport=httpx.MockTransport(docker.handler)
    )
    yield client
    await client.aclose()


def call(request: httpx.Request) -> tuple[str, str, dict[str, str]]:
    return request.method, request.url.path, dict(request.url.params)


def read_timeout(request: httpx.Request) -> float | None:
    return request.extensions["timeout"]["read"]


def body(*chunks: bytes, then: Exception | None = None) -> AsyncIterator[bytes]:
    """A response body that arrives in these chunks, then breaks with ``then`` if given."""

    async def stream() -> AsyncIterator[bytes]:
        for chunk in chunks:
            yield chunk
        if then is not None:
            raise then

    return stream()


def frame(stream: int, payload: bytes) -> bytes:
    """One frame of Docker's multiplexed stream: stream, three zero bytes, size, payload."""
    return struct.pack(">BxxxI", stream, len(payload)) + payload


def split(data: bytes, size: int) -> list[bytes]:
    return [data[start : start + size] for start in range(0, len(data), size)]


async def follow(
    client: DockerClient, docker: FakeDocker, *chunks: bytes, then: Exception | None = None
) -> list[LogLine]:
    docker.answer(
        httpx.Response(
            200,
            content=body(*chunks, then=then),
            headers={"Content-Type": "application/vnd.docker.multiplexed-stream"},
        )
    )
    return [line async for line in client.follow_logs("c0ffee")]


# create, start, inspect, list


async def test_create_posts_the_spec_under_the_name_and_returns_the_id(
    client: DockerClient, docker: FakeDocker
) -> None:
    spec: dict[str, Any] = {
        "Image": "arp-sandbox-pytorch:dev",
        "Labels": {"arp.job": "j1"},
        "HostConfig": {"NetworkMode": "none", "ReadonlyRootfs": True},
    }
    docker.answer(httpx.Response(201, json={"Id": "c0ffee", "Warnings": []}))
    assert await client.create_container("arp-job-j1", spec) == "c0ffee"
    assert call(docker.last) == ("POST", "/v1.47/containers/create", {"name": "arp-job-j1"})
    assert docker.last.headers["content-type"] == "application/json"
    assert json.loads(docker.last.content) == spec
    assert read_timeout(docker.last) == 30.0


async def test_create_logs_the_warnings_docker_returns(
    client: DockerClient, docker: FakeDocker, caplog: pytest.LogCaptureFixture
) -> None:
    warning = "Your kernel does not support swap limit capabilities. Limitation discarded."
    docker.answer(httpx.Response(201, json={"Id": "c0ffee", "Warnings": [warning]}))
    with caplog.at_level(logging.WARNING, logger="agentic_executor.docker"):
        await client.create_container("arp-job-j1", {})
    assert caplog.messages == [f"Docker, creating arp-job-j1: {warning}"]


@pytest.mark.parametrize(
    ("status", "message", "error"),
    [
        (409, 'Conflict. The container name "/arp-job-j1" is already in use', Conflict),
        (404, "No such image: arp-sandbox-pytorch:dev", NotFound),
        (400, "invalid mount config for type bind", DockerError),
        (500, "failed to create the container", DockerError),
    ],
)
async def test_create_errors_carry_dockers_message(
    client: DockerClient, docker: FakeDocker, status: int, message: str, error: type[DockerError]
) -> None:
    docker.answer(httpx.Response(status, json={"message": message}))
    with pytest.raises(DockerError) as raised:
        await client.create_container("arp-job-j1", {})
    assert type(raised.value) is error
    assert (raised.value.status, raised.value.message) == (status, message)


@pytest.mark.parametrize("status", [204, 304])  # 304: it is running already
async def test_start_succeeds_also_for_a_running_container(
    client: DockerClient, docker: FakeDocker, status: int
) -> None:
    docker.answer(httpx.Response(status))
    await client.start_container("c0ffee")
    assert call(docker.last) == ("POST", "/v1.47/containers/c0ffee/start", {})


async def test_start_of_a_missing_container_raises_not_found(
    client: DockerClient, docker: FakeDocker
) -> None:
    docker.answer(httpx.Response(404, json={"message": "No such container: c0ffee"}))
    with pytest.raises(NotFound, match="No such container"):
        await client.start_container("c0ffee")


IMAGE_ID = "sha256:" + "ab" * 32


def inspect_answer(state: dict[str, Any], labels: dict[str, str] | None) -> dict[str, Any]:
    """The part of GET /containers/{id}/json the client reads, plus some it ignores."""
    return {
        "Id": "c0ffee",
        "Name": "/arp-job-j1",
        "Image": IMAGE_ID,
        "State": state,
        "Config": {"Image": "arp-sandbox-pytorch:dev", "Labels": labels},
        "HostConfig": {"NetworkMode": "none"},
    }


async def test_inspect_of_a_running_container(client: DockerClient, docker: FakeDocker) -> None:
    labels = {"arp.job": "j1", "arp.kind": "train", "arp.run": "r1"}
    state = {
        "Status": "running",
        "Running": True,
        "OOMKilled": False,
        "ExitCode": 0,
        "StartedAt": "2026-10-30T12:34:56.123456789Z",  # nanoseconds
        "FinishedAt": "0001-01-01T00:00:00Z",  # Docker's zero time: not yet
    }
    docker.answer(httpx.Response(200, json=inspect_answer(state, labels)))
    assert await client.inspect_container("c0ffee") == ContainerState(
        id="c0ffee",
        name="arp-job-j1",
        image_id=IMAGE_ID,
        labels=labels,
        state="running",
        exit_code=None,  # not the 0 Docker reports while it runs
        oom_killed=False,
        started_at=datetime(2026, 10, 30, 12, 34, 56, 123456, tzinfo=UTC),
        finished_at=None,
    )
    assert call(docker.last) == ("GET", "/v1.47/containers/c0ffee/json", {})


async def test_inspect_of_a_container_the_memory_limit_killed(
    client: DockerClient, docker: FakeDocker
) -> None:
    state = {
        "Status": "exited",
        "OOMKilled": True,
        "ExitCode": 137,
        "StartedAt": "2026-10-30T12:34:56Z",
        "FinishedAt": "2026-10-30T22:00:00.5+09:00",
    }
    docker.answer(httpx.Response(200, json=inspect_answer(state, {"arp.job": "j1"})))
    container = await client.inspect_container("arp-job-j1")
    assert (container.state, container.exit_code, container.oom_killed) == ("exited", 137, True)
    assert container.started_at == datetime(2026, 10, 30, 12, 34, 56, tzinfo=UTC)
    assert container.finished_at == datetime(2026, 10, 30, 13, 0, 0, 500000, tzinfo=UTC)


async def test_inspect_of_a_container_never_started(
    client: DockerClient, docker: FakeDocker
) -> None:
    state = {
        "Status": "created",
        "OOMKilled": False,
        "ExitCode": 0,
        "StartedAt": "0001-01-01T00:00:00Z",
        "FinishedAt": "0001-01-01T00:00:00Z",
    }
    docker.answer(httpx.Response(200, json=inspect_answer(state, None)))  # no labels: null
    container = await client.inspect_container("c0ffee")
    assert container.labels == {}
    assert (container.state, container.exit_code) == ("created", None)
    assert container.started_at is None
    assert container.finished_at is None


async def test_inspect_of_a_missing_container_raises_not_found(
    client: DockerClient, docker: FakeDocker
) -> None:
    docker.answer(httpx.Response(404, json={"message": "No such container: c0ffee"}))
    with pytest.raises(NotFound):
        await client.inspect_container("c0ffee")


async def test_list_filters_by_the_label_and_includes_stopped_containers(
    client: DockerClient, docker: FakeDocker
) -> None:
    docker.answer(
        httpx.Response(
            200,
            json=[
                {
                    "Id": "a1",
                    "Names": ["/arp-job-j1"],
                    "Labels": {"arp.job": "j1"},
                    "State": "running",
                    "Status": "Up 2 minutes",
                },
                {"Id": "b2", "Names": ["/arp-job-j2"], "Labels": None, "State": "exited"},
            ],
        )
    )
    assert await client.list_containers("arp.job") == [
        ContainerSummary(id="a1", name="arp-job-j1", labels={"arp.job": "j1"}, state="running"),
        ContainerSummary(id="b2", name="arp-job-j2", labels={}, state="exited"),
    ]
    method, path, params = call(docker.last)
    assert (method, path) == ("GET", "/v1.47/containers/json")
    assert params["all"] == "1"
    assert json.loads(params["filters"]) == {"label": ["arp.job"]}


# wait, stop, kill, remove


async def test_wait_returns_the_exit_code_and_has_no_read_timeout(
    client: DockerClient, docker: FakeDocker
) -> None:
    docker.answer(httpx.Response(200, json={"StatusCode": 143, "Error": None}))
    assert await client.wait_container("c0ffee") == 143
    assert call(docker.last) == (
        "POST",
        "/v1.47/containers/c0ffee/wait",
        {"condition": "not-running"},
    )
    assert read_timeout(docker.last) is None


@pytest.mark.parametrize("status", [204, 304, 404])  # 304: stopped already; 404: gone
async def test_stop_sends_the_grace_period_and_waits_longer_than_it(
    client: DockerClient, docker: FakeDocker, status: int
) -> None:
    docker.answer(httpx.Response(status))
    await client.stop_container("c0ffee", grace_seconds=2)
    assert call(docker.last) == ("POST", "/v1.47/containers/c0ffee/stop", {"t": "2"})
    timeout = read_timeout(docker.last)
    assert timeout is not None and timeout > 2 + 10


async def test_stop_raises_dockers_other_errors(client: DockerClient, docker: FakeDocker) -> None:
    docker.answer(httpx.Response(500, json={"message": "cannot stop container: tried to kill"}))
    with pytest.raises(DockerError) as raised:
        await client.stop_container("c0ffee", grace_seconds=2)
    assert raised.value.status == 500


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(204),
        httpx.Response(404, json={"message": "No such container: c0ffee"}),
        httpx.Response(
            409, json={"message": "cannot kill container: c0ffee: container c0ffee is not running"}
        ),
    ],
)
async def test_kill_of_a_stopped_or_missing_container_is_not_an_error(
    client: DockerClient, docker: FakeDocker, answer: httpx.Response
) -> None:
    docker.answer(answer)
    await client.kill_container("c0ffee")
    assert call(docker.last) == ("POST", "/v1.47/containers/c0ffee/kill", {})


async def test_kill_raises_any_other_conflict(client: DockerClient, docker: FakeDocker) -> None:
    docker.answer(httpx.Response(409, json={"message": "container c0ffee is restarting"}))
    with pytest.raises(Conflict):
        await client.kill_container("c0ffee")


@pytest.mark.parametrize("status", [204, 404])
async def test_remove_forces_and_takes_the_anonymous_volumes(
    client: DockerClient, docker: FakeDocker, status: int
) -> None:
    docker.answer(httpx.Response(status))
    await client.remove_container("c0ffee")
    assert call(docker.last) == ("DELETE", "/v1.47/containers/c0ffee", {"force": "1", "v": "1"})


async def test_remove_raises_a_conflict(client: DockerClient, docker: FakeDocker) -> None:
    docker.answer(
        httpx.Response(409, json={"message": "removal of container c0ffee is already in progress"})
    )
    with pytest.raises(Conflict, match="already in progress"):
        await client.remove_container("c0ffee")


# download_archive

TAR = bytes(range(256)) * 400  # 100 KiB, the stand-in for a tar


async def test_the_archive_is_streamed_to_the_file(
    client: DockerClient, docker: FakeDocker, tmp_path: Path
) -> None:
    docker.answer(httpx.Response(200, content=body(*split(TAR, 4 * KIB))))
    destination = tmp_path / "out.tar"
    size = await client.download_archive(
        "c0ffee", "/workspace/out", destination, max_bytes=len(TAR)
    )
    assert size == len(TAR)
    assert destination.read_bytes() == TAR
    assert call(docker.last) == (
        "GET",
        "/v1.47/containers/c0ffee/archive",
        {"path": "/workspace/out"},
    )


async def test_an_archive_over_the_cap_is_413_and_leaves_no_file(
    client: DockerClient, docker: FakeDocker, tmp_path: Path
) -> None:
    docker.answer(httpx.Response(200, content=body(*split(TAR, 4 * KIB))))
    destination = tmp_path / "out.tar"
    with pytest.raises(DockerError) as raised:
        await client.download_archive(
            "c0ffee", "/workspace/out", destination, max_bytes=len(TAR) - 1
        )
    assert raised.value.status == 413
    assert not destination.exists()


async def test_an_archive_cut_off_midway_is_status_0_and_leaves_no_file(
    client: DockerClient, docker: FakeDocker, tmp_path: Path
) -> None:
    docker.answer(
        httpx.Response(200, content=body(TAR[:5000], then=httpx.ReadError("connection reset")))
    )
    destination = tmp_path / "out.tar"
    with pytest.raises(DockerError) as raised:
        await client.download_archive("c0ffee", "/workspace/out", destination, max_bytes=len(TAR))
    assert raised.value.status == 0
    assert not destination.exists()


async def test_a_missing_folder_raises_not_found_and_writes_nothing(
    client: DockerClient, docker: FakeDocker, tmp_path: Path
) -> None:
    message = "Could not find the file /workspace/out in container c0ffee"
    docker.answer(httpx.Response(404, json={"message": message}))
    destination = tmp_path / "out.tar"
    with pytest.raises(NotFound, match="Could not find"):
        await client.download_archive("c0ffee", "/workspace/out", destination, max_bytes=100)
    assert not destination.exists()


# follow_logs: Docker's multiplexed stream

MIXED = b"".join(
    [
        frame(STDOUT, b"epoch 1\nepo"),
        frame(STDERR, b"warning: slow step\n"),
        frame(STDOUT, b""),  # an empty frame
        frame(STDOUT, b"ch 2\n"),
        frame(STDERR, b"two\nlines\n"),
    ]
)
MIXED_LINES = [
    LogLine("stdout", "epoch 1"),
    LogLine("stderr", "warning: slow step"),
    LogLine("stdout", "epoch 2"),  # its two halves came in separate frames
    LogLine("stderr", "two"),
    LogLine("stderr", "lines"),
]


async def test_follow_asks_for_both_streams_and_has_no_read_timeout(
    client: DockerClient, docker: FakeDocker
) -> None:
    assert await follow(client, docker, MIXED) == MIXED_LINES
    assert call(docker.last) == (
        "GET",
        "/v1.47/containers/c0ffee/logs",
        {"follow": "1", "stdout": "1", "stderr": "1"},
    )
    assert read_timeout(docker.last) is None


@pytest.mark.parametrize("size", [1, 2, 3, 5, 7, 8, 9, 13, 21, 64])
async def test_frames_and_headers_split_anywhere_give_the_same_lines(
    client: DockerClient, docker: FakeDocker, size: int
) -> None:
    assert await follow(client, docker, *split(MIXED, size)) == MIXED_LINES


async def test_a_header_split_across_two_chunks(client: DockerClient, docker: FakeDocker) -> None:
    data = frame(STDERR, b"err\n") + frame(STDOUT, b"out\n")
    second_header = len(frame(STDERR, b"err\n")) + 3
    lines = await follow(client, docker, data[:second_header], data[second_header:])
    assert lines == [LogLine("stderr", "err"), LogLine("stdout", "out")]


async def test_empty_lines_are_kept(client: DockerClient, docker: FakeDocker) -> None:
    lines = await follow(client, docker, frame(STDOUT, b"\n\nlast\n"))
    assert [line.text for line in lines] == ["", "", "last"]


async def test_invalid_utf8_is_replaced(client: DockerClient, docker: FakeDocker) -> None:
    lines = await follow(client, docker, frame(STDOUT, b"loss \xff\xfe nan\n"))
    assert lines == [LogLine("stdout", "loss �� nan")]


async def test_unterminated_last_lines_arrive_when_the_stream_ends(
    client: DockerClient, docker: FakeDocker
) -> None:
    lines = await follow(client, docker, frame(STDERR, b"Traceback"), frame(STDOUT, b"ARP-DONE"))
    assert lines == [LogLine("stdout", "ARP-DONE"), LogLine("stderr", "Traceback")]


async def test_a_frame_cut_short_still_gives_its_text(
    client: DockerClient, docker: FakeDocker
) -> None:
    lines = await follow(client, docker, frame(STDOUT, b"first\nsecond")[:-3])
    assert lines == [LogLine("stdout", "first"), LogLine("stdout", "sec")]


@pytest.mark.parametrize(
    ("length", "pieces"),
    [
        (64 * KIB, [64 * KIB]),
        (64 * KIB + 1, [64 * KIB, 1]),
        (150 * KIB, [64 * KIB, 64 * KIB, 22 * KIB]),
    ],
)
@pytest.mark.parametrize("chunk", [1000, 1024 * KIB])
async def test_a_long_line_comes_in_pieces_of_at_most_64_kib(
    client: DockerClient, docker: FakeDocker, length: int, pieces: list[int], chunk: int
) -> None:
    data = frame(STDOUT, b"x" * length + b"\nafter\n")
    lines = await follow(client, docker, *split(data, chunk))
    assert [len(line.text) for line in lines] == [*pieces, len("after")]
    assert {line.stream for line in lines} == {"stdout"}


async def test_a_long_line_never_ended_still_comes_in_pieces(
    client: DockerClient, docker: FakeDocker
) -> None:
    lines = await follow(client, docker, *split(frame(STDERR, b"y" * (100 * KIB)), 4 * KIB))
    assert [len(line.text) for line in lines] == [64 * KIB, 36 * KIB]


async def test_a_long_line_is_not_cut_inside_a_character(
    client: DockerClient, docker: FakeDocker
) -> None:
    text = "x" + "é" * 40_000  # 2-byte characters, so 64 KiB falls inside one
    lines = await follow(client, docker, frame(STDOUT, text.encode() + b"\n"))
    assert len(lines) == 2
    assert "�" not in lines[0].text + lines[1].text
    assert lines[0].text + lines[1].text == text
    assert all(len(line.text.encode()) <= 64 * KIB for line in lines)


async def test_dockers_own_errors_are_logged_not_yielded(
    client: DockerClient, docker: FakeDocker, caplog: pytest.LogCaptureFixture
) -> None:
    data = (
        frame(STDOUT, b"before\n")
        + frame(SYSTEM_ERROR, b"Error grabbing logs: unexpected EOF\n")
        + frame(STDOUT, b"after\n")
    )
    with caplog.at_level(logging.WARNING, logger="agentic_executor.docker"):
        lines = await follow(client, docker, data)
    assert lines == [LogLine("stdout", "before"), LogLine("stdout", "after")]
    assert caplog.messages == [
        "Docker, reading the logs of c0ffee: Error grabbing logs: unexpected EOF"
    ]


async def test_a_stream_that_is_not_multiplexed_is_an_error(
    client: DockerClient, docker: FakeDocker
) -> None:
    with pytest.raises(DockerError, match="not a multiplexed log stream") as raised:
        await follow(client, docker, b"hello from a TTY\n")  # raw output, no frames
    assert raised.value.status == 0


async def test_logs_of_a_missing_container_raise_not_found(
    client: DockerClient, docker: FakeDocker
) -> None:
    docker.answer(httpx.Response(404, json={"message": "No such container: c0ffee"}))
    with pytest.raises(NotFound):
        async for _ in client.follow_logs("c0ffee"):
            pass


async def test_a_log_stream_that_breaks_gives_its_lines_then_status_0(
    client: DockerClient, docker: FakeDocker
) -> None:
    docker.answer(
        httpx.Response(
            200,
            content=body(
                frame(STDOUT, b"epoch 1\n"), then=httpx.RemoteProtocolError("peer closed")
            ),
        )
    )
    lines: list[LogLine] = []
    with pytest.raises(DockerError) as raised:
        async for line in client.follow_logs("c0ffee"):
            lines.append(line)
    assert lines == [LogLine("stdout", "epoch 1")]
    assert raised.value.status == 0


# errors and the transport


@pytest.mark.parametrize(("status", "text"), [(403, "Forbidden\n"), (405, "Method Not Allowed\n")])
async def test_a_socket_proxy_refusal_is_a_docker_error_with_its_text(
    client: DockerClient, docker: FakeDocker, status: int, text: str
) -> None:
    docker.answer(httpx.Response(status, text=text))
    with pytest.raises(DockerError) as raised:
        await client.list_containers("arp.job")
    assert type(raised.value) is DockerError
    assert (raised.value.status, raised.value.message) == (status, text.strip())


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectError("[Errno 111] Connection refused"),
        httpx.ConnectTimeout("timed out"),
        httpx.ReadTimeout("timed out"),
        httpx.RemoteProtocolError("Server disconnected without sending a response."),
    ],
)
async def test_transport_failures_are_status_0(
    client: DockerClient, docker: FakeDocker, failure: Exception
) -> None:
    docker.answer(failure)
    with pytest.raises(DockerError) as raised:
        await client.inspect_container("c0ffee")
    assert type(raised.value) is DockerError
    assert raised.value.status == 0
    assert "/run/arp/docker.sock" in raised.value.message


async def test_a_missing_socket_is_status_0(tmp_path: Path) -> None:
    client = DockerClient(tmp_path / "missing.sock")
    try:
        with pytest.raises(DockerError) as raised:
            await client.list_containers("arp.job")
    finally:
        await client.aclose()
    assert raised.value.status == 0


async def test_calls_go_over_the_unix_socket_to_the_versioned_api(tmp_path: Path) -> None:
    heads: list[bytes] = []

    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        heads.append(await reader.readuntil(b"\r\n\r\n"))
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n")
        writer.write(b"Content-Length: 2\r\nConnection: close\r\n\r\n[]")
        await writer.drain()
        writer.close()

    socket_path = tmp_path / "d.sock"
    server = await asyncio.start_unix_server(serve, path=str(socket_path))
    async with server:
        client = DockerClient(socket_path, api_version="v1.47")
        try:
            assert await client.list_containers("arp.job") == []
        finally:
            await client.aclose()
    request_line, *headers = heads[0].decode().split("\r\n")
    assert request_line.startswith("GET /v1.47/containers/json?all=1&filters=")
    assert "Host: docker" in headers


async def test_a_container_reference_stays_one_path_segment(
    client: DockerClient, docker: FakeDocker
) -> None:
    docker.answer(httpx.Response(404, json={"message": "No such container"}))
    with pytest.raises(NotFound):
        await client.inspect_container("../../images/x")
    # Unquoted, the dots would have taken the request to /images/x/json.
    assert docker.last.url.raw_path == b"/v1.47/containers/..%2F..%2Fimages%2Fx/json"

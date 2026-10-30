"""What the executor needs from Docker and from the GPU, as protocols.

The executor's logic (agentic_executor.executor) is tested against fakes of these
(tests/executor_testkit.py). The real clients (agentic_executor.docker, agentic_executor.gpu) stay
thin and are tested against canned HTTP responses and nvidia-smi output.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol


class DockerError(Exception):
    """A Docker API call failed. ``status`` is the HTTP status (0: Docker could not be reached)."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"Docker API error {status}: {message}")
        self.status = status
        self.message = message


class NotFound(DockerError):
    """404: no such container (or, on create, no such image)."""


class Conflict(DockerError):
    """409: on create, the container name is taken."""


@dataclass(frozen=True)
class ContainerSummary:
    """A container in a listing (GET /containers/json?all=1)."""

    id: str
    name: str  # without Docker's leading "/"
    labels: dict[str, str]
    state: str  # created | running | paused | restarting | removing | exited | dead


@dataclass(frozen=True)
class ContainerState:
    """What the executor reads from GET /containers/{id}/json."""

    id: str
    name: str  # without Docker's leading "/"
    image_id: str  # "sha256:…": the image the container was created from
    labels: dict[str, str]
    state: str  # as in ContainerSummary
    exit_code: int | None  # None until the container has stopped
    oom_killed: bool  # the memory limit killed a process in it
    started_at: datetime | None  # None before it first started
    finished_at: datetime | None  # None until it stopped


@dataclass(frozen=True)
class LogLine:
    """One line of a container's output, without its line break; invalid UTF-8 is replaced."""

    stream: str  # "stdout" or "stderr"
    text: str


class DockerApi(Protocol):
    """The Docker Engine API calls the executor makes. All of them are on /containers: the socket
    proxy allows nothing else."""

    async def create_container(self, name: str, spec: dict[str, Any]) -> str:
        """Create a container from ``spec`` (the POST /containers/create body) and return its id.
        Raises Conflict when ``name`` is taken and NotFound when the image is missing."""
        ...

    async def start_container(self, container_id: str) -> None:
        """Start it. A container that is running already is not an error."""
        ...

    async def inspect_container(self, container_id: str) -> ContainerState:
        """Raises NotFound for an unknown id or name."""
        ...

    async def list_containers(self, label: str) -> list[ContainerSummary]:
        """Every container, running or not, that carries the label key ``label``."""
        ...

    def follow_logs(self, container_id: str) -> AsyncIterator[LogLine]:
        """The container's stdout and stderr from its start, line by line, following new output
        until the container stops. A line longer than 64 KiB arrives in pieces of 64 KiB at most."""
        ...

    async def stop_container(self, container_id: str, *, grace_seconds: int) -> None:
        """SIGTERM, then SIGKILL after ``grace_seconds``; returns once it has stopped. A stopped
        or missing container is not an error."""
        ...

    async def kill_container(self, container_id: str) -> None:
        """SIGKILL now. A stopped or missing container is not an error."""
        ...

    async def wait_container(self, container_id: str) -> int:
        """Block until the container stops and return its exit code."""
        ...

    async def remove_container(self, container_id: str) -> None:
        """Remove it, running or not, with its anonymous volumes (the job's output). A missing
        container is not an error."""
        ...

    async def download_archive(
        self, container_id: str, path: str, destination: Path, *, max_bytes: int
    ) -> int:
        """Write the tar of ``path`` in the container (GET /containers/{id}/archive) to
        ``destination`` and return its size. Raises DockerError with status 413 once the tar
        grows past ``max_bytes``, after removing the partial file."""
        ...

    async def aclose(self) -> None: ...


@dataclass(frozen=True)
class GpuSample:
    """One nvidia-smi reading of the jobs' GPU. A field nvidia-smi reports as [N/A] is None."""

    index: int
    name: str
    memory_total_mb: int
    memory_used_mb: int
    utilization_percent: int | None
    temperature_c: int | None
    power_draw_w: float | None
    power_limit_w: float | None
    fan_percent: int | None
    sampled_at: datetime

    @property
    def memory_free_mb(self) -> int:
        return max(self.memory_total_mb - self.memory_used_mb, 0)


class GpuProbe(Protocol):
    async def sample(self) -> GpuSample | None:
        """The GPU's readings now, or None when nvidia-smi is missing, fails or hangs."""
        ...

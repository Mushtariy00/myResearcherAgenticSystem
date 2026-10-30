"""The Docker Engine API client the executor uses, over the socket proxy's Unix socket."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from agentic_executor.ports import ContainerState, ContainerSummary, LogLine


class DockerClient:
    """agentic_executor.ports.DockerApi over ``socket_path`` (httpx, API ``api_version``)."""

    def __init__(self, socket_path: Path, *, api_version: str = "v1.47") -> None:
        self.socket_path = socket_path
        self.api_version = api_version

    async def create_container(self, name: str, spec: dict[str, Any]) -> str:
        raise NotImplementedError

    async def start_container(self, container_id: str) -> None:
        raise NotImplementedError

    async def inspect_container(self, container_id: str) -> ContainerState:
        raise NotImplementedError

    async def list_containers(self, label: str) -> list[ContainerSummary]:
        raise NotImplementedError

    async def follow_logs(self, container_id: str) -> AsyncIterator[LogLine]:
        raise NotImplementedError
        yield  # pragma: no cover

    async def stop_container(self, container_id: str, *, grace_seconds: int) -> None:
        raise NotImplementedError

    async def kill_container(self, container_id: str) -> None:
        raise NotImplementedError

    async def wait_container(self, container_id: str) -> int:
        raise NotImplementedError

    async def remove_container(self, container_id: str) -> None:
        raise NotImplementedError

    async def download_archive(
        self, container_id: str, path: str, destination: Path, *, max_bytes: int
    ) -> int:
        raise NotImplementedError

    async def aclose(self) -> None:
        raise NotImplementedError

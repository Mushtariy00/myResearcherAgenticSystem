"""Fakes and helpers for executor tests: a Docker API that runs scripted containers in memory, a
GPU with a settable reading, a Valkey that accepts publishes, and helpers that create jobs and
wait for them."""

import asyncio
import contextlib
import hashlib
import io
import json
import secrets
import tarfile
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Collection
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.contracts import EventType
from agentic_core.enums import GpuJobKind, GpuJobStatus
from agentic_core.gpu_jobs import DONE_PREFIX, METRIC_PREFIX
from agentic_db.lab_settings import EXECUTOR_STATUS_KEY
from agentic_db.models import Dataset, GpuJob, Project, Run, RunEvent, Setting, StageRun
from agentic_executor import executor as executor_module
from agentic_executor.executor import Executor
from agentic_executor.ports import (
    Conflict,
    ContainerState,
    ContainerSummary,
    DockerError,
    GpuSample,
    LogLine,
    NotFound,
)
from agentic_executor.settings import ExecutorSettings
from agentic_executor.template import container_name

Factory = async_sessionmaker[AsyncSession]
IMAGE = "arp-sandbox-pytorch:test"
GPU_NAME = "NVIDIA GeForce GTX 1060 6GB"
SIGTERM_EXIT = 128 + 15  # harness.job stopped during training
SIGKILL_EXIT = 128 + 9

MODEL_SOURCE = '''"""A tiny depth model."""

import torch
from torch import nn


class Model(nn.Module):
    def __init__(self, width: int = 8) -> None:
        super().__init__()
        self.head = nn.Conv2d(3, 1, 3, padding=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(x)
'''

# A step of a container's script: a line to print (stdout for a str), a pause in seconds, or an
# event to wait for.
type ScriptStep = str | LogLine | float | asyncio.Event


@dataclass
class Script:
    """What a fake container does once started. It prints ``steps``, then ARP-DONE with
    ``exit_code`` (none when it is None). Then it holds until stopped, as harness.job does, or
    with ``hold`` False exits by itself with ``end_exit_code``."""

    steps: list[ScriptStep] = field(default_factory=list)
    exit_code: int | None = 0
    hold: bool = True
    end_exit_code: int = 0
    oom_killed: bool = False
    outputs: dict[str, bytes] = field(default_factory=dict)  # its output folder, while it runs


def image_id(image: str) -> str:
    return f"sha256:{hashlib.sha256(image.encode()).hexdigest()}"


class FakeContainer:
    def __init__(self, container_id: str, name: str, spec: dict[str, Any], script: Script) -> None:
        self.id = container_id
        self.name = name
        self.spec = spec
        self.labels: dict[str, str] = dict(spec.get("Labels") or {})
        self.image_id = image_id(str(spec.get("Image")))
        self.script = script
        self.state = "created"
        self.lines: list[LogLine] = []
        self.exit_code: int | None = None
        self.started_at: datetime | None = None
        self.finished_at: datetime | None = None
        self.done_printed = False
        self.ended = asyncio.Event()
        self.changed = asyncio.Event()  # replaced on every change; followers wait on it
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self.state != "created":
            return
        self.state = "running"
        self.started_at = datetime.now(UTC)
        self._task = asyncio.create_task(self._run())

    def print(self, line: LogLine) -> None:
        self.lines.append(line)
        self._notify()

    def end(self, exit_code: int) -> None:
        if self.ended.is_set():
            return
        self.state = "exited"
        self.exit_code = exit_code
        self.finished_at = datetime.now(UTC)
        self.ended.set()
        self._notify()
        if self._task is not None and self._task is not asyncio.current_task():
            self._task.cancel()

    def inspect(self) -> ContainerState:
        return ContainerState(
            id=self.id,
            name=self.name,
            image_id=self.image_id,
            labels=dict(self.labels),
            state=self.state,
            exit_code=self.exit_code,
            oom_killed=self.script.oom_killed,
            started_at=self.started_at,
            finished_at=self.finished_at,
        )

    def _notify(self) -> None:
        self.changed.set()
        self.changed = asyncio.Event()

    async def _run(self) -> None:
        script = self.script
        for step in script.steps:
            if isinstance(step, asyncio.Event):
                await step.wait()
            elif isinstance(step, LogLine):
                self.print(step)
            elif isinstance(step, str):
                self.print(LogLine("stdout", step))
            else:
                await asyncio.sleep(step)
        if script.exit_code is not None:
            self.print(LogLine("stdout", done_line(script.exit_code)))
            self.done_printed = True
        if script.hold:
            await self.ended.wait()
        else:
            self.end(script.end_exit_code)


class FakeDocker:
    """agentic_executor.ports.DockerApi in memory. It behaves like Docker with the job template's
    tmpfs output volume: the archive API reads a container's outputs only while it runs, and a
    stopped container's output folder is empty. Containers are found by id or by name."""

    def __init__(self, images: Collection[str] = (IMAGE,)) -> None:
        self.images = set(images)
        self.containers: dict[str, FakeContainer] = {}  # by id
        self.scripts: dict[str, Script] = {}  # by name: what a job's containers do
        self.created: list[tuple[str, dict[str, Any]]] = []  # (name, spec) the API created
        self.calls: list[tuple[str, str]] = []  # (operation, container id, name or label)
        self.stops: list[tuple[str, int, float]] = []  # (id, grace seconds, time.monotonic())
        self.downloads: list[tuple[str, str]] = []  # (id, the container's state then)
        self.removed: list[str] = []  # ids
        self.on_create: Callable[[str], Awaitable[None]] | None = None  # before create answers
        # Raised by the next calls of an operation, one each: Docker failing or unreachable.
        self.failures: dict[str, list[DockerError]] = {}
        self.closed = False

    def script(self, job_id: object, script: Script) -> None:
        """What the container of this job will do."""
        self.scripts[container_name(job_id)] = script

    def find(self, ref: str) -> FakeContainer | None:
        found = self.containers.get(ref)
        if found is not None:
            return found
        return next((c for c in self.containers.values() if c.name == ref), None)

    def ops(self, *names: str) -> list[str]:
        """The operations called, in order, among ``names``."""
        return [op for op, _ in self.calls if op in names]

    async def run_container(
        self,
        name: str,
        labels: dict[str, str],
        script: Script | None = None,
        *,
        start: bool = True,
    ) -> str:
        """A container that exists already (left by an earlier executor); not counted in calls."""
        container = self._add(name, {"Image": IMAGE, "Labels": labels}, script or Script())
        if start:
            container.start()
            await asyncio.sleep(0)  # let its script begin
        return container.id

    async def create_container(self, name: str, spec: dict[str, Any]) -> str:
        self._call("create", name)
        if self.on_create is not None:
            await self.on_create(name)
        if self.find(name) is not None:
            raise Conflict(409, f'Conflict. The container name "/{name}" is already in use')
        if spec.get("Image") not in self.images:
            raise NotFound(404, f"No such image: {spec.get('Image')}")
        container = self._add(name, spec, self.scripts.get(name) or Script())
        self.created.append((name, spec))
        return container.id

    async def start_container(self, container_id: str) -> None:
        container = self._get(container_id)
        self._call("start", container.id)
        container.start()

    async def inspect_container(self, container_id: str) -> ContainerState:
        container = self._get(container_id)
        self._call("inspect", container.id)
        return container.inspect()

    async def list_containers(self, label: str) -> list[ContainerSummary]:
        self._call("list", label)
        return [
            ContainerSummary(id=c.id, name=c.name, labels=dict(c.labels), state=c.state)
            for c in self.containers.values()
            if label in c.labels
        ]

    async def follow_logs(self, container_id: str) -> AsyncIterator[LogLine]:
        container = self._get(container_id)
        self._call("logs", container.id)
        index = 0
        while True:
            changed = container.changed
            while index < len(container.lines):
                yield container.lines[index]
                index += 1
            if container.ended.is_set():
                return
            await changed.wait()

    async def stop_container(self, container_id: str, *, grace_seconds: int) -> None:
        container = self.find(container_id)
        ref = container.id if container is not None else container_id
        self._call("stop", ref)
        self.stops.append((ref, grace_seconds, time.monotonic()))
        if container is not None and container.state == "running":
            # SIGTERM: harness.job stops the training, or ends its wait after ARP-DONE.
            container.end(0 if container.done_printed else SIGTERM_EXIT)

    async def kill_container(self, container_id: str) -> None:
        container = self.find(container_id)
        self._call("kill", container.id if container is not None else container_id)
        if container is not None and container.state == "running":
            container.end(SIGKILL_EXIT)

    async def wait_container(self, container_id: str) -> int:
        container = self._get(container_id)
        self._call("wait", container.id)
        await container.ended.wait()
        return container.exit_code or 0

    async def remove_container(self, container_id: str) -> None:
        container = self.find(container_id)
        self._call("remove", container.id if container is not None else container_id)
        if container is None:
            return
        container.end(SIGKILL_EXIT)
        del self.containers[container.id]
        self.removed.append(container.id)

    async def download_archive(
        self, container_id: str, path: str, destination: Path, *, max_bytes: int
    ) -> int:
        container = self._get(container_id)
        self._call("download", container.id)
        self.downloads.append((container.id, container.state))
        files = container.script.outputs if container.state == "running" else {}
        data = output_tar(PurePosixPath(path).name, files)
        if len(data) > max_bytes:
            raise DockerError(413, f"the archive of {path} is over {max_bytes} bytes")
        await asyncio.to_thread(destination.write_bytes, data)
        return len(data)

    async def aclose(self) -> None:
        self.closed = True

    def _call(self, op: str, ref: str) -> None:
        self.calls.append((op, ref))
        failures = self.failures.get(op)
        if failures:
            raise failures.pop(0)

    def _get(self, ref: str) -> FakeContainer:
        container = self.find(ref)
        if container is None:
            raise NotFound(404, f"No such container: {ref}")
        return container

    def _add(self, name: str, spec: dict[str, Any], script: Script) -> FakeContainer:
        container = FakeContainer(secrets.token_hex(32), name, spec, script)
        self.containers[container.id] = container
        return container


def output_tar(folder: str, files: dict[str, bytes]) -> bytes:
    """A tar of an output folder, as Docker's archive API returns it: entries under its name."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        folders = {folder} | {
            f"{folder}/{parent}"
            for path in files
            for parent in map(str, PurePosixPath(path).parents)
            if parent != "."
        }
        for name in sorted(folders):
            info = tarfile.TarInfo(name + "/")
            info.type = tarfile.DIRTYPE
            tar.addfile(info)
        for path, content in sorted(files.items()):
            info = tarfile.TarInfo(f"{folder}/{path}")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


class FakeGpu:
    """agentic_executor.ports.GpuProbe with a settable reading (None: no nvidia-smi)."""

    def __init__(self, reading: GpuSample | None = None) -> None:
        self.reading = reading

    async def sample(self) -> GpuSample | None:
        return self.reading


def gpu_sample(free_mb: int = 5800, *, total_mb: int = 6144) -> GpuSample:
    return GpuSample(
        index=0,
        name=GPU_NAME,
        memory_total_mb=total_mb,
        memory_used_mb=total_mb - free_mb,
        utilization_percent=3,
        temperature_c=41,
        power_draw_w=9.5,
        power_limit_w=120.0,
        fan_percent=None,
        sampled_at=datetime.now(UTC),
    )


class FakeValkey:
    def __init__(self) -> None:
        self.published: list[str] = []

    async def publish(self, channel: str, message: str) -> int:
        self.published.append(channel)
        return 1


def executor_settings(tmp_path: Path, **overrides: Any) -> ExecutorSettings:
    """Settings for a test: its own data dir and nyu2 folder, and intervals in milliseconds."""
    dataset = tmp_path / "datasets" / "nyu2"
    dataset.mkdir(parents=True, exist_ok=True)
    values: dict[str, Any] = {
        "data_dir": tmp_path / "data",
        "dataset_nyu2": dataset,
        "sandbox_image": IMAGE,
        "poll_seconds": 0.02,
        "cancel_check_seconds": 0.02,
        "stop_grace_seconds": 2,
        "min_free_vram_mb": 1024,
        **overrides,
    }
    return ExecutorSettings(**values)


def speed_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """The executor's own intervals in milliseconds, so a test takes as long as its jobs."""
    for name, seconds in {
        "HEARTBEAT_SECONDS": 0.05,
        "LEASE_RENEW_SECONDS": 0.05,
        "PROGRESS_SECONDS": 0.05,
        "REAP_SECONDS": 0.1,
        "RETRY_SECONDS": 0.05,
        "FOLLOW_RETRY_SECONDS": 0.02,
    }.items():
        monkeypatch.setattr(executor_module, name, seconds)


def make_executor(
    db: Factory,
    settings: ExecutorSettings,
    docker: FakeDocker,
    *,
    gpu: FakeGpu | None = None,
    valkey: FakeValkey | None = None,
) -> Executor:
    return Executor(settings, db, docker, gpu or FakeGpu(gpu_sample()), valkey or FakeValkey())


@contextlib.asynccontextmanager
async def running(executor: Executor) -> AsyncIterator[asyncio.Task[None]]:
    """executor.run() in the background, stopped (gracefully) at the end."""
    task = asyncio.create_task(executor.run())
    try:
        yield task
    finally:
        executor.stop()
        await asyncio.wait_for(task, 10)


# Jobs


def job_config(**training: Any) -> dict[str, Any]:
    """A harness config whose paths are wrong on purpose: the executor sets them."""
    return {
        "task": "nyu2_depth",
        "seed": 7,
        "model": {"architecture": "generated", "kwargs": {"width": 8}, "code_dir": "/elsewhere"},
        "data": {"dataset": "nyu2", "root": "/mnt/d/DATASET/nyu2", "batch_size": 2},
        "training": {"epochs": 2, "learning_rate": 0.001, **training},
    }


async def create_dataset(db: Factory, **columns: Any) -> None:
    async with db() as session:
        if await session.get(Dataset, "nyu2") is None:
            values = {"version": "2026.05", "title": "NYU Depth V2", **columns}
            session.add(Dataset(name="nyu2", **values))
            await session.commit()


async def create_job(
    db: Factory,
    *,
    kind: GpuJobKind = GpuJobKind.SMOKE,
    code: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    timeout_seconds: int = 600,
    **columns: Any,
) -> GpuJob:
    """A job of a new run's coding (smoke) or experiment (train) stage attempt."""
    await create_dataset(db)
    async with db() as session:
        project = Project(name="Depth", created_by="user-1")
        session.add(project)
        await session.flush()
        run = Run(project_id=project.id, owner_id="user-1", topic="Monocular depth")
        session.add(run)
        await session.flush()
        stage = "coding" if kind is GpuJobKind.SMOKE else "experiment"
        stage_run = StageRun(run_id=run.id, stage=stage)
        session.add(stage_run)
        await session.flush()
        job = GpuJob(
            stage_run_id=stage_run.id,
            run_id=run.id,
            user_id="user-1",
            kind=kind,
            ordinal=1,
            dataset="nyu2",
            code=code if code is not None else {"model.py": MODEL_SOURCE},
            config=config if config is not None else job_config(),
            timeout_seconds=timeout_seconds,
            **columns,
        )
        session.add(job)
        await session.commit()
        return job


async def get_job(db: Factory, job_id: uuid.UUID) -> GpuJob:
    async with db() as session:
        job = await session.get(GpuJob, job_id)
    assert job is not None
    return job


async def wait_status(
    db: Factory, job_id: uuid.UUID, status: GpuJobStatus, *, within: float = 5.0
) -> GpuJob:
    job = await get_job(db, job_id)

    async def reached() -> bool:
        nonlocal job
        job = await get_job(db, job_id)
        return job.status is status

    await eventually(reached, within=within, what=f"job {job_id} to be {status.value}")
    return job


async def epoch_events(db: Factory, run_id: uuid.UUID) -> list[dict[str, Any]]:
    async with db() as session:
        rows = await session.scalars(
            select(RunEvent)
            .where(RunEvent.run_id == run_id, RunEvent.type == EventType.EXPERIMENT_EPOCH)
            .order_by(RunEvent.seq)
        )
        return [row.payload for row in rows]


async def executor_status(db: Factory) -> dict[str, Any] | None:
    async with db() as session:
        row = await session.get(Setting, EXECUTOR_STATUS_KEY)
        return row.value if row is not None else None


async def eventually(
    check: Callable[[], Awaitable[bool]], *, within: float = 5.0, what: str = "the condition"
) -> None:
    deadline = time.monotonic() + within
    while not await check():
        if time.monotonic() >= deadline:
            raise AssertionError(f"timed out waiting for {what}")
        await asyncio.sleep(0.01)


# What harness.job prints and harness.train writes


def metric_line(**record: Any) -> str:
    return METRIC_PREFIX + json.dumps({"ts": "2026-10-30T12:00:00+00:00", **record})


def epoch_record(epoch: int, loss: float = 0.5) -> dict[str, Any]:
    return {
        "kind": "epoch",
        "epoch": epoch,
        "train": {"loss": loss, "rmse": None, "mae": None, "abs_rel": None},
        "val": {"loss": loss + 0.1, "rmse": 0.92, "mae": 0.71, "abs_rel": 0.24},
    }


def epoch_line(epoch: int, loss: float = 0.5) -> str:
    return metric_line(**epoch_record(epoch, loss))


def step_line(epoch: int, step: int, loss: float) -> str:
    return metric_line(kind="train_step", epoch=epoch, step=step, loss=loss)


def done_line(exit_code: int) -> str:
    return DONE_PREFIX + json.dumps({"exit_code": exit_code})


def results_ok() -> bytes:
    return json.dumps(
        {
            "status": "ok",
            "train_metrics": {"loss": 0.5, "rmse": None, "mae": None, "abs_rel": None},
            "val_metrics": {"loss": 0.6, "rmse": 0.92, "mae": 0.71, "abs_rel": 0.24},
            "param_count": 28,
            "provenance": {
                "harness_version": "0.3.0",
                "seed": 7,
                "device": GPU_NAME,
                "torch": "2.14.1",
                "cuda": "12.6",
            },
            "duration_s": 3.2,
        },
        indent=2,
    ).encode()


def results_failed(error_code: str, error: str) -> bytes:
    return json.dumps(
        {
            "status": "failed",
            "error": error,
            "error_code": error_code,
            "train_metrics": None,
            "val_metrics": None,
            "duration_s": 1.4,
        },
        indent=2,
    ).encode()

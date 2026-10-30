"""Phase 3: the GPU executor runs real jobs on this machine (docs/design/experiments.md, "Live").

It starts an executor of its own (stop any other first), submits jobs straight into the dev
database for a throwaway project, and checks:
  1. a smoke job of the depth_unet example succeeds with real metrics, its provenance, its
     outputs and one experiment.epoch event, and leaves no container behind
  2. refused code (an import of os) fails as code.refused without a container
  3. a cancel during training ends the job within 5 s
  4. an executor killed mid-training leaves the container running, and the next one adopts it:
     one container all along, the job succeeds, and no epoch event is sent twice
The project, its runs and their job folders are removed at the end. Exits non-zero on any FAIL.
Usage: make executor-check (needs make up, the sandbox image and ARP_DATASET_NYU2)
"""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text

from agentic_core.enums import GpuJobKind, GpuJobStatus
from agentic_core.gpu_jobs import JOB_LABEL, job_dir
from agentic_db import create_engine, session_factory
from agentic_db.gpu_jobs import JobRequest, request_cancel, submit_job
from agentic_db.models import GpuJob, Project, Run, RunEvent, StageRun
from agentic_executor.settings import ExecutorSettings

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "sandbox" / "pytorch" / "examples"
LOG = Path.home() / ".local" / "state" / "arp" / "logs" / "executor-check.log"
OWNER = "executor-check"
JOB_SECONDS = 600  # the longest any one check waits for its job
CANCEL_LIMIT_SECONDS = 5.0

passed = 0
failed = 0


def check(ok: bool, what: str) -> bool:
    global passed, failed
    if ok:
        passed += 1
        print(f"  \033[32mPASS\033[0m {what}", flush=True)
    else:
        failed += 1
        print(f"  \033[31mFAIL\033[0m {what}", flush=True)
    return ok


def config(*, epochs: int, train_steps: int, val_steps: int) -> dict[str, Any]:
    """The harness config for the depth_unet example. The executor sets the code and data
    paths itself."""
    return {
        "task": "nyu2_depth",
        "seed": 42,
        "require_gpu": True,
        "model": {"architecture": "generated", "kwargs": {"base_channels": 16}},
        "data": {
            "dataset": "nyu2",
            "split_file_template": "{root}/splits/nyu/{split}.txt",
            "batch_size": 2,
            "num_workers": 2,
        },
        "training": {
            "loss": "generated",
            "epochs": epochs,
            "learning_rate": 0.001,
            "optimizer": "adam",
            "max_train_steps": train_steps,
            "max_val_steps": val_steps,
        },
    }


def code(example: str) -> dict[str, str]:
    folder = EXAMPLES / example
    return {path.name: path.read_text() for path in sorted(folder.glob("*.py"))}


def containers(job_id: uuid.UUID) -> list[str]:
    """The ids of the job's containers, through Docker's own CLI (this check's, not the
    executor's way)."""
    out = subprocess.run(
        ["docker", "ps", "-aq", "--filter", f"label={JOB_LABEL}={job_id}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.split()


def remove_container(container_id: str) -> None:
    subprocess.run(["docker", "rm", "-f", "-v", container_id], capture_output=True)


def container_state(container_id: str) -> str:
    out = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Status}}", container_id],
        capture_output=True,
        text=True,
    )
    return out.stdout.strip() or "gone"


class ExecutorProcess:
    """`python -m agentic_executor` in a process group of its own, logging to LOG."""

    def __init__(self) -> None:
        self.process: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        log = LOG.open("ab")
        self.process = subprocess.Popen(
            ["uv", "run", "--package", "agentic-executor", "python", "-m", "agentic_executor"],
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    def kill(self, signum: int = signal.SIGKILL, wait: float = 15.0) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        os.killpg(self.process.pid, signum)
        try:
            self.process.wait(wait)
        except subprocess.TimeoutExpired:
            os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait()


async def until(
    condition: Callable[[], Awaitable[bool]], seconds: float, every: float = 0.25
) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if await condition():
            return True
        await asyncio.sleep(every)
    return False


class Check:
    def __init__(self, sessions: Any) -> None:
        self.sessions = sessions
        self.project_id: uuid.UUID | None = None
        self.job_ids: list[uuid.UUID] = []

    async def setup(self) -> None:
        async with self.sessions() as session:
            project = Project(name="Executor check (removed when it ends)", created_by=OWNER)
            session.add(project)
            await session.commit()
            self.project_id = project.id

    async def submit(
        self, kind: GpuJobKind, example: str, job_config: dict[str, Any], limit_seconds: int
    ) -> GpuJob:
        stage = "coding" if kind is GpuJobKind.SMOKE else "experiment"
        async with self.sessions() as session:
            run = Run(
                project_id=self.project_id, owner_id=OWNER, topic=f"executor check: {example}"
            )
            session.add(run)
            await session.flush()
            stage_run = StageRun(run_id=run.id, stage=stage)
            session.add(stage_run)
            await session.flush()
            job = await submit_job(
                session,
                JobRequest(
                    stage_run_id=stage_run.id,
                    run_id=run.id,
                    user_id=OWNER,
                    kind=kind,
                    ordinal=1,
                    dataset="nyu2",
                    code=code(example),
                    config=job_config,
                    timeout_seconds=limit_seconds,
                ),
            )
            await session.commit()
        assert job is not None, "the check's own user has no jobs queued"
        self.job_ids.append(job.id)
        return job

    async def job(self, job_id: uuid.UUID) -> GpuJob:
        async with self.sessions() as session:
            job = await session.get(GpuJob, job_id)
        assert job is not None
        return job

    async def ended(self, job_id: uuid.UUID, seconds: float = JOB_SECONDS) -> GpuJob:
        async def terminal() -> bool:
            return (await self.job(job_id)).status.is_terminal

        await until(terminal, seconds, every=0.5)
        return await self.job(job_id)

    async def training(self, job_id: uuid.UUID) -> bool:
        """Whether the job runs and has sent a training step."""
        job = await self.job(job_id)
        return job.status is GpuJobStatus.RUNNING and job.progress is not None

    async def epoch_events(self, job: GpuJob) -> list[int]:
        async with self.sessions() as session:
            rows = await session.scalars(
                select(RunEvent.payload).where(
                    RunEvent.run_id == job.run_id,
                    RunEvent.type == "experiment.epoch",
                    RunEvent.payload["job_id"].astext == str(job.id),
                )
            )
            return sorted(int(payload["epoch"]) for payload in rows)

    async def cleanup(self, data_dir: Path) -> None:
        for job_id in self.job_ids:
            for container_id in containers(job_id):
                remove_container(container_id)
            shutil.rmtree(job_dir(data_dir, job_id), ignore_errors=True)
        if self.project_id is not None:
            async with self.sessions() as session:
                await session.execute(
                    text("DELETE FROM projects WHERE id = :id"), {"id": self.project_id}
                )
                await session.commit()


async def smoke_succeeds(check_: Check, data_dir: Path) -> None:
    print("1/4 A smoke job of the depth_unet example", flush=True)
    job = await check_.submit(
        GpuJobKind.SMOKE, "depth_unet", config(epochs=1, train_steps=2, val_steps=2), 600
    )
    started = time.monotonic()
    job = await check_.ended(job.id)
    took = time.monotonic() - started
    metrics = (job.result or {}).get("val_metrics") or {}
    check(
        job.status is GpuJobStatus.SUCCEEDED,
        f"succeeded in {took:.0f} s ({job.status.value}, {job.error_code or 'no error'})",
    )
    check(
        bool(metrics) and all(value is not None for value in metrics.values()),
        f"real validation metrics: {metrics}",
    )
    provenance = job.provenance or {}
    check(
        str(provenance.get("image_id", "")).startswith("sha256:")
        and set(provenance.get("code_sha256") or {}) == {"model.py", "loss.py"}
        and bool(provenance.get("config_sha256"))
        and (provenance.get("dataset") or {}).get("version") == "2026.05",
        f"provenance: image {str(provenance.get('image_id'))[:19]}, GPU {provenance.get('gpu')}",
    )
    out = job_dir(data_dir, job.id) / "out"
    check(
        (out / "results.json").is_file() and (out / "metrics.jsonl").is_file(),
        "results.json and metrics.jsonl copied out of the container",
    )
    check(await check_.epoch_events(job) == [0], "one experiment.epoch event")
    check(
        job.gpu_seconds is not None and job.gpu_seconds > 0 and job.exit_code == 0,
        f"exit code {job.exit_code}, {job.gpu_seconds} GPU seconds",
    )
    check(containers(job.id) == [], "its container is removed")


async def refused_code_fails(check_: Check) -> None:
    print("2/4 Refused code (an import of os)", flush=True)
    job = await check_.submit(
        GpuJobKind.SMOKE, "refused", config(epochs=1, train_steps=2, val_steps=2), 600
    )
    job = await check_.ended(job.id, 60)
    check(
        job.status is GpuJobStatus.FAILED and job.error_code == "code.refused",
        f"{job.status.value} with {job.error_code}",
    )
    check(job.container_id is None and containers(job.id) == [], "no container was created")


async def cancel_ends_quickly(check_: Check) -> None:
    print("3/4 A cancel during training", flush=True)
    job = await check_.submit(
        GpuJobKind.TRAIN, "depth_unet", config(epochs=3, train_steps=2000, val_steps=20), 1800
    )
    if not check(await until(lambda: check_.training(job.id), JOB_SECONDS), "training started"):
        return
    async with check_.sessions() as session:
        await request_cancel(session, job.id)
        await session.commit()
    asked = time.monotonic()

    async def cancelled() -> bool:
        return (await check_.job(job.id)).status is GpuJobStatus.CANCELLED

    await until(cancelled, 30, every=0.1)
    took = time.monotonic() - asked
    ended = await check_.job(job.id)
    check(
        ended.status is GpuJobStatus.CANCELLED and took <= CANCEL_LIMIT_SECONDS,
        f"cancelled {took:.1f} s after the request ({ended.status.value})",
    )
    check(containers(job.id) == [], "its container is removed")


async def restart_adopts(check_: Check, executor: ExecutorProcess) -> None:
    print("4/4 An executor killed mid-training, and the next one", flush=True)
    job = await check_.submit(
        GpuJobKind.TRAIN, "depth_unet", config(epochs=2, train_steps=150, val_steps=10), 1800
    )
    if not check(await until(lambda: check_.training(job.id), JOB_SECONDS), "training started"):
        return
    before = containers(job.id)
    executor.kill(signal.SIGKILL)
    await asyncio.sleep(2)
    check(
        len(before) == 1 and container_state(before[0]) == "running",
        "SIGKILL to the executor: the container runs on",
    )
    seen: set[str] = set(before)
    most = len(before)

    async def watch() -> None:
        nonlocal most
        while True:
            now = containers(job.id)
            seen.update(now)
            most = max(most, len(now))
            await asyncio.sleep(0.5)

    watcher = asyncio.create_task(watch())
    executor.start()
    try:
        ended = await check_.ended(job.id)
    finally:
        watcher.cancel()
    outcome = f"{ended.status.value}, {ended.error_code or 'no error'}"
    check(ended.status is GpuJobStatus.SUCCEEDED, f"the next executor adopted it ({outcome})")
    check(
        most == 1
        and len(seen) == 1
        and ended.container_id is not None
        and ended.container_id.startswith(before[0]),
        f"one container all along ({len(seen)} seen)",
    )
    epochs = await check_.epoch_events(ended)
    check(epochs == [0, 1], f"epoch events sent once each: {epochs}")


async def lock_is_free(sessions: Any) -> bool:
    async with sessions() as session:
        free = await session.scalar(text("SELECT pg_try_advisory_lock(hashtext('arp.executor'))"))
        if free:
            await session.execute(text("SELECT pg_advisory_unlock(hashtext('arp.executor'))"))
        await session.commit()
        return bool(free)


async def main() -> int:
    settings = ExecutorSettings()
    if settings.dataset_nyu2 is None:
        print("Set ARP_DATASET_NYU2 in .env (the NYU2 folder on this machine)")
        return 1
    engine = create_engine(settings.database_url)
    sessions = session_factory(engine)
    if not await lock_is_free(sessions):
        print("Another executor is running: stop it first (this check starts its own)")
        await engine.dispose()
        return 1
    check_ = Check(sessions)
    executor = ExecutorProcess()
    started = time.monotonic()
    try:
        await check_.setup()
        executor.start()
        print(f"Executor started (log: {LOG}); jobs for a throwaway project", flush=True)
        await smoke_succeeds(check_, settings.data_dir)
        await refused_code_fails(check_)
        await cancel_ends_quickly(check_)
        await restart_adopts(check_, executor)
    finally:
        executor.kill(signal.SIGTERM)
        try:  # a failure here must not hide the one that brought us here
            await check_.cleanup(settings.data_dir)
            async with sessions() as session:
                left = await session.scalar(
                    select(func.count()).select_from(GpuJob).where(GpuJob.user_id == OWNER)
                )
            print(f"Cleaned up ({left} of the check's jobs left)")
        except Exception as exc:
            print(f"Cleanup failed: {exc!r}")
        await engine.dispose()
    print(f"Summary: {passed} passed, {failed} failed in {time.monotonic() - started:.0f} s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

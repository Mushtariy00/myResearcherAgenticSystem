"""The executor: runs the queued GPU jobs, one at a time, each in a fresh sandbox container.

docs/design/experiments.md ("The executor") and docs/adr/0006-gpu-sandbox-hardened-docker.md
are the design. A job goes:
- claimed (``starting``) once the GPU has room, smoke tests first;
- its files are written under ARP_DATA_DIR/jobs/<id> and its code is checked once more;
- its container is created from agentic_executor.template and started (``running``);
- the executor follows the container's output: epoch records become experiment.epoch run
  events, and ARP-DONE says that training ended;
- the outputs are copied out of the container's tmpfs volume while it still runs (after ARP-DONE,
  or at the job's time limit before it is stopped); then the container is killed or stopped and
  inspected, the job's end is recorded, and only then is the container removed.
A cancel stops the container with a short grace period.

Everything needed to pick a job up again is in Postgres and in Docker (the container's JOB_LABEL),
so an executor that stops or crashes leaves nothing behind that the next one can't put right:
recover() requeues the jobs it claimed but never started, adopts the containers still running
and removes the rest. Stopping the executor leaves a running job's container running for it.
For the same reason a Docker or Postgres that is out of reach for a while fails no job: a job
whose container could not be created goes back to the queue, and one that lost touch with
Postgres is recovered once Postgres is back.
"""

from __future__ import annotations

import asyncio
import contextlib
import enum
import hashlib
import itertools
import json
import logging
import os
import shutil
import stat
import threading
import time
import uuid
from collections import defaultdict
from collections.abc import Awaitable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import exc as sa_exc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.codecheck import MAX_SOURCE_BYTES, check_module
from agentic_core.contracts import events_channel
from agentic_core.enums import GpuJobStatus
from agentic_core.gpu_jobs import (
    CODE_FILES,
    CODE_MOUNT,
    CODE_REFUSED,
    DATA_ROOT,
    JOB_BAD_INPUT,
    JOB_LABEL,
    JOB_LOST,
    JOB_NO_RESULT,
    JOB_OOM_KILLED,
    JOB_START_FAILED,
    LOG_FILE,
    MODEL_FILE,
    OUT_DIR,
    RESULTS_FILE,
    TRAIN_ERROR,
    job_dir,
    max_timeout_seconds,
)
from agentic_db.models import Dataset, GpuJob
from agentic_executor import queue
from agentic_executor.archive import ArchiveError, ExtractReport, extract_outputs
from agentic_executor.logs import Done, Epoch, JobOutput, Step, clean_text, jsonable
from agentic_executor.ports import (
    Conflict,
    ContainerState,
    ContainerSummary,
    DockerApi,
    DockerError,
    GpuProbe,
    GpuSample,
    LogLine,
    NotFound,
)
from agentic_executor.settings import ExecutorSettings
from agentic_executor.template import MIB, JobMounts, container_name, container_spec

log = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 5.0  # the executor.status setting
LEASE_RENEW_SECONDS = 5.0  # a held job's lease, well within queue.LEASE
PROGRESS_SECONDS = 5.0  # a job's progress is written at most this often
REAP_SECONDS = 60.0  # an idle executor removes stray containers this often
VRAM_LOG_SECONDS = 60.0  # "waiting for VRAM", at most this often
RETRY_SECONDS = 5.0  # after Docker or Postgres failed, the loop tries again
FOLLOW_RETRY_SECONDS = 1.0  # a log stream that ended before its container is followed again
DRAIN_SECONDS = 5.0  # once a container stopped, how long its last lines may take to arrive
WAKE_TIMEOUT_SECONDS = 2.0  # a wake-up only saves SSE a poll; a stuck Valkey must not stall us
ARCHIVE_SLACK_MB = 16  # the output tar's headers on top of the output volume's quota
COLLECT_ATTEMPTS = 3  # copying the outputs, while Docker can't be reached
FINISH_RETRY_MAX_SECONDS = 30.0
ERROR_CODE_MAX = 64  # gpu_jobs.error_code
# Postgres is down or out of reach (psycopg's errors arrive wrapped in these): worth waiting
# for, unlike a statement it refuses.
DB_UNAVAILABLE = (sa_exc.OperationalError, sa_exc.InterfaceError, sa_exc.TimeoutError)


class _Outcome(enum.Enum):
    """How the supervision of a running container ended."""

    DONE = "done"  # ARP-DONE: training ended and the outputs wait in the container
    STOPPED = "stopped"  # the container stopped before ARP-DONE: its outputs went with it
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"  # the job's time limit passed
    LEAVE = "leave"  # the executor is stopping: the container runs on for the next one
    GONE = "gone"  # the job ended elsewhere, or its row is gone: its container is removed


class _CannotRun(Exception):
    """The job ends failed before it gets a container."""

    def __init__(self, error_code: str, error: str, result: dict[str, Any] | None = None) -> None:
        super().__init__(error)
        self.error_code = error_code
        self.error = error
        self.result = result


class ChecksumCancelled(Exception):
    """manifest_checksum stopped early: the executor is stopping."""


@dataclass
class _Watch:
    """The supervision of one job's container: what its output showed so far."""

    job: GpuJob
    stage: str
    output: JobOutput
    epochs_reported: int
    done: asyncio.Event = field(default_factory=asyncio.Event)
    stopped: asyncio.Event = field(default_factory=asyncio.Event)
    done_at: datetime | None = None
    exit_code: int | None = None  # the training's, from ARP-DONE
    progress: dict[str, Any] | None = None  # the latest train_step record, until it is written
    progress_due: float = 0.0  # time.monotonic() from which progress may be written again


class Executor:
    """Runs the queued GPU jobs one at a time until stop() (see the module docstring)."""

    def __init__(
        self,
        settings: ExecutorSettings,
        sessions: async_sessionmaker[AsyncSession],
        docker: DockerApi,
        gpu: GpuProbe,
        valkey: Any,
    ) -> None:
        self._settings = settings
        self._sessions = sessions
        self._docker = docker
        self._gpu = gpu
        self._valkey = valkey
        self._data_dir = settings.data_dir.absolute()  # Docker binds only absolute paths
        self._stopping = asyncio.Event()
        self._job_id: uuid.UUID | None = None  # the job on the GPU
        self._sample: GpuSample | None = None  # the latest nvidia-smi reading
        self._waiting_for_vram: dict[str, int] | None = None
        self._vram_logged_at: float | None = None
        self._warned_no_gpu = False
        self._reap_at = time.monotonic() + REAP_SECONDS
        # Set when a job lost touch with Postgres: recover() puts it right once Postgres is back.
        self._needs_recovery = False
        self._foreign: set[str] = set()  # labelled containers already warned about (_ours)

    def stop(self) -> None:
        """Stop claiming and supervising. A running job's container keeps running: the next
        executor adopts it."""
        self._stopping.set()

    async def wait_stopped(self, seconds: float) -> bool:
        """Whether stop() was called, waiting ``seconds`` at most for it."""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._stopping.wait(), seconds)
        return self._stopping.is_set()

    async def run(self) -> None:
        """Recover, then run jobs until stop(); recover again after a job lost touch with
        Postgres. The heartbeat and the datasets' checksums run beside the jobs."""
        background = [
            asyncio.create_task(self._heartbeat(), name="executor heartbeat"),
            asyncio.create_task(self._checksum_datasets(), name="dataset checksums"),
        ]
        recovering = True  # nothing is claimed before recover() went through once
        try:
            while not self._stopping.is_set():
                try:
                    if recovering or self._needs_recovery:
                        if not recovering and await self.wait_stopped(RETRY_SECONDS):
                            break  # a job lost touch with Postgres: give it time to come back
                        recovering, self._needs_recovery = True, False
                        await self.recover()
                        recovering = False
                    elif await self.run_next() is None:
                        await self._idle()
                except (DockerError, SQLAlchemyError, OSError) as exc:
                    log.warning("executor loop: %s; trying again in %.0f s", exc, RETRY_SECONDS)
                    await self.wait_stopped(RETRY_SECONDS)
                except Exception:
                    log.exception("executor loop failed; trying again in %.0f s", RETRY_SECONDS)
                    await self.wait_stopped(RETRY_SECONDS)
        finally:
            for task in background:
                task.cancel()
            await asyncio.gather(*background, return_exceptions=True)

    async def run_next(self) -> uuid.UUID | None:
        """Claim the next queued job once the GPU has room for it, and run it to its end. Returns
        its id, or None when nothing was claimed (no job queued, the GPU busy, or stopping)."""
        if self._stopping.is_set():
            return None
        async with self._sessions() as session:
            if not await queue.has_queued(session):
                self._waiting_for_vram = None
                return None
        if not await self._vram_free():
            return None
        async with self._sessions() as session:
            job = await queue.claim_next(session)
        if job is None:
            return None
        log.info("job %s (%s): claimed", job.id, job.kind.value)
        await self._own(job, self._start(job))
        return job.id

    async def recover(self) -> None:
        """Pick up after the last executor, before claiming anything: requeue the jobs it claimed
        but never got running, adopt the containers of its running jobs (supervising each to
        its end), end the running jobs whose container stopped or vanished, and remove every
        other container labelled JOB_LABEL."""
        containers = self._ours(await self._docker.list_containers(JOB_LABEL))
        by_job: dict[str, list[ContainerSummary]] = defaultdict(list)
        for container in containers:
            by_job[container.labels.get(JOB_LABEL, "")].append(container)
        async with self._sessions() as session:
            jobs = await queue.active_jobs(session)
        adopt: list[tuple[GpuJob, str, ContainerState]] = []
        for job in jobs:
            mine = by_job.pop(str(job.id), [])
            if job.status is GpuJobStatus.STARTING:
                await self._requeue(job, mine)
                continue
            running = await self._still_running(job, mine)
            if running is not None:
                adopt.append((job, *running))
        for container in itertools.chain.from_iterable(by_job.values()):
            log.info(
                "removing container %s: its job (%s) is not running",
                container.name,
                container.labels.get(JOB_LABEL),
            )
            await self._docker.remove_container(container.name)
        for job, container, state in adopt:
            if self._stopping.is_set():
                return
            log.info("job %s (%s): adopted container %s", job.id, job.kind.value, container)
            started_at = job.started_at or state.started_at or datetime.now(UTC)
            await self._own(job, self._supervise(job, container, started_at, adopted=True))

    async def reap(self) -> list[str]:
        """Remove the containers labelled JOB_LABEL whose job ended or is unknown (a crash
        between a job's end and its container's removal leaves one); returns their names."""
        containers = self._ours(await self._docker.list_containers(JOB_LABEL))
        if not containers:
            return []
        job_ids = {
            container.id: _job_id(container.labels.get(JOB_LABEL)) for container in containers
        }
        async with self._sessions() as session:
            statuses = await queue.job_statuses(
                session, {job_id for job_id in job_ids.values() if job_id is not None}
            )
        removed: list[str] = []
        for container in containers:
            job_id = job_ids[container.id]
            status = statuses.get(job_id) if job_id is not None else None
            if status is None or status.is_terminal:
                log.info("removing stray container %s (job %s)", container.name, job_id)
                await self._docker.remove_container(container.name)
                removed.append(container.name)
        return removed

    def _ours(self, containers: list[ContainerSummary]) -> list[ContainerSummary]:
        """The labelled containers named as their job's (container_name). The executor reaches
        a container only by that name, and the socket proxy refuses any other, so the rest are
        left alone, with a warning the first time."""
        ours: list[ContainerSummary] = []
        for container in containers:
            job_id = _job_id(container.labels.get(JOB_LABEL))
            if job_id is not None and container.name == container_name(job_id):
                ours.append(container)
            elif container.id not in self._foreign:
                self._foreign.add(container.id)
                log.warning(
                    "container %s has the %s label but not a job container's name: left alone",
                    container.name,
                    JOB_LABEL,
                )
        return ours

    # Running a job

    async def _own(self, job: GpuJob, work: Awaitable[None]) -> None:
        """Run ``work`` for the job on the GPU. When Postgres can't be reached, the job's row and
        its container still say where it stands, so recover() picks it up again once Postgres is
        back. Any other error ends the job failed and frees the GPU, so one job can't stall the
        queue."""
        self._job_id = job.id
        try:
            await work
        except DB_UNAVAILABLE as exc:
            log.warning(
                "job %s (%s): Postgres is unreachable (%s); recovering once it is back",
                job.id,
                job.kind.value,
                exc,
            )
            self._needs_recovery = True
        except Exception as exc:
            log.exception("job %s (%s): the executor failed", job.id, job.kind.value)
            await self._abandon(job, exc)
        finally:
            self._job_id = None

    async def _start(self, job: GpuJob) -> None:
        """Check and write the job's inputs, create and start its container, and supervise it."""
        root = job_dir(self._data_dir, job.id)
        try:
            dataset_path = await self._dataset_path(job.dataset)
            await asyncio.to_thread(write_job_files, root, job.code, job.config, job.dataset)
        except _CannotRun as cannot:
            end = queue.Finish(
                GpuJobStatus.FAILED,
                error_code=cannot.error_code,
                error=cannot.error,
                result=cannot.result,
            )
            await self._finish(job, end, None)
            return
        if self._stopping.is_set():
            async with self._sessions() as session:
                await queue.requeue(session, job.id)
            log.info("job %s (%s): queued again, the executor is stopping", job.id, job.kind.value)
            return
        settings = self._settings
        spec = container_spec(
            image=settings.sandbox_image,
            job_id=str(job.id),
            run_id=str(job.run_id),
            kind=job.kind,
            mounts=JobMounts(
                dataset_name=job.dataset,
                dataset_path=dataset_path,
                code_dir=root / "code",
                config_file=root / "config.json",
            ),
            limits=settings.limits(),
        )
        name = container_name(job.id)
        try:
            container_id = await self._create(name, spec)
        except DockerError as exc:
            if exc.status == 0:
                await self._put_back(job, exc)
                return
            log.warning(
                "job %s (%s): Docker refused its container: %s", job.id, job.kind.value, exc
            )
            await self._remove_quietly(name)  # in case Docker created it and the answer was lost
            end = queue.Finish(
                GpuJobStatus.FAILED, error_code=JOB_START_FAILED, error=self._create_error(exc)
            )
            await self._finish(job, end, None)
            return
        # The id is recorded; every call names the container instead, as the socket proxy
        # allows only job containers' names in its paths.
        async with self._sessions() as session:
            cancel = await queue.record_container(session, job.id, container_id)
        if cancel is None:
            log.warning("job %s is no longer starting: removing its new container", job.id)
            await self._remove_quietly(name)
            return
        if cancel:
            await self._finish(job, queue.Finish(GpuJobStatus.CANCELLED), name)
            return
        try:
            await self._docker.start_container(name)
        except DockerError as exc:
            if exc.status == 0:
                await self._remove_quietly(name)  # or the next create replaces it
                await self._put_back(job, exc)
                return
            log.warning("job %s (%s): its container did not start: %s", job.id, job.kind.value, exc)
            end = queue.Finish(
                GpuJobStatus.FAILED,
                error_code=JOB_START_FAILED,
                error=f"Docker could not start the container: {exc.message}",
            )
            await self._finish(job, end, name)
            return
        async with self._sessions() as session:
            started_at = await queue.mark_running(session, job.id)
        if started_at is None:
            log.warning("job %s is no longer starting: removing its container", job.id)
            await self._discard(name)
            return
        log.info(
            "job %s (%s): running in container %s (%s)",
            job.id,
            job.kind.value,
            name,
            container_id[:12],
        )
        await self._supervise(job, name, started_at)

    async def _dataset_path(self, name: str) -> Path:
        """The job's dataset folder on this machine. _CannotRun when it can't be mounted."""
        async with self._sessions() as session:
            dataset = await session.get(Dataset, name)
        if dataset is None or not dataset.enabled:
            raise _CannotRun(JOB_BAD_INPUT, f"Dataset {name} is not registered or is disabled")
        folder, source = self._dataset_folder(name, dataset.host_path)
        if folder is None:
            raise _CannotRun(
                JOB_BAD_INPUT, f"Dataset {name} has no folder on this machine: set {source}"
            )
        if not await asyncio.to_thread(folder.is_dir):
            raise _CannotRun(
                JOB_BAD_INPUT, f"Dataset {name}'s folder {folder} ({source}) is not a directory"
            )
        return folder.absolute()

    def _dataset_folder(self, name: str, host_path: str | None) -> tuple[Path | None, str]:
        """A dataset's folder on this machine, and what names it (for the job's error)."""
        if host_path:
            return Path(host_path).expanduser(), "its host_path in the datasets table"
        return self._settings.dataset_path(name), f"ARP_DATASET_{name.upper()}"

    async def _create(self, name: str, spec: dict[str, Any]) -> str:
        try:
            return await self._docker.create_container(name, spec)
        except Conflict:
            # A container left over from an executor that went down before it recorded it.
            log.warning("removing the leftover container %s", name)
            await self._docker.remove_container(name)
            return await self._docker.create_container(name, spec)

    async def _put_back(self, job: GpuJob, exc: DockerError) -> None:
        """Docker can't be reached (the socket proxy restarting, say): that is no fault of the
        job's, so it goes back to the queue, and the executor pauses before claiming again."""
        log.warning(
            "job %s (%s): queued again, Docker is unreachable: %s", job.id, job.kind.value, exc
        )
        async with self._sessions() as session:
            await queue.requeue(session, job.id)
        await self.wait_stopped(RETRY_SECONDS)

    def _create_error(self, exc: DockerError) -> str:
        if isinstance(exc, NotFound):
            image = self._settings.sandbox_image
            return f"The sandbox image {image} is missing (make sandbox-build): {exc.message}"
        return f"Docker could not create the container: {exc.message}"

    async def _supervise(
        self, job: GpuJob, container_id: str, started_at: datetime, *, adopted: bool = False
    ) -> None:
        """Watch a running container to the job's end and record it (an adopted one too)."""
        root = job_dir(self._data_dir, job.id)
        async with self._sessions() as session:
            stage = await queue.stage_of(session, job.stage_run_id)
        root.mkdir(parents=True, exist_ok=True)
        watch = _Watch(
            job=job,
            stage=stage or "",
            output=JobOutput(root / LOG_FILE),
            epochs_reported=job.epochs_reported,
        )
        follower = asyncio.create_task(self._follow(watch, container_id))
        waiter = asyncio.create_task(self._wait_stopped(watch, container_id))
        try:
            outcome = await self._outcome(watch, follower, started_at, adopted=adopted)
            if outcome is _Outcome.LEAVE:
                log.info("job %s (%s): left running for the next executor", job.id, job.kind.value)
                return
            if outcome is _Outcome.GONE:
                log.warning("job %s is no longer running: removing its container", job.id)
                await self._discard(container_id)
                return
            report = None
            if outcome in (_Outcome.DONE, _Outcome.TIMEOUT):
                report = await self._collect(job, container_id, root)
                if watch.done.is_set():
                    outcome = _Outcome.DONE  # ARP-DONE came in as the time ran out
            await self._end_container(container_id, outcome)
            await asyncio.wait({follower}, timeout=DRAIN_SECONDS)  # the last lines
            state = await self._inspect(container_id)
            end = await self._end(watch, outcome, root, state, report, started_at)
            await self._finish(job, end, container_id)
        finally:
            follower.cancel()
            waiter.cancel()
            await asyncio.gather(follower, waiter, return_exceptions=True)
            watch.output.close()

    async def _outcome(
        self,
        watch: _Watch,
        follower: asyncio.Task[None],
        started_at: datetime,
        *,
        adopted: bool,
    ) -> _Outcome:
        """Wait for the job's end, checking for a cancel and the time limit every
        cancel_check_seconds and renewing the lease every LEASE_RENEW_SECONDS."""
        job = watch.job
        deadline = started_at + timedelta(seconds=_limit_seconds(job, self._settings))
        if adopted:
            # The replay of its output may hold an ARP-DONE from before the deadline.
            deadline = max(deadline, datetime.now(UTC) + timedelta(seconds=DRAIN_SECONDS))
        renew_at = 0.0
        unreadable = False  # warn once while Postgres is away, not every check
        while True:
            if follower.done() and not follower.cancelled() and follower.exception() is not None:
                raise RuntimeError("the log follower failed") from follower.exception()
            if watch.done.is_set():
                return _Outcome.DONE  # even when stopping: copying the outputs takes seconds
            if self._stopping.is_set():
                return _Outcome.LEAVE
            if watch.stopped.is_set():
                await asyncio.wait({follower}, timeout=DRAIN_SECONDS)  # ARP-DONE may be among them
                return _Outcome.DONE if watch.done.is_set() else _Outcome.STOPPED
            renew = time.monotonic() >= renew_at
            try:
                async with self._sessions() as session:
                    cancel = await queue.poll(session, job.id, renew_lease=renew)
            except (SQLAlchemyError, OSError) as exc:
                if not unreadable:
                    log.warning("job %s: could not read its row: %s", job.id, exc)
                    unreadable = True
            else:
                unreadable = False
                if cancel is None:
                    return _Outcome.GONE
                if cancel:
                    return _Outcome.CANCELLED
                if renew:
                    renew_at = time.monotonic() + LEASE_RENEW_SECONDS
            if datetime.now(UTC) >= deadline:
                return _Outcome.TIMEOUT
            await _first(
                self._settings.cancel_check_seconds, watch.done, watch.stopped, self._stopping
            )

    async def _follow(self, watch: _Watch, container_id: str) -> None:
        """Follow the container's output to its end. A stream that ended or broke off while the
        container runs is followed again; Docker replays it from the start, so the lines seen
        already are skipped."""
        seen = 0
        warned = False
        while True:
            count = 0
            try:
                async for line in self._docker.follow_logs(container_id):
                    count += 1
                    if count > seen:
                        seen = count
                        await self._on_line(watch, line)
            except NotFound:
                return
            except DockerError as exc:
                problem = f"broke off ({exc})"
            else:
                # It ends when the container stops: give the wait a moment to say so.
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(watch.stopped.wait(), FOLLOW_RETRY_SECONDS)
                if watch.stopped.is_set():
                    return
                problem = "ended early"
            if not warned:  # once: Docker may be unreachable for a while
                log.warning("job %s: its log stream %s; following again", watch.job.id, problem)
                warned = True
            await asyncio.sleep(FOLLOW_RETRY_SECONDS)

    async def _on_line(self, watch: _Watch, line: LogLine) -> None:
        record = watch.output.feed(line)
        if isinstance(record, Epoch):
            if record.ordinal > watch.epochs_reported:
                await self._report_epoch(watch, record)
        elif isinstance(record, Step):
            watch.progress = record.record
            if time.monotonic() >= watch.progress_due:
                await self._write_progress(watch)
        elif isinstance(record, Done):
            watch.exit_code = record.exit_code
            watch.done_at = datetime.now(UTC)
            watch.done.set()

    async def _report_epoch(self, watch: _Watch, epoch: Epoch) -> None:
        job = watch.job
        payload = {
            "stage": watch.stage,
            "job_id": str(job.id),
            "kind": job.kind.value,
            "ordinal": job.ordinal,
            "epoch": epoch.record.get("epoch"),
            "train": epoch.record.get("train"),
            "val": epoch.record.get("val"),
        }
        try:
            async with self._sessions() as session:
                sent = await queue.report_epoch(session, job.id, job.run_id, epoch.ordinal, payload)
        except (SQLAlchemyError, OSError) as exc:
            log.warning("job %s: could not report epoch record %d: %s", job.id, epoch.ordinal, exc)
            return
        watch.epochs_reported = epoch.ordinal
        if sent:
            await self._wake(job.run_id)

    async def _write_progress(self, watch: _Watch) -> None:
        progress = watch.progress
        if progress is None:
            return
        try:
            async with self._sessions() as session:
                await queue.record_progress(session, watch.job.id, progress)
        except (SQLAlchemyError, OSError) as exc:
            log.warning("job %s: could not write its progress: %s", watch.job.id, exc)
            return
        watch.progress = None
        watch.progress_due = time.monotonic() + PROGRESS_SECONDS

    async def _wait_stopped(self, watch: _Watch, container_id: str) -> None:
        warned = False
        while True:
            try:
                await self._docker.wait_container(container_id)
            except NotFound:
                pass  # removed: as stopped as it gets
            except DockerError as exc:
                if not warned:
                    log.warning("job %s: could not wait for its container: %s", watch.job.id, exc)
                    warned = True
                await asyncio.sleep(FOLLOW_RETRY_SECONDS)
                continue
            watch.stopped.set()
            return

    async def _collect(self, job: GpuJob, container_id: str, root: Path) -> ExtractReport | None:
        """Copy the outputs out of the running container's output volume into the job's out/
        folder; None when they could not be copied. They are gone once the container stops, so
        a Docker that can't be reached for a moment is tried again."""
        tar = root / "out.tar"
        max_bytes = (self._settings.sandbox_out_mb + ARCHIVE_SLACK_MB) * MIB
        try:
            for attempt in itertools.count(1):
                try:
                    await self._docker.download_archive(
                        container_id, OUT_DIR, tar, max_bytes=max_bytes
                    )
                    break
                except DockerError as exc:
                    if exc.status != 0 or attempt >= COLLECT_ATTEMPTS:
                        raise
                    log.warning("job %s: copying its outputs again: %s", job.id, exc)
                    await asyncio.sleep(RETRY_SECONDS)
            return await asyncio.to_thread(_extract, tar, root / "out")
        except (DockerError, ArchiveError, OSError) as exc:
            log.warning("job %s: could not copy its outputs: %s", job.id, exc)
            return None
        finally:
            with contextlib.suppress(OSError):
                tar.unlink(missing_ok=True)

    async def _end_container(self, container_id: str, outcome: _Outcome) -> None:
        """After ARP-DONE the outputs are copied: kill. A cancel or a timeout: SIGTERM first, so
        harness.job stops the training, then SIGKILL after the grace period."""
        try:
            if outcome is _Outcome.DONE:
                await self._docker.kill_container(container_id)
            elif outcome in (_Outcome.CANCELLED, _Outcome.TIMEOUT):
                await self._docker.stop_container(
                    container_id, grace_seconds=self._settings.stop_grace_seconds
                )
        except DockerError as exc:
            log.warning("could not stop container %s: %s", container_id, exc)

    async def _inspect(self, container_id: str) -> ContainerState | None:
        try:
            return await self._docker.inspect_container(container_id)
        except DockerError as exc:
            log.warning("could not inspect container %s: %s", container_id, exc)
            return None

    async def _end(
        self,
        watch: _Watch,
        outcome: _Outcome,
        root: Path,
        state: ContainerState | None,
        report: ExtractReport | None,
        started_at: datetime,
    ) -> queue.Finish:
        job = watch.job
        results = None
        if report is not None and RESULTS_FILE in report.copied:
            results = await asyncio.to_thread(_read_results, root / "out" / RESULTS_FILE)
        exit_code = watch.exit_code
        if exit_code is None and state is not None:
            exit_code = state.exit_code
        oom = state is not None and state.oom_killed
        status, error_code, error = self._verdict(job, outcome, results, oom, exit_code)
        if report is not None and report.skipped:
            # agentic_core.gpu_jobs.OUTPUT_FILES: a file left behind is noted in the job's error.
            skipped = "; ".join(f"{path} ({why})" for path, why in sorted(report.skipped.items()))
            note = f"Not copied: {skipped}"
            error = f"{error}. {note}" if error else note
        return queue.Finish(
            status,
            error_code=error_code,
            error=clean_text(error) if error is not None else None,
            result=results,
            exit_code=exit_code,
            gpu_seconds=_gpu_seconds(state, started_at, watch.done_at),
            provenance=await self._provenance(job, root, state, results, report),
            log_tail=watch.output.tail or None,
            progress=watch.progress,
        )

    def _verdict(
        self,
        job: GpuJob,
        outcome: _Outcome,
        results: dict[str, Any] | None,
        oom: bool,
        exit_code: int | None,
    ) -> tuple[GpuJobStatus, str | None, str | None]:
        """The job's status, error code and error."""
        memory = f"the container's {self._settings.sandbox_memory_mb} MiB memory limit"
        if outcome is _Outcome.CANCELLED:
            return GpuJobStatus.CANCELLED, None, None
        if outcome is _Outcome.TIMEOUT:
            limit = _limit_seconds(job, self._settings)
            return GpuJobStatus.TIMEOUT, None, f"Stopped at the job's time limit of {limit} s"
        if outcome is _Outcome.STOPPED:
            if oom:
                return (
                    GpuJobStatus.FAILED,
                    JOB_OOM_KILLED,
                    f"Killed by {memory} (exit code {exit_code}); its outputs are lost",
                )
            return (
                GpuJobStatus.FAILED,
                JOB_LOST,
                f"The container stopped (exit code {exit_code}) before its outputs were copied",
            )
        if results is None:
            if oom:
                return (
                    GpuJobStatus.FAILED,
                    JOB_OOM_KILLED,
                    f"Training was killed by {memory} (exit code {exit_code}): no results.json",
                )
            return (
                GpuJobStatus.FAILED,
                JOB_NO_RESULT,
                f"Training ended (exit code {exit_code}) without a results.json",
            )
        if results.get("status") == "ok":
            return GpuJobStatus.SUCCEEDED, None, None
        code = results.get("error_code")
        error = results.get("error")
        return (
            GpuJobStatus.FAILED,
            code[:ERROR_CODE_MAX] if isinstance(code, str) and code else TRAIN_ERROR,
            str(error) if error is not None else None,
        )

    async def _provenance(
        self,
        job: GpuJob,
        root: Path,
        state: ContainerState | None,
        results: dict[str, Any] | None,
        report: ExtractReport | None,
    ) -> dict[str, Any]:
        """What ran: the image, the exact inputs as mounted, the dataset, the seed and the GPU."""
        dataset = None
        try:
            async with self._sessions() as session:
                dataset = await session.get(Dataset, job.dataset)
        except (SQLAlchemyError, OSError) as exc:
            log.warning("job %s: could not read its dataset: %s", job.id, exc)
        code_sha256, config_sha256 = await asyncio.to_thread(_input_hashes, root)
        harness = results.get("provenance") if results is not None else None
        harness = harness if isinstance(harness, dict) else None
        device = harness.get("device") if harness is not None else None
        if not isinstance(device, str):
            device = self._sample.name if self._sample is not None else None
        seed = harness.get("seed") if harness is not None else None
        if seed is None and isinstance(job.config, dict):
            seed = job.config.get("seed")
        provenance: dict[str, Any] = {
            "image": self._settings.sandbox_image,
            "image_id": state.image_id if state is not None else None,
            "code_sha256": code_sha256,
            "config_sha256": config_sha256,
            "dataset": {
                "name": job.dataset,
                "version": dataset.version if dataset is not None else None,
                "checksum": dataset.checksum if dataset is not None else None,
            },
            "seed": seed,
            "gpu": device,
            "harness": harness,
        }
        if report is not None and report.copied:
            provenance["outputs"] = report.copied
        if report is not None and report.skipped:
            provenance["outputs_skipped"] = report.skipped
        return provenance

    async def _finish(self, job: GpuJob, end: queue.Finish, container_id: str | None) -> None:
        """Record the job's end, then remove its container: a crash in between leaves a finished
        job whose container the reaper removes."""
        written = await self._write_end(job, end)
        if written is None:
            return  # stopping while Postgres is down: recover() puts the job right
        if written:
            code = f" ({end.error_code})" if end.error_code else ""
            log.info("job %s (%s): %s%s", job.id, job.kind.value, end.status.value, code)
        else:
            log.warning("job %s ended elsewhere; its end here (%s) is dropped", job.id, end.status)
        if container_id is not None:
            await self._remove_quietly(container_id)

    async def _write_end(self, job: GpuJob, end: queue.Finish) -> bool | None:
        """queue.finish, waiting out a Postgres that is down (None if stop() came first). An end
        Postgres refuses outright is recorded without its details."""
        delay = 1.0
        while True:
            try:
                async with self._sessions() as session:
                    return await queue.finish(session, job.id, end)
            except DB_UNAVAILABLE as exc:
                if self._stopping.is_set():
                    log.warning("job %s: could not record its end: %s", job.id, exc)
                    return None
                log.warning(
                    "job %s: could not record its end (%s); trying again in %.0f s",
                    job.id,
                    exc,
                    delay,
                )
                await self.wait_stopped(delay)
                delay = min(delay * 2, FINISH_RETRY_MAX_SECONDS)
            except SQLAlchemyError:
                log.exception("job %s: its end was refused; recording it without details", job.id)
                async with self._sessions() as session:
                    return await queue.finish(session, job.id, end.bare())

    async def _abandon(self, job: GpuJob, exc: Exception) -> None:
        """After an unexpected error: end the job failed and free the GPU, as far as possible."""
        name = container_name(job.id)
        with contextlib.suppress(DockerError):
            await self._docker.kill_container(name)
        end = queue.Finish(
            GpuJobStatus.FAILED,
            error_code=JOB_LOST,
            error=clean_text(f"The executor failed while running the job: {exc!r}"),
        )
        try:
            async with self._sessions() as session:
                await queue.finish(session, job.id, end)
        except Exception as write_exc:
            log.warning("job %s: could not record its failure (%s)", job.id, write_exc)
            self._needs_recovery = True  # it ends lost or queued again, not running forever
        await self._remove_quietly(name)

    async def _discard(self, container: str) -> None:
        with contextlib.suppress(DockerError):
            await self._docker.kill_container(container)
        await self._remove_quietly(container)

    async def _remove_quietly(self, container: str) -> None:
        try:
            await self._docker.remove_container(container)
        except DockerError as exc:
            log.warning("could not remove container %s: %s", container[:20], exc)

    async def _wake(self, run_id: uuid.UUID) -> None:
        try:
            await asyncio.wait_for(
                self._valkey.publish(events_channel(run_id), "1"), WAKE_TIMEOUT_SECONDS
            )
        except Exception:  # SSE falls back to polling; never fail or stall a job over a wake-up
            log.warning("could not publish wake-up for run %s", run_id)

    # recover()

    async def _requeue(self, job: GpuJob, containers: list[ContainerSummary]) -> None:
        """A job the last executor claimed but never got running starts over."""
        for container in containers:
            await self._docker.remove_container(container.name)
        async with self._sessions() as session:
            status = await queue.requeue(session, job.id)
        if status is not None:
            log.info("job %s (%s): %s after a restart", job.id, job.kind.value, status.value)

    async def _still_running(
        self, job: GpuJob, containers: list[ContainerSummary]
    ) -> tuple[str, ContainerState] | None:
        """A running job's container (by name), if it runs still. If it stopped or vanished,
        the job ends failed: its outputs were in the container's tmpfs volume."""
        chosen = next(
            (container for container in containers if container.id == job.container_id),
            containers[0] if containers else None,
        )
        for extra in containers:
            if extra is not chosen:
                await self._docker.remove_container(extra.name)
        state = None
        if chosen is not None:
            with contextlib.suppress(NotFound):
                state = await self._docker.inspect_container(chosen.name)
        if chosen is not None and state is not None and state.state == "running":
            return chosen.name, state
        if chosen is None or state is None:
            end = queue.Finish(
                GpuJobStatus.FAILED,
                error_code=JOB_LOST,
                error="The job's container is gone",
            )
        else:
            end = queue.Finish(
                GpuJobStatus.FAILED,
                error_code=JOB_OOM_KILLED if state.oom_killed else JOB_LOST,
                error=(
                    f"The container stopped (exit code {state.exit_code}) while no executor "
                    "watched it; its outputs went with it"
                ),
                exit_code=state.exit_code,
                gpu_seconds=_gpu_seconds(state, job.started_at, None) if job.started_at else None,
                log_tail=await self._replay_tail(job, chosen.name),
            )
        await self._finish(job, end, chosen.name if chosen is not None else None)
        return None

    async def _replay_tail(self, job: GpuJob, container_id: str) -> str | None:
        """The output of a container that stopped unwatched: log.txt again, and its tail."""
        root = job_dir(self._data_dir, job.id)
        root.mkdir(parents=True, exist_ok=True)
        output = JobOutput(root / LOG_FILE)
        try:
            async with asyncio.timeout(DRAIN_SECONDS):
                async for line in self._docker.follow_logs(container_id):
                    output.feed(line)
        except (TimeoutError, DockerError) as exc:
            log.warning("job %s: could not read its output: %s", job.id, exc)
        finally:
            output.close()
        return output.tail or None

    # Beside the jobs

    async def _idle(self) -> None:
        """Wait poll_seconds; every REAP_SECONDS, remove stray containers first."""
        if time.monotonic() >= self._reap_at:
            self._reap_at = time.monotonic() + REAP_SECONDS
            try:
                await self.reap()
            except (DockerError, SQLAlchemyError, OSError) as exc:
                log.warning("could not remove stray containers: %s", exc)
        await self.wait_stopped(self._settings.poll_seconds)

    async def _vram_free(self) -> bool:
        """The VRAM preflight: whether min_free_vram_mb is free on the GPU. Without a reading
        (no nvidia-smi) jobs start anyway."""
        sample = await self._read_gpu()
        if sample is None:
            if not self._warned_no_gpu:
                log.warning("nvidia-smi gave no reading: jobs start without the VRAM preflight")
                self._warned_no_gpu = True
            self._waiting_for_vram = None
            return True
        needed = self._settings.min_free_vram_mb
        if sample.memory_free_mb >= needed:
            self._waiting_for_vram = None
            return True
        self._waiting_for_vram = {"free_mb": sample.memory_free_mb, "needed_mb": needed}
        now = time.monotonic()
        if self._vram_logged_at is None or now - self._vram_logged_at >= VRAM_LOG_SECONDS:
            self._vram_logged_at = now
            log.info(
                "waiting for VRAM: %d MiB free on %s, %d MiB needed",
                sample.memory_free_mb,
                sample.name,
                needed,
            )
        return False

    async def _read_gpu(self) -> GpuSample | None:
        sample = await self._gpu.sample()
        if sample is not None:
            self._sample = sample
        return sample

    async def _heartbeat(self) -> None:
        """The executor.status setting, every HEARTBEAT_SECONDS: the queue page shows it."""
        while not self._stopping.is_set():
            try:
                sample = await self._read_gpu()
                value = {
                    "alive_at": datetime.now(UTC).isoformat(),
                    "gpu": _sample_json(sample) if sample is not None else None,
                    "job_id": str(self._job_id) if self._job_id is not None else None,
                    "waiting_for_vram": self._waiting_for_vram,
                }
                async with self._sessions() as session:
                    await queue.write_status(session, value)
            except Exception as exc:
                log.warning("could not write the heartbeat: %s", exc)
            await self.wait_stopped(HEARTBEAT_SECONDS)

    async def _checksum_datasets(self) -> None:
        """Each enabled dataset's manifest checksum, for the jobs' provenance. It walks the whole
        folder (slow on a Windows drive), so it runs in a thread beside the jobs."""
        cancelled = threading.Event()
        try:
            async with self._sessions() as session:
                datasets = await queue.enabled_datasets(session)
            for dataset in datasets:
                folder, _source = self._dataset_folder(dataset.name, dataset.host_path)
                if folder is None or not await asyncio.to_thread(folder.is_dir):
                    continue
                checksum = await asyncio.to_thread(manifest_checksum, folder, cancelled)
                async with self._sessions() as session:
                    await queue.record_checksum(session, dataset.name, checksum)
                log.info("dataset %s: manifest checksum %s", dataset.name, checksum[:16])
        except asyncio.CancelledError:
            cancelled.set()  # the thread stops at its next folder
            raise
        except Exception as exc:
            log.warning("could not compute the dataset checksums: %s", exc)


def write_job_files(root: Path, code: object, config: object, dataset: str) -> None:
    """Write a job's files under ``root`` from scratch: code/ (the sources, checked once more),
    config.json (the job's config with the executor's paths) and an empty log.txt. The sandbox
    user reads them, so folders are 0755 and files 0644. Raises _CannotRun when the code or the
    config can't run, or the files can't be written."""
    sources = _sources(code)
    for name in sorted(sources, key=lambda name: name != MODEL_FILE):  # as the harness loads them
        findings = check_module(sources[name], filename=name)
        if findings:
            detail = "; ".join(f"{f.code} line {f.line}: {f.message}" for f in findings)
            error = f"{name} refused by the allowlist: {detail}"
            raise _CannotRun(
                CODE_REFUSED,
                error,
                {
                    "status": "failed",
                    "error_code": CODE_REFUSED,
                    "error": error,
                    "findings": [
                        {"line": f.line, "code": f.code, "message": f.message} for f in findings
                    ],
                },
            )
    job_config = _job_config(config, dataset)
    try:
        if root.exists():
            shutil.rmtree(root)
        code_dir = root / "code"
        for folder in (root, code_dir):
            folder.mkdir(parents=True)
            folder.chmod(0o755)
        for name, source in sources.items():
            _write_file(code_dir / name, source.encode())
        config_text = json.dumps(job_config, indent=2, sort_keys=True)
        _write_file(root / "config.json", config_text.encode())
        _write_file(root / LOG_FILE, b"")
    except OSError as exc:
        raise _CannotRun(JOB_START_FAILED, f"Could not write the job's files: {exc}") from exc


def manifest_checksum(root: Path, cancelled: threading.Event | None = None) -> str:
    """sha256 of a dataset folder's file list: the path under ``root`` and the size of each
    regular file, in path order, each followed by a NUL. Symlinks are skipped, so the checksum
    covers only what the folder holds. Raises ChecksumCancelled once ``cancelled`` is set."""
    entries: list[tuple[bytes, int]] = []
    for folder, _subfolders, files in os.walk(root):  # never into symlinked folders
        if cancelled is not None and cancelled.is_set():
            raise ChecksumCancelled
        for name in files:
            path = Path(folder) / name
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISREG(info.st_mode):
                entries.append((os.fsencode(path.relative_to(root).as_posix()), info.st_size))
    digest = hashlib.sha256()
    for relative, size in sorted(entries):
        digest.update(relative + b"\0" + str(size).encode() + b"\0")
    return digest.hexdigest()


def _sources(code: object) -> dict[str, str]:
    """The job's source files by name, as agentic_core.gpu_jobs allows them."""
    if not isinstance(code, dict):
        raise _CannotRun(JOB_BAD_INPUT, "The job's code is not a mapping of file names to sources")
    unknown = sorted(str(name) for name in code if name not in CODE_FILES)
    if unknown:
        allowed = ", ".join(sorted(CODE_FILES))
        raise _CannotRun(
            JOB_BAD_INPUT, f"The job's code may hold only {allowed}, not {', '.join(unknown)}"
        )
    if MODEL_FILE not in code:
        raise _CannotRun(JOB_BAD_INPUT, f"The job's code has no {MODEL_FILE}")
    sources: dict[str, str] = {}
    for name, source in code.items():
        if not isinstance(source, str):
            raise _CannotRun(JOB_BAD_INPUT, f"The job's {name} is not text")
        if len(source.encode()) > MAX_SOURCE_BYTES:
            raise _CannotRun(JOB_BAD_INPUT, f"The job's {name} is over {MAX_SOURCE_BYTES} bytes")
        sources[name] = source
    return sources


def _job_config(config: object, dataset: str) -> dict[str, Any]:
    """The job's config with the paths the executor owns: its code's and its dataset's mounts."""
    if not isinstance(config, dict):
        raise _CannotRun(JOB_BAD_INPUT, "The job's config is not a JSON object")
    sections: dict[str, dict[str, Any]] = {}
    for name in ("model", "data"):
        section = config.get(name, {})
        if not isinstance(section, dict):
            raise _CannotRun(JOB_BAD_INPUT, f"The job's config.{name} is not a JSON object")
        sections[name] = section
    return {
        **config,
        "model": {**sections["model"], "code_dir": CODE_MOUNT},
        "data": {**sections["data"], "root": f"{DATA_ROOT}/{dataset}"},
    }


def _write_file(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    os.fchmod(fd, 0o644)  # whatever the umask
    with os.fdopen(fd, "wb") as file:
        file.write(data)


def _input_hashes(root: Path) -> tuple[dict[str, str], str | None]:
    """sha256 of the code files and the config as the container mounted them."""
    code: dict[str, str] = {}
    config_sha256 = None
    try:
        for name in sorted(CODE_FILES):
            path = root / "code" / name
            if path.is_file():
                code[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        config = root / "config.json"
        if config.is_file():
            config_sha256 = hashlib.sha256(config.read_bytes()).hexdigest()
    except OSError as exc:
        log.warning("could not hash the inputs under %s: %s", root, exc)
    return code, config_sha256


def _extract(tar: Path, out: Path) -> ExtractReport:
    shutil.rmtree(out, ignore_errors=True)  # an earlier copy's, from before a restart
    return extract_outputs(tar, out)


def _read_results(path: Path) -> dict[str, Any] | None:
    """results.json as copied out of the container: untrusted, so a JSON object or None."""
    try:
        value = json.loads(path.read_bytes())
    except (OSError, ValueError, RecursionError):
        return None
    return jsonable(value) if isinstance(value, dict) else None


def _limit_seconds(job: GpuJob, settings: ExecutorSettings) -> int:
    """The job's wall clock: what it asked for, within its kind's limit."""
    return min(job.timeout_seconds, max_timeout_seconds(job.kind, settings.max_train_hours))


def _gpu_seconds(
    state: ContainerState | None, started_at: datetime, done_at: datetime | None
) -> float:
    """From the container's start to ARP-DONE, or else to the container's end."""
    start = state.started_at if state is not None and state.started_at else started_at
    end = done_at
    if end is None:
        end = state.finished_at if state is not None and state.finished_at else datetime.now(UTC)
    return round(max((end - start).total_seconds(), 0.0), 3)


def _sample_json(sample: GpuSample) -> dict[str, Any]:
    return {**asdict(sample), "sampled_at": sample.sampled_at.isoformat()}


def _job_id(label: str | None) -> uuid.UUID | None:
    try:
        return uuid.UUID(label) if label else None
    except ValueError:
        return None


async def _first(seconds: float, *events: asyncio.Event) -> None:
    """Wait until one of ``events`` is set, ``seconds`` at most."""
    waiters = [asyncio.ensure_future(event.wait()) for event in events]
    try:
        await asyncio.wait(waiters, timeout=seconds, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for waiter in waiters:
            waiter.cancel()

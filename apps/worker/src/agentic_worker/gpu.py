"""A stage attempt's GPU jobs: submit one once, wait for the executor to run it, read its end.

docs/design/experiments.md ("The stages"). A job is found again by (stage_run_id, kind, ordinal),
so an activity that runs again after a crash or a timeout waits on the job it submitted before
instead of queueing a second one, and the coding stage's tries replay in order.

Only a cancel of the run stops a job: the activity then cancels it and waits until the executor
has stopped it, so the run closes once the container is gone (the workflow waits for that,
WAIT_CANCELLATION_COMPLETED). An activity that times out, is paused or whose worker shuts down
leaves its job running, for the next try of the activity to wait on.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio import activity

from agentic_core.enums import GpuJobKind, GpuJobStatus
from agentic_core.gpu_jobs import MAX_QUEUED_PER_USER
from agentic_db.gpu_jobs import JobRequest, find_job, request_cancel, submit_job
from agentic_db.lab_settings import EXECUTOR_STATUS_KEY
from agentic_db.models import Dataset, GpuJob, Setting
from agentic_worker.progress import ProgressLines
from agentic_worker.stages import StageContext, StageFailedError

log = logging.getLogger(__name__)

POLL_SECONDS = 2.0
# The executor writes its heartbeat every 5 s: one this old means it is not running.
EXECUTOR_STALE = timedelta(seconds=60)
# The executor stops a cancelled job within 5 s; past this the cancel is left to it.
CANCEL_WAIT_SECONDS = 20.0

# Progress lines (codes the web translates; params as below).
QUEUE_FULL = "gpu.queue_full"  # {kind, limit}
QUEUED = "gpu.queued"  # {kind, ordinal}
EXECUTOR_DOWN = "gpu.executor_down"  # {}
STARTED = "gpu.started"  # {kind, ordinal}


@dataclass(frozen=True)
class HarnessDataset:
    """How the harness trains on a dataset (sandbox/pytorch/harness/config.py)."""

    task: str
    split_file_template: str | None


# The datasets the harness can train on, by their registered name.
HARNESS_DATASETS = {
    "nyu2": HarnessDataset(task="nyu2_depth", split_file_template="{root}/splits/nyu/{split}.txt")
}


def harness_config(
    dataset: str,
    *,
    model_kwargs: dict[str, int | float | str | bool],
    loss: str,
    training: dict[str, Any],
    batch_size: int,
    epochs: int,
    max_train_steps: int | None,
    max_val_steps: int | None,
    seed: int = 42,
) -> dict[str, Any]:
    """An ExperimentConfig for the harness, as JSON. ``training`` holds the coding stage's
    choices (learning_rate, optimizer, weight_decay, clip_grad_norm). The executor sets the code
    and data paths itself."""
    harness = HARNESS_DATASETS[dataset]
    data: dict[str, Any] = {"dataset": dataset, "batch_size": batch_size, "num_workers": 2}
    if harness.split_file_template is not None:
        data["split_file_template"] = harness.split_file_template
    return {
        "task": harness.task,
        "seed": seed,
        "require_gpu": True,
        "model": {"architecture": "generated", "kwargs": dict(model_kwargs)},
        "data": data,
        "training": {
            **training,
            "loss": loss,
            "epochs": epochs,
            "max_train_steps": max_train_steps,
            "max_val_steps": max_val_steps,
        },
    }


@dataclass(frozen=True)
class JobSpec:
    """One job of a stage attempt. (kind, ordinal) names it within the attempt."""

    kind: GpuJobKind
    ordinal: int
    dataset: str
    code: dict[str, str]  # file name to source
    config: dict[str, Any]  # harness_config()
    timeout_seconds: int


def run_cancel_requested() -> bool:
    """Whether the activity was cancelled because the run was (or its workflow is gone), rather
    than timed out, paused, reset or stopped with its worker. Outside an activity a cancel is a
    cancel."""
    try:
        details = activity.cancellation_details()
    except RuntimeError:  # not in an activity: tests and scripts
        return True
    return details is not None and (details.cancel_requested or details.not_found)


class GpuJobs:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        poll_seconds: float = POLL_SECONDS,
        cancel_wait_seconds: float = CANCEL_WAIT_SECONDS,
        cancels_job: Callable[[], bool] = run_cancel_requested,
    ) -> None:
        self._sessions = sessions
        self._poll_seconds = poll_seconds
        self._cancel_wait_seconds = cancel_wait_seconds
        self._cancels_job = cancels_job

    async def dataset(self, name: str | None) -> Dataset | None:
        """The registered, enabled dataset ``name`` the harness can train on, if there is one."""
        if name is None or name not in HARNESS_DATASETS:
            return None
        async with self._sessions() as session:
            dataset = await session.get(Dataset, name)
        return dataset if dataset is not None and dataset.enabled else None

    async def run(self, ctx: StageContext, spec: JobSpec, lines: ProgressLines) -> GpuJob:
        """The job's row once it has ended (succeeded, failed, timeout or cancelled), submitting
        it first unless the attempt did so before."""
        try:
            job_id = await self._submit(ctx, spec, lines)
            return await self._ended(ctx, job_id, spec, lines)
        except asyncio.CancelledError:
            if self._cancels_job():
                # Found by its name, not its id: the cancel may come as the submit commits.
                async with self._sessions() as session:
                    job = await find_job(
                        session, uuid.UUID(ctx.stage_run_id), spec.kind, spec.ordinal
                    )
                if job is not None:
                    await self._cancel(job.id)
            raise

    async def _submit(self, ctx: StageContext, spec: JobSpec, lines: ProgressLines) -> uuid.UUID:
        """Queue the job, waiting while the user has MAX_QUEUED_PER_USER jobs queued already."""
        request = JobRequest(
            stage_run_id=uuid.UUID(ctx.stage_run_id),
            run_id=uuid.UUID(ctx.run_id),
            user_id=ctx.owner_id,
            kind=spec.kind,
            ordinal=spec.ordinal,
            dataset=spec.dataset,
            code=spec.code,
            config=spec.config,
            timeout_seconds=spec.timeout_seconds,
        )
        waiting = False
        while True:
            async with self._sessions() as session:
                job = await submit_job(session, request)
                await session.commit()
            if job is not None:
                return job.id
            if not waiting:
                waiting = True
                await lines.say(
                    QUEUE_FULL,
                    {"kind": spec.kind.value, "limit": MAX_QUEUED_PER_USER},
                    f"Waiting: {MAX_QUEUED_PER_USER} of your GPU jobs are queued already",
                )
            await asyncio.sleep(self._poll_seconds)

    async def _ended(
        self, ctx: StageContext, job_id: uuid.UUID, spec: JobSpec, lines: ProgressLines
    ) -> GpuJob:
        said: set[str] = set()
        params = {"kind": spec.kind.value, "ordinal": spec.ordinal}
        while True:
            async with self._sessions() as session:
                job = await session.get(GpuJob, job_id)
                alive = await executor_alive(session)
            if job is None:  # its run was deleted under the attempt
                raise StageFailedError(f"{ctx.stage}.job_gone: the job's row is gone")
            if job.status.is_terminal:
                return job
            if job.status is GpuJobStatus.RUNNING and STARTED not in said:
                said.add(STARTED)
                await lines.say(STARTED, params, f"{_name(spec)} running on the GPU")
            elif QUEUED not in said and STARTED not in said:
                said.add(QUEUED)
                await lines.say(QUEUED, params, f"{_name(spec)} queued for the GPU")
            if not alive and EXECUTOR_DOWN not in said:
                said.add(EXECUTOR_DOWN)
                await lines.say(
                    EXECUTOR_DOWN, {}, "The GPU executor is not running; the job waits for it"
                )
            await asyncio.sleep(self._poll_seconds)

    async def _cancel(self, job_id: uuid.UUID) -> None:
        """Cancel the job and wait, a little, until the executor has stopped it."""
        loop = asyncio.get_running_loop()
        try:
            async with self._sessions() as session:
                status = await request_cancel(session, job_id)
                await session.commit()
            deadline = loop.time() + self._cancel_wait_seconds
            while status is not None and not status.is_terminal and loop.time() < deadline:
                await asyncio.sleep(min(self._poll_seconds, 0.5))
                async with self._sessions() as session:
                    status = await session.scalar(select(GpuJob.status).where(GpuJob.id == job_id))
            if status is not None and not status.is_terminal:
                log.warning(
                    "job %s: still %s after its cancel; the executor stops it", job_id, status
                )
        except Exception:  # the run is cancelled either way; the executor still gets the cancel
            log.warning("job %s: could not cancel it", job_id, exc_info=True)


def _name(spec: JobSpec) -> str:
    return f"Smoke test {spec.ordinal}" if spec.kind is GpuJobKind.SMOKE else "Training"


async def executor_status(session: AsyncSession) -> dict[str, Any] | None:
    """The executor's latest heartbeat (agentic_db.lab_settings.EXECUTOR_STATUS_KEY), if any."""
    status = await session.get(Setting, EXECUTOR_STATUS_KEY)
    return status.value if status is not None else None


async def executor_alive(session: AsyncSession) -> bool:
    """Whether the executor's heartbeat is recent: it writes one every few seconds."""
    status = await executor_status(session)
    alive_at = status.get("alive_at") if status is not None else None
    if not isinstance(alive_at, str):
        return False
    try:
        seen = datetime.fromisoformat(alive_at)
    except ValueError:
        return False
    return datetime.now(UTC) - seen < EXECUTOR_STALE

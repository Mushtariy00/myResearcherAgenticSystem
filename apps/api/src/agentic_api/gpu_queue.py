"""The lab GPU's queue as the queue page shows it (docs/design/experiments.md, "GPU jobs").

The jobs come from ``gpu_jobs``: the starting and running ones (on the GPU; the executor runs one
at a time) and the queued ones, in the order the executor claims them: smoke tests before
training runs, then the oldest first. The GPU's readings come from the executor's heartbeat, and
only while it is recent: an executor that stopped reporting shows none, and its queue waits.

A running job's progress is its latest training step record against the steps its config plans,
and its ETA extrapolates the time it has run so far. Before its first record, and for every
queued job, both are guesses from the job's kind and plan (``estimated``); queued jobs start one
after the other, each when the job before it is expected to finish.
"""

import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_api.auth import CurrentUser
from agentic_api.authz import member_projects
from agentic_api.datasets import TRAIN_SPLIT, split_counts
from agentic_api.schemas import GpuJobOut, GpuOut, GpuQueueOut
from agentic_api.users import users_by_id
from agentic_core.enums import GpuJobKind, GpuJobStatus
from agentic_core.gpu_jobs import MAX_QUEUED_PER_USER
from agentic_db.lab_settings import EXECUTOR_STATUS_KEY
from agentic_db.models import Dataset, GpuJob, Project, Run, Setting

log = logging.getLogger(__name__)

CONCURRENCY = 1  # the executor runs one job at a time
# The executor writes its heartbeat every 5 s: one this old means it is not running (the rule of
# agentic_worker.gpu.executor_alive).
EXECUTOR_STALE = timedelta(seconds=60)
# Guessed lengths: a smoke test is a dry run of a few batches; a training run takes the steps its
# config plans at a few steps a second, or TRAIN_TYPICAL when the config doesn't say.
SMOKE_TYPICAL = timedelta(minutes=2)
TRAIN_STEPS_PER_SECOND = 3.0
TRAIN_TYPICAL = timedelta(minutes=30)
# A running job never shows as done: its last steps, its validation and the copy of its outputs
# are still to come.
MAX_PROGRESS = 0.99
MAX_GUESSED_PROGRESS = 0.95
MIN_REMAINING = timedelta(seconds=10)
# Far more than the queue holds: each user has at most MAX_QUEUED_PER_USER jobs queued.
MAX_JOBS = 200
_ACTIVE = (GpuJobStatus.STARTING, GpuJobStatus.RUNNING)


@dataclass(frozen=True)
class Plan:
    """How long a job trains, as its config says: epochs, and the steps of each (None: unknown)."""

    epochs: int | None
    steps_per_epoch: int | None

    @property
    def total_steps(self) -> int | None:
        if self.epochs is None or self.steps_per_epoch is None:
            return None
        return self.epochs * self.steps_per_epoch


@dataclass(frozen=True)
class Step:
    """A job's latest training step record (agentic_executor.logs.Step), both counted from 0."""

    epoch: int
    step: int


@dataclass(frozen=True)
class QueueEntry:
    """A job on the GPU or waiting for it. ``run_id``, ``topic`` and ``project_name`` are None
    when the caller may not open the run; ``owner_name`` once the account no longer exists."""

    id: uuid.UUID
    kind: GpuJobKind
    active: bool  # starting or running: it holds the GPU
    owner_id: str  # whose queue share it counts against
    owner_name: str | None
    run_id: uuid.UUID | None
    topic: str | None
    project_name: str | None
    dataset: str
    plan: Plan
    step: Step | None
    submitted_at: datetime
    started_at: datetime | None  # None until its container started
    timeout_seconds: int  # the executor stops it then


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _whole(value: object, minimum: int) -> int | None:
    """A JSON whole number of at least ``minimum`` (booleans are not numbers here)."""
    if isinstance(value, int) and not isinstance(value, bool) and value >= minimum:
        return value
    return None


def job_plan(config: object, dataset_details: object) -> Plan:
    """The training a job's config (the harness's ExperimentConfig, as the worker submitted it)
    plans: training.epochs, and per epoch training.max_train_steps or, without that cap, the
    batches of the dataset's training split (the harness drops a last, partial batch); the
    fewer of the two when both are known, since an epoch also ends with its split. A value that
    is missing or malformed is unknown."""
    training = _mapping(_mapping(config).get("training"))
    data = _mapping(_mapping(config).get("data"))
    cap = _whole(training.get("max_train_steps"), 1)
    batch_size = _whole(data.get("batch_size"), 1)
    samples = split_counts(dataset_details).get(TRAIN_SPLIT)
    batches = None
    if samples is not None and batch_size is not None and samples >= batch_size:
        batches = samples // batch_size
    known = [steps for steps in (cap, batches) if steps is not None]
    return Plan(_whole(training.get("epochs"), 1), min(known) if known else None)


def latest_step(progress: object) -> Step | None:
    """The job's progress record ({"kind": "train_step", "epoch", "step", "loss", "ts"}) as a
    Step, if it is one."""
    record = _mapping(progress)
    epoch, step = _whole(record.get("epoch"), 0), _whole(record.get("step"), 0)
    return Step(epoch, step) if epoch is not None and step is not None else None


def done_fraction(step: Step, plan: Plan) -> float | None:
    """The share of its planned steps a job has done once it logged ``step``."""
    total, per_epoch = plan.total_steps, plan.steps_per_epoch
    if total is None or per_epoch is None:
        return None
    done = step.epoch * per_epoch + min(step.step + 1, per_epoch)
    return min(done / total, MAX_PROGRESS)


def typical_duration(kind: GpuJobKind, plan: Plan) -> timedelta:
    """A guess at how long a job runs, before it reports any progress."""
    if kind is GpuJobKind.SMOKE:
        return SMOKE_TYPICAL
    steps = plan.total_steps
    return TRAIN_TYPICAL if steps is None else timedelta(seconds=steps / TRAIN_STEPS_PER_SECOND)


def executor_alive(status: Mapping[str, Any] | None, now: datetime) -> bool:
    """Whether the executor's heartbeat (agentic_db.lab_settings.EXECUTOR_STATUS_KEY) is
    recent."""
    alive_at = status.get("alive_at") if status is not None else None
    if not isinstance(alive_at, str):
        return False
    try:
        seen = datetime.fromisoformat(alive_at)
    except ValueError:
        return False
    if seen.tzinfo is None:  # the executor writes UTC with its offset; read one without as UTC
        seen = seen.replace(tzinfo=UTC)
    return now - seen < EXECUTOR_STALE


def gpu_reading(status: Mapping[str, Any] | None) -> GpuOut | None:
    """The heartbeat's nvidia-smi sample (agentic_executor.ports.GpuSample as JSON), if any."""
    sample = status.get("gpu") if status is not None else None
    if not isinstance(sample, Mapping):
        return None
    try:
        return GpuOut.model_validate({**sample, "demo": False})
    except ValidationError:
        log.warning("the executor's heartbeat holds a GPU sample that does not validate")
        return None


def _limit(entry: QueueEntry) -> timedelta:
    return timedelta(seconds=max(entry.timeout_seconds, 1))


def _out(
    entry: QueueEntry,
    now: datetime,
    caller_id: str,
    *,
    progress: float,
    start: datetime,
    finish: datetime,
    estimated: bool,
) -> GpuJobOut:
    step = entry.step if entry.active else None
    epoch = None if step is None else step.epoch + 1
    if epoch is not None and entry.plan.epochs is not None:
        epoch = min(epoch, entry.plan.epochs)
    return GpuJobOut(
        id=str(entry.id),
        kind="smoke" if entry.kind is GpuJobKind.SMOKE else "train",
        status="running" if entry.active else "queued",
        run_id=entry.run_id,
        topic=entry.topic,
        project_name=entry.project_name,
        owner_name=entry.owner_name,
        is_mine=entry.owner_id == caller_id,
        dataset=entry.dataset,
        progress=round(progress, 3),
        epoch=epoch,
        total_epochs=entry.plan.epochs,
        gpu_memory_mb=None,  # the executor reads the whole GPU's memory, not a job's
        submitted_at=entry.submitted_at,
        started_at=entry.started_at if entry.active else None,
        estimated_start_at=start,
        estimated_finish_at=finish,
        eta_seconds=max(0, round((finish - now).total_seconds())),
        estimated=estimated,
        demo=False,
    )


def _running(entry: QueueEntry, now: datetime, caller_id: str) -> GpuJobOut:
    """On the GPU since started_at (or about to be, while its container is created). Once it
    logged a step, its run so far is extrapolated over the share of its steps that took."""
    begin = entry.started_at or now
    elapsed = max(now - begin, timedelta(0))
    fraction = done_fraction(entry.step, entry.plan) if entry.step is not None else None
    if fraction is not None and elapsed > timedelta(0):
        total = min(elapsed / fraction, _limit(entry))
        progress, estimated = fraction, False
    else:
        total = min(typical_duration(entry.kind, entry.plan), _limit(entry))
        progress, estimated = min(MAX_GUESSED_PROGRESS, elapsed / total), True
    finish = max(begin + total, now + MIN_REMAINING)
    return _out(
        entry, now, caller_id, progress=progress, start=begin, finish=finish, estimated=estimated
    )


def _queued(entry: QueueEntry, start: datetime, now: datetime, caller_id: str) -> GpuJobOut:
    finish = start + min(typical_duration(entry.kind, entry.plan), _limit(entry))
    return _out(entry, now, caller_id, progress=0.0, start=start, finish=finish, estimated=True)


def queue_snapshot(
    now: datetime,
    entries: Sequence[QueueEntry],
    status: Mapping[str, Any] | None,
    caller_id: str,
) -> GpuQueueOut:
    """The queue at ``now``: ``entries`` are the jobs on the GPU, then the queued ones in the
    order they will run; ``status`` is the executor's latest heartbeat, if any."""
    running = [_running(entry, now, caller_id) for entry in entries if entry.active]
    free_at = max((job.estimated_finish_at for job in running), default=now)
    queued: list[GpuJobOut] = []
    for entry in entries:
        if not entry.active:
            queued.append(_queued(entry, free_at, now, caller_id))
            free_at = queued[-1].estimated_finish_at
    alive = executor_alive(status, now)
    mine = [index for index, job in enumerate([*running, *queued]) if job.is_mine]
    position = None
    if mine:  # 0: the caller's job is on the GPU; queue positions count from 1
        position = 0 if mine[0] < len(running) else mine[0] - len(running) + 1
    return GpuQueueOut(
        gpu=gpu_reading(status) if alive else None,
        executor_alive=alive,
        concurrency=CONCURRENCY,
        running=running,
        queued=queued,
        my_position=position,
        my_jobs=len(mine),
        per_user_limit=MAX_QUEUED_PER_USER,
        demo=False,
    )


async def gpu_queue(db: AsyncSession, user: CurrentUser) -> GpuQueueOut:
    """The queue now, as ``user`` may see it: runs in projects they can't open show no run,
    topic or project name."""
    rows = (
        await db.execute(
            select(
                GpuJob.id,
                GpuJob.kind,
                GpuJob.status,
                GpuJob.user_id,
                GpuJob.run_id,
                GpuJob.dataset,
                GpuJob.config,
                GpuJob.progress,
                GpuJob.created_at,
                GpuJob.started_at,
                GpuJob.timeout_seconds,
                Run.topic,
                Project.id.label("project_id"),
                Project.name.label("project_name"),
                Dataset.details.label("dataset_details"),
            )
            .join(Run, Run.id == GpuJob.run_id)
            .join(Project, Project.id == Run.project_id)
            .join(Dataset, Dataset.name == GpuJob.dataset)
            .where(
                or_(
                    GpuJob.status.in_(_ACTIVE),
                    # A queued job with a cancel requested is never claimed (it ends cancelled).
                    and_(GpuJob.status == GpuJobStatus.QUEUED, GpuJob.cancel_requested.is_(False)),
                )
            )
            # As agentic_executor.queue.claim_next takes them, after the ones it holds.
            .order_by(
                GpuJob.status == GpuJobStatus.QUEUED,
                GpuJob.kind == GpuJobKind.TRAIN,
                GpuJob.created_at,
                GpuJob.id,
            )
            .limit(MAX_JOBS)
        )
    ).all()
    heartbeat = await db.get(Setting, EXECUTOR_STATUS_KEY)
    visible = {project.id for project, _ in await member_projects(db, user)}
    owners = await users_by_id(db, [row.user_id for row in rows])
    entries: list[QueueEntry] = []
    for row in rows:
        shown = row.project_id in visible
        owner = owners.get(row.user_id)
        active = row.status in _ACTIVE
        entries.append(
            QueueEntry(
                id=row.id,
                kind=row.kind,
                active=active,
                owner_id=row.user_id,
                owner_name=owner.name if owner else None,
                run_id=row.run_id if shown else None,
                topic=row.topic if shown else None,
                project_name=row.project_name if shown else None,
                dataset=row.dataset,
                plan=job_plan(row.config, row.dataset_details),
                step=latest_step(row.progress) if active else None,
                submitted_at=row.created_at,
                started_at=row.started_at,
                timeout_seconds=row.timeout_seconds,
            )
        )
    status = heartbeat.value if heartbeat is not None else None
    return queue_snapshot(datetime.now(UTC), entries, status, user.id)

"""The executor's SQL: the job queue and the rows a job writes as it runs.

The worker submits jobs and requests cancels (agentic_db.gpu_jobs); everything else a job goes
through is here. Every write to a job is a compare-and-set on its status, so a job that ended,
or whose row is gone, is never changed again. Each function commits its own transaction.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, null, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from agentic_core.contracts import EventType
from agentic_core.enums import GpuJobKind, GpuJobStatus
from agentic_db import append_event
from agentic_db.lab_settings import EXECUTOR_STATUS_KEY
from agentic_db.models import Dataset, GpuJob, Run, Setting, StageRun

# A held job's lease. The executor renews it every few seconds, so a lease in the past means the
# executor is down.
LEASE = timedelta(seconds=30)
ACTIVE = (GpuJobStatus.STARTING, GpuJobStatus.RUNNING)
EXECUTOR = "executor"  # settings.updated_by of the heartbeat


@dataclass(frozen=True)
class Finish:
    """A job's end, as the executor records it."""

    status: GpuJobStatus
    error_code: str | None = None
    error: str | None = None
    result: dict[str, Any] | None = None  # results.json
    exit_code: int | None = None
    gpu_seconds: float | None = None
    provenance: dict[str, Any] | None = None
    log_tail: str | None = None
    progress: dict[str, Any] | None = None  # the latest train_step record, if not written yet

    def bare(self) -> Finish:
        """Only the status, codes and numbers: for an end whose details Postgres refused."""
        return replace(self, error=None, result=None, provenance=None, log_tail=None, progress=None)


async def has_queued(session: AsyncSession) -> bool:
    """Whether a job waits to be claimed. A queued job with a cancel requested never is."""
    found = await session.scalar(
        select(GpuJob.id)
        .where(GpuJob.status == GpuJobStatus.QUEUED, GpuJob.cancel_requested.is_(False))
        .limit(1)
    )
    return found is not None


async def claim_next(session: AsyncSession) -> GpuJob | None:
    """Claim the next queued job: ``starting``, with a lease. Smoke tests go before training runs
    (a coding stage waits on its smoke test, a few minutes at most), then the oldest first.

    SKIP LOCKED: a job that a cancel holds at the moment is passed over, never waited for.
    """
    candidate = aliased(GpuJob)
    next_id = (
        select(candidate.id)
        .where(candidate.status == GpuJobStatus.QUEUED, candidate.cancel_requested.is_(False))
        .order_by(candidate.kind == GpuJobKind.TRAIN, candidate.created_at, candidate.id)
        .limit(1)
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )
    job = await session.scalar(
        update(GpuJob)
        .where(GpuJob.id == next_id)
        .values(status=GpuJobStatus.STARTING, lease_until=func.now() + LEASE)
        .returning(GpuJob)
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    return job


async def record_container(
    session: AsyncSession, job_id: uuid.UUID, container_id: str
) -> bool | None:
    """Note a starting job's new container. Returns whether a cancel was requested meanwhile, or
    None when the job is no longer starting."""
    cancel = await session.scalar(
        update(GpuJob)
        .where(GpuJob.id == job_id, GpuJob.status == GpuJobStatus.STARTING)
        .values(container_id=container_id)
        .returning(GpuJob.cancel_requested)
    )
    await session.commit()
    return cancel


async def mark_running(session: AsyncSession, job_id: uuid.UUID) -> datetime | None:
    """A starting job's container started: ``running`` from now. Returns started_at, or None
    when the job is no longer starting."""
    started_at = await session.scalar(
        update(GpuJob)
        .where(GpuJob.id == job_id, GpuJob.status == GpuJobStatus.STARTING)
        .values(
            status=GpuJobStatus.RUNNING,
            started_at=func.now(),
            lease_until=func.now() + LEASE,
        )
        .returning(GpuJob.started_at)
    )
    await session.commit()
    return started_at


async def poll(session: AsyncSession, job_id: uuid.UUID, *, renew_lease: bool) -> bool | None:
    """Whether a cancel was requested for the job, renewing its lease first if asked. None when
    the job is no longer starting or running (or its row is gone)."""
    if not renew_lease:
        return await session.scalar(
            select(GpuJob.cancel_requested).where(GpuJob.id == job_id, GpuJob.status.in_(ACTIVE))
        )
    cancel = await session.scalar(
        update(GpuJob)
        .where(GpuJob.id == job_id, GpuJob.status.in_(ACTIVE))
        .values(lease_until=func.now() + LEASE)
        .returning(GpuJob.cancel_requested)
    )
    await session.commit()
    return cancel


async def report_epoch(
    session: AsyncSession,
    job_id: uuid.UUID,
    run_id: uuid.UUID,
    ordinal: int,
    payload: dict[str, Any],
) -> bool:
    """Record the job's ``ordinal``-th epoch record as an experiment.epoch run event, once.

    epochs_reported moves in the same transaction, so an executor that follows the output again
    after a restart skips the records reported before. The run is locked first, as the worker's
    writes lock it (no deadlock between the two), and a run with a final status gets no more
    events. Returns whether an event was written.
    """
    run_status = await session.scalar(select(Run.status).where(Run.id == run_id).with_for_update())
    reported = await session.scalar(
        update(GpuJob)
        .where(
            GpuJob.id == job_id,
            GpuJob.status.in_(ACTIVE),
            GpuJob.epochs_reported < ordinal,
        )
        .values(epochs_reported=ordinal)
        .returning(GpuJob.id)
    )
    if reported is None:
        await session.rollback()
        return False
    sent = run_status is not None and not run_status.is_terminal
    if sent:
        await append_event(session, run_id, EventType.EXPERIMENT_EPOCH, payload)
    await session.commit()
    return sent


async def record_progress(
    session: AsyncSession, job_id: uuid.UUID, progress: dict[str, Any]
) -> None:
    await session.execute(
        update(GpuJob)
        .where(GpuJob.id == job_id, GpuJob.status.in_(ACTIVE))
        .values(progress=progress)
    )
    await session.commit()


async def finish(session: AsyncSession, job_id: uuid.UUID, end: Finish) -> bool:
    """Record a starting or running job's end. False when it is neither (anymore)."""
    values: dict[str, Any] = {
        "status": end.status,
        "error_code": end.error_code,
        "error": end.error,
        "result": _jsonb(end.result),
        "exit_code": end.exit_code,
        "gpu_seconds": end.gpu_seconds,
        "provenance": _jsonb(end.provenance),
        "log_tail": end.log_tail,
        "finished_at": func.now(),
        "lease_until": None,
    }
    if end.progress is not None:
        values["progress"] = end.progress
    finished = await session.scalar(
        update(GpuJob)
        .where(GpuJob.id == job_id, GpuJob.status.in_(ACTIVE))
        .values(**values)
        .returning(GpuJob.id)
    )
    await session.commit()
    return finished is not None


async def requeue(session: AsyncSession, job_id: uuid.UUID) -> GpuJobStatus | None:
    """A job an executor claimed but never got running (it went down meanwhile): queued again
    from scratch, or cancelled when a cancel was requested meanwhile. None when the job is not
    starting."""
    cancelled = await session.scalar(
        update(GpuJob)
        .where(
            GpuJob.id == job_id,
            GpuJob.status == GpuJobStatus.STARTING,
            GpuJob.cancel_requested.is_(True),
        )
        .values(
            status=GpuJobStatus.CANCELLED,
            container_id=None,
            lease_until=None,
            finished_at=func.now(),
        )
        .returning(GpuJob.status)
    )
    status = cancelled or await session.scalar(
        update(GpuJob)
        .where(GpuJob.id == job_id, GpuJob.status == GpuJobStatus.STARTING)
        .values(status=GpuJobStatus.QUEUED, container_id=None, started_at=None, lease_until=None)
        .returning(GpuJob.status)
    )
    await session.commit()
    return status


async def active_jobs(session: AsyncSession) -> list[GpuJob]:
    """The starting and running jobs, oldest first."""
    jobs = await session.scalars(
        select(GpuJob).where(GpuJob.status.in_(ACTIVE)).order_by(GpuJob.created_at, GpuJob.id)
    )
    return list(jobs)


async def job_statuses(
    session: AsyncSession, job_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, GpuJobStatus]:
    if not job_ids:
        return {}
    rows = await session.execute(
        select(GpuJob.id, GpuJob.status).where(GpuJob.id.in_(list(job_ids)))
    )
    return {job_id: status for job_id, status in rows}


async def stage_of(session: AsyncSession, stage_run_id: uuid.UUID) -> str | None:
    """The stage a job was submitted for (coding, experiment), for its run events."""
    return await session.scalar(select(StageRun.stage).where(StageRun.id == stage_run_id))


async def write_status(session: AsyncSession, value: dict[str, Any]) -> None:
    """The executor's heartbeat (agentic_db.lab_settings.EXECUTOR_STATUS_KEY)."""
    statement = insert(Setting).values(key=EXECUTOR_STATUS_KEY, value=value, updated_by=EXECUTOR)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[Setting.key],
            set_={
                "value": statement.excluded.value,
                "updated_by": statement.excluded.updated_by,
                "updated_at": func.now(),
            },
        )
    )
    await session.commit()


async def enabled_datasets(session: AsyncSession) -> list[Dataset]:
    datasets = await session.scalars(
        select(Dataset).where(Dataset.enabled.is_(True)).order_by(Dataset.name)
    )
    return list(datasets)


async def record_checksum(session: AsyncSession, name: str, checksum: str) -> None:
    await session.execute(
        update(Dataset)
        .where(Dataset.name == name)
        .values(checksum=checksum, checksum_at=func.now())
    )
    await session.commit()


def _jsonb(value: dict[str, Any] | None) -> Any:
    # A JSON column stores Python's None as JSON null; a missing value is SQL NULL.
    return null() if value is None else value

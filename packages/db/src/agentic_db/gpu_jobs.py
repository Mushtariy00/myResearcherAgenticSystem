"""Submitting and cancelling GPU jobs: the worker's side of the executor's queue.

The executor (apps/executor) claims queued jobs and runs them; see agentic_core.gpu_jobs for the
contract and docs/design/experiments.md for the design.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_core.enums import GpuJobKind, GpuJobStatus
from agentic_core.gpu_jobs import MAX_QUEUED_PER_USER
from agentic_db.models import GpuJob


@dataclass(frozen=True)
class JobRequest:
    """One job a stage attempt asks for. (stage_run_id, kind, ordinal) names it."""

    stage_run_id: uuid.UUID
    run_id: uuid.UUID
    user_id: str
    kind: GpuJobKind
    ordinal: int
    dataset: str
    code: dict[str, str]  # file name to source; agentic_core.gpu_jobs.CODE_FILES only
    config: dict[str, Any]  # the harness's ExperimentConfig as JSON
    timeout_seconds: int


async def find_job(
    session: AsyncSession, stage_run_id: uuid.UUID, kind: GpuJobKind, ordinal: int
) -> GpuJob | None:
    return await session.scalar(
        select(GpuJob).where(
            GpuJob.stage_run_id == stage_run_id,
            GpuJob.kind == kind,
            GpuJob.ordinal == ordinal,
        )
    )


async def submit_job(session: AsyncSession, request: JobRequest) -> GpuJob | None:
    """The job for ``request``, queued now unless it exists already; None while the user already
    has MAX_QUEUED_PER_USER jobs queued (the caller waits and asks again).

    A request that was submitted before returns that job, whatever its status, so an activity
    that runs again after a crash finds its job instead of queueing a second one. Runs inside the
    caller's transaction; commit to queue the job.
    """
    # One submit per user at a time, so two of the user's stages can't both pass the limit, and a
    # request submitted twice at once finds the first one's job after the lock.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext('gpu_jobs.submit:' || :user_id))"),
        {"user_id": request.user_id},
    )
    existing = await find_job(session, request.stage_run_id, request.kind, request.ordinal)
    if existing is not None:
        return existing
    queued = await session.scalar(
        select(func.count())
        .select_from(GpuJob)
        .where(GpuJob.user_id == request.user_id, GpuJob.status == GpuJobStatus.QUEUED)
    )
    if (queued or 0) >= MAX_QUEUED_PER_USER:
        return None
    await session.execute(
        insert(GpuJob)
        .values(
            stage_run_id=request.stage_run_id,
            run_id=request.run_id,
            user_id=request.user_id,
            kind=request.kind,
            ordinal=request.ordinal,
            status=GpuJobStatus.QUEUED,
            dataset=request.dataset,
            code=request.code,
            config=request.config,
            timeout_seconds=request.timeout_seconds,
        )
        .on_conflict_do_nothing(index_elements=["stage_run_id", "kind", "ordinal"])
    )
    return await find_job(session, request.stage_run_id, request.kind, request.ordinal)


async def request_cancel(session: AsyncSession, job_id: uuid.UUID) -> GpuJobStatus | None:
    """Cancel a job: a queued one ends cancelled at once; a starting or running one is marked
    cancel_requested, and the executor stops its container within seconds. Returns the job's
    status after the call (None for an unknown job). Runs inside the caller's transaction.

    Both updates are compare-and-set on the status, so a cancel that races the executor's claim
    either cancels the queued job or flags the claimed one, never neither.
    """
    cancelled = await session.scalar(
        update(GpuJob)
        .where(GpuJob.id == job_id, GpuJob.status == GpuJobStatus.QUEUED)
        .values(status=GpuJobStatus.CANCELLED, cancel_requested=True, finished_at=func.now())
        .returning(GpuJob.status)
    )
    if cancelled is not None:
        return cancelled
    flagged = await session.scalar(
        update(GpuJob)
        .where(
            GpuJob.id == job_id,
            GpuJob.status.in_([GpuJobStatus.STARTING, GpuJobStatus.RUNNING]),
        )
        .values(cancel_requested=True)
        .returning(GpuJob.status)
    )
    if flagged is not None:
        return flagged
    return await session.scalar(select(GpuJob.status).where(GpuJob.id == job_id))

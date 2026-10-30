"""The executor's queue SQL: claim order, SKIP LOCKED, compare-and-set ends and epoch events."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from agentic_core.enums import GpuJobKind, GpuJobStatus, RunStatus
from agentic_db.models import GpuJob, Run
from agentic_executor import queue
from executor_testkit import Factory, create_job, epoch_events, get_job


async def _claim(db: Factory) -> GpuJob | None:
    async with db() as session:
        return await queue.claim_next(session)


async def test_smoke_jobs_are_claimed_first_then_the_oldest(db: Factory) -> None:
    now = datetime.now(UTC)
    train = await create_job(db, kind=GpuJobKind.TRAIN, created_at=now - timedelta(minutes=4))
    older_smoke = await create_job(db, created_at=now - timedelta(minutes=3))
    newer_smoke = await create_job(db, created_at=now - timedelta(minutes=2))
    later_train = await create_job(db, kind=GpuJobKind.TRAIN, created_at=now - timedelta(minutes=1))
    claimed = [await _claim(db) for _ in range(5)]
    assert [job.id if job else None for job in claimed] == [
        older_smoke.id,
        newer_smoke.id,
        train.id,
        later_train.id,
        None,
    ]
    first = claimed[0]
    assert first is not None and first.status is GpuJobStatus.STARTING
    assert first.lease_until is not None and first.lease_until > datetime.now(UTC)


async def test_a_queued_job_with_a_cancel_requested_is_never_claimed(db: Factory) -> None:
    job = await create_job(db, cancel_requested=True)
    async with db() as session:
        assert not await queue.has_queued(session)
    assert await _claim(db) is None
    assert (await get_job(db, job.id)).status is GpuJobStatus.QUEUED


async def test_concurrent_claims_never_take_the_same_job(db: Factory) -> None:
    jobs = {(await create_job(db)).id for _ in range(3)}
    claimed = await asyncio.gather(*(_claim(db) for _ in range(4)))
    ids = [job.id for job in claimed if job is not None]
    assert sorted(ids) == sorted(jobs) and len(ids) == 3


async def test_an_end_is_recorded_once_and_only_for_an_active_job(db: Factory) -> None:
    job = await create_job(db, status=GpuJobStatus.RUNNING)
    async with db() as session:
        assert await queue.finish(
            session, job.id, queue.Finish(GpuJobStatus.SUCCEEDED, exit_code=0)
        )
    async with db() as session:
        again = queue.Finish(GpuJobStatus.FAILED, error_code="job.lost")
        assert not await queue.finish(session, job.id, again)
    finished = await get_job(db, job.id)
    assert finished.status is GpuJobStatus.SUCCEEDED and finished.error_code is None
    assert finished.result is None and finished.provenance is None  # SQL NULL, not JSON null
    async with db() as session:
        assert not await queue.finish(session, uuid.uuid4(), again)


async def test_a_starting_job_is_requeued_or_cancelled(db: Factory) -> None:
    starting = await create_job(db, status=GpuJobStatus.STARTING, container_id="c1")
    flagged = await create_job(db, status=GpuJobStatus.STARTING, cancel_requested=True)
    running = await create_job(db, status=GpuJobStatus.RUNNING)
    async with db() as session:
        assert await queue.requeue(session, starting.id) is GpuJobStatus.QUEUED
        assert await queue.requeue(session, flagged.id) is GpuJobStatus.CANCELLED
        assert await queue.requeue(session, running.id) is None
    requeued = await get_job(db, starting.id)
    assert requeued.container_id is None and requeued.lease_until is None
    assert (await get_job(db, flagged.id)).finished_at is not None
    assert (await get_job(db, running.id)).status is GpuJobStatus.RUNNING


async def test_each_epoch_is_reported_once(db: Factory) -> None:
    job = await create_job(db, status=GpuJobStatus.RUNNING)
    payload = {"stage": "coding", "epoch": 0}
    async with db() as session:
        assert await queue.report_epoch(session, job.id, job.run_id, 1, payload)
    async with db() as session:
        assert not await queue.report_epoch(session, job.id, job.run_id, 1, payload)
    assert await epoch_events(db, job.run_id) == [payload]
    assert (await get_job(db, job.id)).epochs_reported == 1


async def test_a_closed_run_gets_no_more_epoch_events(db: Factory) -> None:
    job = await create_job(db, status=GpuJobStatus.RUNNING)
    async with db() as session:
        await session.execute(
            update(Run).where(Run.id == job.run_id).values(status=RunStatus.CANCELLED)
        )
        await session.commit()
    async with db() as session:
        assert not await queue.report_epoch(session, job.id, job.run_id, 1, {"epoch": 0})
    assert await epoch_events(db, job.run_id) == []
    assert (await get_job(db, job.id)).epochs_reported == 1  # not sent again later either

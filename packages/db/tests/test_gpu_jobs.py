"""Submitting and cancelling GPU jobs (agentic_db.gpu_jobs), and the migration that adds them."""

import asyncio
import uuid
from collections.abc import Callable

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.enums import GpuJobKind, GpuJobStatus
from agentic_core.gpu_jobs import MAX_QUEUED_PER_USER
from agentic_db.gpu_jobs import JobRequest, find_job, request_cancel, submit_job
from agentic_db.models import Dataset, GpuJob, Project, Run, StageRun
from agentic_db.testing import ALEMBIC_INI

Factory = async_sessionmaker[AsyncSession]


async def _stage_run(db: Factory, owner: str = "user-1") -> tuple[uuid.UUID, uuid.UUID]:
    """A run with a coding stage attempt, and the nyu2 dataset its jobs mount."""
    async with db() as session:
        if await session.get(Dataset, "nyu2") is None:
            session.add(Dataset(name="nyu2", version="2026.05", title="NYU Depth V2"))
        project = Project(name="Depth estimation", created_by=owner)
        session.add(project)
        await session.flush()
        run = Run(project_id=project.id, owner_id=owner, topic="Monocular depth")
        session.add(run)
        await session.flush()
        stage_run = StageRun(run_id=run.id, stage="coding")
        session.add(stage_run)
        await session.commit()
        return run.id, stage_run.id


def _request(
    run_id: uuid.UUID, stage_run_id: uuid.UUID, *, ordinal: int = 1, user: str = "user-1"
) -> JobRequest:
    return JobRequest(
        stage_run_id=stage_run_id,
        run_id=run_id,
        user_id=user,
        kind=GpuJobKind.SMOKE,
        ordinal=ordinal,
        dataset="nyu2",
        code={"model.py": "class Model: ...\n"},
        config={"task": "nyu2_depth"},
        timeout_seconds=600,
    )


async def _submitted(db: Factory, request: JobRequest) -> GpuJob:
    async with db() as session:
        job = await submit_job(session, request)
        await session.commit()
    assert job is not None
    return job


async def test_a_request_submitted_twice_is_one_queued_job(db: Factory) -> None:
    run_id, stage_run_id = await _stage_run(db)
    first = await _submitted(db, _request(run_id, stage_run_id))
    again = await _submitted(db, _request(run_id, stage_run_id))
    assert again.id == first.id
    assert first.status is GpuJobStatus.QUEUED
    async with db() as session:
        assert await session.scalar(select(func.count()).select_from(GpuJob)) == 1
        found = await find_job(session, stage_run_id, GpuJobKind.SMOKE, 1)
    assert found is not None and found.id == first.id


async def test_concurrent_submits_of_one_request_queue_one_job(db: Factory) -> None:
    run_id, stage_run_id = await _stage_run(db)

    async def submit() -> uuid.UUID | None:
        async with db() as session:
            job = await submit_job(session, _request(run_id, stage_run_id))
            await session.commit()
            return job.id if job else None

    ids = await asyncio.gather(*(submit() for _ in range(4)))
    assert None not in ids
    assert len(set(ids)) == 1


async def test_a_user_has_at_most_two_jobs_queued(db: Factory) -> None:
    run_id, stage_run_id = await _stage_run(db)
    async with db() as session:
        jobs = [
            await submit_job(session, _request(run_id, stage_run_id, ordinal=n))
            for n in range(1, MAX_QUEUED_PER_USER + 2)
        ]
        await session.commit()
    queued, refused = jobs[:MAX_QUEUED_PER_USER], jobs[MAX_QUEUED_PER_USER]
    assert all(job is not None for job in queued)
    assert refused is None

    # Another user's share is their own.
    other_run, other_stage_run = await _stage_run(db, owner="user-2")
    await _submitted(db, _request(other_run, other_stage_run, user="user-2"))

    # Once one of the user's jobs leaves the queue, the next one goes in.
    first = queued[0]
    assert first is not None
    async with db() as session:
        await session.execute(
            update(GpuJob).where(GpuJob.id == first.id).values(status=GpuJobStatus.RUNNING)
        )
        await session.commit()
    await _submitted(db, _request(run_id, stage_run_id, ordinal=9))


async def _status(db: Factory, job_id: uuid.UUID) -> tuple[GpuJobStatus, bool, bool]:
    async with db() as session:
        job = await session.get(GpuJob, job_id)
        assert job is not None
        return job.status, job.cancel_requested, job.finished_at is not None


async def _set_status(db: Factory, job_id: uuid.UUID, status: GpuJobStatus) -> None:
    async with db() as session:
        await session.execute(update(GpuJob).where(GpuJob.id == job_id).values(status=status))
        await session.commit()


async def _cancel(db: Factory, job_id: uuid.UUID) -> GpuJobStatus | None:
    async with db() as session:
        status = await request_cancel(session, job_id)
        await session.commit()
        return status


async def test_cancelling_a_queued_job_ends_it_at_once(db: Factory) -> None:
    job = await _submitted(db, _request(*await _stage_run(db)))
    assert await _cancel(db, job.id) is GpuJobStatus.CANCELLED
    assert await _status(db, job.id) == (GpuJobStatus.CANCELLED, True, True)


async def test_cancelling_a_running_job_leaves_the_stop_to_the_executor(db: Factory) -> None:
    job = await _submitted(db, _request(*await _stage_run(db)))
    await _set_status(db, job.id, GpuJobStatus.RUNNING)
    assert await _cancel(db, job.id) is GpuJobStatus.RUNNING
    assert await _status(db, job.id) == (GpuJobStatus.RUNNING, True, False)


async def test_cancelling_a_finished_or_unknown_job_changes_nothing(db: Factory) -> None:
    job = await _submitted(db, _request(*await _stage_run(db)))
    await _set_status(db, job.id, GpuJobStatus.SUCCEEDED)
    assert await _cancel(db, job.id) is GpuJobStatus.SUCCEEDED
    assert await _status(db, job.id) == (GpuJobStatus.SUCCEEDED, False, False)
    assert await _cancel(db, uuid.uuid4()) is None


async def test_a_cancel_that_races_the_executors_claim_is_never_lost(db: Factory) -> None:
    job = await _submitted(db, _request(*await _stage_run(db)))
    async with db() as claim:
        # The executor's claim holds the row until it commits the job as starting.
        await claim.execute(
            text("SELECT id FROM gpu_jobs WHERE id = :id FOR UPDATE"), {"id": job.id}
        )
        await claim.execute(
            update(GpuJob).where(GpuJob.id == job.id).values(status=GpuJobStatus.STARTING)
        )
        cancel = asyncio.create_task(_cancel(db, job.id))
        await asyncio.sleep(0.3)
        assert not cancel.done()  # it waits for the claim
        await claim.commit()
    assert await cancel is GpuJobStatus.STARTING
    assert await _status(db, job.id) == (GpuJobStatus.STARTING, True, False)


REVISION = "a92a312bd5d3"
BEFORE = "164cac3d30f1"
TABLES = {"gpu_jobs", "datasets"}


async def _alembic(database_url: str, step: Callable[[Config, str], None], revision: str) -> None:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url)
    # env.py runs an event loop of its own, so Alembic gets a thread of its own.
    await asyncio.to_thread(step, config, revision)


async def _tables(db: Factory) -> set[str]:
    async with db() as session:
        rows = await session.scalars(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        return set(rows)


async def test_the_migration_registers_nyu2_and_takes_both_tables_away(
    db: Factory, database_url: str
) -> None:
    try:
        await _alembic(database_url, command.downgrade, BEFORE)
        assert not TABLES & await _tables(db)

        await _alembic(database_url, command.upgrade, REVISION)
        assert TABLES.issubset(await _tables(db))
        async with db() as session:
            nyu2 = await session.get(Dataset, "nyu2")
            assert nyu2 is not None
            assert (nyu2.version, nyu2.host_path, nyu2.enabled) == ("2026.05", None, True)
            assert nyu2.contract["units"] == "metres"
            assert nyu2.details["splits"] == {"train": 50688, "val": 654, "test": 0}

        await _alembic(database_url, command.downgrade, BEFORE)
        assert not TABLES & await _tables(db)
    finally:
        await _alembic(database_url, command.upgrade, "head")


async def test_nyu2_2026_10_is_the_copy_with_training_depth_in_metres(
    db: Factory, database_url: str
) -> None:
    async def nyu2() -> tuple[str, str | None, str]:
        async with db() as session:
            row = await session.get(Dataset, "nyu2", populate_existing=True)
            assert row is not None
            return row.version, row.checksum, row.details["description"]

    try:
        await _alembic(database_url, command.downgrade, BEFORE)
        await _alembic(database_url, command.upgrade, REVISION)  # registers nyu2 2026.05
        async with db() as session:
            await session.execute(text("UPDATE datasets SET checksum = repeat('a', 64)"))
            await session.commit()
        await _alembic(database_url, command.upgrade, "5e8b1f0c9d42")
        version, checksum, description = await nyu2()
        assert (version, checksum) == ("2026.10", None)  # the export's checksum isn't the copy's
        assert "training depths converted to metres" in description
        await _alembic(database_url, command.downgrade, REVISION)
        assert (await nyu2())[0] == "2026.05"
    finally:
        await _alembic(database_url, command.upgrade, "head")

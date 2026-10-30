"""A stage attempt's GPU jobs (agentic_worker.gpu): submitted once, waited on, and cancelled only
when the run is."""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, update

from agentic_core.enums import GpuJobKind, GpuJobStatus
from agentic_db.lab_settings import EXECUTOR_STATUS_KEY
from agentic_db.models import Dataset, GpuJob, Setting, StageRun
from agentic_worker.gpu import (
    EXECUTOR_DOWN,
    QUEUE_FULL,
    QUEUED,
    STARTED,
    GpuJobs,
    JobSpec,
    harness_config,
)
from agentic_worker.progress import ProgressLines
from agentic_worker.stages import StageContext
from worker_testkit import Factory, create_run

Lines = list[tuple[str, dict[str, Any]]]


def _spec(ordinal: int = 1) -> JobSpec:
    return JobSpec(
        kind=GpuJobKind.SMOKE,
        ordinal=ordinal,
        dataset="nyu2",
        code={"model.py": "class Model: ...\n"},
        config=harness_config(
            "nyu2",
            model_kwargs={"base_channels": 16},
            loss="l1",
            training={"learning_rate": 0.001, "optimizer": "adam"},
            batch_size=2,
            epochs=1,
            max_train_steps=2,
            max_val_steps=2,
        ),
        timeout_seconds=600,
    )


async def _attempt(db: Factory, lines: Lines, owner: str = "bob") -> StageContext:
    """A coding attempt of a new run, whose progress lines go to ``lines``."""
    run_id = await create_run(db)
    async with db() as session:
        if await session.get(Dataset, "nyu2") is None:
            session.add(Dataset(name="nyu2", version="2026.05", title="NYU Depth V2"))
        stage_run = StageRun(run_id=uuid.UUID(run_id), stage="coding", attempt=1)
        session.add(stage_run)
        await session.commit()

    async def log(code: str, params: dict[str, Any], message: str) -> None:
        lines.append((code, params))

    return StageContext(
        run_id=run_id,
        stage_run_id=str(stage_run.id),
        stage="coding",
        attempt=1,
        feedback="",
        topic="Monocular depth estimation",
        owner_id=owner,
        project_id=str(uuid.uuid4()),
        llm_policy="auto",
        budget_cap_usd=None,
        log=log,
    )


def _jobs(db: Factory, **options: Any) -> GpuJobs:
    return GpuJobs(db, poll_seconds=0.02, **options)


async def _job(db: Factory, ctx: StageContext) -> GpuJob | None:
    async with db() as session:
        return await session.scalar(
            select(GpuJob).where(GpuJob.stage_run_id == uuid.UUID(ctx.stage_run_id))
        )


async def _set(db: Factory, job_id: uuid.UUID, **values: Any) -> None:
    async with db() as session:
        await session.execute(update(GpuJob).where(GpuJob.id == job_id).values(**values))
        await session.commit()


async def _eventually(check: Callable[[], Awaitable[bool]], seconds: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + seconds
    while not await check():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("timed out")
        await asyncio.sleep(0.02)


async def _alive(db: Factory) -> None:
    """The executor's heartbeat, just now."""
    async with db() as session:
        session.add(
            Setting(
                key=EXECUTOR_STATUS_KEY,
                value={"alive_at": datetime.now(UTC).isoformat()},
                updated_by="executor",
            )
        )
        await session.commit()


async def _runs_to_its_end(db: Factory, ctx: StageContext, end: GpuJobStatus) -> None:
    """Play the executor for the attempt's job: start it, then end it with ``end``."""

    async def submitted() -> bool:
        return await _job(db, ctx) is not None

    await _eventually(submitted)
    job = await _job(db, ctx)
    assert job is not None
    await _set(db, job.id, status=GpuJobStatus.RUNNING, started_at=datetime.now(UTC))
    await asyncio.sleep(0.1)
    await _set(db, job.id, status=end, finished_at=datetime.now(UTC))


async def test_a_job_is_submitted_once_and_waited_on_to_its_end(db: Factory) -> None:
    await _alive(db)
    lines: Lines = []
    ctx = await _attempt(db, lines)
    jobs = _jobs(db)
    executor = asyncio.create_task(_runs_to_its_end(db, ctx, GpuJobStatus.SUCCEEDED))
    ended = await jobs.run(ctx, _spec(), ProgressLines(ctx))
    await executor
    assert ended.status is GpuJobStatus.SUCCEEDED
    assert [code for code, _ in lines] == [QUEUED, STARTED]
    assert lines[0][1] == {"kind": "smoke", "ordinal": 1}

    # An activity that runs again finds the job it submitted, and submits no other.
    again = await jobs.run(ctx, _spec(), ProgressLines(ctx))
    assert again.id == ended.id
    async with db() as session:
        assert await session.scalar(select(func.count()).select_from(GpuJob)) == 1


async def test_it_waits_while_the_users_queue_is_full(db: Factory) -> None:
    await _alive(db)
    busy = [await _attempt(db, [], owner="bob") for _ in range(2)]
    queued = []
    for other in busy:
        async with db() as session:
            job = GpuJob(
                stage_run_id=uuid.UUID(other.stage_run_id),
                run_id=uuid.UUID(other.run_id),
                user_id="bob",
                kind=GpuJobKind.TRAIN,
                ordinal=1,
                dataset="nyu2",
                code={},
                config={},
                timeout_seconds=600,
            )
            session.add(job)
            await session.commit()
            queued.append(job.id)
    lines: Lines = []
    ctx = await _attempt(db, lines, owner="bob")
    waiting = asyncio.create_task(_jobs(db).run(ctx, _spec(), ProgressLines(ctx)))

    async def said_full() -> bool:
        return any(code == QUEUE_FULL for code, _ in lines)

    await _eventually(said_full)
    assert await _job(db, ctx) is None
    await _set(db, queued[0], status=GpuJobStatus.RUNNING)  # one of bob's jobs leaves the queue
    await _runs_to_its_end(db, ctx, GpuJobStatus.FAILED)
    assert (await waiting).status is GpuJobStatus.FAILED
    assert lines[0] == (QUEUE_FULL, {"kind": "smoke", "limit": 2})


async def test_a_cancelled_run_cancels_its_job(db: Factory) -> None:
    await _alive(db)
    ctx = await _attempt(db, [])
    waiting = asyncio.create_task(_jobs(db).run(ctx, _spec(), ProgressLines(ctx)))

    async def running() -> bool:
        job = await _job(db, ctx)
        if job is None:
            return False
        await _set(db, job.id, status=GpuJobStatus.RUNNING)
        return True

    await _eventually(running)
    await asyncio.sleep(0.1)
    waiting.cancel()

    async def executor_stops_it() -> bool:  # as the executor does once it sees the cancel
        job = await _job(db, ctx)
        if job is None or not job.cancel_requested:
            return False
        await _set(db, job.id, status=GpuJobStatus.CANCELLED)
        return True

    await _eventually(executor_stops_it)
    with pytest.raises(asyncio.CancelledError):
        await waiting
    job = await _job(db, ctx)
    assert job is not None and job.status is GpuJobStatus.CANCELLED


async def test_an_activity_that_timed_out_leaves_its_job_running(db: Factory) -> None:
    await _alive(db)
    ctx = await _attempt(db, [])
    jobs = _jobs(db, cancels_job=lambda: False)  # a timeout, not a cancel of the run
    waiting = asyncio.create_task(jobs.run(ctx, _spec(), ProgressLines(ctx)))

    async def submitted() -> bool:
        return await _job(db, ctx) is not None

    await _eventually(submitted)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    job = await _job(db, ctx)
    assert job is not None
    assert (job.status, job.cancel_requested) == (GpuJobStatus.QUEUED, False)


async def test_a_queued_job_without_an_executor_says_so_once(db: Factory) -> None:
    lines: Lines = []
    ctx = await _attempt(db, lines)
    async with db() as session:  # a heartbeat from long ago
        session.add(
            Setting(
                key=EXECUTOR_STATUS_KEY,
                value={"alive_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat()},
                updated_by="executor",
            )
        )
        await session.commit()
    waiting = asyncio.create_task(_jobs(db).run(ctx, _spec(), ProgressLines(ctx)))
    await asyncio.sleep(0.3)
    await _runs_to_its_end(db, ctx, GpuJobStatus.SUCCEEDED)
    await waiting
    assert [code for code, _ in lines].count(EXECUTOR_DOWN) == 1


async def test_only_a_registered_enabled_dataset_the_harness_knows(db: Factory) -> None:
    async with db() as session:
        session.add(Dataset(name="nyu2", version="2026.05", title="NYU Depth V2"))
        session.add(Dataset(name="kitti", version="eigen", title="KITTI"))
        await session.commit()
    jobs = _jobs(db)
    found = await jobs.dataset("nyu2")
    assert found is not None and found.version == "2026.05"
    assert await jobs.dataset("kitti") is None  # registered, but not a harness dataset
    assert await jobs.dataset(None) is None
    async with db() as session:
        await session.execute(update(Dataset).where(Dataset.name == "nyu2").values(enabled=False))
        await session.commit()
    assert await jobs.dataset("nyu2") is None


def test_the_harness_config_holds_the_stage_choices() -> None:
    config = _spec().config
    assert config["task"] == "nyu2_depth"
    assert config["model"] == {"architecture": "generated", "kwargs": {"base_channels": 16}}
    assert config["data"]["split_file_template"] == "{root}/splits/nyu/{split}.txt"
    assert config["training"] == {
        "learning_rate": 0.001,
        "optimizer": "adam",
        "loss": "l1",
        "epochs": 1,
        "max_train_steps": 2,
        "max_val_steps": 2,
    }

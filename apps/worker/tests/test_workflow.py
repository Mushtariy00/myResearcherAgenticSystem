"""The run workflow on Temporal's time-skipping test server, with real activities and database."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio.client import (
    Client,
    WorkflowFailureError,
    WorkflowHandle,
    WorkflowUpdateFailedError,
)
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from agentic_core.contracts import (
    DECIDE_UPDATE,
    RUN_WORKFLOW,
    STATUS_QUERY,
    TASK_QUEUE,
    DecisionInput,
    RunInput,
)
from agentic_core.enums import RunStatus, StageStatus
from agentic_db.models import Approval, Project, Run, RunEvent, StageOutput, StageRun
from agentic_worker.activities import StageActivities
from agentic_worker.workflows import RunWorkflow
from worker_testkit import FakeRunner, FakeValkey

Factory = async_sessionmaker[AsyncSession]


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    async with await WorkflowEnvironment.start_time_skipping() as environment:
        yield environment


@pytest.fixture
def runner() -> FakeRunner:
    return FakeRunner()


@pytest.fixture
async def client(
    env: WorkflowEnvironment, db: Factory, runner: FakeRunner
) -> AsyncIterator[Client]:
    activities = StageActivities(db, FakeValkey(), runner)
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[RunWorkflow],
        activities=[
            activities.start_stage,
            activities.execute_stage,
            activities.record_decision,
            activities.finish_run,
        ],
    ):
        yield env.client


async def start(client: Client, db: Factory) -> tuple[str, WorkflowHandle]:
    async with db() as session:
        project = Project(name="Depth", created_by="bob")
        session.add(project)
        await session.flush()
        run = Run(project_id=project.id, owner_id="bob", topic="Monocular depth")
        session.add(run)
        await session.commit()
    run_id = str(run.id)
    handle = await client.start_workflow(
        RUN_WORKFLOW, RunInput(run_id=run_id), id=f"run-{run_id}", task_queue=TASK_QUEUE
    )
    return run_id, handle


async def awaiting(handle: WorkflowHandle, db: Factory, stage: str) -> DecisionInput:
    """Wait until `stage` has an output to review; return an approve decision for it."""
    for _ in range(400):
        status = await handle.query(STATUS_QUERY)
        if status["awaiting"] and status["stage"] == stage:
            async with db() as session:
                output = await session.get(StageOutput, uuid.UUID(status["awaiting"]))
            assert output is not None
            return DecisionInput(
                stage=stage,
                stage_output_id=str(output.id),
                sha256=output.sha256,
                decision="approve",
                actor_id="bob",
            )
        await asyncio.sleep(0.05)
    raise AssertionError(f"{stage} never became ready for review")


async def run_status(db: Factory, run_id: str) -> tuple[RunStatus, str | None]:
    async with db() as session:
        run = await session.get(Run, uuid.UUID(run_id))
    assert run is not None
    return RunStatus(run.status), run.error


async def test_approving_every_stage_completes_the_run(client: Client, db: Factory) -> None:
    run_id, handle = await start(client, db)
    for stage in ("literature", "method", "coding", "experiment", "writing"):
        await handle.execute_update(DECIDE_UPDATE, await awaiting(handle, db, stage))
    assert await handle.result() == "completed"
    assert await run_status(db, run_id) == (RunStatus.COMPLETED, None)
    async with db() as session:
        approvals = (await session.scalars(select(Approval))).all()
        seqs = (
            await session.scalars(
                select(RunEvent.seq)
                .where(RunEvent.run_id == uuid.UUID(run_id))
                .order_by(RunEvent.seq)
            )
        ).all()
    assert len(approvals) == 5
    assert list(seqs) == list(range(1, len(seqs) + 1))  # gap-free event log


async def test_request_changes_reruns_the_stage_with_the_feedback(
    client: Client, db: Factory, runner: FakeRunner
) -> None:
    _, handle = await start(client, db)
    first = await awaiting(handle, db, "literature")
    await handle.execute_update(
        DECIDE_UPDATE,
        DecisionInput(
            stage="literature",
            stage_output_id=first.stage_output_id,
            sha256=first.sha256,
            decision="request_changes",
            actor_id="bob",
            comment="Focus on 2024",
        ),
    )
    second = await awaiting(handle, db, "literature")
    assert second.stage_output_id != first.stage_output_id
    assert [(c.stage, c.attempt, c.feedback) for c in runner.seen] == [
        ("literature", 1, ""),
        ("literature", 2, "Focus on 2024"),
    ]
    async with db() as session:
        attempts = (await session.scalars(select(StageRun).order_by(StageRun.attempt))).all()
    assert [(a.attempt, a.status) for a in attempts] == [
        (1, StageStatus.CHANGES_REQUESTED),
        (2, StageStatus.OUTPUT_READY),
    ]
    await handle.cancel()


async def test_reject_stops_the_run(client: Client, db: Factory) -> None:
    run_id, handle = await start(client, db)
    decision = await awaiting(handle, db, "literature")
    await handle.execute_update(
        DECIDE_UPDATE,
        DecisionInput(
            stage="literature",
            stage_output_id=decision.stage_output_id,
            sha256=decision.sha256,
            decision="reject",
            actor_id="bob",
        ),
    )
    assert await handle.result() == "rejected"
    assert (await run_status(db, run_id))[0] == RunStatus.REJECTED


async def test_stale_or_repeated_decisions_are_refused(client: Client, db: Factory) -> None:
    _, handle = await start(client, db)
    decision = await awaiting(handle, db, "literature")
    stale = DecisionInput(
        stage="literature",
        stage_output_id=decision.stage_output_id,
        sha256="0" * 64,
        decision="approve",
        actor_id="bob",
    )
    with pytest.raises(WorkflowUpdateFailedError):
        await handle.execute_update(DECIDE_UPDATE, stale)
    wrong_stage = DecisionInput(
        stage="method",
        stage_output_id=decision.stage_output_id,
        sha256=decision.sha256,
        decision="approve",
        actor_id="bob",
    )
    with pytest.raises(WorkflowUpdateFailedError):
        await handle.execute_update(DECIDE_UPDATE, wrong_stage)
    await handle.execute_update(DECIDE_UPDATE, decision)
    with pytest.raises(WorkflowUpdateFailedError):
        await handle.execute_update(DECIDE_UPDATE, decision)  # literature is no longer awaited
    await handle.cancel()


async def test_cancel_while_waiting_for_review(client: Client, db: Factory) -> None:
    run_id, handle = await start(client, db)
    await awaiting(handle, db, "literature")
    await handle.cancel()
    with pytest.raises(WorkflowFailureError):
        await handle.result()
    assert (await run_status(db, run_id))[0] == RunStatus.CANCELLED
    async with db() as session:
        stage_run = (await session.scalars(select(StageRun))).one()
    assert stage_run.status == StageStatus.CANCELLED


async def test_failing_stage_fails_the_run_honestly(
    client: Client, db: Factory, runner: FakeRunner
) -> None:
    runner.fail_stage = "method"
    run_id, handle = await start(client, db)
    await handle.execute_update(DECIDE_UPDATE, await awaiting(handle, db, "literature"))
    assert await handle.result() == "failed"
    assert await run_status(db, run_id) == (RunStatus.FAILED, "method.invalid_output")


async def test_unanswered_review_expires_after_seven_days(
    env: WorkflowEnvironment, client: Client, db: Factory
) -> None:
    run_id, handle = await start(client, db)
    await awaiting(handle, db, "literature")
    await env.sleep(timedelta(days=8))
    assert await handle.result() == "cancelled"
    assert await run_status(db, run_id) == (RunStatus.CANCELLED, "approval.expired")

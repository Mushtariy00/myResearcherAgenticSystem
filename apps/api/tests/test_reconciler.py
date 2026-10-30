import asyncio
import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_api.reconciler import reconcile_forever, start_unstarted_runs
from agentic_core.enums import RunStatus
from agentic_db.models import Project, Run
from api_testkit import FakeOrchestrator

Factory = async_sessionmaker[AsyncSession]
LONG_AGO = timedelta(minutes=5)


async def _runs(db: Factory, *specs: tuple[RunStatus, str | None, timedelta]) -> list[uuid.UUID]:
    """Runs with (status, workflow id, age), in a project of their own."""
    async with db() as session:
        project = Project(name="Depth", created_by="root")
        session.add(project)
        await session.flush()
        runs = [
            Run(
                project_id=project.id,
                owner_id="bob",
                topic="Monocular depth",
                status=status,
                workflow_id=workflow_id,
                created_at=datetime.now(UTC) - age,
            )
            for status, workflow_id, age in specs
        ]
        session.add_all(runs)
        await session.commit()
        return [run.id for run in runs]


async def _workflow_ids(db: Factory, run_ids: list[uuid.UUID]) -> list[str | None]:
    async with db() as session:
        rows = await session.execute(select(Run.id, Run.workflow_id).where(Run.id.in_(run_ids)))
        stored = {run_id: workflow_id for run_id, workflow_id in rows}
    return [stored[run_id] for run_id in run_ids]


async def test_runs_queued_without_a_workflow_are_started_after_the_grace_period(
    db: Factory, orchestrator: FakeOrchestrator
) -> None:
    lost, *others = await _runs(
        db,
        (RunStatus.QUEUED, None, LONG_AGO),  # the API died between its commit and the start
        (RunStatus.QUEUED, None, timedelta(seconds=1)),  # create_run is still starting it
        (RunStatus.QUEUED, "run-started", LONG_AGO),  # started; the worker hasn't picked it up
        # Seeded demo rows: paused and finished runs are written without a workflow.
        (RunStatus.PAUSED_BUDGET, None, LONG_AGO),
        (RunStatus.COMPLETED, None, LONG_AGO),
        (RunStatus.CANCELLED, None, LONG_AGO),
    )
    assert await start_unstarted_runs(db, orchestrator) == [lost]
    assert orchestrator.started == [lost]
    assert await _workflow_ids(db, [lost, *others]) == [
        f"run-{lost}",
        None,
        "run-started",
        None,
        None,
        None,
    ]
    assert await start_unstarted_runs(db, orchestrator) == []  # nothing left to start


async def test_runs_wait_for_the_next_pass_while_temporal_is_unreachable(
    db: Factory, orchestrator: FakeOrchestrator
) -> None:
    lost = await _runs(db, (RunStatus.QUEUED, None, LONG_AGO), (RunStatus.QUEUED, None, LONG_AGO))
    orchestrator.fail_start = True
    assert await start_unstarted_runs(db, orchestrator) == []
    assert await _workflow_ids(db, lost) == [None, None]
    orchestrator.fail_start = False
    assert sorted(await start_unstarted_runs(db, orchestrator)) == sorted(lost)


class _RefusesOne(FakeOrchestrator):
    refused: uuid.UUID | None = None

    async def start_run(self, run_id: uuid.UUID) -> str:
        if run_id == self.refused:
            raise ValueError("this run can't start")
        return await super().start_run(run_id)


async def test_a_run_that_cannot_start_does_not_hold_up_the_others(db: Factory) -> None:
    first, second = await _runs(
        db, (RunStatus.QUEUED, None, LONG_AGO * 2), (RunStatus.QUEUED, None, LONG_AGO)
    )
    orchestrator = _RefusesOne()
    orchestrator.refused = first
    assert await start_unstarted_runs(db, orchestrator) == [second]
    assert await _workflow_ids(db, [first, second]) == [None, f"run-{second}"]


async def test_api_instances_passing_at_once_start_each_run_once(
    db: Factory, orchestrator: FakeOrchestrator
) -> None:
    lost = await _runs(db, *[(RunStatus.QUEUED, None, LONG_AGO)] * 4)
    orchestrator.start_delay = 0.05  # long enough for the passes to overlap
    first, second = await asyncio.gather(
        start_unstarted_runs(db, orchestrator), start_unstarted_runs(db, orchestrator)
    )
    assert sorted(first + second) == sorted(lost)
    assert sorted(orchestrator.started) == sorted(lost)  # no run was started twice


async def test_the_background_task_keeps_passing(
    db: Factory, orchestrator: FakeOrchestrator
) -> None:
    [lost] = await _runs(db, (RunStatus.QUEUED, None, LONG_AGO))
    orchestrator.fail_start = True  # the first passes fail; the task carries on
    task = asyncio.create_task(reconcile_forever(db, orchestrator, interval_seconds=0.01))
    try:
        await asyncio.sleep(0.1)
        orchestrator.fail_start = False
        for _ in range(500):  # a later pass starts the run and stores its workflow id
            if await _workflow_ids(db, [lost]) == [f"run-{lost}"]:
                break
            await asyncio.sleep(0.01)
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    assert orchestrator.started == [lost]
    assert await _workflow_ids(db, [lost]) == [f"run-{lost}"]

import uuid
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.enums import RunStatus, StageStatus
from agentic_db.models import AuditLog, Run, RunEvent
from api_testkit import (
    ADMIN,
    FakeOrchestrator,
    add_stage_run,
    as_user,
    set_run_status,
    start_run,
    team_project,
)

Factory = async_sessionmaker[AsyncSession]


async def _failed_run(
    client: httpx.AsyncClient,
    db: Factory,
    project_id: str,
    owner: str = "bob",
    status: RunStatus = RunStatus.FAILED,
    **body: Any,
) -> str:
    """A run that approved literature, then ended in ``status`` during method."""
    run_id = await start_run(client, project_id, user=owner, **body)
    await add_stage_run(db, run_id, "literature", StageStatus.APPROVED)
    await add_stage_run(db, run_id, "method", StageStatus.FAILED, error="stage.error")
    await set_run_status(db, run_id, status, "stage.error" if status == RunStatus.FAILED else None)
    return run_id


def _retry(client: httpx.AsyncClient, run_id: str, stage: str, user: dict[str, str]) -> Any:
    return client.post(f"/api/v1/runs/{run_id}/retry", params={"stage": stage}, headers=user)


async def _events(db: Factory, run_id: str) -> list[tuple[str, dict[str, Any]]]:
    async with db() as session:
        events = await session.scalars(
            select(RunEvent).where(RunEvent.run_id == uuid.UUID(run_id)).order_by(RunEvent.seq)
        )
        return [(event.type, event.payload) for event in events]


async def test_retry_starts_a_new_execution_at_the_stage(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    project_id = await team_project(client)
    run_id = await _failed_run(client, db, project_id)

    response = await _retry(client, run_id, "method", as_user("bob"))
    assert response.status_code == 202, response.text
    assert response.json() == {"status": "accepted"}
    assert orchestrator.restarted == [(uuid.UUID(run_id), "method")]
    async with db() as session:
        run = await session.get(Run, uuid.UUID(run_id))
        audit = (
            await session.scalars(select(AuditLog).where(AuditLog.action == "run.retry"))
        ).one()
    assert run is not None
    assert (run.status, run.error, run.workflow_id) == (RunStatus.RUNNING, None, f"run-{run_id}")
    assert (await _events(db, run_id))[-1] == (
        "run.status",
        {"status": "running", "retry_stage": "method"},
    )
    assert (audit.actor_id, audit.target_id, audit.details) == (
        "bob",
        run_id,
        {"stage": "method", "previous_status": "failed"},
    )


async def test_only_finished_runs_can_be_retried(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    project_id = await team_project(client)
    for status in (
        RunStatus.QUEUED,
        RunStatus.RUNNING,
        RunStatus.AWAITING_APPROVAL,
        RunStatus.PAUSED_BUDGET,
    ):
        run_id = await _failed_run(client, db, project_id, status=status)
        response = await _retry(client, run_id, "literature", as_user("bob"))
        assert (response.status_code, response.json()["detail"]) == (409, "run.not_retryable")
    for status in (RunStatus.COMPLETED, RunStatus.REJECTED, RunStatus.CANCELLED):
        run_id = await _failed_run(client, db, project_id, status=status)
        assert (await _retry(client, run_id, "literature", as_user("bob"))).status_code == 202
    assert len(orchestrator.restarted) == 3


async def test_retry_needs_a_reached_stage_of_the_run(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    project_id = await team_project(client)
    run_id = await _failed_run(
        client, db, project_id, config={"stages": ["literature", "method", "coding"]}
    )
    await add_stage_run(db, run_id, "experiment", StageStatus.FAILED)  # outside the run's stages

    for stage in ("coding", "experiment", "writing", "review"):
        response = await _retry(client, run_id, stage, as_user("bob"))
        assert (response.status_code, response.json()["detail"]) == (409, "stage.not_reached")
    missing = await client.post(f"/api/v1/runs/{run_id}/retry", headers=as_user("bob"))
    assert missing.status_code == 422
    assert (await _retry(client, run_id, "literature", as_user("bob"))).status_code == 202
    assert orchestrator.restarted == [(uuid.UUID(run_id), "literature")]


async def test_who_may_retry(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    project_id = await team_project(client)
    alices = await _failed_run(client, db, project_id, owner="alice")
    for user, status in (
        (as_user("bob"), 403),  # a researcher steers only their own runs
        (as_user("vera"), 403),  # viewers only read
        (as_user("carol"), 404),  # not a member
        ({}, 401),
    ):
        assert (await _retry(client, alices, "method", user)).status_code == status
    assert orchestrator.restarted == []
    assert (await _retry(client, alices, "method", ADMIN)).status_code == 202

    bobs = await _failed_run(client, db, project_id, owner="bob")
    assert (await _retry(client, bobs, "method", as_user("alice"))).status_code == 202  # owner
    assert len(orchestrator.restarted) == 2


async def test_retry_restores_the_run_when_temporal_is_down(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    project_id = await team_project(client)
    run_id = await _failed_run(client, db, project_id)
    orchestrator.fail_start = True

    response = await _retry(client, run_id, "method", as_user("bob"))
    assert (response.status_code, response.json()["detail"]) == (503, "orchestrator.unavailable")
    async with db() as session:
        run = await session.get(Run, uuid.UUID(run_id))
        audit = (
            await session.scalars(select(AuditLog).where(AuditLog.action == "run.retry"))
        ).all()
    assert run is not None
    assert (run.status, run.error) == (RunStatus.FAILED, "stage.error")
    assert (await _events(db, run_id))[-2:] == [
        ("run.status", {"status": "running", "retry_stage": "method"}),
        ("run.status", {"status": "failed", "error": "stage.error"}),
    ]
    assert audit == []

    orchestrator.fail_start = False  # Temporal is back: the same retry now works
    assert (await _retry(client, run_id, "method", as_user("bob"))).status_code == 202


async def test_retry_waits_until_the_previous_execution_closes(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    project_id = await team_project(client)
    run_id = await _failed_run(client, db, project_id, status=RunStatus.CANCELLED)
    orchestrator.still_running = True

    response = await _retry(client, run_id, "method", as_user("bob"))
    assert (response.status_code, response.json()["detail"]) == (409, "run.not_retryable")
    async with db() as session:
        run = await session.get(Run, uuid.UUID(run_id))
    assert run is not None
    assert (run.status, run.error) == (RunStatus.CANCELLED, None)

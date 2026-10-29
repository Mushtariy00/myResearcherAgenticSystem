import hashlib
import json
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.enums import RunStatus, StageStatus
from agentic_db.models import Approval, Run, RunEvent, StageOutput, StageRun
from api_testkit import FakeOrchestrator, as_user

Factory = async_sessionmaker[AsyncSession]


async def _team_project(client: httpx.AsyncClient) -> str:
    """alice owns it; bob is a researcher; vera is a viewer."""
    project_id = (
        await client.post("/api/v1/projects", json={"name": "Depth"}, headers=as_user("alice"))
    ).json()["id"]
    for email, role in (("bob@lab.test", "researcher"), ("vera@lab.test", "viewer")):
        response = await client.post(
            f"/api/v1/projects/{project_id}/members",
            json={"email": email, "role": role},
            headers=as_user("alice"),
        )
        assert response.status_code == 201
    return project_id


async def _run(client: httpx.AsyncClient, project_id: str, user: str = "bob") -> str:
    response = await client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={"topic": "Monocular depth"},
        headers=as_user(user),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _awaiting_output(db: Factory, run_id: str) -> tuple[str, str]:
    """Simulate the worker: the literature stage produced an output waiting for review."""
    data = {"summary": "two papers"}
    sha = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    async with db() as session:
        stage_run = StageRun(
            run_id=uuid.UUID(run_id), stage="literature", status=StageStatus.OUTPUT_READY
        )
        session.add(stage_run)
        await session.flush()
        output = StageOutput(stage_run_id=stage_run.id, data=data, sha256=sha)
        session.add(output)
        run = await session.get(Run, uuid.UUID(run_id))
        assert run is not None
        run.status = RunStatus.AWAITING_APPROVAL
        await session.commit()
        return str(output.id), sha


async def test_researcher_starts_a_run(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    project_id = await _team_project(client)
    run_id = await _run(client, project_id)
    assert orchestrator.started == [uuid.UUID(run_id)]
    async with db() as session:
        events = (
            await session.scalars(select(RunEvent).where(RunEvent.run_id == uuid.UUID(run_id)))
        ).all()
    assert [(e.seq, e.type) for e in events] == [(1, "run.created")]


async def test_viewers_cannot_start_runs(client: httpx.AsyncClient) -> None:
    project_id = await _team_project(client)
    response = await client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={"topic": "Monocular depth"},
        headers=as_user("vera"),
    )
    assert response.status_code == 403


async def test_run_is_marked_failed_when_temporal_is_down(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    project_id = await _team_project(client)
    orchestrator.fail_start = True
    response = await client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={"topic": "Monocular depth"},
        headers=as_user("bob"),
    )
    assert response.status_code == 503
    async with db() as session:
        run = (await session.scalars(select(Run))).one()
    assert run.status == RunStatus.FAILED
    assert run.error == "orchestrator.unavailable"


async def test_run_detail_shows_the_output_to_review(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project_id = await _team_project(client)
    run_id = await _run(client, project_id)
    output_id, sha = await _awaiting_output(db, run_id)

    detail = (await client.get(f"/api/v1/runs/{run_id}", headers=as_user("bob"))).json()
    assert detail["awaiting_stage"] == "literature"
    assert (detail["awaiting"]["id"], detail["awaiting"]["sha256"]) == (output_id, sha)
    assert detail["can_steer"] is True
    assert (await client.get(f"/api/v1/runs/{run_id}", headers=as_user("vera"))).json()[
        "can_steer"
    ] is False


async def test_approval_reaches_the_workflow(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    project_id = await _team_project(client)
    run_id = await _run(client, project_id)
    output_id, sha = await _awaiting_output(db, run_id)

    response = await client.post(
        f"/api/v1/runs/{run_id}/approvals",
        json={"stage_output_id": output_id, "sha256": sha, "decision": "approve", "comment": "ok"},
        headers=as_user("bob"),
    )
    assert response.status_code == 202, response.text
    [(sent_run, decision)] = orchestrator.decisions
    assert sent_run == uuid.UUID(run_id)
    assert (decision.stage, decision.stage_output_id, decision.decision, decision.actor_id) == (
        "literature",
        output_id,
        "approve",
        "bob",
    )


async def test_stale_or_duplicate_approvals_conflict(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project_id = await _team_project(client)
    run_id = await _run(client, project_id)
    output_id, sha = await _awaiting_output(db, run_id)
    url = f"/api/v1/runs/{run_id}/approvals"

    stale = await client.post(
        url,
        json={"stage_output_id": output_id, "sha256": "0" * 64, "decision": "approve"},
        headers=as_user("bob"),
    )
    assert (stale.status_code, stale.json()["detail"]) == (409, "approval.stale")

    async with db() as session:
        session.add(
            Approval(
                stage_output_id=uuid.UUID(output_id), sha256=sha, decision="approve", actor_id="bob"
            )
        )
        await session.commit()
    duplicate = await client.post(
        url,
        json={"stage_output_id": output_id, "sha256": sha, "decision": "reject"},
        headers=as_user("alice"),
    )
    assert (duplicate.status_code, duplicate.json()["detail"]) == (409, "approval.duplicate")


async def test_who_may_decide(client: httpx.AsyncClient, db: Factory) -> None:
    project_id = await _team_project(client)
    run_id = await _run(client, project_id, user="alice")  # owned by alice, not bob
    output_id, sha = await _awaiting_output(db, run_id)
    body = {"stage_output_id": output_id, "sha256": sha, "decision": "approve"}
    url = f"/api/v1/runs/{run_id}/approvals"

    assert (await client.post(url, json=body, headers=as_user("vera"))).status_code == 403  # viewer
    assert (
        await client.post(url, json=body, headers=as_user("bob"))
    ).status_code == 403  # not his run
    assert (await client.post(url, json=body, headers=as_user("alice"))).status_code == 202


async def test_workflow_refusal_is_a_conflict(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    project_id = await _team_project(client)
    run_id = await _run(client, project_id)
    output_id, sha = await _awaiting_output(db, run_id)
    orchestrator.reject_decisions = True
    response = await client.post(
        f"/api/v1/runs/{run_id}/approvals",
        json={"stage_output_id": output_id, "sha256": sha, "decision": "approve"},
        headers=as_user("bob"),
    )
    assert (response.status_code, response.json()["detail"]) == (
        409,
        "approval.rejected_by_workflow",
    )


async def test_cancel(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    project_id = await _team_project(client)
    run_id = await _run(client, project_id)
    assert (
        await client.post(f"/api/v1/runs/{run_id}/cancel", headers=as_user("vera"))
    ).status_code == 403
    assert (
        await client.post(f"/api/v1/runs/{run_id}/cancel", headers=as_user("bob"))
    ).status_code == 202
    assert orchestrator.cancelled == [uuid.UUID(run_id)]

    async with db() as session:
        run = await session.get(Run, uuid.UUID(run_id))
        assert run is not None
        run.status = RunStatus.CANCELLED
        await session.commit()
    again = await client.post(f"/api/v1/runs/{run_id}/cancel", headers=as_user("bob"))
    assert (again.status_code, again.json()["detail"]) == (409, "run.already_finished")

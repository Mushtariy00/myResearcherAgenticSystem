import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.enums import RunStatus, StageStatus
from agentic_db.models import Approval, AuditLog, Run, RunEvent, StageRun
from api_testkit import (
    ADMIN,
    FakeOrchestrator,
    add_stage_run,
    as_user,
    awaiting_output,
    set_run_status,
    start_run,
    team_project,
)

Factory = async_sessionmaker[AsyncSession]


async def test_researcher_starts_a_run(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    assert orchestrator.started == [uuid.UUID(run_id)]
    async with db() as session:
        events = (
            await session.scalars(select(RunEvent).where(RunEvent.run_id == uuid.UUID(run_id)))
        ).all()
    assert [(e.seq, e.type) for e in events] == [(1, "run.created")]


async def test_viewers_cannot_start_runs(client: httpx.AsyncClient) -> None:
    project_id = await team_project(client)
    response = await client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={"topic": "Monocular depth"},
        headers=as_user("vera"),
    )
    assert response.status_code == 403


async def test_run_is_marked_failed_when_temporal_is_down(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    project_id = await team_project(client)
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


async def test_run_options_are_stored_and_shown(client: httpx.AsyncClient, db: Factory) -> None:
    project_id = await team_project(client)
    options = {"year_from": 2021, "sources": ["arxiv"], "max_papers": 10, "stages": ["literature"]}
    response = await client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={"topic": "Monocular depth", "config": options},
        headers=as_user("bob"),
    )
    assert response.status_code == 201, response.text
    expected = {
        "year_from": 2021,
        "year_to": 2026,
        "sources": ["arxiv"],
        "max_papers": 10,
        "stages": ["literature"],
        "dataset": "nyu2",
    }
    assert response.json()["config"] == expected
    run_id = response.json()["id"]

    async with db() as session:
        run = await session.get(Run, uuid.UUID(run_id))
        assert run is not None
        assert run.config == expected  # stored as JSON, defaults included
    detail = (await client.get(f"/api/v1/runs/{run_id}", headers=as_user("vera"))).json()
    assert detail["config"] == expected
    listed = (
        await client.get(f"/api/v1/projects/{project_id}/runs", headers=as_user("vera"))
    ).json()
    assert listed[0]["config"] == expected


async def test_run_options_default_and_are_validated(client: httpx.AsyncClient) -> None:
    project_id = await team_project(client)
    url = f"/api/v1/projects/{project_id}/runs"
    created = await client.post(url, json={"topic": "Monocular depth"}, headers=as_user("bob"))
    assert created.json()["config"]["stages"] == [
        "literature",
        "method",
        "coding",
        "experiment",
        "writing",
    ]
    for config in (
        {"stages": ["method"]},  # must start with literature
        {"year_from": 2026, "year_to": 2020},
        {"sources": ["arxiv", "arxiv"]},
        {"max_papers": 500},
        {"unknown": True},
    ):
        response = await client.post(
            url, json={"topic": "Monocular depth", "config": config}, headers=as_user("bob")
        )
        assert response.status_code == 422, config


async def test_runs_stored_before_run_options_read_as_defaults(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project_id = await team_project(client)
    async with db() as session:
        session.add_all(
            [
                Run(project_id=uuid.UUID(project_id), owner_id="bob", topic="Old", config={}),
                Run(
                    project_id=uuid.UUID(project_id),
                    owner_id="bob",
                    topic="Odd",
                    config={"stages": "everything"},
                ),
            ]
        )
        await session.commit()
    runs = (await client.get(f"/api/v1/projects/{project_id}/runs", headers=as_user("bob"))).json()
    assert [run["config"]["max_papers"] for run in runs] == [20, 20]


async def test_recent_runs_span_the_callers_projects(client: httpx.AsyncClient) -> None:
    depth = await team_project(client, "Depth")
    other = (
        await client.post("/api/v1/projects", json={"name": "Other"}, headers=as_user("carol"))
    ).json()["id"]
    first = await start_run(client, depth, user="bob")
    hidden = await start_run(client, other, user="carol")
    second = await start_run(client, depth, user="alice")

    mine = (await client.get("/api/v1/runs", headers=as_user("vera"))).json()
    assert [(r["id"], r["project_name"]) for r in mine] == [(second, "Depth"), (first, "Depth")]
    assert mine[0]["config"]["dataset"] == "nyu2"
    everything = (await client.get("/api/v1/runs", headers=ADMIN)).json()
    assert [r["id"] for r in everything] == [second, hidden, first]
    assert (await client.get("/api/v1/runs")).status_code == 401


async def test_recent_runs_filter_by_status_and_limit(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project_id = await team_project(client)
    runs = [await start_run(client, project_id) for _ in range(3)]
    await set_run_status(db, runs[0], RunStatus.FAILED, "stage.error")

    failed = (await client.get("/api/v1/runs?status=failed", headers=as_user("bob"))).json()
    assert [(r["id"], r["error"]) for r in failed] == [(runs[0], "stage.error")]
    newest = (await client.get("/api/v1/runs?limit=2", headers=as_user("bob"))).json()
    assert [r["id"] for r in newest] == [runs[2], runs[1]]
    assert (await client.get("/api/v1/runs?limit=0", headers=as_user("bob"))).status_code == 422
    assert (
        await client.get("/api/v1/runs?status=nonsense", headers=as_user("bob"))
    ).status_code == 422


async def test_run_detail_shows_the_output_to_review(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    output_id, sha = await awaiting_output(db, run_id)

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
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    output_id, sha = await awaiting_output(db, run_id)

    response = await client.post(
        f"/api/v1/runs/{run_id}/approvals",
        json={"stage_output_id": output_id, "sha256": sha, "decision": "approve", "comment": "ok"},
        headers=as_user("bob"),
    )
    assert response.status_code == 202, response.text
    [(sent_run, decision)] = orchestrator.decisions
    assert sent_run == uuid.UUID(run_id)
    assert (
        decision.stage,
        decision.stage_output_id,
        decision.decision,
        decision.actor_id,
        decision.edited_data,
    ) == ("literature", output_id, "approve", "bob", None)


async def test_stale_or_duplicate_approvals_conflict(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    output_id, sha = await awaiting_output(db, run_id)
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
    project_id = await team_project(client)
    run_id = await start_run(client, project_id, user="alice")  # owned by alice, not bob
    output_id, sha = await awaiting_output(db, run_id)
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
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    output_id, sha = await awaiting_output(db, run_id)
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
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
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


async def test_cancel_closes_a_run_that_has_no_workflow(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    """A demo row (or a run whose start was lost) has nothing in Temporal to cancel."""
    project_id = await team_project(client)
    async with db() as session:
        run = Run(
            project_id=uuid.UUID(project_id),
            owner_id="bob",
            topic="Seeded",
            status=RunStatus.AWAITING_APPROVAL,
        )
        session.add(run)
        await session.commit()
    run_id = str(run.id)
    await add_stage_run(db, run_id, "literature", StageStatus.APPROVED)
    await add_stage_run(db, run_id, "method", StageStatus.OUTPUT_READY)

    response = await client.post(f"/api/v1/runs/{run_id}/cancel", headers=as_user("bob"))
    assert response.status_code == 202, response.text
    assert orchestrator.cancelled == []
    async with db() as session:
        stored = await session.get(Run, run.id)
        assert stored is not None
        stages = {
            s.stage: (s.status, s.finished_at is not None)
            for s in await session.scalars(select(StageRun).where(StageRun.run_id == run.id))
        }
        events = (await session.scalars(select(RunEvent).where(RunEvent.run_id == run.id))).all()
        audit = (await session.scalars(select(AuditLog).where(AuditLog.target_id == run_id))).one()
    assert (stored.status, stored.error) == (RunStatus.CANCELLED, None)
    assert stages == {
        "literature": (StageStatus.APPROVED, False),
        "method": (StageStatus.CANCELLED, True),
    }
    assert [(e.type, e.payload) for e in events] == [
        ("run.status", {"status": "cancelled", "error": None})
    ]
    assert (audit.action, audit.actor_id, audit.details) == (
        "run.cancel",
        "bob",
        {"without_workflow": True},
    )
    again = await client.post(f"/api/v1/runs/{run_id}/cancel", headers=as_user("bob"))
    assert (again.status_code, again.json()["detail"]) == (409, "run.already_finished")


async def test_cancel_reports_an_unreachable_temporal(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    orchestrator.fail_start = True
    response = await client.post(f"/api/v1/runs/{run_id}/cancel", headers=as_user("bob"))
    assert (response.status_code, response.json()["detail"]) == (503, "orchestrator.unavailable")
    async with db() as session:
        run = await session.get(Run, uuid.UUID(run_id))
        audit = (
            await session.scalars(select(AuditLog).where(AuditLog.action == "run.cancel"))
        ).all()
    assert run is not None
    assert run.status == RunStatus.QUEUED
    assert audit == []

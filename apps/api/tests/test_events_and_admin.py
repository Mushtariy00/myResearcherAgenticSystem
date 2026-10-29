import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.enums import RunStatus
from agentic_db import append_event
from agentic_db.models import Run
from api_testkit import as_user

Factory = async_sessionmaker[AsyncSession]


async def test_sse_replays_only_events_after_last_event_id(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project_id = (
        await client.post("/api/v1/projects", json={"name": "Depth"}, headers=as_user("alice"))
    ).json()["id"]
    run_id = (
        await client.post(
            f"/api/v1/projects/{project_id}/runs", json={"topic": "Depth"}, headers=as_user("alice")
        )
    ).json()["id"]
    async with db() as session:
        await append_event(session, uuid.UUID(run_id), "stage.started", {"stage": "literature"})
        await append_event(session, uuid.UUID(run_id), "run.status", {"status": "completed"})
        run = await session.get(Run, uuid.UUID(run_id))
        assert run is not None
        run.status = RunStatus.COMPLETED  # a finished run's stream ends after the replay
        await session.commit()

    response = await client.get(
        f"/api/v1/runs/{run_id}/events", headers={**as_user("alice"), "last-event-id": "1"}
    )
    body = response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "id: 1\n" not in body  # run.created was already seen
    assert body.index("id: 2\n") < body.index("id: 3\n")
    assert body.rstrip().endswith("event: end\ndata: {}")


async def test_sse_is_for_members_only(client: httpx.AsyncClient) -> None:
    project_id = (
        await client.post("/api/v1/projects", json={"name": "Depth"}, headers=as_user("alice"))
    ).json()["id"]
    run_id = (
        await client.post(
            f"/api/v1/projects/{project_id}/runs", json={"topic": "Depth"}, headers=as_user("alice")
        )
    ).json()["id"]
    assert (
        await client.get(f"/api/v1/runs/{run_id}/events", headers=as_user("bob"))
    ).status_code == 404


async def test_only_admins_set_budgets_and_users_see_their_own(client: httpx.AsyncClient) -> None:
    denied = await client.put(
        "/api/v1/admin/budgets/bob", json={"monthly_usd": "5"}, headers=as_user("bob")
    )
    assert denied.status_code == 403

    response = await client.put(
        "/api/v1/admin/budgets/bob", json={"monthly_usd": "5.50"}, headers=as_user("root", "admin")
    )
    assert response.status_code == 200
    me = (await client.get("/api/v1/me", headers=as_user("bob"))).json()
    assert (me["budget_usd"], me["spent_usd"]) == ("5.500000", "0")


async def test_paid_model_kill_switch(client: httpx.AsyncClient) -> None:
    admin = as_user("root", "admin")
    assert (await client.get("/api/v1/admin/settings/paid-models", headers=admin)).json() == {
        "enabled": True
    }
    await client.put("/api/v1/admin/settings/paid-models", json={"enabled": False}, headers=admin)
    assert (await client.get("/api/v1/admin/settings/paid-models", headers=admin)).json() == {
        "enabled": False
    }

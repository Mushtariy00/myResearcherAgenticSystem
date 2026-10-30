import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.enums import RunStatus
from agentic_db import append_event
from agentic_db.models import AuditLog, Budget, Run
from api_testkit import as_user, create_project

Factory = async_sessionmaker[AsyncSession]


async def test_sse_replays_only_events_after_last_event_id(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project_id = await create_project(client, "Depth")
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
    project_id = await create_project(client, "Depth")
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


async def test_budgets_are_for_existing_accounts_in_storable_amounts(
    client: httpx.AsyncClient, db: Factory
) -> None:
    admin = as_user("root", "admin")
    missing = await client.put(
        "/api/v1/admin/budgets/bobb", json={"monthly_usd": "5"}, headers=admin
    )  # a typo: nobody could ever spend this budget
    assert (missing.status_code, missing.json()["detail"]) == (404, "user.not_found")
    too_long = await client.put(
        f"/api/v1/admin/budgets/{'x' * 65}", json={"monthly_usd": "5"}, headers=admin
    )
    assert too_long.status_code == 422  # ids are at most 64 characters, as their columns
    for amount in ("5.1234567", "10000.5", "-1"):  # more decimals than stored, too much, negative
        response = await client.put(
            "/api/v1/admin/budgets/bob", json={"monthly_usd": amount}, headers=admin
        )
        assert response.status_code == 422, amount
    async with db() as session:
        assert (await session.scalars(select(Budget))).all() == []
        assert (await session.scalars(select(AuditLog))).all() == []

    exact = await client.put(
        "/api/v1/admin/budgets/bob", json={"monthly_usd": "5.123456"}, headers=admin
    )
    assert (exact.status_code, exact.json()["monthly_usd"]) == (200, "5.123456")


async def test_run_budget_caps_are_storable_amounts(client: httpx.AsyncClient) -> None:
    project_id = await create_project(client, "Depth")
    url = f"/api/v1/projects/{project_id}/runs"
    alice = as_user("alice")
    refused = await client.post(
        url, json={"topic": "Depth", "budget_cap_usd": "0.0000001"}, headers=alice
    )
    assert refused.status_code == 422
    created = await client.post(
        url, json={"topic": "Depth", "budget_cap_usd": "0.000001"}, headers=alice
    )
    assert (created.status_code, created.json()["budget_cap_usd"]) == (201, "0.000001")


async def test_paid_model_kill_switch(client: httpx.AsyncClient) -> None:
    admin = as_user("root", "admin")
    assert (await client.get("/api/v1/admin/settings/paid-models", headers=admin)).json() == {
        "enabled": True
    }
    await client.put("/api/v1/admin/settings/paid-models", json={"enabled": False}, headers=admin)
    assert (await client.get("/api/v1/admin/settings/paid-models", headers=admin)).json() == {
        "enabled": False
    }

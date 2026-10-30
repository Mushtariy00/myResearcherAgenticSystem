import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.contracts import EventType
from agentic_core.enums import Decision, LlmCallState, LlmTier, RunStatus, StageStatus
from agentic_db import append_event
from agentic_db.models import Approval, LlmCall, NotificationRead, Run
from agentic_db.spend import month_start
from api_testkit import (
    ADMIN,
    METHOD_OUTPUT,
    add_output,
    add_stage_run,
    as_user,
    awaiting_output,
    create_project,
    set_run_status,
    start_run,
    team_project,
)

Factory = async_sessionmaker[AsyncSession]
URL = "/api/v1/me/notifications"


async def _notifications(client: httpx.AsyncClient, user: str, role: str = "user") -> dict:
    response = await client.get(URL, headers=as_user(user, role))
    assert response.status_code == 200, response.text
    return response.json()


async def _keys(client: httpx.AsyncClient, user: str, role: str = "user") -> set[str]:
    return {item["key"] for item in (await _notifications(client, user, role))["items"]}


async def _finished_run(
    db: Factory,
    project_id: str,
    owner: str,
    status: RunStatus,
    finished_at: datetime | None = None,
    error: str | None = None,
) -> str:
    async with db() as session:
        run = Run(
            project_id=uuid.UUID(project_id),
            owner_id=owner,
            topic=f"{status.value} run",
            status=status,
            error=error,
        )
        session.add(run)
        await session.flush()
        if finished_at is not None:
            await session.execute(
                update(Run).where(Run.id == run.id).values(updated_at=finished_at)
            )
        await session.commit()
        return str(run.id)


async def test_approvals_notify_whoever_may_decide(client: httpx.AsyncClient, db: Factory) -> None:
    project_id = await team_project(client)
    await create_project(client, "Other", owner="carol")
    bobs_run = await start_run(client, project_id, user="bob")
    bobs_output, _ = await awaiting_output(db, bobs_run, "literature")
    alices_run = await start_run(client, project_id, user="alice")
    alices_output, _ = await awaiting_output(db, alices_run, "method", METHOD_OUTPUT)

    bobs, alices = f"approval:{bobs_output}", f"approval:{alices_output}"
    assert await _keys(client, "bob") == {bobs}  # researchers decide on their own runs only
    assert await _keys(client, "alice") == {bobs, alices}  # owners decide on every run
    assert await _keys(client, "root", "admin") == {bobs, alices}
    assert await _keys(client, "vera") == set()  # viewers never decide
    assert await _keys(client, "carol") == set()  # not a member

    [item] = (await _notifications(client, "bob"))["items"]
    assert item == {
        "key": bobs,
        "kind": "approval_needed",
        "created_at": item["created_at"],
        "read": False,
        "run_id": bobs_run,
        "project_id": project_id,
        "stage": "literature",
        "params": {"topic": "Monocular depth", "project": "Depth", "stage": "literature"},
    }


async def test_only_the_latest_undecided_output_of_a_waiting_run_notifies(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    literature, _ = await awaiting_output(db, run_id, "literature")
    decided = await add_stage_run(db, run_id, "coding", StageStatus.OUTPUT_READY)
    decided_output, decided_sha = await add_output(db, decided, {"summary": "code"})
    async with db() as session:  # decided, but the worker hasn't moved the stage on yet
        session.add(
            Approval(
                stage_output_id=uuid.UUID(decided_output),
                sha256=decided_sha,
                decision=Decision.APPROVE,
                actor_id="alice",
            )
        )
        await session.commit()
    edited = await add_stage_run(db, run_id, "method", StageStatus.OUTPUT_READY)
    await add_output(db, edited, METHOD_OUTPUT, version=1)
    latest, _ = await add_output(db, edited, METHOD_OUTPUT, version=2, edited_by="alice")

    assert await _keys(client, "bob") == {f"approval:{literature}", f"approval:{latest}"}
    await set_run_status(db, run_id, RunStatus.RUNNING)  # not waiting any more
    assert await _keys(client, "bob") == set()


async def test_approvals_warn_a_day_before_they_expire(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project_id = await team_project(client)
    await client.put(
        f"/api/v1/projects/{project_id}/settings",
        json={
            "privacy": "standard",
            "allow_free_models": True,
            "auto_approve": False,
            "approval_expiry_days": 3,
        },
        headers=as_user("alice"),
    )
    now = datetime.now(UTC)
    ready_at = now - timedelta(days=2, hours=12)
    old_run = await start_run(client, project_id)
    old_stage = await add_stage_run(db, old_run, "literature")
    old_output, _ = await add_output(db, old_stage, {"summary": "old"}, created_at=ready_at)
    new_run = await start_run(client, project_id)
    new_stage = await add_stage_run(db, new_run, "literature")
    new_output, _ = await add_output(
        db, new_stage, {"summary": "new"}, created_at=now - timedelta(days=1)
    )
    for run_id in (old_run, new_run):
        await set_run_status(db, run_id, RunStatus.AWAITING_APPROVAL)

    items = {item["key"]: item for item in (await _notifications(client, "bob"))["items"]}
    assert set(items) == {
        f"approval:{old_output}",
        f"approval.expiring:{old_output}",
        f"approval:{new_output}",
    }
    expiring = items[f"approval.expiring:{old_output}"]
    assert expiring["kind"] == "approval_expiring"
    assert datetime.fromisoformat(expiring["created_at"]) == ready_at + timedelta(days=2)
    assert expiring["params"]["days"] == 3
    expires_at = datetime.fromisoformat(str(expiring["params"]["expires_at"]))
    assert expires_at == ready_at + timedelta(days=3)


async def test_finished_runs_notify_their_owner(client: httpx.AsyncClient, db: Factory) -> None:
    project_id = await team_project(client)
    now = datetime.now(UTC)
    completed = await _finished_run(db, project_id, "bob", RunStatus.COMPLETED)
    failed = await _finished_run(db, project_id, "bob", RunStatus.FAILED, error="stage.error")
    cancelled = await _finished_run(db, project_id, "bob", RunStatus.CANCELLED)
    rejected = await _finished_run(db, project_id, "bob", RunStatus.REJECTED)
    await _finished_run(db, project_id, "bob", RunStatus.COMPLETED, now - timedelta(days=15))
    await _finished_run(db, project_id, "bob", RunStatus.RUNNING)
    alices = await _finished_run(db, project_id, "alice", RunStatus.COMPLETED)

    items = {item["run_id"]: item for item in (await _notifications(client, "bob"))["items"]}
    assert {run_id: item["kind"] for run_id, item in items.items()} == {
        completed: "run_completed",
        failed: "run_failed",
        cancelled: "run_cancelled",
        rejected: "run_rejected",
    }
    assert items[failed]["key"] == f"run.finished:{failed}"
    assert items[failed]["params"] == {
        "topic": "failed run",
        "project": "Depth",
        "error": "stage.error",
    }
    assert await _keys(client, "alice") == {f"run.finished:{alices}"}

    await client.delete(f"/api/v1/projects/{project_id}/members/bob", headers=as_user("alice"))
    assert await _keys(client, "bob") == set()  # runs in projects bob left are not his news


async def _status_event(db: Factory, run_id: str, status: RunStatus) -> int:
    """The run moved to ``status``, as the worker records it."""
    async with db() as session:
        run = await session.get(Run, uuid.UUID(run_id))
        assert run is not None
        run.status = status
        seq = await append_event(session, run.id, EventType.RUN_STATUS, {"status": status})
        await session.commit()
        return seq


async def test_paused_runs_notify_their_owner_and_lab_admins(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project_id = await team_project(client)
    bobs = await start_run(client, project_id, user="bob")
    alices = await start_run(client, project_id, user="alice")
    await _status_event(db, bobs, RunStatus.RUNNING)
    paused_at = await _status_event(db, bobs, RunStatus.PAUSED_BUDGET)
    await _status_event(db, bobs, RunStatus.PAUSED_BUDGET)  # still the same pause
    await _status_event(db, alices, RunStatus.RUNNING)  # not paused

    key = f"run.paused:{bobs}:{paused_at}"
    [item] = (await _notifications(client, "bob"))["items"]
    assert item == {
        "key": key,
        "kind": "run_paused",
        "created_at": item["created_at"],
        "read": False,
        "run_id": bobs,
        "project_id": project_id,
        "stage": None,
        "params": {"topic": "Monocular depth", "project": "Depth"},
    }
    assert await _keys(client, "root", "admin") == {key}  # admins can top the balance up
    assert await _keys(client, "alice") == set()  # her project, not her run
    assert await _keys(client, "vera") == set()

    await client.post(f"{URL}/read", json={"keys": [key]}, headers=as_user("bob"))
    assert (await _notifications(client, "bob"))["unread_count"] == 0
    # It resumes after a top-up, and later the balance runs out again: that is news again.
    await _status_event(db, bobs, RunStatus.RUNNING)
    assert await _keys(client, "bob") == set()
    again = await _status_event(db, bobs, RunStatus.PAUSED_BUDGET)
    [item] = (await _notifications(client, "bob"))["items"]
    assert (item["key"], item["read"]) == (f"run.paused:{bobs}:{again}", False)

    await client.delete(f"/api/v1/projects/{project_id}/members/bob", headers=as_user("alice"))
    assert await _keys(client, "bob") == set()  # runs in projects bob left are not his news


async def _paid_call(
    db: Factory,
    at: datetime,
    *,
    state: LlmCallState = LlmCallState.SETTLED,
    cost: str | None = None,
    reserved: str = "0",
    tier: LlmTier = LlmTier.PAID,
) -> None:
    async with db() as session:
        session.add(
            LlmCall(
                idempotency_key=str(uuid.uuid4()),
                user_id="bob",
                role="literature",
                tier=tier,
                model="openai/gpt-5.4",
                state=state,
                reserved_usd=Decimal(reserved),
                cost_usd=Decimal(cost) if cost is not None else None,
                created_at=at,
            )
        )
        await session.commit()


async def test_budget_alerts_at_80_and_100_percent(client: httpx.AsyncClient, db: Factory) -> None:
    month = month_start()
    label = month.strftime("%Y-%m")
    await client.put("/api/v1/admin/budgets/bob", json={"monthly_usd": "10"}, headers=ADMIN)
    assert await _keys(client, "bob") == set()

    await _paid_call(db, month + timedelta(seconds=1), cost="5")
    await _paid_call(db, month + timedelta(seconds=2), cost="9", tier=LlmTier.FREE)  # not budget
    await _paid_call(db, month + timedelta(seconds=3), state=LlmCallState.RELEASED, reserved="9")
    await _paid_call(db, month + timedelta(seconds=4), cost="3.5")
    [alert] = (await _notifications(client, "bob"))["items"]
    assert alert["key"] == f"budget:{label}:80"
    assert alert["kind"] == "budget_alert"
    assert datetime.fromisoformat(alert["created_at"]) == month + timedelta(seconds=4)
    assert alert["params"] == {
        "percent": 80,
        "month": label,
        "budget_usd": "10.000000",
        "spent_usd": "8.500000",
    }

    # An open reservation counts until it settles, as it does for routing.
    await _paid_call(db, month + timedelta(seconds=5), state=LlmCallState.SENT, reserved="2")
    alerts = (await _notifications(client, "bob"))["items"]
    assert [(a["key"], datetime.fromisoformat(a["created_at"])) for a in alerts] == [
        (f"budget:{label}:100", month + timedelta(seconds=5)),
        (f"budget:{label}:80", month + timedelta(seconds=4)),
    ]
    assert await _keys(client, "alice") == set()  # no budget, no alerts


async def test_read_state_is_per_user_and_idempotent(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    output_id, _ = await awaiting_output(db, run_id)
    finished = await _finished_run(db, project_id, "bob", RunStatus.COMPLETED)
    approval = f"approval:{output_id}"
    assert (await _notifications(client, "bob"))["unread_count"] == 2

    body = {"keys": [approval, "approval:not-mine", f"run.finished:{uuid.uuid4()}"]}
    for _ in range(2):
        response = await client.post(f"{URL}/read", json=body, headers=as_user("bob"))
        assert response.status_code == 200, response.text
        listing = response.json()
        assert listing["unread_count"] == 1
        assert {i["key"]: i["read"] for i in listing["items"]} == {
            approval: True,
            f"run.finished:{finished}": False,
        }
    async with db() as session:
        stored = (await session.scalars(select(NotificationRead))).all()
    assert [(r.user_id, r.notification_key) for r in stored] == [("bob", approval)]
    alices = await _notifications(client, "alice")  # read state belongs to each user
    assert [(i["key"], i["read"]) for i in alices["items"]] == [(approval, False)]

    everything = await client.post(f"{URL}/read", json={"all": True}, headers=as_user("bob"))
    assert everything.json()["unread_count"] == 0
    assert all(item["read"] for item in (await _notifications(client, "bob"))["items"])

    for invalid in ({}, {"keys": []}, {"keys": ["x" * 201]}, {"all": True, "extra": 1}):
        response = await client.post(f"{URL}/read", json=invalid, headers=as_user("bob"))
        assert response.status_code == 422, invalid
    assert (await client.get(URL)).status_code == 401
    assert (await client.post(f"{URL}/read", json={"all": True})).status_code == 401


async def test_a_retry_makes_the_next_finish_news_again(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    await add_stage_run(db, run_id, "literature", StageStatus.FAILED)
    await set_run_status(db, run_id, RunStatus.FAILED, "stage.error")
    key = f"run.finished:{run_id}"
    await client.post(f"{URL}/read", json={"keys": [key]}, headers=as_user("bob"))
    [item] = (await _notifications(client, "bob"))["items"]
    assert (item["key"], item["kind"], item["read"]) == (key, "run_failed", True)

    retried = await client.post(
        f"/api/v1/runs/{run_id}/retry", params={"stage": "literature"}, headers=as_user("bob")
    )
    assert retried.status_code == 202
    assert await _keys(client, "bob") == set()  # running again
    await set_run_status(db, run_id, RunStatus.COMPLETED)
    [item] = (await _notifications(client, "bob"))["items"]
    assert (item["key"], item["kind"], item["read"]) == (key, "run_completed", False)


async def test_the_list_keeps_the_newest_fifty(client: httpx.AsyncClient, db: Factory) -> None:
    project_id = await team_project(client)
    now = datetime.now(UTC)
    runs = [
        await _finished_run(db, project_id, "bob", RunStatus.COMPLETED, now - timedelta(minutes=i))
        for i in range(55)
    ]
    listing = await _notifications(client, "bob")
    assert listing["unread_count"] == 55
    assert [item["run_id"] for item in listing["items"]] == runs[:50]

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import QueuePool

from agentic_api.orchestrator import OrchestratorUnavailableError, WorkflowNotFoundError
from agentic_api.routers import runs
from agentic_core.enums import LlmCallState, LlmTier, RunStatus, StageStatus
from agentic_db.models import Approval, AuditLog, LlmCall, Run, RunEvent, StageRun
from api_testkit import (
    ADMIN,
    FakeOrchestrator,
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

    # The worker's own knobs sit next to the options (the demo seed's runs) and don't hide them.
    async with db() as session:
        await session.execute(
            update(Run)
            .where(Run.id == uuid.UUID(run_id))
            .values(config={**expected, "simulated": True, "demo_stage_seconds": 600})
        )
        await session.commit()
    detail = (await client.get(f"/api/v1/runs/{run_id}", headers=as_user("vera"))).json()
    assert detail["config"] == expected


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
    other = await create_project(client, "Other", owner="carol")
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


async def test_cancel_reaches_a_workflow_started_while_it_looked(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    """Temporal had no workflow for the run when the cancel asked, and the reconciler started
    one before the cancel could record it in the database: that workflow is cancelled."""
    project_id = await team_project(client)
    async with db() as session:
        run = Run(project_id=uuid.UUID(project_id), owner_id="bob", topic="Lost start")
        session.add(run)
        await session.commit()
    asked = 0

    async def reconciler_starts_it_meanwhile(run_id: uuid.UUID) -> None:
        nonlocal asked
        asked += 1
        if asked == 1:
            async with db() as session:
                await session.execute(
                    update(Run).where(Run.id == run_id).values(workflow_id=f"run-{run_id}")
                )
                await session.commit()
            orchestrator.started.append(run_id)
            raise WorkflowNotFoundError(f"run-{run_id}")  # Temporal answered before the start

    orchestrator.before_cancel = reconciler_starts_it_meanwhile
    response = await client.post(f"/api/v1/runs/{run.id}/cancel", headers=as_user("bob"))
    assert response.status_code == 202, response.text
    assert orchestrator.cancelled == [run.id]
    async with db() as session:
        stored = await session.get(Run, run.id)
        audit = (
            await session.scalars(select(AuditLog).where(AuditLog.action == "run.cancel"))
        ).one()
    assert stored is not None
    assert stored.status == RunStatus.QUEUED  # the workflow records the cancel on its way out
    assert audit.details == {}


async def test_runs_in_hidden_projects_look_like_missing_runs(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    output_id, sha = await awaiting_output(db, run_id)
    carol = as_user("carol")  # not a member
    for target in (run_id, str(uuid.uuid4())):
        base = f"/api/v1/runs/{target}"
        for response in (
            await client.get(base, headers=carol),
            await client.get(f"{base}/stages/literature", headers=carol),
            await client.get(f"{base}/events", headers=carol),
            await client.get(f"{base}/artifacts", headers=carol),
            await client.post(f"{base}/approvals", json=_decision(output_id, sha), headers=carol),
            await client.post(f"{base}/cancel", headers=carol),
            await client.post(f"{base}/retry", params={"stage": "literature"}, headers=carol),
        ):
            assert (response.status_code, response.json()["detail"]) == (404, "run.not_found"), (
                response.url
            )


async def test_runs_list_pages_newest_first(client: httpx.AsyncClient, db: Factory) -> None:
    project_id = await team_project(client)
    other = await create_project(client, "Other", owner="carol")
    start = datetime(2026, 10, 1, tzinfo=UTC)
    async with db() as session:
        # Runs 0 to 2 share a creation time: their ids keep the order stable across pages.
        mine = [
            Run(
                project_id=uuid.UUID(project_id),
                owner_id="bob",
                topic=f"Run {i}",
                created_at=start + timedelta(minutes=max(i, 2)),
            )
            for i in range(5)
        ]
        foreign = Run(project_id=uuid.UUID(other), owner_id="carol", topic="Elsewhere")
        session.add_all([*mine, foreign])
        await session.commit()
    newest_first = [
        str(run.id) for run in sorted(mine, key=lambda run: (run.created_at, run.id), reverse=True)
    ]
    url = f"/api/v1/projects/{project_id}/runs"

    async def page(**params: Any) -> list[str]:
        response = await client.get(url, params=params, headers=as_user("vera"))
        assert response.status_code == 200, response.text
        return [run["id"] for run in response.json()]

    assert await page() == newest_first  # 50 a page by default
    first = await page(limit=2)
    second = await page(limit=2, before=first[-1])
    last = await page(limit=2, before=second[-1])
    assert (first, second, last) == (newest_first[:2], newest_first[2:4], newest_first[4:])
    assert await page(before=newest_first[-1]) == []

    for cursor in (str(uuid.uuid4()), str(foreign.id)):  # unknown, or another project's run
        response = await client.get(url, params={"before": cursor}, headers=as_user("vera"))
        assert (response.status_code, response.json()["detail"]) == (404, "run.not_found")
    for limit in (0, 201):
        response = await client.get(url, params={"limit": limit}, headers=as_user("vera"))
        assert response.status_code == 422


def _decision(output_id: str, sha: str, decision: str = "approve", **body: Any) -> dict[str, Any]:
    return {"stage_output_id": output_id, "sha256": sha, "decision": decision, **body}


async def _awaiting_attempt(
    db: Factory, run_id: str, attempt: int, last_attempt: int | None
) -> tuple[str, str]:
    """Attempt ``attempt`` of literature waits for review; its execution allows attempts up to
    ``last_attempt`` (None: recorded before the cap was)."""
    stage_run_id = await add_stage_run(
        db, run_id, "literature", attempt=attempt, last_attempt=last_attempt
    )
    output = await add_output(db, stage_run_id, {"summary": f"attempt {attempt}"})
    await set_run_status(db, run_id, RunStatus.AWAITING_APPROVAL)
    return output


async def _detail(client: httpx.AsyncClient, run_id: str) -> dict[str, Any]:
    response = await client.get(f"/api/v1/runs/{run_id}", headers=as_user("vera"))
    assert response.status_code == 200, response.text
    return response.json()


async def test_run_detail_counts_attempts_left_and_spend(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    other_run = await start_run(client, project_id)
    detail = await _detail(client, run_id)
    assert (detail["max_attempts"], detail["attempts_left"], Decimal(detail["spend_usd"])) == (
        3,
        None,  # nothing waits for a decision
        0,
    )

    await add_stage_run(
        db, run_id, "literature", StageStatus.CHANGES_REQUESTED, attempt=1, last_attempt=3
    )
    await _awaiting_attempt(db, run_id, attempt=2, last_attempt=3)
    calls = [  # run, state, reserved, cost
        (run_id, LlmCallState.SETTLED, "0.30", "0.25"),
        (run_id, LlmCallState.SENT, "0.10", None),
        (run_id, LlmCallState.UNKNOWN, "0.05", None),
        (run_id, LlmCallState.RESERVED, "0.02", None),
        (run_id, LlmCallState.RELEASED, "5", None),  # never sent: it cost nothing
        (other_run, LlmCallState.SETTLED, "1", "1"),
    ]
    async with db() as session:
        session.add_all(
            LlmCall(
                idempotency_key=str(uuid.uuid4()),
                run_id=uuid.UUID(run),
                user_id="bob",
                role="researcher",
                tier=LlmTier.PAID,
                model="google/gemini-2.5-flash",
                state=state,
                reserved_usd=Decimal(reserved),
                cost_usd=Decimal(cost) if cost is not None else None,
            )
            for run, state, reserved, cost in calls
        )
        await session.commit()
    detail = await _detail(client, run_id)
    assert (detail["attempts_left"], Decimal(detail["spend_usd"])) == (1, Decimal("0.42"))

    final = await start_run(client, project_id)
    await _awaiting_attempt(db, final, attempt=3, last_attempt=3)
    assert (await _detail(client, final))["attempts_left"] == 0
    legacy = await start_run(client, project_id)
    await _awaiting_attempt(db, legacy, attempt=1, last_attempt=None)
    assert (await _detail(client, legacy))["attempts_left"] is None


async def test_request_changes_needs_a_comment(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    output_id, sha = await awaiting_output(db, run_id)
    url = f"/api/v1/runs/{run_id}/approvals"
    for comment in ("", "  \n\t ", "\x00\x07"):
        response = await client.post(
            url,
            json=_decision(output_id, sha, "request_changes", comment=comment),
            headers=as_user("bob"),
        )
        assert (response.status_code, response.json()) == (
            422,
            {"detail": "decision.comment_required"},
        )
    assert orchestrator.decide_calls == 0
    accepted = await client.post(
        url,
        json=_decision(output_id, sha, "request_changes", comment="Add the 2024 papers"),
        headers=as_user("bob"),
    )
    assert accepted.status_code == 202, accepted.text


async def test_request_changes_needs_an_attempt_left(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    output_id, sha = await _awaiting_attempt(db, run_id, attempt=3, last_attempt=3)
    url = f"/api/v1/runs/{run_id}/approvals"
    changes = _decision(output_id, sha, "request_changes", comment="One more try")
    refused = await client.post(url, json=changes, headers=as_user("bob"))
    assert (refused.status_code, refused.json()["detail"]) == (409, "decision.no_attempts_left")
    assert orchestrator.decide_calls == 0
    assert (
        await client.post(url, json=_decision(output_id, sha), headers=as_user("bob"))
    ).status_code == 202

    # Without a recorded cap the workflow's validator decides.
    legacy = await start_run(client, project_id)
    legacy_output, legacy_sha = await _awaiting_attempt(db, legacy, attempt=3, last_attempt=None)
    orchestrator.refusals = ["decision.no_attempts_left"]
    response = await client.post(
        f"/api/v1/runs/{legacy}/approvals",
        json=_decision(legacy_output, legacy_sha, "request_changes", comment="One more try"),
        headers=as_user("bob"),
    )
    assert (response.status_code, response.json()["detail"]) == (409, "decision.no_attempts_left")


@pytest.mark.parametrize(
    ("code", "answer"),
    [
        ("decision.stale", (409, {"detail": "approval.rejected_by_workflow"})),
        ("decision.invalid", (409, {"detail": "approval.rejected_by_workflow"})),
        ("decision.no_attempts_left", (409, {"detail": "decision.no_attempts_left"})),
        (
            "decision.invalid_edit",
            (422, {"detail": "decision.invalid_edit", "loc": [], "type": "value_error"}),
        ),
        # Whatever else a validator says is never repeated to the client.
        ("ValueError: SELECT * FROM approvals", (409, {"detail": "approval.rejected_by_workflow"})),
    ],
)
async def test_workflow_refusals_get_their_own_answers(
    client: httpx.AsyncClient,
    db: Factory,
    orchestrator: FakeOrchestrator,
    code: str,
    answer: tuple[int, dict[str, Any]],
) -> None:
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    output_id, sha = await awaiting_output(db, run_id)
    orchestrator.refusals = [code]
    response = await client.post(
        f"/api/v1/runs/{run_id}/approvals", json=_decision(output_id, sha), headers=as_user("bob")
    )
    assert (response.status_code, response.json()) == answer
    async with db() as session:
        audit = (
            await session.scalars(select(AuditLog).where(AuditLog.target_id == output_id))
        ).all()
    assert audit == []


async def test_an_unreachable_temporal_is_not_a_conflict(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    output_id, sha = await awaiting_output(db, run_id)
    url = f"/api/v1/runs/{run_id}/approvals"

    orchestrator.decide_error = OrchestratorUnavailableError("no answer in time")
    response = await client.post(url, json=_decision(output_id, sha), headers=as_user("bob"))
    assert (response.status_code, response.json()["detail"]) == (503, "orchestrator.unavailable")
    orchestrator.decide_error = WorkflowNotFoundError(f"run-{run_id}")  # the workflow is gone
    response = await client.post(url, json=_decision(output_id, sha), headers=as_user("bob"))
    assert (response.status_code, response.json()["detail"]) == (
        409,
        "approval.rejected_by_workflow",
    )
    assert orchestrator.decide_calls == 2  # neither is retried


async def test_no_database_connection_waits_on_temporal(
    client: httpx.AsyncClient, db: Factory, db_engine: AsyncEngine, orchestrator: FakeOrchestrator
) -> None:
    """Temporal can take seconds to answer (a worker restarting, say); the pool's connections
    must not wait with it."""
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    output_id, sha = await awaiting_output(db, run_id)
    pool = db_engine.pool
    assert isinstance(pool, QueuePool)
    checked_out: list[int] = []

    async def count_connections(_: uuid.UUID) -> None:
        checked_out.append(pool.checkedout())

    orchestrator.before_decide = orchestrator.before_cancel = count_connections
    orchestrator.refusals = ["decision.not_awaited"]  # one retry, after a look at the database
    response = await client.post(
        f"/api/v1/runs/{run_id}/approvals", json=_decision(output_id, sha), headers=as_user("bob")
    )
    assert response.status_code == 202, response.text
    cancelled = await client.post(f"/api/v1/runs/{run_id}/cancel", headers=as_user("bob"))
    assert cancelled.status_code == 202, cancelled.text
    assert checked_out == [0, 0, 0]


async def test_a_decision_waits_for_the_workflow_to_catch_up(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    """The output is in the database a moment before the workflow waits for its decision."""
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    output_id, sha = await awaiting_output(db, run_id)
    orchestrator.refusals = ["decision.not_awaited", "decision.not_awaited"]
    response = await client.post(
        f"/api/v1/runs/{run_id}/approvals", json=_decision(output_id, sha), headers=as_user("bob")
    )
    assert response.status_code == 202, response.text
    assert (orchestrator.decide_calls, len(orchestrator.decisions)) == (3, 1)


async def test_a_decision_the_workflow_never_awaits_is_a_conflict(
    client: httpx.AsyncClient,
    db: Factory,
    orchestrator: FakeOrchestrator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runs, "NOT_AWAITED_RETRY_SECONDS", 0.6)
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    output_id, sha = await awaiting_output(db, run_id)
    url = f"/api/v1/runs/{run_id}/approvals"
    orchestrator.refusals = ["decision.not_awaited"] * 50
    response = await client.post(url, json=_decision(output_id, sha), headers=as_user("bob"))
    assert (response.status_code, response.json()["detail"]) == (
        409,
        "approval.rejected_by_workflow",
    )
    assert 1 < orchestrator.decide_calls < 50

    # Once the database no longer shows the output waiting, there is nothing to wait for.
    async def decided_elsewhere(run_id: uuid.UUID) -> None:
        async with db() as session:
            await session.execute(
                update(StageRun)
                .where(StageRun.run_id == run_id)
                .values(status=StageStatus.APPROVED)
            )
            await session.commit()

    orchestrator.before_decide = decided_elsewhere
    orchestrator.decide_calls = 0
    response = await client.post(url, json=_decision(output_id, sha), headers=as_user("bob"))
    assert (response.status_code, orchestrator.decide_calls) == (409, 1)


async def test_control_characters_are_dropped_from_topics_and_comments(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    project_id = await team_project(client)
    created = await client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={"topic": "Depth\x00 maps\x1b[1m\tfrom\r\none image"},
        headers=as_user("bob"),
    )
    assert created.status_code == 201, created.text
    assert created.json()["topic"] == "Depth maps[1m\tfrom\none image"  # tab and newline stay
    run_id = created.json()["id"]
    output_id, sha = await awaiting_output(db, run_id)
    response = await client.post(
        f"/api/v1/runs/{run_id}/approvals",
        json=_decision(output_id, sha, comment="Fine\x00 by me\x07"),
        headers=as_user("bob"),
    )
    assert response.status_code == 202, response.text
    [(_, decision)] = orchestrator.decisions
    assert decision.comment == "Fine by me"
    async with db() as session:
        audit = (
            await session.scalars(select(AuditLog).where(AuditLog.action == "stage.approve"))
        ).one()
    assert audit.details["comment"] == "Fine by me"

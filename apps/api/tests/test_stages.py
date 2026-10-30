import copy
import uuid
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.enums import Decision, StageStatus
from agentic_db.models import Approval, AuditLog
from api_testkit import (
    METHOD_OUTPUT,
    FakeOrchestrator,
    add_output,
    add_stage_run,
    as_user,
    awaiting_output,
    start_run,
    team_project,
)

Factory = async_sessionmaker[AsyncSession]


async def _decide(db: Factory, output_id: str, sha: str, decision: Decision, actor: str) -> None:
    async with db() as session:
        session.add(
            Approval(
                stage_output_id=uuid.UUID(output_id),
                sha256=sha,
                decision=decision,
                comment=f"{actor} says {decision.value}",
                actor_id=actor,
            )
        )
        await session.commit()


async def test_stage_detail_has_every_attempt_version_and_decision(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    first = await add_stage_run(db, run_id, "method", StageStatus.CHANGES_REQUESTED, attempt=1)
    draft_id, draft_sha = await add_output(db, first, {"summary": "placeholder"})
    await _decide(db, draft_id, draft_sha, Decision.REQUEST_CHANGES, "alice")
    second = await add_stage_run(
        db, run_id, "method", StageStatus.APPROVED, attempt=2, feedback="add metrics"
    )
    v1_id, _ = await add_output(
        db, second, METHOD_OUTPUT, model="openai/gpt-5.4", prompt_version="method@3"
    )
    edited = {**METHOD_OUTPUT, "implementation_focus": "A smaller student."}
    v2_id, v2_sha = await add_output(db, second, edited, version=2, edited_by="bob")
    await _decide(db, v2_id, v2_sha, Decision.APPROVE, "bob")

    response = await client.get(f"/api/v1/runs/{run_id}/stages/method", headers=as_user("vera"))
    assert response.status_code == 200, response.text
    detail = response.json()
    assert (detail["run_id"], detail["stage"]) == (run_id, "method")
    attempt_1, attempt_2 = detail["attempts"]
    assert (attempt_1["attempt"], attempt_1["status"], attempt_1["feedback"]) == (
        1,
        "changes_requested",
        None,
    )
    [draft] = attempt_1["outputs"]
    assert (draft["id"], draft["schema_ok"], draft["edited_by"]) == (draft_id, False, None)
    assert draft["approval"] == {
        "decision": "request_changes",
        "comment": "alice says request_changes",
        "actor_id": "alice",
        "actor_name": "Alice",
        "at": draft["approval"]["at"],
    }

    assert (attempt_2["attempt"], attempt_2["status"], attempt_2["feedback"]) == (
        2,
        "approved",
        "add metrics",
    )
    v1, v2 = attempt_2["outputs"]
    assert (v1["id"], v1["version"], v1["schema_ok"], v1["approval"]) == (v1_id, 1, True, None)
    assert (v1["model"], v1["prompt_version"], v1["data"]) == (
        "openai/gpt-5.4",
        "method@3",
        METHOD_OUTPUT,
    )
    assert (v2["id"], v2["version"], v2["sha256"], v2["schema_ok"]) == (v2_id, 2, v2_sha, True)
    assert (v2["edited_by"], v2["edited_by_name"]) == ("bob", "Bob")
    assert (v2["approval"]["decision"], v2["approval"]["actor_name"]) == ("approve", "Bob")
    assert set(v2) == {
        "id",
        "version",
        "sha256",
        "data",
        "degraded",
        "degraded_reason",
        "model",
        "prompt_version",
        "edited_by",
        "edited_by_name",
        "created_at",
        "schema_ok",
        "approval",
    }

    untouched = await client.get(f"/api/v1/runs/{run_id}/stages/writing", headers=as_user("vera"))
    assert untouched.json() == {"run_id": run_id, "stage": "writing", "attempts": []}


async def test_stage_detail_is_for_members_and_known_stages(client: httpx.AsyncClient) -> None:
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    url = f"/api/v1/runs/{run_id}/stages"

    unknown = await client.get(f"{url}/review", headers=as_user("bob"))
    assert (unknown.status_code, unknown.json()["detail"]) == (404, "stage.not_found")
    assert (await client.get(f"{url}/method", headers=as_user("carol"))).status_code == 404
    assert (await client.get(f"{url}/method", headers=as_user("root", "admin"))).status_code == 200
    assert (await client.get(f"{url}/method")).status_code == 401
    missing = await client.get(f"/api/v1/runs/{uuid.uuid4()}/stages/method", headers=as_user("bob"))
    assert (missing.status_code, missing.json()["detail"]) == (404, "run.not_found")


async def _awaiting_method(client: httpx.AsyncClient, db: Factory) -> tuple[str, str, str]:
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    output_id, sha = await awaiting_output(db, run_id, "method", METHOD_OUTPUT)
    return run_id, output_id, sha


async def _approve_with(
    client: httpx.AsyncClient,
    run_id: str,
    output_id: str,
    sha: str,
    edited: dict[str, Any],
    decision: str = "approve",
    user: str = "bob",
) -> httpx.Response:
    return await client.post(
        f"/api/v1/runs/{run_id}/approvals",
        json={
            "stage_output_id": output_id,
            "sha256": sha,
            "decision": decision,
            "comment": "fixed the focus",
            "edited_data": edited,
        },
        headers=as_user(user),
    )


async def test_approve_with_edits_sends_the_normalized_edit(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    run_id, output_id, sha = await _awaiting_method(client, db)
    edited = copy.deepcopy(METHOD_OUTPUT)
    edited["implementation_focus"] = "  A smaller student.  "
    del edited["proposals"][0]["evidence_paper_ids"]  # optional: the schema fills in []

    response = await _approve_with(client, run_id, output_id, sha, edited)
    assert response.status_code == 202, response.text
    [(_, decision)] = orchestrator.decisions
    expected = copy.deepcopy(METHOD_OUTPUT)
    expected["implementation_focus"] = "A smaller student."
    expected["proposals"][0]["evidence_paper_ids"] = []
    assert (decision.decision, decision.stage_output_id, decision.edited_data) == (
        "approve",
        output_id,
        expected,
    )
    async with db() as session:
        audit = (
            await session.scalars(select(AuditLog).where(AuditLog.action == "stage.approve"))
        ).one()
    assert audit.details["edited"] is True


async def test_an_unchanged_edit_is_a_plain_approval(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    run_id, output_id, sha = await _awaiting_method(client, db)
    response = await _approve_with(client, run_id, output_id, sha, copy.deepcopy(METHOD_OUTPUT))
    assert response.status_code == 202, response.text
    [(_, decision)] = orchestrator.decisions
    assert decision.edited_data is None


async def test_edits_must_be_an_approval_of_a_valid_output(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    run_id, output_id, sha = await _awaiting_method(client, db)

    async def refused(edited: dict[str, Any], **kwargs: str) -> dict[str, Any]:
        response = await _approve_with(client, run_id, output_id, sha, edited, **kwargs)
        assert response.status_code == 422, response.text
        return response.json()

    not_approve = await refused(METHOD_OUTPUT, decision="request_changes")
    assert not_approve == {"detail": "decision.edit_requires_approve"}

    missing = {k: v for k, v in METHOD_OUTPUT.items() if k != "datasets"}
    assert await refused(missing) == {
        "detail": "decision.invalid_edit",
        "loc": ["datasets"],
        "type": "missing",
    }
    nested = copy.deepcopy(METHOD_OUTPUT)
    nested["proposals"][0]["risk"] = "   "
    assert await refused(nested) == {
        "detail": "decision.invalid_edit",
        "loc": ["proposals", 0, "risk"],
        "type": "string_too_short",
    }
    sneaky = {**METHOD_OUTPUT, "<img src=x onerror=alert(1)>": 1}
    assert await refused(sneaky) == {
        "detail": "decision.invalid_edit",
        "loc": ["*"],  # the key the client sent is never echoed
        "type": "extra_forbidden",
    }
    inconsistent = {**METHOD_OUTPUT, "recommended_option": "Something else"}
    assert await refused(inconsistent) == {
        "detail": "decision.invalid_edit",
        "loc": [],
        "type": "value_error",
    }
    huge = {**METHOD_OUTPUT, "implementation_focus": "x" * 1_000_001}
    assert await refused(huge) == {"detail": "decision.edit_too_large"}
    assert orchestrator.decisions == []


async def test_edits_keep_the_permission_and_conflict_rules(
    client: httpx.AsyncClient, db: Factory, orchestrator: FakeOrchestrator
) -> None:
    run_id, output_id, sha = await _awaiting_method(client, db)
    viewer = await _approve_with(client, run_id, output_id, sha, METHOD_OUTPUT, user="vera")
    assert viewer.status_code == 403
    stale = await _approve_with(client, run_id, output_id, "0" * 64, METHOD_OUTPUT)
    assert (stale.status_code, stale.json()["detail"]) == (409, "approval.stale")
    orchestrator.reject_decisions = True
    edited = {**METHOD_OUTPUT, "implementation_focus": "A smaller student."}
    refused = await _approve_with(client, run_id, output_id, sha, edited)
    assert (refused.status_code, refused.json()["detail"]) == (
        409,
        "approval.rejected_by_workflow",
    )

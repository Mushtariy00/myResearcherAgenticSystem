"""The run workflow with demo stages: stage selection, retries, approve with edits, project
settings and runs started on older code (time-skipping Temporal server, real database)."""

import asyncio
import copy
import dataclasses
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import pytest
from phase1_workflow import Phase1RunWorkflow
from settings_workflow import SettingsRunWorkflow
from sqlalchemy import select
from temporalio.client import Client, WorkflowUpdateFailedError
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment, WorkflowEnvironment
from temporalio.worker import Replayer, Worker

from agentic_core import demo
from agentic_core.contracts import DECIDE_UPDATE, STATUS_QUERY, TASK_QUEUE, DecisionInput
from agentic_core.enums import RunStatus, StageStatus
from agentic_core.schemas import (
    CodingOutput,
    ExperimentOutput,
    LiteratureOutput,
    MethodOutput,
    RunConfig,
    WritingOutput,
    validate_stage_output,
)
from agentic_db.models import Approval, Run, RunEvent, StageOutput, StageRun
from agentic_worker.activities import StageActivities
from agentic_worker.gateway_llm import GatewayRateLimitedError, GatewayUnavailableError
from agentic_worker.outputs import content_sha256
from agentic_worker.stages import (
    PipelineStageRunner,
    PlannedSearch,
    StageContext,
    StageOutcome,
)
from agentic_worker.types import (
    DecisionRecordIn,
    FinishIn,
    RunPrepareIn,
    RunResumeIn,
    StageExecIn,
    StageStartIn,
    StageWaitIn,
)
from agentic_worker.workflows import AUTO_APPROVE_ACTOR, RunWorkflow
from worker_testkit import (
    HEARTBEAT_THROTTLE,
    Factory,
    FakePlanner,
    FakeValkey,
    HangingValkey,
    awaiting,
    create_run,
    retry_run,
    run_events,
    run_status,
    start_run,
)

STAGES = ("literature", "method", "coding", "experiment", "writing")


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    async with await WorkflowEnvironment.start_time_skipping() as environment:
        yield environment


@pytest.fixture
def planner() -> FakePlanner:
    return FakePlanner()


@pytest.fixture
def activities(db: Factory, planner: FakePlanner) -> StageActivities:
    return StageActivities(db, FakeValkey(), PipelineStageRunner(planner, demo_stage_seconds=0))


@pytest.fixture
async def client(env: WorkflowEnvironment, activities: StageActivities) -> AsyncIterator[Client]:
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[RunWorkflow],
        activities=activities.all(),
        max_heartbeat_throttle_interval=HEARTBEAT_THROTTLE,
    ):
        yield env.client


async def stage_runs(db: Factory, run_id: str) -> list[tuple[str, int, StageStatus]]:
    async with db() as session:
        rows = await session.scalars(
            select(StageRun)
            .where(StageRun.run_id == uuid.UUID(run_id))
            .order_by(StageRun.started_at, StageRun.attempt)
        )
        return [(row.stage, row.attempt, StageStatus(row.status)) for row in rows]


async def output_data(db: Factory, stage_output_id: str) -> dict[str, Any]:
    async with db() as session:
        output = await session.get(StageOutput, uuid.UUID(stage_output_id))
    if output is None:
        raise AssertionError(f"stage output {stage_output_id} is missing")
    return output.data


async def approve_all(handle: Any, db: Factory, stages: tuple[str, ...] = STAGES) -> None:
    for stage in stages:
        await handle.execute_update(DECIDE_UPDATE, await awaiting(handle, db, stage))


async def approved_output_ids(db: Factory, run_id: str) -> dict[str, str]:
    """The approved output id of each stage (the latest approved attempt)."""
    async with db() as session:
        rows = await session.execute(
            select(StageRun.stage, Approval.stage_output_id)
            .join(StageOutput, StageOutput.stage_run_id == StageRun.id)
            .join(Approval, Approval.stage_output_id == StageOutput.id)
            .where(StageRun.run_id == uuid.UUID(run_id), StageRun.status == StageStatus.APPROVED)
            .order_by(StageRun.attempt)
        )
        return {stage: str(output_id) for stage, output_id in rows}


async def add_stage_run(
    db: Factory, run_id: str, stage: str, status: StageStatus = StageStatus.RUNNING
) -> str:
    async with db() as session:
        stage_run = StageRun(run_id=uuid.UUID(run_id), stage=stage, attempt=1, status=status)
        session.add(stage_run)
        await session.commit()
    return str(stage_run.id)


async def method_awaiting_review(db: Factory) -> tuple[str, str, StageOutput]:
    """A run whose demo method output waits for a decision: (run id, stage run id, output)."""
    run_id = await create_run(db, status=RunStatus.AWAITING_APPROVAL)
    stage_run_id = await add_stage_run(db, run_id, "method", StageStatus.OUTPUT_READY)
    plan = demo.research_plan("Monocular depth", 2)
    literature = demo.literature("Monocular depth", plan, RunConfig(), 2)
    data = demo.method("Monocular depth", literature, 2).model_dump(mode="json")
    async with db() as session:
        output = StageOutput(
            stage_run_id=uuid.UUID(stage_run_id),
            data=data,
            sha256=content_sha256(data),
            degraded=True,
            degraded_reason="stage.demo",
            prompt_version="demo@1",
        )
        session.add(output)
        await session.commit()
    return run_id, stage_run_id, output


async def test_every_stage_produces_a_demo_output_built_on_the_approved_ones(
    client: Client, db: Factory
) -> None:
    run_id = await create_run(db)
    handle = await start_run(client, run_id)
    await approve_all(handle, db)
    assert await handle.result() == "completed"

    async with db() as session:
        rows = (
            await session.execute(
                select(StageRun.stage, StageOutput)
                .join(StageOutput, StageOutput.stage_run_id == StageRun.id)
                .where(StageRun.run_id == uuid.UUID(run_id))
            )
        ).all()
    outputs = {stage: output for stage, output in rows}
    assert set(outputs) == set(STAGES)
    for stage, output in outputs.items():
        validate_stage_output(stage, output.data)
        assert output.sha256 == content_sha256(output.data)
        assert output.degraded
        expected = (
            ("literature.demo_search", "literature-plan@1")
            if stage == "literature"
            else ("stage.demo", "demo@1")
        )
        assert (output.degraded_reason, output.prompt_version) == expected

    literature = LiteratureOutput.model_validate(outputs["literature"].data)
    method = MethodOutput.model_validate(outputs["method"].data)
    coding = CodingOutput.model_validate(outputs["coding"].data)
    experiment = ExperimentOutput.model_validate(outputs["experiment"].data)
    writing = WritingOutput.model_validate(outputs["writing"].data)
    included = {paper.paper_id for paper in literature.papers if paper.decision == "include"}
    assert all(set(proposal.evidence_paper_ids) <= included for proposal in method.proposals)
    assert method.recommended_option in coding.summary
    assert experiment.provenance.code_sha256 == demo.code_hashes(coding)[0]
    assert {citation.paper_id for citation in writing.citations} <= included

    logs = await run_events(db, run_id, "log")
    assert all(set(payload) == {"stage", "code", "params", "message"} for payload in logs)
    codes = {payload["code"] for payload in logs}
    assert {"demo.search", "demo.screen", "demo.analyse", "demo.epoch", "demo.draft"} <= codes
    assert {payload["stage"] for payload in logs} == set(STAGES)
    calls = await run_events(db, run_id, "llm.call")
    assert [(call["stage"], call["tier"]) for call in calls] == [("literature", "free")]


async def test_the_run_completes_after_the_last_configured_stage(
    client: Client, db: Factory
) -> None:
    run_id = await create_run(db, config={"stages": ["literature", "method"], "max_papers": 6})
    handle = await start_run(client, run_id)
    await approve_all(handle, db, ("literature", "method"))
    assert await handle.result() == "completed"
    assert await stage_runs(db, run_id) == [
        ("literature", 1, StageStatus.APPROVED),
        ("method", 1, StageStatus.APPROVED),
    ]
    literature = await output_data(db, (await approved_output_ids(db, run_id))["literature"])
    assert len(literature["papers"]) <= 6  # the rest of the config reaches the stages too


async def test_an_invalid_stored_config_fails_the_run_with_a_code(
    client: Client, db: Factory
) -> None:
    run_id = await create_run(db, config={"stages": ["method"]})
    handle = await start_run(client, run_id)
    assert await handle.result() == "failed"
    assert await run_status(db, run_id) == (RunStatus.FAILED, "stage.error")


async def test_retry_keeps_earlier_approvals_and_invalidates_later_stages(
    client: Client, db: Factory
) -> None:
    run_id = await create_run(db)
    first = await start_run(client, run_id)
    literature = await awaiting(first, db, "literature")
    changes = dataclasses.replace(literature, decision="request_changes", comment="Fewer surveys")
    await first.execute_update(DECIDE_UPDATE, changes)
    await approve_all(first, db)
    assert await first.result() == "completed"
    method_output = (await approved_output_ids(db, run_id))["method"]

    retry = await retry_run(client, db, run_id, "coding")
    coding = await awaiting(retry, db, "coding")
    assert await run_status(db, run_id) == (RunStatus.AWAITING_APPROVAL, None)
    assert await stage_runs(db, run_id) == [
        ("literature", 1, StageStatus.CHANGES_REQUESTED),
        ("literature", 2, StageStatus.APPROVED),
        ("method", 1, StageStatus.APPROVED),
        ("coding", 1, StageStatus.INVALIDATED),
        ("experiment", 1, StageStatus.INVALIDATED),
        ("writing", 1, StageStatus.INVALIDATED),
        ("coding", 2, StageStatus.OUTPUT_READY),
    ]
    invalidated = await run_events(db, run_id, "stage.invalidated")
    assert [(e["stage"], e["attempt"], e["retry_stage"]) for e in invalidated] == [
        ("coding", 1, "coding"),
        ("experiment", 1, "coding"),
        ("writing", 1, "coding"),
    ]
    retried = await run_events(db, run_id, "run.retried")
    assert [(e["stage"], e["requested_stage"]) for e in retried] == [("coding", "coding")]

    await retry.execute_update(DECIDE_UPDATE, coding)
    await approve_all(retry, db, ("experiment", "writing"))
    assert await retry.result() == "completed"
    assert await run_status(db, run_id) == (RunStatus.COMPLETED, None)
    attempts = [(stage, attempt) for stage, attempt, _ in await stage_runs(db, run_id)]
    assert attempts[-3:] == [("coding", 2), ("experiment", 2), ("writing", 2)]
    # The kept method approval is still the one later stages build on.
    assert (await approved_output_ids(db, run_id))["method"] == method_output


async def test_retry_restarts_at_the_first_stage_without_an_approval(
    client: Client, db: Factory, planner: FakePlanner
) -> None:
    planner.fail_times = 1  # the first literature attempt gets an unusable model answer
    run_id = await create_run(db)
    failed = await start_run(client, run_id)
    assert await failed.result() == "failed"
    assert await run_status(db, run_id) == (RunStatus.FAILED, "literature.invalid_output")
    failures = await run_events(db, run_id, "stage.failed")
    assert failures == [{"stage": "literature", "attempt": 1, "error": "literature.invalid_output"}]

    retry = await retry_run(client, db, run_id, "method")
    await awaiting(retry, db, "literature")
    retried = await run_events(db, run_id, "run.retried")
    assert [(e["stage"], e["requested_stage"]) for e in retried] == [("literature", "method")]
    assert await stage_runs(db, run_id) == [
        ("literature", 1, StageStatus.FAILED),
        ("literature", 2, StageStatus.OUTPUT_READY),
    ]
    assert await run_status(db, run_id) == (RunStatus.AWAITING_APPROVAL, None)
    await retry.cancel()


async def test_retry_from_a_stage_outside_the_config_fails(client: Client, db: Factory) -> None:
    run_id = await create_run(db, config={"stages": ["literature"]})
    first = await start_run(client, run_id)
    await approve_all(first, db, ("literature",))
    assert await first.result() == "completed"
    retry = await retry_run(client, db, run_id, "writing")
    assert await retry.result() == "failed"
    assert await run_status(db, run_id) == (RunStatus.FAILED, "stage.error")


async def test_approve_with_edits_approves_a_new_version_that_later_stages_use(
    client: Client, db: Factory
) -> None:
    run_id = await create_run(db)
    handle = await start_run(client, run_id)
    reviewed = await awaiting(handle, db, "literature")
    original = await output_data(db, reviewed.stage_output_id)
    edited = copy.deepcopy(original)
    keep = {p["paper_id"] for p in edited["papers"] if p["decision"] == "include"}
    keep = set(sorted(keep)[:3])
    for paper in edited["papers"]:
        if paper["decision"] == "include" and paper["paper_id"] not in keep:
            paper["decision"], paper["decision_reason"] = "exclude", "Not about indoor scenes."
    edited["analyses"] = [a for a in edited["analyses"] if a["paper_id"] in keep]
    edited["synthesis"] = "Edited by the reviewer: three papers carry the argument."
    approve_edited = dataclasses.replace(
        reviewed, actor_id="alice", comment="Kept three papers", edited_data=edited
    )

    for refused in (
        dataclasses.replace(approve_edited, decision="request_changes"),  # edits need approve
        dataclasses.replace(approve_edited, edited_data={**edited, "papers": []}),  # invalid
        dataclasses.replace(approve_edited, sha256="0" * 64),  # stale
    ):
        with pytest.raises(WorkflowUpdateFailedError):
            await handle.execute_update(DECIDE_UPDATE, refused)
    await handle.execute_update(DECIDE_UPDATE, approve_edited)
    with pytest.raises(WorkflowUpdateFailedError):
        await handle.execute_update(DECIDE_UPDATE, approve_edited)  # duplicate
    method_decision = await awaiting(handle, db, "method")

    async with db() as session:
        versions = (
            await session.scalars(
                select(StageOutput)
                .join(StageRun, StageRun.id == StageOutput.stage_run_id)
                .where(StageRun.run_id == uuid.UUID(run_id), StageRun.stage == "literature")
                .order_by(StageOutput.version)
            )
        ).all()
        approvals = (await session.scalars(select(Approval))).all()
    assert [output.version for output in versions] == [1, 2]
    first, second = versions
    assert second.data == LiteratureOutput.model_validate(edited).model_dump(mode="json")
    assert second.sha256 == content_sha256(second.data)
    assert (second.edited_by, second.degraded, second.degraded_reason) == ("alice", False, None)
    assert (second.model, second.prompt_version) == (first.model, first.prompt_version)
    assert [(a.stage_output_id, a.sha256, a.actor_id) for a in approvals] == [
        (second.id, second.sha256, "alice")
    ]
    decided = (await run_events(db, run_id, "stage.decided"))[-1]
    assert decided["edited"] is True and decided["automatic"] is False
    assert (decided["stage_output_id"], decided["version"]) == (str(second.id), 2)

    method = MethodOutput.model_validate(await output_data(db, method_decision.stage_output_id))
    assert all(set(proposal.evidence_paper_ids) <= keep for proposal in method.proposals)
    await handle.cancel()


async def test_auto_approve_skips_the_reviewer_except_for_coding(
    client: Client, db: Factory
) -> None:
    run_id = await create_run(db, auto_approve=True)
    handle = await start_run(client, run_id)
    coding = await awaiting(handle, db, "coding")  # literature and method went through alone
    statuses = [e["status"] for e in await run_events(db, run_id, "run.status")]
    assert statuses.count("awaiting_approval") == 1  # only for coding
    await handle.execute_update(DECIDE_UPDATE, coding)
    assert await handle.result() == "completed"

    decided = await run_events(db, run_id, "stage.decided")
    assert [(e["stage"], e["actor_id"], e["automatic"]) for e in decided] == [
        ("literature", AUTO_APPROVE_ACTOR, True),
        ("method", AUTO_APPROVE_ACTOR, True),
        ("coding", "bob", False),
        ("experiment", AUTO_APPROVE_ACTOR, True),
        ("writing", AUTO_APPROVE_ACTOR, True),
    ]
    async with db() as session:
        approvals = (await session.scalars(select(Approval))).all()
    assert len(approvals) == 5 and all(a.decision == "approve" for a in approvals)


async def test_an_unanswered_review_expires_after_the_projects_expiry(
    env: WorkflowEnvironment, client: Client, db: Factory
) -> None:
    run_id = await create_run(db, approval_expiry_days=2)
    handle = await start_run(client, run_id)
    await awaiting(handle, db, "literature")
    await env.sleep(timedelta(days=1))
    assert (await handle.query(STATUS_QUERY))["status"] == "awaiting_approval"
    await env.sleep(timedelta(days=1, hours=1))
    assert await handle.result() == "cancelled"
    assert await run_status(db, run_id) == (RunStatus.CANCELLED, "approval.expired")


async def test_runs_started_on_phase1_code_continue_on_the_new_code(
    env: WorkflowEnvironment, db: Factory, activities: StageActivities
) -> None:
    # Even in a project with auto-approve, a Phase 1 run keeps its original behaviour.
    run_id = await create_run(db, auto_approve=True)
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[Phase1RunWorkflow],
        activities=activities.all(),
        # No sticky cache: the test server never hands a stopped worker's sticky tasks back.
        max_cached_workflows=0,
    ):
        handle = await start_run(env.client, run_id)
        literature = await awaiting(handle, db, "literature")
    await Replayer(workflows=[RunWorkflow]).replay_workflow(await handle.fetch_history())

    async with Worker(
        env.client, task_queue=TASK_QUEUE, workflows=[RunWorkflow], activities=activities.all()
    ):
        await handle.execute_update(DECIDE_UPDATE, literature)
        await approve_all(handle, db, STAGES[1:])  # nothing is approved automatically
        assert await handle.result() == "completed"
    decided = await run_events(db, run_id, "stage.decided")
    assert [e["automatic"] for e in decided] == [False] * 5


async def test_runs_started_before_stage_waits_continue_on_the_new_code(
    env: WorkflowEnvironment, db: Factory, activities: StageActivities
) -> None:
    run_id = await create_run(db)
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[SettingsRunWorkflow],
        activities=activities.all(),
        max_cached_workflows=0,
    ):
        handle = await start_run(env.client, run_id)
        literature = await awaiting(handle, db, "literature")
    await Replayer(workflows=[RunWorkflow]).replay_workflow(await handle.fetch_history())

    async with Worker(
        env.client, task_queue=TASK_QUEUE, workflows=[RunWorkflow], activities=activities.all()
    ):
        changes = dataclasses.replace(literature, decision="request_changes", comment="Fewer")
        await handle.execute_update(DECIDE_UPDATE, changes)
        await approve_all(handle, db)
        assert await handle.result() == "completed"
    await Replayer(workflows=[RunWorkflow]).replay_workflow(await handle.fetch_history())
    async with db() as session:
        caps = await session.execute(
            select(StageRun.attempt, StageRun.last_attempt)
            .where(StageRun.stage == "literature")
            .order_by(StageRun.attempt)
        )
        # The old code started attempt 1; the new code records the cap of attempt 2.
        assert [tuple(row) for row in caps] == [(1, None), (2, 3)]


# --- activities under retries ---------------------------------------------------------------


async def test_prepare_run_records_a_retry_once(db: Factory, activities: StageActivities) -> None:
    run_id = await create_run(db, status=RunStatus.RUNNING)  # the API marks a retry running
    async with db() as session:
        session.add(
            StageRun(run_id=uuid.UUID(run_id), stage="literature", status=StageStatus.FAILED)
        )
        await session.commit()
    environment = ActivityEnvironment()
    retry = RunPrepareIn(run_id=run_id, start_stage="literature")
    first = await environment.run(activities.prepare_run, retry)
    again = await environment.run(activities.prepare_run, retry)  # activity retry
    assert first == again
    assert (first.stages[0], first.first_attempts["literature"]) == ("literature", 2)
    assert len(await run_events(db, run_id, "run.retried")) == 1
    assert await run_status(db, run_id) == (RunStatus.RUNNING, None)


async def test_execute_stage_reuses_a_committed_output_on_retry(
    db: Factory, activities: StageActivities, planner: FakePlanner
) -> None:
    run_id = await create_run(db, status=RunStatus.RUNNING)
    stage_run_id = await add_stage_run(db, run_id, "literature")
    request = StageExecIn(run_id=run_id, stage_run_id=stage_run_id, stage="literature", attempt=1)
    environment = ActivityEnvironment()
    first = await environment.run(activities.execute_stage, request)
    again = await environment.run(activities.execute_stage, request)
    assert first == again and len(planner.seen) == 1
    async with db() as session:
        assert len((await session.scalars(select(StageOutput))).all()) == 1


async def test_a_stage_finishing_after_a_cancel_does_not_reopen_the_run(db: Factory) -> None:
    run_id = await create_run(db, status=RunStatus.RUNNING)
    stage_run_id = await add_stage_run(db, run_id, "literature")

    class CancelledMeanwhile:
        async def run(self, ctx: StageContext) -> StageOutcome:
            async with db() as session:
                run = await session.get(Run, uuid.UUID(run_id))
                assert run is not None
                run.status = RunStatus.CANCELLED
                await session.commit()
            return StageOutcome(data={"stage": ctx.stage})

    activities = StageActivities(db, FakeValkey(), CancelledMeanwhile())
    request = StageExecIn(run_id=run_id, stage_run_id=stage_run_id, stage="literature", attempt=1)
    with pytest.raises(ApplicationError, match=r"run\.closed"):
        await ActivityEnvironment().run(activities.execute_stage, request)
    assert await run_status(db, run_id) == (RunStatus.CANCELLED, None)
    async with db() as session:
        assert (await session.scalars(select(StageOutput))).all() == []


async def test_a_closed_run_is_never_changed_again(
    db: Factory, activities: StageActivities, planner: FakePlanner
) -> None:
    """A cancel can close the run while an older activity still runs; that one changes nothing."""
    run_id, stage_run_id, output = await method_awaiting_review(db)
    async with db() as session:
        run = await session.get(Run, uuid.UUID(run_id))
        assert run is not None
        run.status = RunStatus.CANCELLED
        await session.commit()
    environment = ActivityEnvironment()
    with pytest.raises(ApplicationError, match=r"run\.closed"):
        await environment.run(
            activities.prepare_run, RunPrepareIn(run_id=run_id, start_stage="method")
        )
    with pytest.raises(ApplicationError, match=r"run\.closed"):
        await activities.start_stage(StageStartIn(run_id=run_id, stage="method", attempt=2))
    with pytest.raises(ApplicationError, match=r"run\.closed"):
        await environment.run(
            activities.execute_stage,
            StageExecIn(run_id=run_id, stage_run_id=stage_run_id, stage="method", attempt=1),
        )
    with pytest.raises(ApplicationError, match=r"run\.closed"):
        await activities.stage_waiting(
            StageWaitIn(
                run_id=run_id,
                stage="method",
                attempt=1,
                reason="lab_balance.exhausted",
                retry_at="2026-10-30T12:15:00+00:00",
                pause=True,
            )
        )
    with pytest.raises(ApplicationError, match=r"run\.closed"):
        await activities.resume_run(RunResumeIn(run_id=run_id))
    decision = DecisionInput(
        stage="method",
        stage_output_id=str(output.id),
        sha256=output.sha256,
        decision="approve",
        actor_id="alice",
    )
    with pytest.raises(ApplicationError, match=r"run\.closed"):
        await activities.record_decision(
            DecisionRecordIn(run_id=run_id, stage_run_id=stage_run_id, decision=decision)
        )
    await activities.finish_run(FinishIn(run_id=run_id, status="failed", error="stage.error"))

    assert await run_status(db, run_id) == (RunStatus.CANCELLED, None)
    assert await stage_runs(db, run_id) == [("method", 1, StageStatus.OUTPUT_READY)]
    assert planner.seen == []
    async with db() as session:
        assert (await session.scalars(select(Approval))).all() == []
        assert (await session.scalars(select(RunEvent))).all() == []


@dataclass
class CallingPlanner:
    """Reports its gateway call as it arrives, like CrewAIPlanner; fails while there are errors."""

    errors: list[BaseException]
    seen: list[StageContext] = field(default_factory=list)

    async def plan(self, ctx: StageContext) -> PlannedSearch:
        self.seen.append(ctx)
        call = {
            "model": "paid/a",
            "tier": "paid",
            "cost_usd": "0.002",
            "replayed": len(self.seen) > 1,  # a rerun of the attempt replays its first call
            "idempotency_key": f"{ctx.stage_run_id}:call-1",
        }
        ctx.llm_calls.append(call)
        if self.errors:
            raise self.errors.pop(0)
        plan = demo.research_plan(ctx.topic, 1, config=ctx.config)
        return PlannedSearch(plan=plan, model="paid/a", llm_calls=[call])


async def test_calls_of_an_unsuccessful_attempt_are_recorded_once(db: Factory) -> None:
    planner = CallingPlanner(
        errors=[
            GatewayUnavailableError("HTTP 502"),
            GatewayRateLimitedError(90, "call.in_progress"),
        ]
    )
    activities = StageActivities(
        db, FakeValkey(), PipelineStageRunner(planner, demo_stage_seconds=0)
    )
    run_id = await create_run(db, status=RunStatus.RUNNING)
    stage_run_id = await add_stage_run(db, run_id, "literature")
    request = StageExecIn(run_id=run_id, stage_run_id=stage_run_id, stage="literature", attempt=1)
    environment = ActivityEnvironment()
    recorded = [(f"{stage_run_id}:call-1", "0.002")]
    with pytest.raises(ApplicationError) as gateway:
        await environment.run(activities.execute_stage, request)
    assert (gateway.value.type, gateway.value.message) == ("GatewayError", "gateway.error")
    assert not gateway.value.non_retryable
    calls = await run_events(db, run_id, "llm.call")
    assert [(c["idempotency_key"], c["cost_usd"]) for c in calls] == recorded

    with pytest.raises(ApplicationError) as limited:
        await environment.run(activities.execute_stage, request)
    assert (limited.value.type, limited.value.message) == ("RateLimited", "call.in_progress")
    assert limited.value.next_retry_delay == timedelta(seconds=90)
    await environment.run(activities.execute_stage, request)
    calls = await run_events(db, run_id, "llm.call")
    assert [(c["idempotency_key"], c["cost_usd"]) for c in calls] == recorded  # replays: once
    assert all(ctx.cancelled.is_set() for ctx in planner.seen[:2])  # the attempts that ended


async def test_a_stuck_valkey_does_not_stall_an_activity(
    db: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("agentic_worker.activities.WAKE_TIMEOUT_SECONDS", 0.05)
    runner = PipelineStageRunner(FakePlanner(), demo_stage_seconds=0)
    activities = StageActivities(db, HangingValkey(), runner)
    run_id = await create_run(db)
    start = StageStartIn(run_id=run_id, stage="literature", attempt=1, last_attempt=3)
    started = await asyncio.wait_for(activities.start_stage(start), timeout=10)
    async with db() as session:
        stage_run = await session.get(StageRun, uuid.UUID(started.stage_run_id))
    assert stage_run is not None and stage_run.last_attempt == 3


async def test_record_decision_stores_an_edit_once_under_retries(
    db: Factory, activities: StageActivities
) -> None:
    run_id, stage_run_id, output = await method_awaiting_review(db)
    decision = DecisionInput(
        stage="method",
        stage_output_id=str(output.id),
        sha256=output.sha256,
        decision="approve",
        actor_id="alice",
        edited_data={**output.data, "implementation_focus": "Start with the smallest model."},
    )
    record = DecisionRecordIn(run_id=run_id, stage_run_id=stage_run_id, decision=decision)
    await activities.record_decision(record)
    await activities.record_decision(record)  # activity retry after the commit
    async with db() as session:
        versions = (await session.scalars(select(StageOutput.version))).all()
        approvals = (await session.scalars(select(Approval))).all()
    assert sorted(versions) == [1, 2] and len(approvals) == 1
    assert len(await run_events(db, run_id, "stage.decided")) == 1


async def test_record_decision_refuses_an_invalid_edit(
    db: Factory, activities: StageActivities
) -> None:
    """The API and the workflow validator check edits first; this is the last line."""
    run_id, stage_run_id, output = await method_awaiting_review(db)
    decision = DecisionInput(
        stage="method",
        stage_output_id=str(output.id),
        sha256=output.sha256,
        decision="approve",
        actor_id="alice",
        edited_data={**output.data, "proposals": []},
    )
    with pytest.raises(ApplicationError) as error:
        await activities.record_decision(
            DecisionRecordIn(run_id=run_id, stage_run_id=stage_run_id, decision=decision)
        )
    assert (error.value.message, error.value.non_retryable) == ("decision.invalid_edit", True)
    async with db() as session:
        assert (await session.scalars(select(Approval))).all() == []

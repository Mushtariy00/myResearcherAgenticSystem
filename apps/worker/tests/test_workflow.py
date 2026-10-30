"""The run workflow on Temporal's time-skipping test server, with real activities and database."""

import asyncio
import dataclasses
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from temporalio import activity
from temporalio.api.enums.v1 import EventType as HistoryEvent
from temporalio.client import (
    Client,
    WorkflowFailureError,
    WorkflowHandle,
    WorkflowUpdateFailedError,
)
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, UnsandboxedWorkflowRunner, Worker

from agentic_core.contracts import (
    DECIDE_UPDATE,
    RUN_WORKFLOW,
    STATUS_QUERY,
    TASK_QUEUE,
    DecisionInput,
    RunInput,
)
from agentic_core.enums import RunStatus, StageStatus
from agentic_db.models import Approval, Project, Run, RunEvent, StageOutput, StageRun
from agentic_worker.activities import StageActivities
from agentic_worker.gateway_llm import (
    GatewayRateLimitedError,
    GatewayUnavailableError,
    LabBalanceExhaustedError,
    RunInactiveError,
)
from agentic_worker.stages import StageFailedError
from agentic_worker.types import DecisionRecordIn, FinishIn
from agentic_worker.workflows import RunWorkflow
from worker_testkit import (
    HEARTBEAT_THROTTLE,
    Factory,
    FakeRunner,
    FakeValkey,
    awaiting,
    run_events,
    run_status,
)


def refusal(error: WorkflowUpdateFailedError) -> str:
    """The code the decide validator refused an Update with."""
    cause = error.cause
    assert isinstance(cause, ApplicationError)
    return cause.message


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    async with await WorkflowEnvironment.start_time_skipping() as environment:
        yield environment


@pytest.fixture
def runner() -> FakeRunner:
    return FakeRunner()


@pytest.fixture
async def client(
    env: WorkflowEnvironment, db: Factory, runner: FakeRunner
) -> AsyncIterator[Client]:
    activities = StageActivities(db, FakeValkey(), runner)
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[RunWorkflow],
        activities=activities.all(),
        max_heartbeat_throttle_interval=HEARTBEAT_THROTTLE,
    ):
        yield env.client


async def start(client: Client, db: Factory) -> tuple[str, WorkflowHandle]:
    async with db() as session:
        project = Project(name="Depth", created_by="bob")
        session.add(project)
        await session.flush()
        run = Run(project_id=project.id, owner_id="bob", topic="Monocular depth")
        session.add(run)
        await session.commit()
    run_id = str(run.id)
    handle = await client.start_workflow(
        RUN_WORKFLOW, RunInput(run_id=run_id), id=f"run-{run_id}", task_queue=TASK_QUEUE
    )
    return run_id, handle


async def test_approving_every_stage_completes_the_run(client: Client, db: Factory) -> None:
    run_id, handle = await start(client, db)
    for stage in ("literature", "method", "coding", "experiment", "writing"):
        await handle.execute_update(DECIDE_UPDATE, await awaiting(handle, db, stage))
    assert await handle.result() == "completed"
    assert await run_status(db, run_id) == (RunStatus.COMPLETED, None)
    async with db() as session:
        approvals = (await session.scalars(select(Approval))).all()
        seqs = (
            await session.scalars(
                select(RunEvent.seq)
                .where(RunEvent.run_id == uuid.UUID(run_id))
                .order_by(RunEvent.seq)
            )
        ).all()
    assert len(approvals) == 5
    assert list(seqs) == list(range(1, len(seqs) + 1))  # gap-free event log


async def test_request_changes_reruns_the_stage_with_the_feedback(
    client: Client, db: Factory, runner: FakeRunner
) -> None:
    _, handle = await start(client, db)
    first = await awaiting(handle, db, "literature")
    await handle.execute_update(
        DECIDE_UPDATE,
        DecisionInput(
            stage="literature",
            stage_output_id=first.stage_output_id,
            sha256=first.sha256,
            decision="request_changes",
            actor_id="bob",
            comment="Focus on 2024",
        ),
    )
    second = await awaiting(handle, db, "literature")
    assert second.stage_output_id != first.stage_output_id
    assert [(c.stage, c.attempt, c.feedback) for c in runner.seen] == [
        ("literature", 1, ""),
        ("literature", 2, "Focus on 2024"),
    ]
    async with db() as session:
        attempts = (await session.scalars(select(StageRun).order_by(StageRun.attempt))).all()
    assert [(a.attempt, a.status) for a in attempts] == [
        (1, StageStatus.CHANGES_REQUESTED),
        (2, StageStatus.OUTPUT_READY),
    ]
    await handle.cancel()


async def test_reject_stops_the_run(client: Client, db: Factory) -> None:
    run_id, handle = await start(client, db)
    decision = await awaiting(handle, db, "literature")
    await handle.execute_update(
        DECIDE_UPDATE,
        DecisionInput(
            stage="literature",
            stage_output_id=decision.stage_output_id,
            sha256=decision.sha256,
            decision="reject",
            actor_id="bob",
        ),
    )
    assert await handle.result() == "rejected"
    assert (await run_status(db, run_id))[0] == RunStatus.REJECTED


async def test_stale_or_repeated_decisions_are_refused(client: Client, db: Factory) -> None:
    _, handle = await start(client, db)
    decision = await awaiting(handle, db, "literature")
    stale = DecisionInput(
        stage="literature",
        stage_output_id=decision.stage_output_id,
        sha256="0" * 64,
        decision="approve",
        actor_id="bob",
    )
    with pytest.raises(WorkflowUpdateFailedError):
        await handle.execute_update(DECIDE_UPDATE, stale)
    wrong_stage = DecisionInput(
        stage="method",
        stage_output_id=decision.stage_output_id,
        sha256=decision.sha256,
        decision="approve",
        actor_id="bob",
    )
    with pytest.raises(WorkflowUpdateFailedError):
        await handle.execute_update(DECIDE_UPDATE, wrong_stage)
    await handle.execute_update(DECIDE_UPDATE, decision)
    with pytest.raises(WorkflowUpdateFailedError):
        await handle.execute_update(DECIDE_UPDATE, decision)  # literature is no longer awaited
    await handle.cancel()


async def test_cancel_while_waiting_for_review(client: Client, db: Factory) -> None:
    run_id, handle = await start(client, db)
    await awaiting(handle, db, "literature")
    await handle.cancel()
    with pytest.raises(WorkflowFailureError):
        await handle.result()
    assert (await run_status(db, run_id))[0] == RunStatus.CANCELLED
    async with db() as session:
        stage_run = (await session.scalars(select(StageRun))).one()
    assert stage_run.status == StageStatus.CANCELLED


async def test_cancel_while_a_stage_is_running(
    client: Client, db: Factory, runner: FakeRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Found by the live run: this used to be recorded as 'failed'."""
    monkeypatch.setattr("agentic_worker.activities.HEARTBEAT_SECONDS", 0.1)
    runner.block_stage = "literature"
    run_id, handle = await start(client, db)
    await asyncio.wait_for(runner.blocked.wait(), timeout=20)
    await handle.cancel()
    with pytest.raises(WorkflowFailureError):
        await handle.result()
    assert (await run_status(db, run_id))[0] == RunStatus.CANCELLED
    async with db() as session:
        stage_run = (await session.scalars(select(StageRun))).one()
    assert stage_run.status == StageStatus.CANCELLED
    assert runner.seen[0].cancelled.is_set()  # work left in a thread calls the gateway no more


async def test_cancel_waits_for_the_running_stage_to_stop(
    client: Client, db: Factory, runner: FakeRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run closes after the stage's last write, never while the stage still writes."""
    monkeypatch.setattr("agentic_worker.activities.HEARTBEAT_SECONDS", 0.1)
    runner.block_stage, runner.on_cancel = "literature", "log"
    run_id, handle = await start(client, db)
    await asyncio.wait_for(runner.blocked.wait(), timeout=20)
    await handle.cancel()
    with pytest.raises(WorkflowFailureError):
        await handle.result()
    async with db() as session:
        types = await session.scalars(
            select(RunEvent.type).where(RunEvent.run_id == uuid.UUID(run_id)).order_by(RunEvent.seq)
        )
        assert types.all()[-2:] == ["log", "run.status"]
    assert await run_status(db, run_id) == (RunStatus.CANCELLED, None)


@pytest.mark.parametrize("on_cancel", ["finish", "fail"])
async def test_a_stage_ending_as_the_cancel_reaches_it_still_cancels_the_run(
    client: Client,
    db: Factory,
    runner: FakeRunner,
    monkeypatch: pytest.MonkeyPatch,
    on_cancel: Any,
) -> None:
    """Like a CrewAI thread that ignores the cancel: its output or failure comes in after it."""
    monkeypatch.setattr("agentic_worker.activities.HEARTBEAT_SECONDS", 0.1)
    runner.block_stage, runner.on_cancel = "literature", on_cancel
    run_id, handle = await start(client, db)
    await asyncio.wait_for(runner.blocked.wait(), timeout=20)
    await handle.cancel()
    with pytest.raises(WorkflowFailureError):
        await handle.result()
    assert await run_status(db, run_id) == (RunStatus.CANCELLED, None)
    async with db() as session:
        stage_run = (await session.scalars(select(StageRun))).one()
    assert stage_run.status == StageStatus.CANCELLED


async def test_failing_stage_fails_the_run_honestly(
    client: Client, db: Factory, runner: FakeRunner
) -> None:
    runner.fail_stage = "method"
    run_id, handle = await start(client, db)
    await handle.execute_update(DECIDE_UPDATE, await awaiting(handle, db, "literature"))
    assert await handle.result() == "failed"
    assert await run_status(db, run_id) == (RunStatus.FAILED, "method.invalid_output")


async def test_unanswered_review_expires_after_seven_days(
    env: WorkflowEnvironment, client: Client, db: Factory
) -> None:
    run_id, handle = await start(client, db)
    await awaiting(handle, db, "literature")
    await env.sleep(timedelta(days=8))
    assert await handle.result() == "cancelled"
    assert await run_status(db, run_id) == (RunStatus.CANCELLED, "approval.expired")


async def output_data(db: Factory, stage_output_id: str) -> dict[str, Any]:
    async with db() as session:
        output = await session.get(StageOutput, uuid.UUID(stage_output_id))
    if output is None:
        raise AssertionError(f"stage output {stage_output_id} is missing")
    return output.data


async def test_changes_revise_the_previous_output_until_no_attempt_is_left(
    client: Client, db: Factory, runner: FakeRunner
) -> None:
    _, handle = await start(client, db)
    comments = ("Focus on 2024", "Add a query on self-supervised methods")
    reviewed: list[str] = []
    for comment in comments:
        output = await awaiting(handle, db, "literature")
        reviewed.append(output.stage_output_id)
        changes = dataclasses.replace(output, decision="request_changes", comment=comment)
        await handle.execute_update(DECIDE_UPDATE, changes)
    last = await awaiting(handle, db, "literature")
    with pytest.raises(WorkflowUpdateFailedError) as refused:
        await handle.execute_update(
            DECIDE_UPDATE, dataclasses.replace(last, decision="request_changes", comment="More")
        )
    assert refusal(refused.value) == "decision.no_attempts_left"

    first, second, third = runner.seen
    assert (first.previous_output, first.feedback_history) == (None, ())
    assert second.previous_output == await output_data(db, reviewed[0])
    assert second.feedback_history == comments[:1]
    assert third.previous_output == await output_data(db, reviewed[1])
    assert third.feedback_history == comments
    async with db() as session:
        attempts = (await session.scalars(select(StageRun).order_by(StageRun.attempt))).all()
    assert [(a.attempt, a.last_attempt) for a in attempts] == [(1, 3), (2, 3), (3, 3)]

    await handle.execute_update(DECIDE_UPDATE, last)  # approving the last attempt still works
    await awaiting(handle, db, "method")
    await handle.cancel()


async def test_rate_limits_are_waited_out_without_using_up_attempts(
    env: WorkflowEnvironment, client: Client, db: Factory, runner: FakeRunner
) -> None:
    # More waits than STAGE_RETRY has attempts: a wait is a timer, not a retry.
    runner.errors["literature"] = [
        *(GatewayRateLimitedError(3600, "free_quota.exhausted") for _ in range(9)),
        GatewayRateLimitedError(20, "call.in_progress"),
    ]
    run_id, handle = await start(client, db)
    await env.sleep(timedelta(hours=10))  # queries don't skip time; waiting on a result would
    await awaiting(handle, db, "literature")
    waits = await run_events(db, run_id, "stage.waiting")
    assert [w["reason"] for w in waits] == ["free_quota.exhausted"] * 9 + ["call.in_progress"]
    assert {(w["stage"], w["attempt"]) for w in waits} == {("literature", 1)}
    first, second = (datetime.fromisoformat(w["retry_at"]) for w in waits[:2])
    assert first.utcoffset() == timedelta(0) and second - first >= timedelta(hours=1)
    # Every wait ran the same attempt again.
    assert len(runner.seen) == 11 and len({ctx.stage_run_id for ctx in runner.seen}) == 1
    assert (await run_status(db, run_id))[0] == RunStatus.AWAITING_APPROVAL
    await handle.cancel()
    with pytest.raises(WorkflowFailureError):
        await handle.result()
    await Replayer(workflows=[RunWorkflow]).replay_workflow(await handle.fetch_history())


async def test_rate_limit_waits_end_after_seven_days(
    client: Client, db: Factory, runner: FakeRunner
) -> None:
    runner.errors["literature"] = [
        GatewayRateLimitedError(86_400, "free_quota.exhausted") for _ in range(9)
    ]
    run_id, handle = await start(client, db)
    assert await handle.result() == "failed"
    assert await run_status(db, run_id) == (RunStatus.FAILED, "free_quota.exhausted")
    assert len(await run_events(db, run_id, "stage.waiting")) == 7


async def test_an_exhausted_lab_balance_pauses_the_run_until_calls_work_again(
    env: WorkflowEnvironment, client: Client, db: Factory, runner: FakeRunner
) -> None:
    runner.errors["literature"] = [LabBalanceExhaustedError(), LabBalanceExhaustedError()]
    run_id, handle = await start(client, db)
    await env.sleep(timedelta(hours=1))  # tries after 15, then 30 more minutes
    await awaiting(handle, db, "literature")
    # One pause, however many tries fail the same way: no running/paused flapping, so the
    # event log and the run_paused notification don't repeat every check.
    changes = await run_events(db, run_id, "run.status")
    assert [e["status"] for e in changes] == ["running", "paused_budget", "awaiting_approval"]
    assert changes[1].get("error") == "lab_balance.exhausted"
    assert (await run_status(db, run_id)) == (RunStatus.AWAITING_APPROVAL, None)
    waits = await run_events(db, run_id, "stage.waiting")
    assert [w["reason"] for w in waits] == ["lab_balance.exhausted"] * 2
    first, second = (datetime.fromisoformat(w["retry_at"]) for w in waits)
    assert second - first >= timedelta(minutes=30)  # the second try waited twice as long
    assert len({ctx.stage_run_id for ctx in runner.seen}) == 1
    await handle.cancel()
    with pytest.raises(WorkflowFailureError):
        await handle.result()
    await Replayer(workflows=[RunWorkflow]).replay_workflow(await handle.fetch_history())


async def test_cancel_while_paused(client: Client, db: Factory, runner: FakeRunner) -> None:
    runner.errors["literature"] = [LabBalanceExhaustedError() for _ in range(5)]
    run_id, handle = await start(client, db)
    for _ in range(400):
        if (await run_status(db, run_id))[0] == RunStatus.PAUSED_BUDGET:
            break
        await asyncio.sleep(0.05)
    else:
        raise AssertionError("the run never paused")
    await handle.cancel()
    with pytest.raises(WorkflowFailureError):
        await handle.result()
    assert await run_status(db, run_id) == (RunStatus.CANCELLED, None)
    async with db() as session:
        stage_run = (await session.scalars(select(StageRun))).one()
    assert stage_run.status == StageStatus.CANCELLED


async def test_a_pause_fails_the_run_once_it_has_lasted_too_long(
    env: WorkflowEnvironment, db: Factory, runner: FakeRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Seven days of checks, scaled down to an hour: unsandboxed, the workflow sees the patched
    # limit. Checks after 15, 30 and 60 minutes pass it, and the fourth failure ends the run.
    monkeypatch.setattr("agentic_worker.workflows.MAX_STAGE_WAIT", timedelta(hours=1))
    runner.errors["literature"] = [LabBalanceExhaustedError() for _ in range(9)]
    activities = StageActivities(db, FakeValkey(), runner)
    async with Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[RunWorkflow],
        activities=activities.all(),
        workflow_runner=UnsandboxedWorkflowRunner(),
    ):
        run_id, handle = await start(env.client, db)
        assert await handle.result() == "failed"
    assert await run_status(db, run_id) == (RunStatus.FAILED, "lab_balance.exhausted")
    assert len(await run_events(db, run_id, "stage.waiting")) == 3
    changes = await run_events(db, run_id, "run.status")
    assert [e["status"] for e in changes] == ["running", "paused_budget", "failed"]


async def test_a_wait_for_quota_after_a_pause_ends_the_pause(
    env: WorkflowEnvironment, client: Client, db: Factory, runner: FakeRunner
) -> None:
    """A try that gets past the lab balance and then waits for the free quota is no longer
    paused: the run is running (and waiting), not paused_budget."""
    runner.errors["literature"] = [
        LabBalanceExhaustedError(),
        GatewayRateLimitedError(60, "free_quota.exhausted"),
    ]
    run_id, handle = await start(client, db)
    await env.sleep(timedelta(minutes=30))
    await awaiting(handle, db, "literature")
    changes = await run_events(db, run_id, "run.status")
    assert [e["status"] for e in changes] == [
        "running",
        "paused_budget",
        "running",
        "awaiting_approval",
    ]
    waits = await run_events(db, run_id, "stage.waiting")
    assert [w["reason"] for w in waits] == ["lab_balance.exhausted", "free_quota.exhausted"]
    await handle.cancel()
    with pytest.raises(WorkflowFailureError):
        await handle.result()
    await Replayer(workflows=[RunWorkflow]).replay_workflow(await handle.fetch_history())


async def test_gateway_failures_fail_the_run_with_a_code(
    client: Client, db: Factory, runner: FakeRunner
) -> None:
    runner.errors["literature"] = [GatewayUnavailableError("HTTP 502") for _ in range(8)]
    run_id, handle = await start(client, db)
    assert await handle.result() == "failed"
    assert await run_status(db, run_id) == (RunStatus.FAILED, "gateway.error")
    assert len(runner.seen) == 8  # STAGE_RETRY's attempts
    failed = await run_events(db, run_id, "stage.failed")
    assert failed == [{"stage": "literature", "attempt": 1, "error": "gateway.error"}]


async def test_unexpected_errors_are_stored_as_a_code_not_as_text(
    client: Client, db: Factory, runner: FakeRunner
) -> None:
    runner.errors["literature"] = [RuntimeError("no route to http://10.0.0.5") for _ in range(8)]
    run_id, handle = await start(client, db)
    assert await handle.result() == "failed"
    assert await run_status(db, run_id) == (RunStatus.FAILED, "stage.error")
    finished = (await run_events(db, run_id, "run.status"))[-1]
    assert finished == {"status": "failed", "error": "stage.error"}


async def test_a_literature_search_that_finds_nothing_says_so(
    client: Client, db: Factory, runner: FakeRunner
) -> None:
    runner.errors["literature"] = [StageFailedError("literature.no_papers: nothing matched")]
    run_id, handle = await start(client, db)
    assert await handle.result() == "failed"
    assert await run_status(db, run_id) == (RunStatus.FAILED, "literature.no_papers")


async def test_a_decision_the_database_refuses_fails_the_run_visibly(
    client: Client, db: Factory
) -> None:
    """Postgres stores no NUL character; retrying the write forever used to wedge the run."""
    run_id, handle = await start(client, db)
    decision = await awaiting(handle, db, "literature")
    await handle.execute_update(DECIDE_UPDATE, dataclasses.replace(decision, comment="ok\x00"))
    assert await asyncio.wait_for(handle.result(), timeout=60) == "failed"
    assert await run_status(db, run_id) == (RunStatus.FAILED, "db.error")
    # Not retried: the history's attempt count, since the time-skipping clock jumps over the
    # timers of other tests' workflows and can't measure retries.
    events = (await handle.fetch_history()).events
    scheduled = {
        event.event_id
        for event in events
        if event.HasField("activity_task_scheduled_event_attributes")
        and event.activity_task_scheduled_event_attributes.activity_type.name == "record_decision"
    }
    attempts = [
        event.activity_task_started_event_attributes.attempt
        for event in events
        if event.HasField("activity_task_started_event_attributes")
        and event.activity_task_started_event_attributes.scheduled_event_id in scheduled
    ]
    assert attempts == [1]


async def test_a_run_the_gateway_reports_ended_keeps_its_status(
    client: Client, db: Factory, runner: FakeRunner
) -> None:
    """409 run.inactive: the run was closed elsewhere, so the workflow ends without a word."""
    runner.errors["literature"] = [RunInactiveError("stage-run:call-1")]
    run_id, handle = await start(client, db)
    assert await handle.result() == "run.inactive"
    assert await run_status(db, run_id) == (RunStatus.RUNNING, None)
    assert [e["status"] for e in await run_events(db, run_id, "run.status")] == ["running"]


class SlowFinish(StageActivities):
    """finish_run holds until the test lets it go."""

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.finishing, self.release = asyncio.Event(), asyncio.Event()

    @activity.defn(name="finish_run")
    async def finish_run(self, inp: FinishIn) -> None:
        self.finishing.set()
        await self.release.wait()
        await super().finish_run(inp)


@pytest.mark.parametrize("closed_by", ["expiry", "cancel"])
async def test_decisions_are_refused_once_the_run_is_closing(
    env: WorkflowEnvironment, db: Factory, runner: FakeRunner, closed_by: str
) -> None:
    """Accepted while finish_run ran, a decision used to be acknowledged and then dropped."""
    activities = SlowFinish(db, FakeValkey(), runner)
    async with Worker(
        env.client, task_queue=TASK_QUEUE, workflows=[RunWorkflow], activities=activities.all()
    ):
        run_id, handle = await start(env.client, db)
        decision = await awaiting(handle, db, "literature")
        if closed_by == "expiry":
            await env.sleep(timedelta(days=7))  # exactly the wait: finish_run then holds time
        else:
            await handle.cancel()
        await asyncio.wait_for(activities.finishing.wait(), timeout=20)
        assert (await handle.query(STATUS_QUERY))["awaiting"] is None
        with pytest.raises(WorkflowUpdateFailedError) as refused:
            await handle.execute_update(DECIDE_UPDATE, decision)
        assert refusal(refused.value) == "decision.not_awaited"
        activities.release.set()
        if closed_by == "expiry":
            assert await handle.result() == "cancelled"
        else:
            with pytest.raises(WorkflowFailureError):
                await handle.result()
    error = "approval.expired" if closed_by == "expiry" else None
    assert await run_status(db, run_id) == (RunStatus.CANCELLED, error)
    async with db() as session:
        assert (await session.scalars(select(Approval))).all() == []


class SlowRecord(StageActivities):
    """record_decision holds until the test lets it go."""

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.recording, self.release = asyncio.Event(), asyncio.Event()

    @activity.defn(name="record_decision")
    async def record_decision(self, inp: DecisionRecordIn) -> None:
        self.recording.set()
        await self.release.wait()
        await super().record_decision(inp)


async def cancel_seen(handle: WorkflowHandle) -> None:
    """Wait until the workflow has completed a task since the cancel request."""
    requested = HistoryEvent.EVENT_TYPE_WORKFLOW_EXECUTION_CANCEL_REQUESTED
    completed = HistoryEvent.EVENT_TYPE_WORKFLOW_TASK_COMPLETED
    for _ in range(200):
        events = [event.event_type for event in (await handle.fetch_history()).events]
        if requested in events and completed in events[events.index(requested) :]:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("the workflow never handled the cancel")


async def test_a_decision_accepted_before_a_cancel_is_still_recorded(
    env: WorkflowEnvironment, db: Factory, runner: FakeRunner
) -> None:
    """The reviewer got 202 for it, so the run records it before it closes."""
    activities = SlowRecord(db, FakeValkey(), runner)
    async with Worker(
        env.client, task_queue=TASK_QUEUE, workflows=[RunWorkflow], activities=activities.all()
    ):
        run_id, handle = await start(env.client, db)
        await handle.execute_update(DECIDE_UPDATE, await awaiting(handle, db, "literature"))
        await asyncio.wait_for(activities.recording.wait(), timeout=20)
        await handle.cancel()
        await cancel_seen(handle)
        activities.release.set()
        with pytest.raises(WorkflowFailureError):
            await handle.result()
    assert await run_status(db, run_id) == (RunStatus.CANCELLED, None)
    async with db() as session:
        approvals = (await session.scalars(select(Approval))).all()
    assert [approval.decision for approval in approvals] == ["approve"]

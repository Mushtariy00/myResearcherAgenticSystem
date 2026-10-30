"""Fakes and helpers for worker tests: runners and a planner without LLMs, a Valkey that accepts
publishes, and helpers that create runs and wait for a stage's output."""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio.client import Client, WorkflowHandle

from agentic_core import demo
from agentic_core.contracts import (
    RUN_WORKFLOW,
    STATUS_QUERY,
    TASK_QUEUE,
    DecisionInput,
    EventType,
    RunInput,
    workflow_id_for,
)
from agentic_core.enums import RunStatus
from agentic_db import append_event
from agentic_db.models import Project, Run, RunEvent, StageOutput
from agentic_worker.stages import PlannedSearch, StageContext, StageFailedError, StageOutcome

Factory = async_sessionmaker[AsyncSession]
# A cancel reaches a running stage in a heartbeat response, and the workflow waits for the
# stage to stop: test workers send every heartbeat, as the worker entry point does.
HEARTBEAT_THROTTLE = timedelta(milliseconds=100)


@dataclass
class FakeRunner:
    fail_stage: str | None = None
    block_stage: str | None = None  # this stage runs until the activity is cancelled
    # What the blocked stage does once cancelled: stop, finish anyway (like a CrewAI thread
    # that ignores the cancel), fail, or log a line a moment later and then stop.
    on_cancel: Literal["stop", "finish", "fail", "log"] = "stop"
    # Raised in turn, one per run of the stage, before it succeeds.
    errors: dict[str, list[BaseException]] = field(default_factory=dict)
    blocked: asyncio.Event = field(default_factory=asyncio.Event)
    seen: list[StageContext] = field(default_factory=list)

    async def run(self, ctx: StageContext) -> StageOutcome:
        self.seen.append(ctx)
        queued = self.errors.get(ctx.stage)
        if queued:
            raise queued.pop(0)
        if ctx.stage == self.fail_stage:
            raise StageFailedError(f"{ctx.stage}.invalid_output: the model returned prose")
        if ctx.stage == self.block_stage:
            self.blocked.set()
            try:
                await asyncio.Event().wait()  # never set: only cancellation ends this
            except asyncio.CancelledError:
                if self.on_cancel == "fail":
                    raise StageFailedError(f"{ctx.stage}.invalid_output: cut short") from None
                if self.on_cancel == "log":
                    await asyncio.sleep(0.5)
                    await ctx.log("fake.stopping", {}, "Stopping")
                if self.on_cancel != "finish":
                    raise
        return StageOutcome(
            data={"stage": ctx.stage, "attempt": ctx.attempt, "feedback": ctx.feedback},
            model="fake/model",
        )


@dataclass
class FakePlanner:
    """The literature plan without an LLM: a generated plan and one free gateway call."""

    fail_times: int = 0  # the first calls raise StageFailedError (an invalid model answer)
    seen: list[StageContext] = field(default_factory=list)

    async def plan(self, ctx: StageContext) -> PlannedSearch:
        self.seen.append(ctx)
        if len(self.seen) <= self.fail_times:
            raise StageFailedError("literature.invalid_output: the model returned prose")
        return PlannedSearch(
            plan=demo.research_plan(ctx.topic, 1, config=ctx.config, feedback=ctx.feedback),
            model="fake/free-model:free",
            llm_calls=[{"model": "fake/free-model:free", "tier": "free", "cost_usd": "0"}],
        )


class FakeValkey:
    def __init__(self) -> None:
        self.published: list[str] = []

    async def publish(self, channel: str, message: str) -> int:
        self.published.append(channel)
        return 1


class HangingValkey:
    """A Valkey that never answers (a half-open connection)."""

    async def publish(self, channel: str, message: str) -> int:
        await asyncio.Event().wait()
        return 0


async def create_run(
    db: Factory,
    *,
    topic: str = "Monocular depth estimation",
    config: dict[str, Any] | None = None,
    auto_approve: bool = False,
    approval_expiry_days: int = 7,
    status: RunStatus = RunStatus.QUEUED,
) -> str:
    async with db() as session:
        project = Project(
            name="Depth",
            created_by="bob",
            auto_approve=auto_approve,
            approval_expiry_days=approval_expiry_days,
        )
        session.add(project)
        await session.flush()
        run = Run(
            project_id=project.id, owner_id="bob", topic=topic, config=config or {}, status=status
        )
        session.add(run)
        await session.commit()
    return str(run.id)


async def start_run(client: Client, run_id: str, start_stage: str | None = None) -> WorkflowHandle:
    """Start an execution of RunWorkflow, as the API does (a retry passes ``start_stage``)."""
    return await client.start_workflow(
        RUN_WORKFLOW,
        RunInput(run_id=run_id, start_stage=start_stage),
        id=workflow_id_for(run_id),
        task_queue=TASK_QUEUE,
    )


async def retry_run(client: Client, db: Factory, run_id: str, start_stage: str) -> WorkflowHandle:
    """Retry a finished run as the API does: mark it running, then start a new execution."""
    async with db() as session:
        run = await session.get(Run, uuid.UUID(run_id), with_for_update=True)
        if run is None:
            raise AssertionError(f"run {run_id} is missing")
        run.status, run.error = RunStatus.RUNNING, None
        await append_event(
            session,
            run.id,
            EventType.RUN_STATUS,
            {"status": RunStatus.RUNNING.value, "retry_stage": start_stage},
        )
        await session.commit()
    return await start_run(client, run_id, start_stage)


async def awaiting(
    handle: WorkflowHandle, db: Factory, stage: str, actor: str = "bob"
) -> DecisionInput:
    """Wait until `stage` has an output to review; return an approve decision for it."""
    for _ in range(400):
        status = await handle.query(STATUS_QUERY)
        if status["awaiting"] and status["stage"] == stage:
            async with db() as session:
                output = await session.get(StageOutput, uuid.UUID(status["awaiting"]))
            if output is None:
                raise AssertionError(f"{stage} output {status['awaiting']} is missing")
            return DecisionInput(
                stage=stage,
                stage_output_id=str(output.id),
                sha256=output.sha256,
                decision="approve",
                actor_id=actor,
            )
        await asyncio.sleep(0.05)
    raise AssertionError(f"{stage} never became ready for review")


async def run_status(db: Factory, run_id: str) -> tuple[RunStatus, str | None]:
    async with db() as session:
        run = await session.get(Run, uuid.UUID(run_id))
    if run is None:
        raise AssertionError(f"run {run_id} is missing")
    return RunStatus(run.status), run.error


async def run_events(db: Factory, run_id: str, event_type: str) -> list[dict[str, Any]]:
    async with db() as session:
        rows = await session.scalars(
            select(RunEvent)
            .where(RunEvent.run_id == uuid.UUID(run_id), RunEvent.type == event_type)
            .order_by(RunEvent.seq)
        )
        return [row.payload for row in rows]

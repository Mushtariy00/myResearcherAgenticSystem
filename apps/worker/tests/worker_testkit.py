"""Fakes and helpers for worker tests: runners and a planner without LLMs, a Valkey that accepts
publishes, and helpers that create runs and wait for a stage's output."""

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio.client import Client, WorkflowHandle

from agentic_core import demo
from agentic_core.contracts import (
    RUN_WORKFLOW,
    STATUS_QUERY,
    TASK_QUEUE,
    DecisionInput,
    RunInput,
    workflow_id_for,
)
from agentic_core.enums import RunStatus
from agentic_db.models import Project, Run, StageOutput
from agentic_worker.stages import PlannedSearch, StageContext, StageFailedError, StageOutcome

Factory = async_sessionmaker[AsyncSession]


@dataclass
class FakeRunner:
    fail_stage: str | None = None
    block_stage: str | None = None  # this stage runs until the activity is cancelled
    blocked: asyncio.Event = field(default_factory=asyncio.Event)
    seen: list[StageContext] = field(default_factory=list)

    async def run(self, ctx: StageContext) -> StageOutcome:
        self.seen.append(ctx)
        if ctx.stage == self.fail_stage:
            raise StageFailedError(f"{ctx.stage}.invalid_output: the model returned prose")
        if ctx.stage == self.block_stage:
            self.blocked.set()
            await asyncio.Event().wait()  # never set: only cancellation ends this
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

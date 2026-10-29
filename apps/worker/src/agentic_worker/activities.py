"""Stage activities: every database change and run event happens here, never in workflow code."""

import asyncio
import contextlib
import hashlib
import json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio import activity
from temporalio.exceptions import ApplicationError

from agentic_core.contracts import EventType, events_channel
from agentic_core.enums import Decision, RunStatus, StageStatus
from agentic_db import append_event
from agentic_db.models import Approval, Run, StageOutput, StageRun
from agentic_worker.gateway_llm import (
    FreeModelsDisabledError,
    GatewayRateLimitedError,
    LabBalanceExhaustedError,
)
from agentic_worker.stages import StageContext, StageFailedError, StageRunner
from agentic_worker.types import (
    DecisionRecordIn,
    FinishIn,
    StageExecIn,
    StageResult,
    StageStarted,
    StageStartIn,
)

log = logging.getLogger(__name__)
HEARTBEAT_SECONDS = 10.0
_DECISION_STATUS = {
    Decision.APPROVE: StageStatus.APPROVED,
    Decision.REQUEST_CHANGES: StageStatus.CHANGES_REQUESTED,
    Decision.REJECT: StageStatus.REJECTED,
}


def _require[T](value: T | None, what: str) -> T:
    if value is None:
        raise ApplicationError(f"{what}.not_found", type="NotFound", non_retryable=True)
    return value


def content_sha256(data: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@contextlib.asynccontextmanager
async def heartbeating() -> AsyncIterator[None]:
    """Heartbeat while long work runs, so Temporal can deliver cancellation promptly."""

    async def beat() -> None:
        while True:
            activity.heartbeat()
            await asyncio.sleep(HEARTBEAT_SECONDS)

    task = asyncio.create_task(beat())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


class StageActivities:
    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], valkey: Any, runner: StageRunner
    ) -> None:
        self._sessions = sessions
        self._valkey = valkey
        self._runner = runner

    async def _wake(self, run_id: uuid.UUID) -> None:
        try:
            await self._valkey.publish(events_channel(run_id), "1")
        except Exception:  # SSE falls back to polling; never fail a stage over a wake-up
            log.warning("could not publish wake-up for run %s", run_id)

    @activity.defn(name="start_stage")
    async def start_stage(self, inp: StageStartIn) -> StageStarted:
        run_id = uuid.UUID(inp.run_id)
        async with self._sessions() as session:
            existing = await session.scalar(
                select(StageRun).where(
                    StageRun.run_id == run_id,
                    StageRun.stage == inp.stage,
                    StageRun.attempt == inp.attempt,
                )
            )
            if existing is not None:  # activity retry: the row was committed last time
                return StageStarted(stage_run_id=str(existing.id))
            stage_run = StageRun(
                run_id=run_id,
                stage=inp.stage,
                attempt=inp.attempt,
                status=StageStatus.RUNNING,
                feedback=inp.feedback or None,
                started_at=datetime.now(UTC),
            )
            session.add(stage_run)
            run = _require(await session.get(Run, run_id), "run")
            run.status = RunStatus.RUNNING
            await session.flush()
            await append_event(
                session,
                run_id,
                EventType.STAGE_STARTED,
                {"stage": inp.stage, "attempt": inp.attempt},
            )
            await append_event(session, run_id, EventType.RUN_STATUS, {"status": RunStatus.RUNNING})
            await session.commit()
        await self._wake(run_id)
        return StageStarted(stage_run_id=str(stage_run.id))

    @activity.defn(name="execute_stage")
    async def execute_stage(self, inp: StageExecIn) -> StageResult:
        run_id, stage_run_id = uuid.UUID(inp.run_id), uuid.UUID(inp.stage_run_id)
        async with self._sessions() as session:
            run = _require(await session.get(Run, run_id), "run")
            ctx = StageContext(
                run_id=inp.run_id,
                stage_run_id=inp.stage_run_id,
                stage=inp.stage,
                attempt=inp.attempt,
                feedback=inp.feedback,
                topic=run.topic,
                owner_id=run.owner_id,
                project_id=str(run.project_id),
                llm_policy=str(run.llm_policy),
                budget_cap_usd=str(run.budget_cap_usd) if run.budget_cap_usd is not None else None,
            )
        try:
            async with heartbeating():
                outcome = await self._runner.run(ctx)
        except GatewayRateLimitedError as exc:
            # Retryable: Temporal waits durably (a server-side timer) before the next attempt.
            raise ApplicationError(
                str(exc), type="RateLimited", next_retry_delay=timedelta(seconds=exc.retry_after)
            ) from exc
        except LabBalanceExhaustedError as exc:
            raise ApplicationError(
                "lab_balance.exhausted", type="LabBalanceExhausted", non_retryable=True
            ) from exc
        except FreeModelsDisabledError as exc:
            raise ApplicationError(
                "free_models.disabled", type="FreeModelsDisabled", non_retryable=True
            ) from exc
        except StageFailedError as exc:
            raise ApplicationError(str(exc), type="StageFailed", non_retryable=True) from exc

        sha = content_sha256(outcome.data)
        async with self._sessions() as session:
            output = StageOutput(
                stage_run_id=stage_run_id,
                data=outcome.data,
                sha256=sha,
                model=outcome.model,
                degraded=outcome.degraded,
                degraded_reason=outcome.degraded_reason,
                prompt_version=outcome.prompt_version,
            )
            session.add(output)
            stage_run = _require(await session.get(StageRun, stage_run_id), "stage_run")
            run = _require(await session.get(Run, run_id), "run")
            stage_run.status = StageStatus.OUTPUT_READY
            run.status = RunStatus.AWAITING_APPROVAL
            await session.flush()
            for call in outcome.llm_calls:
                await append_event(
                    session,
                    run_id,
                    EventType.LLM_CALL,
                    {
                        "stage": inp.stage,
                        "model": call.get("model"),
                        "tier": call.get("tier"),
                        "cost_usd": str(call.get("cost_usd")),
                        "switched_to_free": call.get("switched_to_free", False),
                        "replayed": call.get("replayed", False),
                    },
                )
            await append_event(
                session,
                run_id,
                EventType.STAGE_OUTPUT_READY,
                {
                    "stage": inp.stage,
                    "attempt": inp.attempt,
                    "stage_output_id": str(output.id),
                    "degraded": outcome.degraded,
                },
            )
            await append_event(
                session, run_id, EventType.RUN_STATUS, {"status": RunStatus.AWAITING_APPROVAL}
            )
            await session.commit()
        await self._wake(run_id)
        return StageResult(stage_output_id=str(output.id), sha256=sha, degraded=outcome.degraded)

    @activity.defn(name="record_decision")
    async def record_decision(self, inp: DecisionRecordIn) -> None:
        run_id, decision = uuid.UUID(inp.run_id), inp.decision
        output_id = uuid.UUID(decision.stage_output_id)
        async with self._sessions() as session:
            if await session.scalar(
                select(Approval.id).where(Approval.stage_output_id == output_id)
            ):
                return  # activity retry after the commit below
            session.add(
                Approval(
                    stage_output_id=output_id,
                    sha256=decision.sha256,
                    decision=Decision(decision.decision),
                    comment=decision.comment,
                    actor_id=decision.actor_id,
                )
            )
            stage_run = _require(
                await session.get(StageRun, uuid.UUID(inp.stage_run_id)), "stage_run"
            )
            run = _require(await session.get(Run, run_id), "run")
            stage_run.status = _DECISION_STATUS[Decision(decision.decision)]
            stage_run.finished_at = datetime.now(UTC)
            if decision.decision != Decision.REJECT:
                run.status = RunStatus.RUNNING
            await append_event(
                session,
                run_id,
                EventType.STAGE_DECIDED,
                {
                    "stage": decision.stage,
                    "decision": decision.decision,
                    "actor_id": decision.actor_id,
                    "comment": decision.comment,
                    "attempt": stage_run.attempt,
                },
            )
            await session.commit()
        await self._wake(run_id)

    @activity.defn(name="finish_run")
    async def finish_run(self, inp: FinishIn) -> None:
        run_id, status = uuid.UUID(inp.run_id), RunStatus(inp.status)
        async with self._sessions() as session:
            run = _require(await session.get(Run, run_id), "run")
            if run.status == status:
                return  # activity retry
            run.status = status
            run.error = inp.error
            if status in (RunStatus.CANCELLED, RunStatus.FAILED):
                open_stages = await session.scalars(
                    select(StageRun).where(
                        StageRun.run_id == run_id,
                        StageRun.status.in_([StageStatus.RUNNING, StageStatus.OUTPUT_READY]),
                    )
                )
                for stage_run in open_stages:
                    stage_run.status = (
                        StageStatus.CANCELLED
                        if status == RunStatus.CANCELLED
                        else StageStatus.FAILED
                    )
                    stage_run.error = inp.error
                    stage_run.finished_at = datetime.now(UTC)
            await append_event(
                session, run_id, EventType.RUN_STATUS, {"status": status, "error": inp.error}
            )
            await session.commit()
        await self._wake(run_id)

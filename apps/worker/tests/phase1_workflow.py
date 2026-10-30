"""The run workflow as Phase 1 shipped it (commit afb9e3a), for replay tests.

Runs started on that code may still wait for an approval when a worker with newer code takes
over. Tests run this class to build such a history, then replay and continue it on the current
RunWorkflow. Keep the command sequence exactly as it was; do not "fix" this file.
"""

import asyncio
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError, is_cancelled_exception

with workflow.unsafe.imports_passed_through():
    from agentic_core.contracts import (
        DECIDE_UPDATE,
        RUN_WORKFLOW,
        STATUS_QUERY,
        DecisionInput,
        RunInput,
    )
    from agentic_core.enums import Decision, RunStatus
    from agentic_core.stages import STAGE_ORDER
    from agentic_worker.types import (
        DecisionRecordIn,
        FinishIn,
        PendingDecision,
        StageExecIn,
        StageResult,
        StageStarted,
        StageStartIn,
    )

MAX_ATTEMPTS = 3
APPROVAL_TIMEOUT = timedelta(days=7)
DB_STEP = timedelta(seconds=30)
STAGE_STEP = timedelta(minutes=30)
DB_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1), maximum_interval=timedelta(seconds=30)
)
STAGE_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    maximum_interval=timedelta(minutes=5),
    maximum_attempts=8,
    non_retryable_error_types=["StageFailed", "LabBalanceExhausted", "FreeModelsDisabled"],
)
DECISIONS = frozenset(d.value for d in Decision)


def _error_code(error: ActivityError) -> str:
    cause = error.cause
    if isinstance(cause, ApplicationError):
        return (
            cause.message.split(":")[0]
            if cause.type == "StageFailed"
            else (cause.message or str(cause.type))
        )
    return "stage.error"


@workflow.defn(name=RUN_WORKFLOW)
class Phase1RunWorkflow:
    def __init__(self) -> None:
        self._pending: PendingDecision | None = None
        self._decision: DecisionInput | None = None
        self._stage: str | None = None
        self._status = RunStatus.QUEUED.value

    @workflow.run
    async def run(self, inp: RunInput) -> str:
        try:
            for stage in (s.value for s in STAGE_ORDER):
                feedback = ""
                for attempt in range(1, MAX_ATTEMPTS + 1):
                    decision = await self._run_attempt(inp.run_id, stage, attempt, feedback)
                    if decision.decision == Decision.APPROVE:
                        break
                    if decision.decision == Decision.REJECT:
                        return await self._finish(inp.run_id, RunStatus.REJECTED)
                    feedback = decision.comment
                else:
                    return await self._finish(
                        inp.run_id, RunStatus.FAILED, "stage.too_many_attempts"
                    )
            return await self._finish(inp.run_id, RunStatus.COMPLETED)
        except asyncio.CancelledError:
            await self._finish(inp.run_id, RunStatus.CANCELLED)
            raise
        except TimeoutError:
            return await self._finish(inp.run_id, RunStatus.CANCELLED, "approval.expired")
        except ActivityError as error:
            if is_cancelled_exception(error):
                await self._finish(inp.run_id, RunStatus.CANCELLED)
                raise asyncio.CancelledError from error
            return await self._finish(inp.run_id, RunStatus.FAILED, _error_code(error))

    async def _run_attempt(
        self, run_id: str, stage: str, attempt: int, feedback: str
    ) -> DecisionInput:
        self._stage, self._status = stage, RunStatus.RUNNING.value
        started = await workflow.execute_activity(
            "start_stage",
            StageStartIn(run_id=run_id, stage=stage, attempt=attempt, feedback=feedback),
            start_to_close_timeout=DB_STEP,
            retry_policy=DB_RETRY,
            result_type=StageStarted,
        )
        result = await workflow.execute_activity(
            "execute_stage",
            StageExecIn(
                run_id=run_id,
                stage_run_id=started.stage_run_id,
                stage=stage,
                attempt=attempt,
                feedback=feedback,
            ),
            start_to_close_timeout=STAGE_STEP,
            heartbeat_timeout=timedelta(minutes=2),
            retry_policy=STAGE_RETRY,
            result_type=StageResult,
        )
        self._decision = None
        self._pending = PendingDecision(
            stage=stage, stage_output_id=result.stage_output_id, sha256=result.sha256
        )
        self._status = RunStatus.AWAITING_APPROVAL.value
        await workflow.wait_condition(lambda: self._decision is not None, timeout=APPROVAL_TIMEOUT)
        decision = self._decision
        if decision is None:
            raise ApplicationError("decision.missing", non_retryable=True)
        self._pending = None
        await workflow.execute_activity(
            "record_decision",
            DecisionRecordIn(run_id=run_id, stage_run_id=started.stage_run_id, decision=decision),
            start_to_close_timeout=DB_STEP,
            retry_policy=DB_RETRY,
        )
        return decision

    async def _finish(self, run_id: str, status: RunStatus, error: str | None = None) -> str:
        self._status = status.value
        await workflow.execute_activity(
            "finish_run",
            FinishIn(run_id=run_id, status=status.value, error=error),
            start_to_close_timeout=DB_STEP,
            retry_policy=DB_RETRY,
        )
        return status.value

    @workflow.update(name=DECIDE_UPDATE)
    async def decide(self, decision: DecisionInput) -> None:
        self._decision = decision

    @decide.validator
    def _validate_decide(self, decision: DecisionInput) -> None:
        pending = self._pending
        if pending is None or self._decision is not None:
            raise ValueError("decision.not_awaited")
        if (decision.stage, decision.stage_output_id, decision.sha256) != (
            pending.stage,
            pending.stage_output_id,
            pending.sha256,
        ):
            raise ValueError("decision.stale")
        if decision.decision not in DECISIONS:
            raise ValueError("decision.invalid")

    @workflow.query(name=STATUS_QUERY)
    def status(self) -> dict[str, Any]:
        return {
            "status": self._status,
            "stage": self._stage,
            "awaiting": self._pending.stage_output_id if self._pending else None,
        }

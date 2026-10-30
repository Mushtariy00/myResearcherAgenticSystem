"""The run workflow (deterministic: no I/O here; activities do all side effects).

Each stage: start → execute → wait for a human decision (a validated Temporal Update) →
approve: next stage | request changes: new attempt with the feedback | reject: stop.

A run executes the stages in its config, can be retried from a stage (a new execution of this
workflow with ``RunInput.start_stage``), and follows its project's settings: auto-approve
(never for coding) and how many days an unanswered approval waits.
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
    from agentic_core.schemas import validate_stage_output
    from agentic_core.stages import NEVER_AUTO_APPROVE, STAGE_ORDER, Stage
    from agentic_worker.types import (
        DecisionRecordIn,
        FinishIn,
        PendingDecision,
        RunPlan,
        RunPrepareIn,
        StageExecIn,
        StageResult,
        StageStarted,
        StageStartIn,
    )

MAX_ATTEMPTS = 3  # per stage and execution: the first try plus two change requests
APPROVAL_TIMEOUT = timedelta(days=7)  # runs started before project settings existed
DB_STEP = timedelta(seconds=30)
STAGE_STEP = timedelta(minutes=30)
DB_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1), maximum_interval=timedelta(seconds=30)
)
# About 15 minutes of backoff for transient failures. Rate limits retry after the gateway's
# Retry-After instead (next_retry_delay), e.g. at the free tier's daily reset.
STAGE_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    maximum_interval=timedelta(minutes=5),
    maximum_attempts=8,
    non_retryable_error_types=["StageFailed", "LabBalanceExhausted", "FreeModelsDisabled"],
)
DECISIONS = frozenset(d.value for d in Decision)
AUTO_APPROVE_ACTOR = "system:auto-approve"
# Runs that started before stage selection, retries and project settings replay their history
# without this marker and keep the original command sequence; they may wait days for review.
RUN_SETTINGS_PATCH = "run-config-retry-project-settings"


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
class RunWorkflow:
    def __init__(self) -> None:
        self._pending: PendingDecision | None = None
        self._decision: DecisionInput | None = None
        self._stage: str | None = None
        self._status = RunStatus.QUEUED.value

    @workflow.run
    async def run(self, inp: RunInput) -> str:
        try:
            if workflow.patched(RUN_SETTINGS_PATCH):
                return await self._run_planned_stages(inp)
            return await self._run_every_stage(inp)
        except asyncio.CancelledError:
            # Cancellation interrupts whatever we were awaiting; record it, then let it propagate.
            await self._finish(inp.run_id, RunStatus.CANCELLED)
            raise
        except TimeoutError:
            return await self._finish(inp.run_id, RunStatus.CANCELLED, "approval.expired")
        except ActivityError as error:
            if is_cancelled_exception(error):
                # Cancelled while an activity ran: Temporal reports it as an activity error.
                await self._finish(inp.run_id, RunStatus.CANCELLED)
                raise asyncio.CancelledError from error
            return await self._finish(inp.run_id, RunStatus.FAILED, _error_code(error))

    async def _run_planned_stages(self, inp: RunInput) -> str:
        """The configured stages, from the retry stage on; project settings apply."""
        plan = await workflow.execute_activity(
            "prepare_run",
            RunPrepareIn(run_id=inp.run_id, start_stage=inp.start_stage),
            start_to_close_timeout=DB_STEP,
            retry_policy=DB_RETRY,
            result_type=RunPlan,
        )
        for stage in plan.stages:
            first = plan.first_attempts.get(stage, 1)
            outcome = await self._run_stage(inp.run_id, stage, first, settings=True)
            if outcome is not None:
                return outcome
        return await self._finish(inp.run_id, RunStatus.COMPLETED)

    async def _run_every_stage(self, inp: RunInput) -> str:
        """Phase 1 behaviour, kept for runs whose history predates RUN_SETTINGS_PATCH."""
        for stage in (s.value for s in STAGE_ORDER):
            outcome = await self._run_stage(inp.run_id, stage, 1, settings=False)
            if outcome is not None:
                return outcome
        return await self._finish(inp.run_id, RunStatus.COMPLETED)

    async def _run_stage(
        self, run_id: str, stage: str, first_attempt: int, *, settings: bool
    ) -> str | None:
        """Attempts until approved (None: continue with the next stage) or the run ends."""
        feedback = ""
        for attempt in range(first_attempt, first_attempt + MAX_ATTEMPTS):
            decision = await self._run_attempt(run_id, stage, attempt, feedback, settings=settings)
            if decision.decision == Decision.APPROVE:
                return None
            if decision.decision == Decision.REJECT:
                return await self._finish(run_id, RunStatus.REJECTED)
            feedback = decision.comment
        return await self._finish(run_id, RunStatus.FAILED, "stage.too_many_attempts")

    async def _run_attempt(
        self, run_id: str, stage: str, attempt: int, feedback: str, *, settings: bool
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
                apply_project_settings=settings,
            ),
            start_to_close_timeout=STAGE_STEP,
            heartbeat_timeout=timedelta(minutes=2),
            retry_policy=STAGE_RETRY,
            result_type=StageResult,
        )
        automatic = settings and result.auto_approve and Stage(stage) not in NEVER_AUTO_APPROVE
        if automatic:
            decision = DecisionInput(
                stage=stage,
                stage_output_id=result.stage_output_id,
                sha256=result.sha256,
                decision=Decision.APPROVE.value,
                actor_id=AUTO_APPROVE_ACTOR,
            )
        else:
            expiry = APPROVAL_TIMEOUT
            if settings and result.approval_expiry_days:
                expiry = timedelta(days=max(1, result.approval_expiry_days))
            decision = await self._wait_for_decision(stage, result, expires_after=expiry)
        await workflow.execute_activity(
            "record_decision",
            DecisionRecordIn(
                run_id=run_id,
                stage_run_id=started.stage_run_id,
                decision=decision,
                automatic=automatic,
            ),
            start_to_close_timeout=DB_STEP,
            retry_policy=DB_RETRY,
        )
        return decision

    async def _wait_for_decision(
        self, stage: str, result: StageResult, *, expires_after: timedelta
    ) -> DecisionInput:
        """Wait for a reviewer; TimeoutError (the run is cancelled) after ``expires_after``."""
        self._decision = None
        self._pending = PendingDecision(
            stage=stage, stage_output_id=result.stage_output_id, sha256=result.sha256
        )
        self._status = RunStatus.AWAITING_APPROVAL.value
        await workflow.wait_condition(lambda: self._decision is not None, timeout=expires_after)
        decision = self._decision
        if decision is None:  # unreachable: wait_condition returned because it was set
            raise ApplicationError("decision.missing", non_retryable=True)
        self._pending = None
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
        """Runs before anything is recorded: a rejected Update leaves no trace in history."""
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
        if decision.edited_data is not None:
            # Approve with edits only; the edited output must be valid for the stage.
            if decision.decision != Decision.APPROVE.value:
                raise ValueError("decision.invalid")
            try:
                validate_stage_output(decision.stage, decision.edited_data)
            except ValueError:  # pydantic's ValidationError is a ValueError
                raise ValueError("decision.invalid_edit") from None

    @workflow.query(name=STATUS_QUERY)
    def status(self) -> dict[str, Any]:
        return {
            "status": self._status,
            "stage": self._stage,
            "awaiting": self._pending.stage_output_id if self._pending else None,
        }

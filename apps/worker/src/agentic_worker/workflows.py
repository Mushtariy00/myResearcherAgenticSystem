"""The run workflow (deterministic: no I/O here; activities do all side effects).

Each stage: start → execute → wait for a human decision (a validated Temporal Update) →
approve: next stage | request changes: new attempt with the feedback | reject: stop.

A run executes the stages in its config, can be retried from a stage (a new execution of this
workflow with ``RunInput.start_stage``), and follows its project's settings: auto-approve
(never for coding) and how many days an unanswered approval waits. When the gateway asks a
stage to wait (free quota, a call still in flight, an exhausted lab balance), the attempt waits
on a durable timer and runs again; the run is paused_budget while the lab's balance is empty.
"""

import asyncio
import re
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
    from agentic_core.stages import MAX_ATTEMPTS, NEVER_AUTO_APPROVE, STAGE_ORDER, Stage
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
        StageWaitIn,
    )

APPROVAL_TIMEOUT = timedelta(days=7)  # runs started before project settings existed
DB_STEP = timedelta(seconds=30)
STAGE_STEP = timedelta(minutes=30)
# The literature stage searches, fetches PDFs and makes tens of LLM calls in one activity. An
# activity option, so changing it leaves the command sequence (and replay) as it was.
LITERATURE_STEP = timedelta(hours=2)
STAGE_HEARTBEAT = timedelta(minutes=2)
# Database errors that no retry fixes, e.g. a NUL character in a comment. Temporal names an
# activity's exception by its class, here SQLAlchemy's.
DB_DETERMINISTIC_ERRORS = ("DataError", "ProgrammingError", "NotSupportedError")
DB_ERRORS = frozenset(
    {
        *DB_DETERMINISTIC_ERRORS,
        "IntegrityError",
        "OperationalError",
        "InterfaceError",
        "InternalError",
        "DatabaseError",
        "DBAPIError",
    }
)
# About 10 minutes of backoff while the database is unreachable; then the run fails (db.error).
DB_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=25,
    non_retryable_error_types=list(DB_DETERMINISTIC_ERRORS),
)
# The final status must reach the database, however long it is down.
FINISH_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=30),
    non_retryable_error_types=list(DB_DETERMINISTIC_ERRORS),
)
_STAGE_FAILURES = [
    "StageFailed",
    "LabBalanceExhausted",
    "FreeModelsDisabled",
    "RunClosed",
    *DB_DETERMINISTIC_ERRORS,
]
# About 15 minutes of backoff for transient failures (gateway errors, a lost worker). Rate
# limits and an exhausted lab balance are waited out by the workflow and use no attempts.
STAGE_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    maximum_interval=timedelta(minutes=5),
    maximum_attempts=8,
    non_retryable_error_types=[*_STAGE_FAILURES, "RateLimited"],
)
# Runs started before STAGE_WAITS_PATCH: Temporal retries a rate limit after its Retry-After.
LEGACY_STAGE_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    maximum_interval=timedelta(minutes=5),
    maximum_attempts=8,
    non_retryable_error_types=_STAGE_FAILURES,
)
# An attempt waits up to this long for rate limits, and as long again while the lab's balance
# is exhausted; then the run fails (free_quota.exhausted, lab_balance.exhausted).
MAX_STAGE_WAIT = timedelta(days=7)
# A paused run tries the gateway again after 15 minutes, then less often (doubling up to an
# hour), so a long pause writes a few dozen events a day, not one every 15 minutes.
BUDGET_RECHECK = timedelta(minutes=15)
MAX_BUDGET_RECHECK = timedelta(hours=1)
DEFAULT_RETRY_AFTER = timedelta(minutes=1)
DECISIONS = frozenset(d.value for d in Decision)
AUTO_APPROVE_ACTOR = "system:auto-approve"
# Runs that started before stage selection, retries and project settings replay their history
# without this marker and keep the original command sequence; they may wait days for review.
RUN_SETTINGS_PATCH = "run-config-retry-project-settings"
# Runs that started before waits and pauses keep their command sequence the same way: Temporal
# retries their rate limits, an exhausted lab balance fails them, and a cancel waits neither for
# the running stage to stop nor for an accepted decision to be recorded.
STAGE_WAITS_PATCH = "stage-waits-budget-pause-cancel-completion"
# runs.error and stage_runs.error hold these codes, which the web translates; details are logged.
_ERROR_CODES = {
    "RateLimited": "free_quota.exhausted",
    "LabBalanceExhausted": "lab_balance.exhausted",
    "FreeModelsDisabled": "free_models.disabled",
    "GatewayError": "gateway.error",
    **dict.fromkeys(DB_ERRORS, "db.error"),
}
_INVALID_OUTPUT = re.compile(r"[a-z_]+\.invalid_output")
# What else a stage may fail with (StageFailed "<code>: <details>"); the web translates these.
_STAGE_FAILURES = frozenset({"literature.no_papers"})


def _stage_timeout(stage: str) -> timedelta:
    return LITERATURE_STEP if stage == Stage.LITERATURE.value else STAGE_STEP


def _error_code(error: ActivityError) -> str:
    cause = error.cause
    if not isinstance(cause, ApplicationError):
        return "stage.error"
    if cause.type == "StageFailed":  # "<code>: <details>"
        code = cause.message.split(":")[0]
        known = _INVALID_OUTPUT.fullmatch(code) or code in _STAGE_FAILURES
        return code if known else "stage.error"
    return _ERROR_CODES.get(cause.type or "", "stage.error")


@workflow.defn(name=RUN_WORKFLOW)
class RunWorkflow:
    def __init__(self) -> None:
        self._pending: PendingDecision | None = None
        self._decision: DecisionInput | None = None
        self._stage: str | None = None
        self._status = RunStatus.QUEUED.value
        self._closing = False  # the run is finishing: decisions are no longer taken
        self._waits = False  # STAGE_WAITS_PATCH applies

    @workflow.run
    async def run(self, inp: RunInput) -> str:
        """The run's final status, or the code of why it ended without one (run.closed)."""
        try:
            if workflow.patched(RUN_SETTINGS_PATCH):
                self._waits = workflow.patched(STAGE_WAITS_PATCH)
                return await self._run_planned_stages(inp)
            return await self._run_every_stage(inp)
        except asyncio.CancelledError:
            # Cancellation interrupts whatever we were awaiting; record it, then let it propagate.
            await self._finish(inp.run_id, RunStatus.CANCELLED)
            raise
        except TimeoutError:
            return await self._finish(inp.run_id, RunStatus.CANCELLED, "approval.expired")
        except ActivityError as error:
            cancelled = self._waits and workflow.cancellation_reason() is not None
            if cancelled or is_cancelled_exception(error):
                # Cancelled while an activity ran: Temporal reports it as an activity error. A
                # stage that failed as the cancel reached it counts as cancelled too.
                await self._finish(inp.run_id, RunStatus.CANCELLED)
                raise asyncio.CancelledError from error
            cause = error.cause
            if self._waits and isinstance(cause, ApplicationError) and cause.type == "RunClosed":
                # Closed elsewhere, or the gateway reports it ended: its status stays as it is.
                self._pending, self._closing = None, True
                return cause.message
            code = _error_code(error)
            workflow.logger.warning("run %s failed (%s): %s", inp.run_id, code, cause)
            return await self._finish(inp.run_id, RunStatus.FAILED, code)

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
        last_attempt = first_attempt + MAX_ATTEMPTS - 1
        feedback, revises = "", None
        history: list[str] = []
        for attempt in range(first_attempt, last_attempt + 1):
            start = StageStartIn(
                run_id=run_id,
                stage=stage,
                attempt=attempt,
                feedback=feedback,
                last_attempt=last_attempt,
            )
            decision = await self._run_attempt(start, history, revises, settings=settings)
            if decision.decision == Decision.APPROVE:
                return None
            if decision.decision == Decision.REJECT:
                return await self._finish(run_id, RunStatus.REJECTED)
            # The next attempt revises this output, with every comment that led to it.
            feedback, revises = decision.comment, decision.stage_output_id
            if decision.comment:
                history = [*history, decision.comment]
        # The validator refuses changes on the last attempt; histories from before it did not.
        return await self._finish(run_id, RunStatus.FAILED, "stage.too_many_attempts")

    async def _run_attempt(
        self, start: StageStartIn, history: list[str], revises: str | None, *, settings: bool
    ) -> DecisionInput:
        self._stage, self._status = start.stage, RunStatus.RUNNING.value
        started = await workflow.execute_activity(
            "start_stage",
            start,
            start_to_close_timeout=DB_STEP,
            retry_policy=DB_RETRY,
            result_type=StageStarted,
        )
        result = await self._execute(
            StageExecIn(
                run_id=start.run_id,
                stage_run_id=started.stage_run_id,
                stage=start.stage,
                attempt=start.attempt,
                feedback=start.feedback,
                apply_project_settings=settings,
                revises_output_id=revises,
                feedback_history=history,
            )
        )
        automatic = (
            settings and result.auto_approve and Stage(start.stage) not in NEVER_AUTO_APPROVE
        )
        if automatic:
            decision = DecisionInput(
                stage=start.stage,
                stage_output_id=result.stage_output_id,
                sha256=result.sha256,
                decision=Decision.APPROVE.value,
                actor_id=AUTO_APPROVE_ACTOR,
            )
        else:
            expiry = APPROVAL_TIMEOUT
            if settings and result.approval_expiry_days:
                expiry = timedelta(days=max(1, result.approval_expiry_days))
            decision = await self._wait_for_decision(start, result, expires_after=expiry)
        record = workflow.start_activity(
            "record_decision",
            DecisionRecordIn(
                run_id=start.run_id,
                stage_run_id=started.stage_run_id,
                decision=decision,
                automatic=automatic,
            ),
            start_to_close_timeout=DB_STEP,
            retry_policy=DB_RETRY,
        )
        if not self._waits:
            await record
            return decision
        try:
            await asyncio.shield(record)
        except asyncio.CancelledError:
            # A cancel that came with the decision: the reviewer was told it was accepted, so
            # it is recorded before the run closes.
            await record
            raise
        return decision

    async def _execute(self, inp: StageExecIn) -> StageResult:
        """Run the stage attempt until it has an output.

        Under STAGE_WAITS_PATCH a rate limit or an exhausted lab balance waits on a timer and
        runs the same attempt again, and a cancel waits until the running stage has stopped.
        """
        if not self._waits:
            return await workflow.execute_activity(
                "execute_stage",
                inp,
                start_to_close_timeout=_stage_timeout(inp.stage),
                heartbeat_timeout=STAGE_HEARTBEAT,
                retry_policy=LEGACY_STAGE_RETRY,
                result_type=StageResult,
            )
        rate_limited = paused = timedelta(0)
        checks = 0  # tries of the gateway since the run paused
        while True:
            try:
                result = await workflow.execute_activity(
                    "execute_stage",
                    inp,
                    start_to_close_timeout=_stage_timeout(inp.stage),
                    heartbeat_timeout=STAGE_HEARTBEAT,
                    retry_policy=STAGE_RETRY,
                    # finish_run must not race a stage that is still writing.
                    cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
                    result_type=StageResult,
                )
            except ActivityError as error:
                cause = error.cause
                if workflow.cancellation_reason() is not None or not isinstance(
                    cause, ApplicationError
                ):
                    raise
                if cause.type == "RateLimited" and rate_limited < MAX_STAGE_WAIT:
                    delay = cause.next_retry_delay or DEFAULT_RETRY_AFTER
                    rate_limited += delay
                    checks = 0  # past the balance check: a pause is over (stage_waiting)
                    self._status = RunStatus.RUNNING.value
                    await self._wait(inp, cause.message, delay)
                elif cause.type == "LabBalanceExhausted" and paused < MAX_STAGE_WAIT:
                    delay = min(BUDGET_RECHECK * 2**checks, MAX_BUDGET_RECHECK)
                    checks += 1
                    paused += delay
                    await self._pause(inp, delay)
                else:
                    raise
            else:
                if workflow.cancellation_reason() is not None:
                    # The stage finished as the cancel arrived; the run is cancelled all the same.
                    raise asyncio.CancelledError
                self._status = RunStatus.RUNNING.value  # execute_stage ended a pause, if any
                return result

    async def _wait(
        self, inp: StageExecIn, reason: str, delay: timedelta, *, pause: bool = False
    ) -> None:
        """Record why and until when the attempt waits, then sleep on a durable timer."""
        retry_at = workflow.now() + delay
        await workflow.execute_activity(
            "stage_waiting",
            StageWaitIn(
                run_id=inp.run_id,
                stage=inp.stage,
                attempt=inp.attempt,
                reason=reason,
                retry_at=retry_at.isoformat(),
                pause=pause,
            ),
            start_to_close_timeout=DB_STEP,
            retry_policy=DB_RETRY,
        )
        await workflow.sleep(delay, summary=reason)

    async def _pause(self, inp: StageExecIn, delay: timedelta) -> None:
        """The lab's balance is exhausted: the run stays paused_budget through the tries that
        fail the same way, and execute_stage (or a wait for something else) resumes it once a
        try gets past the balance. A try that fails again only says when the next one is."""
        self._status = RunStatus.PAUSED_BUDGET.value
        await self._wait(inp, "lab_balance.exhausted", delay, pause=True)

    async def _wait_for_decision(
        self, start: StageStartIn, result: StageResult, *, expires_after: timedelta
    ) -> DecisionInput:
        """Wait for a reviewer; TimeoutError (the run is cancelled) after ``expires_after``."""
        self._decision = None
        self._pending = PendingDecision(
            stage=start.stage,
            stage_output_id=result.stage_output_id,
            sha256=result.sha256,
            attempt=start.attempt,
            last_attempt=start.last_attempt,
        )
        self._status = RunStatus.AWAITING_APPROVAL.value
        await workflow.wait_condition(lambda: self._decision is not None, timeout=expires_after)
        decision = self._decision
        if decision is None:  # unreachable: wait_condition returned because it was set
            raise ApplicationError("decision.missing", non_retryable=True)
        self._pending = None
        return decision

    async def _finish(self, run_id: str, status: RunStatus, error: str | None = None) -> str:
        # From here on no decision is taken: it would be accepted, then never recorded.
        self._status, self._pending, self._closing = status.value, None, True
        await workflow.execute_activity(
            "finish_run",
            FinishIn(run_id=run_id, status=status.value, error=error),
            start_to_close_timeout=DB_STEP,
            retry_policy=FINISH_RETRY,
        )
        return status.value

    @workflow.update(name=DECIDE_UPDATE)
    async def decide(self, decision: DecisionInput) -> None:
        self._decision = decision

    @decide.validator
    def _validate_decide(self, decision: DecisionInput) -> None:
        """Runs before anything is recorded: a rejected Update leaves no trace in history."""
        pending = self._pending
        # A cancel delivered in this workflow task has not reached the run coroutine yet.
        closing = self._closing or workflow.cancellation_reason() is not None
        if closing or pending is None or self._decision is not None:
            raise ValueError("decision.not_awaited")
        if (decision.stage, decision.stage_output_id, decision.sha256) != (
            pending.stage,
            pending.stage_output_id,
            pending.sha256,
        ):
            raise ValueError("decision.stale")
        if decision.decision not in DECISIONS:
            raise ValueError("decision.invalid")
        if (
            decision.decision == Decision.REQUEST_CHANGES.value
            and pending.last_attempt is not None
            and pending.attempt >= pending.last_attempt
        ):
            raise ValueError("decision.no_attempts_left")
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

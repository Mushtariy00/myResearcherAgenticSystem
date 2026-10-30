"""Stage activities: every database change and run event happens here, never in workflow code.

An activity that changes a run or its stages locks the run row first and leaves a run with a
final status alone: a cancel can close the run while an older activity is still running.
"""

import asyncio
import contextlib
import logging
import uuid
from collections.abc import AsyncIterator, Callable, Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio import activity
from temporalio.exceptions import ApplicationError

from agentic_core.contracts import DecisionInput, EventType, events_channel
from agentic_core.enums import Decision, RunStatus, StageStatus
from agentic_core.schemas import RunConfig, validate_stage_output
from agentic_core.stages import NEVER_AUTO_APPROVE, STAGE_ORDER, Stage
from agentic_db import append_event
from agentic_db.models import Approval, Project, Run, RunEvent, StageOutput, StageRun
from agentic_worker import events
from agentic_worker.gateway_llm import (
    FreeModelsDisabledError,
    GatewayRateLimitedError,
    GatewayUnavailableError,
    LabBalanceExhaustedError,
    RunInactiveError,
)
from agentic_worker.outputs import content_sha256
from agentic_worker.stages import LogEvent, StageContext, StageFailedError, StageRunner
from agentic_worker.types import (
    DecisionRecordIn,
    FinishIn,
    RunPlan,
    RunPrepareIn,
    RunResumeIn,
    StageExecIn,
    StageResult,
    StageStarted,
    StageStartIn,
    StageWaitIn,
)

log = logging.getLogger(__name__)
HEARTBEAT_SECONDS = 10.0
WAKE_TIMEOUT_SECONDS = 2.0  # a wake-up only saves SSE a poll; a stuck Valkey must not stall us
_DECISION_STATUS = {
    Decision.APPROVE: StageStatus.APPROVED,
    Decision.REQUEST_CHANGES: StageStatus.CHANGES_REQUESTED,
    Decision.REJECT: StageStatus.REJECTED,
}
# A per-run knob next to the RunConfig keys in runs.config; not a wizard option.
DEMO_STAGE_SECONDS_KEY = "demo_stage_seconds"

__all__ = ["HEARTBEAT_SECONDS", "StageActivities", "content_sha256", "heartbeating"]


def _require[T](value: T | None, what: str) -> T:
    if value is None:
        raise ApplicationError(f"{what}.not_found", type="NotFound", non_retryable=True)
    return value


def _run_closed() -> ApplicationError:
    return ApplicationError("run.closed", type="RunClosed", non_retryable=True)


async def _lock_open_run(session: AsyncSession, run_id: uuid.UUID) -> Run:
    """The run, locked until commit; a run with a final status is never changed again."""
    run = _require(await session.get(Run, run_id, with_for_update=True), "run")
    if run.status.is_terminal:
        raise _run_closed()
    return run


async def _append_calls(
    session: AsyncSession, run_id: uuid.UUID, stage: str, calls: Sequence[Mapping[str, Any]]
) -> None:
    """One llm.call event per gateway call. A retried attempt replays its earlier calls under
    the same idempotency keys; those are recorded already."""
    keys = [call["idempotency_key"] for call in calls if call.get("idempotency_key")]
    recorded: set[str] = set()
    if keys:
        payloads = await session.scalars(
            select(RunEvent.payload).where(
                RunEvent.run_id == run_id,
                RunEvent.type == EventType.LLM_CALL,
                or_(*(RunEvent.payload.contains({"idempotency_key": key}) for key in keys)),
            )
        )
        recorded = {payload["idempotency_key"] for payload in payloads}
    for call in calls:
        key = call.get("idempotency_key")
        if key in recorded:
            continue
        if key:
            recorded.add(key)
        await append_event(session, run_id, *events.llm_call(stage, call))


@contextlib.contextmanager
def _stage_errors() -> Iterator[None]:
    """Stage and gateway exceptions as the activity errors the workflow acts on."""
    try:
        yield
    except GatewayRateLimitedError as exc:
        # The workflow waits on a timer and runs the attempt again. Runs started before it did
        # (STAGE_WAITS_PATCH) leave the wait to Temporal's retry, after Retry-After.
        raise ApplicationError(
            exc.reason, type="RateLimited", next_retry_delay=timedelta(seconds=exc.retry_after)
        ) from exc
    except LabBalanceExhaustedError as exc:
        raise ApplicationError(
            "lab_balance.exhausted", type="LabBalanceExhausted", non_retryable=True
        ) from exc
    except FreeModelsDisabledError as exc:
        raise ApplicationError(
            "free_models.disabled", type="FreeModelsDisabled", non_retryable=True
        ) from exc
    except RunInactiveError as exc:
        raise ApplicationError("run.inactive", type="RunClosed", non_retryable=True) from exc
    except GatewayUnavailableError as exc:
        raise ApplicationError("gateway.error", type="GatewayError") from exc
    except StageFailedError as exc:
        raise ApplicationError(str(exc), type="StageFailed", non_retryable=True) from exc


def run_config(stored: dict[str, Any]) -> RunConfig:
    """Validate the RunConfig keys of ``runs.config``; other keys are internal knobs."""
    known = {key: value for key, value in stored.items() if key in RunConfig.model_fields}
    try:
        return RunConfig.model_validate(known)
    except ValidationError as exc:
        log.warning("invalid run config %s: %s", known, exc)
        raise ApplicationError(
            "run.invalid_config", type="InvalidConfig", non_retryable=True
        ) from None


def demo_stage_seconds(stored: dict[str, Any]) -> float | None:
    """The run's override of the simulated stage duration, if it set a sensible one."""
    value = stored.get(DEMO_STAGE_SECONDS_KEY)
    if isinstance(value, int | float) and not isinstance(value, bool) and value >= 0:
        return float(value)
    return None


async def approved_outputs(
    session: AsyncSession, run_id: uuid.UUID, stage: str
) -> dict[str, dict[str, Any]]:
    """The approved output (an edited version when there is one) of each stage before ``stage``.

    Stage runs invalidated by a retry are no longer ``approved``, so they drop out here.
    """
    earlier = [s.value for s in STAGE_ORDER[: STAGE_ORDER.index(Stage(stage))]]
    if not earlier:
        return {}
    rows = await session.execute(
        select(StageRun.stage, StageOutput.data)
        .join(StageOutput, StageOutput.stage_run_id == StageRun.id)
        .join(Approval, Approval.stage_output_id == StageOutput.id)
        .where(
            StageRun.run_id == run_id,
            StageRun.stage.in_(earlier),
            StageRun.status == StageStatus.APPROVED,
            Approval.decision == Decision.APPROVE,
        )
        .order_by(StageRun.attempt, StageOutput.version)
    )
    return {stage_name: data for stage_name, data in rows}  # ordered: the latest one wins


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

    def all(self) -> list[Callable[..., Any]]:
        """Every activity, for registering with a Temporal worker."""
        return [
            self.prepare_run,
            self.start_stage,
            self.execute_stage,
            self.stage_waiting,
            self.resume_run,
            self.record_decision,
            self.finish_run,
        ]

    async def _wake(self, run_id: uuid.UUID) -> None:
        try:
            await asyncio.wait_for(
                self._valkey.publish(events_channel(run_id), "1"), WAKE_TIMEOUT_SECONDS
            )
        except Exception:  # SSE falls back to polling; never fail or stall a stage over a wake-up
            log.warning("could not publish wake-up for run %s", run_id)

    @activity.defn(name="prepare_run")
    async def prepare_run(self, inp: RunPrepareIn) -> RunPlan:
        """Plan this execution: the configured stages, and for a retry the stage to restart at.

        A retry keeps the approved outputs before the restart stage, invalidates approved or
        waiting outputs from it on, and continues each stage's attempt numbering. The API marks
        the run running before it starts a retry, so a closed run here was cancelled meanwhile.
        """
        run_id = uuid.UUID(inp.run_id)
        async with self._sessions() as session:
            run = await _lock_open_run(session, run_id)
            stages = [stage.value for stage in run_config(run.config).stages]
            attempts = await session.execute(
                select(StageRun.stage, func.max(StageRun.attempt))
                .where(StageRun.run_id == run_id)
                .group_by(StageRun.stage)
            )
            latest: dict[str, int] = {stage: attempt for stage, attempt in attempts}
            first_attempts = {stage: latest.get(stage, 0) + 1 for stage in stages}
            if inp.start_stage is None:
                return RunPlan(stages=stages, first_attempts=first_attempts)
            if inp.start_stage not in stages:
                raise ApplicationError(
                    "retry.invalid_stage", type="InvalidRetry", non_retryable=True
                )
            approved = set(
                await session.scalars(
                    select(StageRun.stage).where(
                        StageRun.run_id == run_id, StageRun.status == StageStatus.APPROVED
                    )
                )
            )
            before = stages[: stages.index(inp.start_stage)]
            # Restart earlier when a stage before the requested one has nothing approved.
            start = next((stage for stage in before if stage not in approved), inp.start_stage)
            execution_id = _require(activity.info().workflow_run_id, "workflow_run")
            recorded = await session.scalar(
                select(RunEvent.seq).where(
                    RunEvent.run_id == run_id,
                    RunEvent.type == EventType.RUN_RETRIED,
                    RunEvent.payload.contains({"execution_id": execution_id}),
                )
            )
            if recorded is None:  # not an activity retry after the commit below
                await self._restart_from(session, run, start)
                await append_event(
                    session, run_id, *events.run_retried(start, inp.start_stage, execution_id)
                )
                await session.commit()
                await self._wake(run_id)
        return RunPlan(stages=stages[stages.index(start) :], first_attempts=first_attempts)

    async def _restart_from(self, session: AsyncSession, run: Run, start: str) -> None:
        """Invalidate the outputs of ``start`` and later stages, and mark the run running."""
        later = [stage.value for stage in STAGE_ORDER[STAGE_ORDER.index(Stage(start)) :]]
        stale = await session.scalars(
            select(StageRun)
            .where(
                StageRun.run_id == run.id,
                StageRun.stage.in_(later),
                StageRun.status.in_([StageStatus.APPROVED, StageStatus.OUTPUT_READY]),
            )
            .order_by(StageRun.started_at, StageRun.attempt)
        )
        for stage_run in stale:
            stage_run.status = StageStatus.INVALIDATED
            stage_run.finished_at = stage_run.finished_at or datetime.now(UTC)
            await append_event(
                session,
                run.id,
                *events.stage_invalidated(
                    stage_run.stage, stage_run.attempt, str(stage_run.id), start
                ),
            )
        # Running again; start_stage reports the status change with the first stage.
        run.status = RunStatus.RUNNING
        run.error = None

    @activity.defn(name="start_stage")
    async def start_stage(self, inp: StageStartIn) -> StageStarted:
        run_id = uuid.UUID(inp.run_id)
        async with self._sessions() as session:
            run = await _lock_open_run(session, run_id)
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
                last_attempt=inp.last_attempt,
                started_at=datetime.now(UTC),
            )
            session.add(stage_run)
            run.status = RunStatus.RUNNING
            await session.flush()
            await append_event(session, run_id, *events.stage_started(inp.stage, inp.attempt))
            await append_event(session, run_id, *events.run_status(RunStatus.RUNNING))
            await session.commit()
        await self._wake(run_id)
        return StageStarted(stage_run_id=str(stage_run.id))

    def _logger(self, run_id: uuid.UUID, stage: str) -> LogEvent:
        async def write(code: str, params: dict[str, Any], message: str) -> None:
            async with self._sessions() as session:
                run = await session.get(Run, run_id, with_for_update=True)
                if run is None or run.status.is_terminal:
                    return  # cancelled meanwhile: the stage stops at its next heartbeat
                await append_event(session, run_id, *events.log(stage, code, params, message))
                await session.commit()
            await self._wake(run_id)

        return write

    @activity.defn(name="execute_stage")
    async def execute_stage(self, inp: StageExecIn) -> StageResult:
        run_id, stage_run_id = uuid.UUID(inp.run_id), uuid.UUID(inp.stage_run_id)
        async with self._sessions() as session:
            run = _require(await session.get(Run, run_id), "run")
            if run.status.is_terminal:  # left over from a cancelled run: don't spend on it
                raise _run_closed()
            project = _require(await session.get(Project, run.project_id), "project")
            # Read when the output is ready, so a changed setting applies to the next stage.
            auto_approve = (
                inp.apply_project_settings
                and project.auto_approve
                and Stage(inp.stage) not in NEVER_AUTO_APPROVE
            )
            expiry_days = project.approval_expiry_days if inp.apply_project_settings else None
            existing = await session.scalar(
                select(StageOutput)
                .where(StageOutput.stage_run_id == stage_run_id)
                .order_by(StageOutput.version)
                .limit(1)
            )
            if existing is not None:  # activity retry after the output was committed
                return StageResult(
                    stage_output_id=str(existing.id),
                    sha256=existing.sha256,
                    degraded=existing.degraded,
                    auto_approve=auto_approve,
                    approval_expiry_days=expiry_days,
                )
            revised = None
            if inp.revises_output_id is not None:
                revised = await session.get(StageOutput, uuid.UUID(inp.revises_output_id))
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
                config=run_config(run.config),
                inputs=await approved_outputs(session, run_id, inp.stage),
                demo_stage_seconds=demo_stage_seconds(run.config),
                log=self._logger(run_id, inp.stage),
                previous_output=revised.data if revised is not None else None,
                # Scheduled before the workflow sent the history: the latest comment only.
                feedback_history=tuple(inp.feedback_history)
                or ((inp.feedback,) if inp.feedback else ()),
            )
        try:
            with _stage_errors():
                async with heartbeating():
                    outcome = await self._runner.run(ctx)
        except BaseException:  # cancelled too
            ctx.cancelled.set()  # a CrewAI thread can outlive this attempt; it calls no more
            await self._record_calls(run_id, inp.stage, ctx.llm_calls)
            raise

        sha = content_sha256(outcome.data)
        async with self._sessions() as session:
            # Closed while the stage ran, e.g. cancelled in a run started before the workflow
            # waited for a cancelled stage to stop (STAGE_WAITS_PATCH).
            run = await _lock_open_run(session, run_id)
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
            stage_run.status = StageStatus.OUTPUT_READY
            if not auto_approve:  # an automatic approval follows at once; the run keeps running
                run.status = RunStatus.AWAITING_APPROVAL
            await session.flush()
            await _append_calls(session, run_id, inp.stage, outcome.llm_calls)
            await append_event(
                session,
                run_id,
                *events.stage_output_ready(inp.stage, inp.attempt, str(output.id), output.degraded),
            )
            if not auto_approve:
                await append_event(session, run_id, *events.run_status(RunStatus.AWAITING_APPROVAL))
            await session.commit()
        await self._wake(run_id)
        return StageResult(
            stage_output_id=str(output.id),
            sha256=sha,
            degraded=outcome.degraded,
            auto_approve=auto_approve,
            approval_expiry_days=expiry_days,
        )

    async def _record_calls(
        self, run_id: uuid.UUID, stage: str, calls: Sequence[Mapping[str, Any]]
    ) -> None:
        """llm.call events for an attempt that ends without an output: it still paid for them."""
        if not calls:
            return
        try:
            async with self._sessions() as session:
                run = await session.get(Run, run_id, with_for_update=True)
                if run is None or run.status.is_terminal:
                    return
                # A copy: the CrewAI thread of a cancelled attempt may still be adding to it.
                await _append_calls(session, run_id, stage, list(calls))
                await session.commit()
        except Exception:  # the gateway's journal has them too; the attempt's own error matters
            log.warning("run %s: could not record the %s calls", run_id, stage, exc_info=True)
            return
        await self._wake(run_id)

    @activity.defn(name="stage_waiting")
    async def stage_waiting(self, inp: StageWaitIn) -> None:
        """The attempt waits until ``retry_at``; for an exhausted lab balance the run pauses."""
        run_id = uuid.UUID(inp.run_id)
        waiting = events.stage_waiting(inp.stage, inp.attempt, inp.reason, inp.retry_at)
        async with self._sessions() as session:
            run = await _lock_open_run(session, run_id)
            recorded = await session.scalar(
                select(RunEvent.seq).where(
                    RunEvent.run_id == run_id,
                    RunEvent.type == EventType.STAGE_WAITING,
                    RunEvent.payload.contains(waiting[1]),
                )
            )
            if recorded is not None:
                return  # activity retry after the commit below
            if inp.pause and run.status != RunStatus.PAUSED_BUDGET:
                run.status, run.error = RunStatus.PAUSED_BUDGET, inp.reason
                await append_event(
                    session, run_id, *events.run_finished(RunStatus.PAUSED_BUDGET, inp.reason)
                )
            await append_event(session, run_id, *waiting)
            await session.commit()
        await self._wake(run_id)

    @activity.defn(name="resume_run")
    async def resume_run(self, inp: RunResumeIn) -> None:
        """A paused run is running again while its stage retries the gateway."""
        run_id = uuid.UUID(inp.run_id)
        async with self._sessions() as session:
            run = await _lock_open_run(session, run_id)
            if run.status != RunStatus.PAUSED_BUDGET:
                return  # activity retry after the commit below
            run.status, run.error = RunStatus.RUNNING, None
            await append_event(session, run_id, *events.run_status(RunStatus.RUNNING))
            await session.commit()
        await self._wake(run_id)

    @activity.defn(name="record_decision")
    async def record_decision(self, inp: DecisionRecordIn) -> None:
        run_id, decision = uuid.UUID(inp.run_id), inp.decision
        stage_run_id = uuid.UUID(inp.stage_run_id)
        async with self._sessions() as session:
            run = await _lock_open_run(session, run_id)
            decided = await session.scalar(
                select(Approval.id)
                .join(StageOutput, StageOutput.id == Approval.stage_output_id)
                .where(StageOutput.stage_run_id == stage_run_id)
            )
            if decided is not None:
                return  # activity retry after the commit below (one decision per attempt)
            stage_run = _require(await session.get(StageRun, stage_run_id), "stage_run")
            reviewed = _require(
                await session.get(StageOutput, uuid.UUID(decision.stage_output_id)),
                "stage_output",
            )
            edited = None
            if decision.edited_data is not None:
                edited = await self._edited_version(
                    session, stage_run, reviewed, decision, decision.edited_data
                )
            approved = edited or reviewed
            session.add(
                Approval(
                    stage_output_id=approved.id,
                    # The content decided on: the reviewer's own version when they edited it.
                    sha256=approved.sha256 if edited else decision.sha256,
                    decision=Decision(decision.decision),
                    comment=decision.comment,
                    actor_id=decision.actor_id,
                )
            )
            stage_run.status = _DECISION_STATUS[Decision(decision.decision)]
            stage_run.finished_at = datetime.now(UTC)
            if decision.decision != Decision.REJECT:
                run.status = RunStatus.RUNNING
            await append_event(
                session,
                run_id,
                *events.stage_decided(
                    stage=decision.stage,
                    decision=decision.decision,
                    actor_id=decision.actor_id,
                    comment=decision.comment,
                    attempt=stage_run.attempt,
                    stage_output_id=str(approved.id),
                    version=approved.version,
                    edited=edited is not None,
                    automatic=inp.automatic,
                ),
            )
            await session.commit()
        await self._wake(run_id)

    @staticmethod
    async def _edited_version(
        session: AsyncSession,
        stage_run: StageRun,
        reviewed: StageOutput,
        decision: DecisionInput,
        edited_data: dict[str, Any],
    ) -> StageOutput | None:
        """Store an approve-with-edits as the next output version (None if nothing changed)."""
        if decision.decision != Decision.APPROVE:  # the workflow validator already refuses it
            raise ApplicationError("decision.invalid", type="InvalidDecision", non_retryable=True)
        try:
            data = validate_stage_output(stage_run.stage, edited_data).model_dump(mode="json")
        except ValidationError as exc:
            raise ApplicationError(
                "decision.invalid_edit", type="InvalidDecision", non_retryable=True
            ) from exc
        sha = content_sha256(data)
        if sha == reviewed.sha256:
            return None  # an "edit" without changes is a plain approval of what was reviewed
        latest = await session.scalar(
            select(func.max(StageOutput.version)).where(StageOutput.stage_run_id == stage_run.id)
        )
        output = StageOutput(
            stage_run_id=stage_run.id,
            version=(latest or reviewed.version) + 1,
            data=data,
            sha256=sha,
            schema_version=reviewed.schema_version,
            prompt_version=reviewed.prompt_version,
            model=reviewed.model,
            degraded=False,  # a reviewer wrote this version
            degraded_reason=None,
            edited_by=decision.actor_id,
        )
        session.add(output)
        await session.flush()
        return output

    @activity.defn(name="finish_run")
    async def finish_run(self, inp: FinishIn) -> None:
        run_id, status = uuid.UUID(inp.run_id), RunStatus(inp.status)
        async with self._sessions() as session:
            run = _require(await session.get(Run, run_id, with_for_update=True), "run")
            if run.status.is_terminal:
                return  # activity retry, or closed elsewhere: a final status is never replaced
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
                    stage_run.error = inp.error
                    stage_run.finished_at = datetime.now(UTC)
                    if status == RunStatus.CANCELLED:
                        stage_run.status = StageStatus.CANCELLED
                        continue
                    stage_run.status = StageStatus.FAILED
                    await append_event(
                        session,
                        run_id,
                        *events.stage_failed(stage_run.stage, stage_run.attempt, inp.error),
                    )
            await append_event(session, run_id, *events.run_finished(status, inp.error))
            await session.commit()
        await self._wake(run_id)

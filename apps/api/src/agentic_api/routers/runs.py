import json
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import ValidationError
from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_api.auth import CurrentUser, current_user
from agentic_api.authz import EDITORS, can_steer, get_db, load_project, load_run, require_role
from agentic_api.errors import ErrorWithFields
from agentic_api.notifications import run_finished_key
from agentic_api.orchestrator import (
    DecisionRejectedError,
    Orchestrator,
    WorkflowNotFoundError,
    WorkflowStillRunningError,
)
from agentic_api.schemas import (
    Accepted,
    ApprovalOut,
    DecisionIn,
    OutputVersionOut,
    RecentRunOut,
    RunCreate,
    RunDetail,
    RunOut,
    StageAttemptOut,
    StageDetail,
    StageOutputOut,
    StageRunOut,
    stored_run_config,
)
from agentic_api.users import AuthUser, users_by_id
from agentic_core.contracts import DecisionInput, EventType
from agentic_core.enums import Decision, RunStatus, StageStatus
from agentic_core.schemas import validate_stage_output
from agentic_core.stages import Stage
from agentic_db import append_event
from agentic_db.models import (
    Approval,
    AuditLog,
    NotificationRead,
    Project,
    ProjectMember,
    Run,
    StageOutput,
    StageRun,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["runs"])
User = Annotated[CurrentUser, Depends(current_user)]
Db = Annotated[AsyncSession, Depends(get_db)]
STAGE_NAMES = frozenset(stage.value for stage in Stage)
RETRYABLE = frozenset(
    {RunStatus.FAILED, RunStatus.REJECTED, RunStatus.CANCELLED, RunStatus.COMPLETED}
)
OPEN_STAGE_STATUSES = (StageStatus.PENDING, StageStatus.RUNNING, StageStatus.OUTPUT_READY)
# Edits reach the workflow inside a Temporal Update; stay well below its 2 MB payload limit.
MAX_EDIT_BYTES = 1_000_000
_PLAIN_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def _orchestrator(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


Orch = Annotated[Orchestrator, Depends(_orchestrator)]


@router.post(
    "/projects/{project_id}/runs", status_code=status.HTTP_201_CREATED, operation_id="createRun"
)
async def create_run(
    project_id: uuid.UUID, body: RunCreate, user: User, db: Db, orch: Orch
) -> RunOut:
    _, role = await load_project(db, project_id, user)
    require_role(user, role, EDITORS)
    run = Run(
        project_id=project_id,
        owner_id=user.id,
        topic=body.topic,
        llm_policy=body.llm_policy,
        budget_cap_usd=body.budget_cap_usd,
        config=body.config.model_dump(mode="json"),
    )
    db.add(run)
    await db.flush()
    await append_event(
        db, run.id, EventType.RUN_CREATED, {"topic": body.topic, "owner_id": user.id}
    )
    await db.commit()  # the worker must see the row before the workflow starts

    try:
        run.workflow_id = await orch.start_run(run.id)
    except Exception:
        log.exception("could not start workflow for run %s", run.id)
        run.status = RunStatus.FAILED
        run.error = "orchestrator.unavailable"
        await append_event(
            db, run.id, EventType.RUN_STATUS, {"status": run.status, "error": run.error}
        )
        await db.commit()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "orchestrator.unavailable"
        ) from None
    await db.commit()
    await db.refresh(run)
    return RunOut.model_validate(run)


@router.get("/projects/{project_id}/runs", operation_id="listRuns")
async def list_runs(project_id: uuid.UUID, user: User, db: Db) -> list[RunOut]:
    await load_project(db, project_id, user)
    runs = await db.scalars(
        select(Run).where(Run.project_id == project_id).order_by(Run.created_at.desc()).limit(200)
    )
    return [RunOut.model_validate(run) for run in runs]


@router.get("/runs", operation_id="listRecentRuns")
async def list_recent_runs(
    user: User,
    db: Db,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    run_status: Annotated[RunStatus | None, Query(alias="status")] = None,
) -> list[RecentRunOut]:
    """Newest runs across the caller's projects (every project for lab admins): the dashboard."""
    query = select(Run, Project.name).join(Project, Project.id == Run.project_id)
    if not user.is_admin:
        query = query.join(
            ProjectMember,
            (ProjectMember.project_id == Run.project_id) & (ProjectMember.user_id == user.id),
        )
    if run_status is not None:
        query = query.where(Run.status == run_status)
    rows = await db.execute(query.order_by(Run.created_at.desc(), Run.id.desc()).limit(limit))
    return [
        RecentRunOut(**RunOut.model_validate(run).model_dump(), project_name=project_name)
        for run, project_name in rows.all()
    ]


@router.get("/runs/{run_id}", operation_id="getRun")
async def get_run(run_id: uuid.UUID, user: User, db: Db) -> RunDetail:
    run, role = await load_run(db, run_id, user)
    stage_runs = (
        await db.scalars(
            select(StageRun)
            .where(StageRun.run_id == run_id)
            .order_by(StageRun.started_at, StageRun.attempt)
        )
    ).all()
    outputs = (
        await db.scalars(
            select(StageOutput)
            .where(StageOutput.stage_run_id.in_([s.id for s in stage_runs]))
            .order_by(StageOutput.version)
        )
    ).all()
    by_stage_run: dict[uuid.UUID, list[StageOutput]] = {}
    for output in outputs:
        by_stage_run.setdefault(output.stage_run_id, []).append(output)

    stages = []
    awaiting: StageOutputOut | None = None
    awaiting_stage: str | None = None
    for stage_run in stage_runs:
        stage_outputs = [
            StageOutputOut.model_validate(o) for o in by_stage_run.get(stage_run.id, [])
        ]
        stages.append(
            StageRunOut.model_validate(stage_run).model_copy(update={"outputs": stage_outputs})
        )
        if stage_run.status == StageStatus.OUTPUT_READY and stage_outputs:
            awaiting, awaiting_stage = stage_outputs[-1], stage_run.stage

    return RunDetail(
        **RunOut.model_validate(run).model_dump(),
        stages=stages,
        awaiting=awaiting,
        awaiting_stage=awaiting_stage,
        can_steer=can_steer(user, role, run),
    )


def _normalized_output(stage: str, data: dict[str, Any]) -> dict[str, Any] | None:
    """``data`` as the stage's strict output schema normalizes it, or None when it fails."""
    try:
        return validate_stage_output(stage, data).model_dump(mode="json")
    except ValueError:  # a pydantic ValidationError, or a stage name without a schema
        return None


def _version_out(
    stage: str, output: StageOutput, approval: Approval | None, users: dict[str, AuthUser]
) -> OutputVersionOut:
    editor = users.get(output.edited_by) if output.edited_by else None
    actor = users.get(approval.actor_id) if approval else None
    return OutputVersionOut(
        id=output.id,
        version=output.version,
        sha256=output.sha256,
        data=output.data,
        degraded=output.degraded,
        degraded_reason=output.degraded_reason,
        model=output.model,
        prompt_version=output.prompt_version,
        edited_by=output.edited_by,
        edited_by_name=editor.name if editor else None,
        created_at=output.created_at,
        schema_ok=_normalized_output(stage, output.data) is not None,
        approval=ApprovalOut(
            decision=approval.decision,
            comment=approval.comment,
            actor_id=approval.actor_id,
            actor_name=actor.name if actor else None,
            at=approval.created_at,
        )
        if approval
        else None,
    )


@router.get("/runs/{run_id}/stages/{stage}", operation_id="getStage")
async def get_stage(run_id: uuid.UUID, stage: str, user: User, db: Db) -> StageDetail:
    """Every attempt of one stage, with each attempt's output versions and their decisions."""
    await load_run(db, run_id, user)
    if stage not in STAGE_NAMES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stage.not_found")
    attempts = (
        await db.scalars(
            select(StageRun)
            .where(StageRun.run_id == run_id, StageRun.stage == stage)
            .order_by(StageRun.attempt)
        )
    ).all()
    outputs = (
        await db.scalars(
            select(StageOutput)
            .where(StageOutput.stage_run_id.in_([a.id for a in attempts]))
            .order_by(StageOutput.version)
        )
    ).all()
    approvals = {
        approval.stage_output_id: approval
        for approval in await db.scalars(
            select(Approval).where(Approval.stage_output_id.in_([o.id for o in outputs]))
        )
    }
    users = await users_by_id(
        db,
        [o.edited_by for o in outputs if o.edited_by] + [a.actor_id for a in approvals.values()],
    )
    by_attempt: dict[uuid.UUID, list[OutputVersionOut]] = {}
    for output in outputs:
        by_attempt.setdefault(output.stage_run_id, []).append(
            _version_out(stage, output, approvals.get(output.id), users)
        )
    return StageDetail(
        run_id=run_id,
        stage=stage,
        attempts=[
            StageAttemptOut(
                id=attempt.id,
                attempt=attempt.attempt,
                status=attempt.status,
                feedback=attempt.feedback,
                error=attempt.error,
                started_at=attempt.started_at,
                finished_at=attempt.finished_at,
                outputs=by_attempt.get(attempt.id, []),
            )
            for attempt in attempts
        ],
    )


def _error_location(loc: tuple[int | str, ...]) -> list[int | str]:
    """A validation error's path, for the client: list indexes and plain field names only.
    Anything else (such as an odd key the client sent) is masked, never echoed back."""
    return [part if isinstance(part, int) or _PLAIN_NAME.match(part) else "*" for part in loc[:16]]


def _checked_edit(
    stage: str, edited: dict[str, Any], current: dict[str, Any]
) -> dict[str, Any] | None:
    """The reviewer's corrected output as the stage schema normalizes it, or None when it says
    the same as the version under review (then the decision is a plain approval)."""
    if len(json.dumps(edited, ensure_ascii=False).encode()) > MAX_EDIT_BYTES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "decision.edit_too_large")
    try:
        normalized = validate_stage_output(stage, edited).model_dump(mode="json")
    except ValidationError as exc:
        errors = exc.errors(include_url=False, include_context=False, include_input=False)
        first = errors[0] if errors else None
        raise ErrorWithFields(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "decision.invalid_edit",
            loc=_error_location(first["loc"]) if first else [],
            type=first["type"] if first else "value_error",
        ) from None
    except ValueError:  # the stage run names a stage without an output schema
        raise ErrorWithFields(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "decision.invalid_edit",
            loc=[],
            type="unknown_stage",
        ) from None
    return None if normalized == _normalized_output(stage, current) else normalized


@router.post(
    "/runs/{run_id}/approvals", status_code=status.HTTP_202_ACCEPTED, operation_id="decideStage"
)
async def decide_stage(
    run_id: uuid.UUID, body: DecisionIn, user: User, db: Db, orch: Orch
) -> Accepted:
    """Approve, request changes or reject the output waiting for a decision.

    Approve with edits sends ``edited_data``: it must pass the stage's output schema (422
    ``decision.invalid_edit`` with ``loc`` and ``type`` of the first error otherwise).
    """
    run, role = await load_run(db, run_id, user)
    if not can_steer(user, role, run):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "permission.denied")
    if body.edited_data is not None and body.decision != Decision.APPROVE:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "decision.edit_requires_approve")

    output = await db.get(StageOutput, body.stage_output_id)
    stage_run = await db.get(StageRun, output.stage_run_id) if output else None
    if output is None or stage_run is None or stage_run.run_id != run_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stage_output.not_found")
    if await db.scalar(select(Approval.id).where(Approval.stage_output_id == output.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "approval.duplicate")
    latest_version = await db.scalar(
        select(StageOutput.version)
        .where(StageOutput.stage_run_id == stage_run.id)
        .order_by(StageOutput.version.desc())
        .limit(1)
    )
    if (
        stage_run.status != StageStatus.OUTPUT_READY
        or output.version != latest_version
        or output.sha256 != body.sha256
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "approval.stale")
    edited_data = (
        _checked_edit(stage_run.stage, body.edited_data, output.data)
        if body.edited_data is not None
        else None
    )

    decision = DecisionInput(
        stage=stage_run.stage,
        stage_output_id=str(output.id),
        sha256=body.sha256,
        decision=body.decision.value,
        actor_id=user.id,
        comment=body.comment,
        edited_data=edited_data,
    )
    await db.commit()  # end the read transaction: don't hold a connection while Temporal works
    try:
        await orch.decide(run_id, decision)  # the workflow re-validates and records the decision
    except DecisionRejectedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "approval.rejected_by_workflow") from exc
    db.add(
        AuditLog(
            actor_id=user.id,
            action=f"stage.{body.decision.value}",
            target_type="stage_output",
            target_id=str(output.id),
            details={
                "run_id": str(run_id),
                "stage": stage_run.stage,
                "comment": body.comment,
                "edited": edited_data is not None,
            },
        )
    )
    await db.commit()
    return Accepted()


async def _restore_after_failed_retry(
    db: AsyncSession, run_id: uuid.UUID, previous: RunStatus, error: str | None
) -> None:
    """Put back the status a retry replaced, unless something has changed the run since."""
    run = await db.get(Run, run_id, with_for_update=True, populate_existing=True)
    if run is None or run.status != RunStatus.RUNNING:
        return
    run.status, run.error = previous, error
    await append_event(db, run_id, EventType.RUN_STATUS, {"status": previous, "error": error})
    await db.commit()


@router.post("/runs/{run_id}/retry", status_code=status.HTTP_202_ACCEPTED, operation_id="retryRun")
async def retry_run(
    run_id: uuid.UUID,
    stage: Annotated[str, Query(min_length=1, max_length=32)],
    user: User,
    db: Db,
    orch: Orch,
) -> Accepted:
    """Run a finished run again from ``stage``, in a new execution of its workflow.

    The workflow keeps the approved outputs of the stages before ``stage`` and invalidates the
    outputs from ``stage`` on.
    """
    run, role = await load_run(db, run_id, user)
    if not can_steer(user, role, run):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "permission.denied")
    # Lock the row: of two concurrent retries, the second must see the first one's "running".
    await db.refresh(run, with_for_update=True)
    if run.status not in RETRYABLE:
        raise HTTPException(status.HTTP_409_CONFLICT, "run.not_retryable")
    reached = await db.scalar(
        select(exists().where(StageRun.run_id == run_id, StageRun.stage == stage))
    )
    if not reached or stage not in stored_run_config(run.config).stages:
        raise HTTPException(status.HTTP_409_CONFLICT, "stage.not_reached")

    previous, previous_error = RunStatus(run.status), run.error
    run.status, run.error = RunStatus.RUNNING, None
    await append_event(
        db, run_id, EventType.RUN_STATUS, {"status": RunStatus.RUNNING, "retry_stage": stage}
    )
    await db.commit()  # the new execution must find the run running

    try:
        workflow_id = await orch.restart_run(run_id, stage)
    except WorkflowStillRunningError:
        # The previous execution is still closing (its final status is already stored).
        await _restore_after_failed_retry(db, run_id, previous, previous_error)
        raise HTTPException(status.HTTP_409_CONFLICT, "run.not_retryable") from None
    except Exception:
        log.exception("could not restart workflow for run %s", run_id)
        await _restore_after_failed_retry(db, run_id, previous, previous_error)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "orchestrator.unavailable"
        ) from None
    run.workflow_id = workflow_id
    db.add(
        AuditLog(
            actor_id=user.id,
            action="run.retry",
            target_type="run",
            target_id=str(run_id),
            details={"stage": stage, "previous_status": previous.value},
        )
    )
    # The run's next finish is news again, even to an owner who read the previous one.
    await db.execute(
        delete(NotificationRead).where(
            NotificationRead.notification_key == run_finished_key(run_id)
        )
    )
    await db.commit()
    return Accepted()


async def _cancel_without_workflow(db: AsyncSession, run_id: uuid.UUID, user: CurrentUser) -> None:
    """Cancel a run that has no workflow execution (it never started, or is a seeded demo row):
    record what the workflow would have recorded on its way out."""
    run = await db.get(Run, run_id, with_for_update=True, populate_existing=True)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run.not_found")
    if RunStatus(run.status).is_terminal:
        raise HTTPException(status.HTTP_409_CONFLICT, "run.already_finished")
    now = datetime.now(UTC)
    for stage_run in await db.scalars(
        select(StageRun).where(StageRun.run_id == run_id, StageRun.status.in_(OPEN_STAGE_STATUSES))
    ):
        stage_run.status = StageStatus.CANCELLED
        stage_run.finished_at = now
    run.status, run.error = RunStatus.CANCELLED, None
    await append_event(
        db, run_id, EventType.RUN_STATUS, {"status": RunStatus.CANCELLED, "error": None}
    )
    db.add(
        AuditLog(
            actor_id=user.id,
            action="run.cancel",
            target_type="run",
            target_id=str(run_id),
            details={"without_workflow": True},
        )
    )
    await db.commit()


@router.post(
    "/runs/{run_id}/cancel", status_code=status.HTTP_202_ACCEPTED, operation_id="cancelRun"
)
async def cancel_run(run_id: uuid.UUID, user: User, db: Db, orch: Orch) -> Accepted:
    run, role = await load_run(db, run_id, user)
    if not can_steer(user, role, run):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "permission.denied")
    if RunStatus(run.status).is_terminal:
        raise HTTPException(status.HTTP_409_CONFLICT, "run.already_finished")
    await db.commit()  # end the read transaction: don't hold a connection while Temporal works
    try:
        await orch.cancel_run(run_id)
    except WorkflowNotFoundError:
        await _cancel_without_workflow(db, run_id, user)
        return Accepted()
    except Exception:
        log.exception("could not cancel workflow for run %s", run_id)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "orchestrator.unavailable"
        ) from None
    db.add(
        AuditLog(actor_id=user.id, action="run.cancel", target_type="run", target_id=str(run_id))
    )
    await db.commit()
    return Accepted()

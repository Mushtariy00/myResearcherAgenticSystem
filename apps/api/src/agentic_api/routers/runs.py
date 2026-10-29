import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_api.auth import CurrentUser, current_user
from agentic_api.authz import EDITORS, can_steer, get_db, load_project, load_run, require_role
from agentic_api.orchestrator import DecisionRejectedError, Orchestrator
from agentic_api.schemas import (
    Accepted,
    DecisionIn,
    RunCreate,
    RunDetail,
    RunOut,
    StageOutputOut,
    StageRunOut,
)
from agentic_core.contracts import DecisionInput, EventType
from agentic_core.enums import RunStatus, StageStatus
from agentic_db import append_event
from agentic_db.models import Approval, AuditLog, Run, StageOutput, StageRun

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["runs"])
User = Annotated[CurrentUser, Depends(current_user)]
Db = Annotated[AsyncSession, Depends(get_db)]


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
        config={},
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


@router.post(
    "/runs/{run_id}/approvals", status_code=status.HTTP_202_ACCEPTED, operation_id="decideStage"
)
async def decide_stage(
    run_id: uuid.UUID, body: DecisionIn, user: User, db: Db, orch: Orch
) -> Accepted:
    run, role = await load_run(db, run_id, user)
    if not can_steer(user, role, run):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "permission.denied")

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

    decision = DecisionInput(
        stage=stage_run.stage,
        stage_output_id=str(output.id),
        sha256=body.sha256,
        decision=body.decision.value,
        actor_id=user.id,
        comment=body.comment,
    )
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
            details={"run_id": str(run_id), "stage": stage_run.stage, "comment": body.comment},
        )
    )
    await db.commit()
    return Accepted()


@router.post(
    "/runs/{run_id}/cancel", status_code=status.HTTP_202_ACCEPTED, operation_id="cancelRun"
)
async def cancel_run(run_id: uuid.UUID, user: User, db: Db, orch: Orch) -> Accepted:
    run, role = await load_run(db, run_id, user)
    if not can_steer(user, role, run):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "permission.denied")
    if RunStatus(run.status).is_terminal:
        raise HTTPException(status.HTTP_409_CONFLICT, "run.already_finished")
    await orch.cancel_run(run_id)
    db.add(
        AuditLog(actor_id=user.id, action="run.cancel", target_type="run", target_id=str(run_id))
    )
    await db.commit()
    return Accepted()

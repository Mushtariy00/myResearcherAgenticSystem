"""Registered datasets and the lab's GPU queue (both demo until the executor is built)."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_api.auth import CurrentUser, current_user
from agentic_api.authz import get_db, member_projects
from agentic_api.demo.datasets import DATASETS
from agentic_api.demo.gpu import RealJob, queue_snapshot
from agentic_api.schemas import DatasetList, GpuQueueOut, stored_run_config
from agentic_api.users import users_by_id
from agentic_core.enums import RunStatus, StageStatus
from agentic_core.stages import Stage
from agentic_db.models import Project, Run, StageRun

router = APIRouter(prefix="/api/v1", tags=["compute"])
User = Annotated[CurrentUser, Depends(current_user)]
Db = Annotated[AsyncSession, Depends(get_db)]
MAX_REAL_JOBS = 50


@router.get("/datasets", operation_id="listDatasets")
async def list_datasets(user: User) -> DatasetList:
    """Datasets experiments can mount (read-only), with their data contracts."""
    return DatasetList(items=list(DATASETS), demo=True)


@router.get("/gpu/queue", operation_id="getGpuQueue")
async def get_gpu_queue(user: User, db: Db) -> GpuQueueOut:
    """The GPU's live readings, the job on it and the jobs waiting, with the caller's place.

    Real experiment stages that are running come from the database, oldest first; runs in
    projects the caller can't open show no topic. Telemetry and the other jobs are demo data.
    """
    rows = (
        await db.execute(
            select(
                StageRun.id.label("job_id"),
                StageRun.started_at,
                Run.id.label("run_id"),
                Run.topic,
                Run.owner_id,
                Run.config,
                Project.id.label("project_id"),
                Project.name.label("project_name"),
            )
            .join(Run, Run.id == StageRun.run_id)
            .join(Project, Project.id == Run.project_id)
            .where(
                StageRun.stage == Stage.EXPERIMENT.value,
                StageRun.status == StageStatus.RUNNING,
                Run.status == RunStatus.RUNNING,
            )
            .order_by(StageRun.started_at.asc().nulls_last(), StageRun.id)
            .limit(MAX_REAL_JOBS)
        )
    ).all()
    now = datetime.now(UTC)
    visible = {project.id for project, _ in await member_projects(db, user)}
    owners = await users_by_id(db, [row.owner_id for row in rows])
    jobs = []
    for row in rows:
        shown = row.project_id in visible
        owner = owners.get(row.owner_id)
        jobs.append(
            RealJob(
                id=str(row.job_id),
                run_id=row.run_id if shown else None,
                topic=row.topic if shown else None,
                project_name=row.project_name if shown else None,
                owner_id=row.owner_id,
                owner_name=owner.name if owner else None,
                dataset=stored_run_config(row.config).dataset,
                submitted_at=row.started_at or now,
            )
        )
    return queue_snapshot(now, jobs, user.id)

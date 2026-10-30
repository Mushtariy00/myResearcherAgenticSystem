"""Registered datasets and the lab's GPU queue."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_api.auth import CurrentUser, current_user
from agentic_api.authz import get_db
from agentic_api.datasets import enabled_datasets
from agentic_api.gpu_queue import gpu_queue
from agentic_api.schemas import DatasetList, GpuQueueOut

router = APIRouter(prefix="/api/v1", tags=["compute"])
User = Annotated[CurrentUser, Depends(current_user)]
Db = Annotated[AsyncSession, Depends(get_db)]


@router.get("/datasets", operation_id="listDatasets")
async def list_datasets(user: User, db: Db) -> DatasetList:
    """Datasets experiments can mount (read-only), with their data contracts: the enabled
    registered datasets."""
    return DatasetList(items=await enabled_datasets(db), demo=False)


@router.get("/gpu/queue", operation_id="getGpuQueue")
async def get_gpu_queue(user: User, db: Db) -> GpuQueueOut:
    """The GPU's live readings, the jobs on it and the jobs waiting, with the caller's place.

    The jobs are the executor's (gpu_jobs), queued ones in the order it will run them; runs in
    projects the caller can't open show no run, topic or project. The readings come from the
    executor's heartbeat, and are null while it is not running.
    """
    return await gpu_queue(db, user)

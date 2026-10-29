"""Starts, steers and cancels run workflows. The API never imports worker code (contracts only)."""

import uuid
from typing import Protocol

from temporalio.client import Client, WorkflowUpdateFailedError
from temporalio.service import RPCError

from agentic_core.contracts import (
    DECIDE_UPDATE,
    RUN_WORKFLOW,
    TASK_QUEUE,
    DecisionInput,
    RunInput,
    workflow_id_for,
)


class DecisionRejectedError(Exception):
    """The workflow refused the decision: stale output, wrong stage, or already decided."""


class Orchestrator(Protocol):
    async def start_run(self, run_id: uuid.UUID) -> str: ...

    async def decide(self, run_id: uuid.UUID, decision: DecisionInput) -> None: ...

    async def cancel_run(self, run_id: uuid.UUID) -> None: ...


class TemporalOrchestrator:
    def __init__(self, client: Client) -> None:
        self._client = client

    async def start_run(self, run_id: uuid.UUID) -> str:
        workflow_id = workflow_id_for(str(run_id))
        await self._client.start_workflow(
            RUN_WORKFLOW, RunInput(run_id=str(run_id)), id=workflow_id, task_queue=TASK_QUEUE
        )
        return workflow_id

    async def decide(self, run_id: uuid.UUID, decision: DecisionInput) -> None:
        handle = self._client.get_workflow_handle(workflow_id_for(str(run_id)))
        try:
            await handle.execute_update(DECIDE_UPDATE, decision)
        except (WorkflowUpdateFailedError, RPCError) as exc:
            raise DecisionRejectedError(str(exc)) from exc

    async def cancel_run(self, run_id: uuid.UUID) -> None:
        await self._client.get_workflow_handle(workflow_id_for(str(run_id))).cancel()

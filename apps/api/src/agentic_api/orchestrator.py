"""Starts, steers and cancels run workflows. The API never imports worker code (contracts only)."""

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from temporalio.api.enums.v1 import TaskQueueType
from temporalio.api.taskqueue.v1 import TaskQueue
from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest, DescribeTaskQueueRequest
from temporalio.client import Client, WorkflowUpdateFailedError
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from agentic_core.contracts import (
    DECIDE_UPDATE,
    RUN_WORKFLOW,
    TASK_QUEUE,
    DecisionInput,
    RunInput,
    workflow_id_for,
)

# Health probes must answer quickly; the health endpoint also bounds each probe as a whole.
PROBE_TIMEOUT = timedelta(seconds=2)


class DecisionRejectedError(Exception):
    """The workflow refused the decision: stale output, wrong stage, or already decided."""


class WorkflowNotFoundError(Exception):
    """Temporal has no open execution for the run: it never started (or is a seeded demo row),
    or it already closed."""


class WorkflowStillRunningError(Exception):
    """A new execution can't start while the run's previous one is still open."""


@dataclass(frozen=True)
class TaskQueuePollers:
    """Workers seen polling the run task queue recently (Temporal keeps a few minutes)."""

    workflow: int
    activity: int


class Orchestrator(Protocol):
    async def start_run(self, run_id: uuid.UUID) -> str: ...

    async def restart_run(self, run_id: uuid.UUID, start_stage: str) -> str: ...

    async def decide(self, run_id: uuid.UUID, decision: DecisionInput) -> None: ...

    async def cancel_run(self, run_id: uuid.UUID) -> None: ...

    async def check_namespace(self) -> None: ...

    async def task_queue_pollers(self) -> TaskQueuePollers | None: ...


class TemporalOrchestrator:
    def __init__(self, client: Client) -> None:
        self._client = client

    async def start_run(self, run_id: uuid.UUID) -> str:
        workflow_id = workflow_id_for(str(run_id))
        await self._client.start_workflow(
            RUN_WORKFLOW, RunInput(run_id=str(run_id)), id=workflow_id, task_queue=TASK_QUEUE
        )
        return workflow_id

    async def restart_run(self, run_id: uuid.UUID, start_stage: str) -> str:
        """Start a new execution under the run's workflow id that resumes at ``start_stage``.

        The id may be reused once the previous execution has closed, whatever its outcome;
        while it is still open the start is refused (WorkflowStillRunningError).
        """
        workflow_id = workflow_id_for(str(run_id))
        try:
            await self._client.start_workflow(
                RUN_WORKFLOW,
                RunInput(run_id=str(run_id), start_stage=start_stage),
                id=workflow_id,
                task_queue=TASK_QUEUE,
                id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
                id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
            )
        except WorkflowAlreadyStartedError as exc:
            raise WorkflowStillRunningError(workflow_id) from exc
        return workflow_id

    async def decide(self, run_id: uuid.UUID, decision: DecisionInput) -> None:
        handle = self._client.get_workflow_handle(workflow_id_for(str(run_id)))
        try:
            await handle.execute_update(DECIDE_UPDATE, decision)
        except (WorkflowUpdateFailedError, RPCError) as exc:
            raise DecisionRejectedError(str(exc)) from exc

    async def cancel_run(self, run_id: uuid.UUID) -> None:
        handle = self._client.get_workflow_handle(workflow_id_for(str(run_id)))
        try:
            await handle.cancel()
        except RPCError as exc:
            if exc.status == RPCStatusCode.NOT_FOUND:
                raise WorkflowNotFoundError(handle.id) from exc
            raise

    async def check_namespace(self) -> None:
        """Raises unless the server answers for our namespace."""
        await self._client.workflow_service.describe_namespace(
            DescribeNamespaceRequest(namespace=self._client.namespace), timeout=PROBE_TIMEOUT
        )

    async def task_queue_pollers(self) -> TaskQueuePollers | None:
        """Pollers per task type, or None when the server can't describe task queues."""
        counts: list[int] = []
        for queue_type in (
            TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW,
            TaskQueueType.TASK_QUEUE_TYPE_ACTIVITY,
        ):
            try:
                response = await self._client.workflow_service.describe_task_queue(
                    DescribeTaskQueueRequest(
                        namespace=self._client.namespace,
                        task_queue=TaskQueue(name=TASK_QUEUE),
                        task_queue_type=queue_type,
                    ),
                    timeout=PROBE_TIMEOUT,
                )
            except RPCError as exc:
                if exc.status == RPCStatusCode.UNIMPLEMENTED:  # e.g. the time-skipping server
                    return None
                raise
            counts.append(len(response.pollers))
        return TaskQueuePollers(workflow=counts[0], activity=counts[1])

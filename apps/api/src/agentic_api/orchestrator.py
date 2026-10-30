"""Starts, steers and cancels run workflows. The API never imports worker code (contracts only)."""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from temporalio.api.enums.v1 import TaskQueueType
from temporalio.api.taskqueue.v1 import TaskQueue
from temporalio.api.workflowservice.v1 import DescribeNamespaceRequest, DescribeTaskQueueRequest
from temporalio.client import (
    Client,
    WorkflowUpdateFailedError,
    WorkflowUpdateRPCTimeoutOrCancelledError,
)
from temporalio.common import WorkflowIDConflictPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import ApplicationError, WorkflowAlreadyStartedError
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
# A request waits this long for Temporal. An Update needs a worker to run its validator, and
# without a deadline it waits for one forever (while a worker restarts, say).
RPC_TIMEOUT = timedelta(seconds=10)


class DecisionRejectedError(Exception):
    """The workflow's validator refused the decision. ``code`` is its reason (``decision.stale``,
    ``decision.not_awaited``, ``decision.no_attempts_left``, ...): for mapping, never for display.
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class OrchestratorUnavailableError(Exception):
    """Temporal could not be reached or did not answer in time."""


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
    def __init__(self, client: Client, *, rpc_timeout: timedelta = RPC_TIMEOUT) -> None:
        self._client = client
        self._rpc_timeout = rpc_timeout

    async def start_run(self, run_id: uuid.UUID) -> str:
        """Start the run's workflow. Starting it again while it runs changes nothing, so a start
        whose outcome is unknown (the reconciler's case) can simply be repeated."""
        workflow_id = workflow_id_for(str(run_id))
        try:
            await self._client.start_workflow(
                RUN_WORKFLOW,
                RunInput(run_id=str(run_id)),
                id=workflow_id,
                task_queue=TASK_QUEUE,
                id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
                rpc_timeout=self._rpc_timeout,
            )
        except RPCError as exc:
            raise OrchestratorUnavailableError(workflow_id) from exc
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
                rpc_timeout=self._rpc_timeout,
            )
        except WorkflowAlreadyStartedError as exc:
            raise WorkflowStillRunningError(workflow_id) from exc
        except RPCError as exc:
            raise OrchestratorUnavailableError(workflow_id) from exc
        return workflow_id

    async def decide(self, run_id: uuid.UUID, decision: DecisionInput) -> None:
        handle = self._client.get_workflow_handle(workflow_id_for(str(run_id)))
        try:
            # The SDK re-sends the Update until a worker has accepted it, each send with its own
            # rpc_timeout; only the outer deadline bounds the whole wait.
            async with asyncio.timeout(self._rpc_timeout.total_seconds()):
                await handle.execute_update(DECIDE_UPDATE, decision, rpc_timeout=self._rpc_timeout)
        except WorkflowUpdateFailedError as exc:
            cause = exc.cause
            raise DecisionRejectedError(
                cause.message if isinstance(cause, ApplicationError) else "decision.failed"
            ) from exc
        except (WorkflowUpdateRPCTimeoutOrCancelledError, TimeoutError) as exc:
            raise OrchestratorUnavailableError(handle.id) from exc
        except RPCError as exc:
            if exc.status == RPCStatusCode.NOT_FOUND:  # never started, or already closed
                raise WorkflowNotFoundError(handle.id) from exc
            raise OrchestratorUnavailableError(handle.id) from exc

    async def cancel_run(self, run_id: uuid.UUID) -> None:
        handle = self._client.get_workflow_handle(workflow_id_for(str(run_id)))
        try:
            await handle.cancel(rpc_timeout=self._rpc_timeout)
        except RPCError as exc:
            if exc.status == RPCStatusCode.NOT_FOUND:
                raise WorkflowNotFoundError(handle.id) from exc
            raise OrchestratorUnavailableError(handle.id) from exc

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

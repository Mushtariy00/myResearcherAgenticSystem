"""TemporalOrchestrator against Temporal's time-skipping test server, with a stand-in workflow
(the API never imports the worker's)."""

import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import cast

import pytest
from temporalio import workflow
from temporalio.api.enums.v1 import TaskQueueType
from temporalio.api.taskqueue.v1 import PollerInfo
from temporalio.api.workflowservice.v1 import DescribeTaskQueueRequest, DescribeTaskQueueResponse
from temporalio.client import Client, WorkflowExecutionStatus, WorkflowFailureError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from agentic_api.orchestrator import (
    TaskQueuePollers,
    TemporalOrchestrator,
    WorkflowNotFoundError,
    WorkflowStillRunningError,
)
from agentic_core.contracts import RUN_WORKFLOW, TASK_QUEUE, RunInput, workflow_id_for


@workflow.defn(name=RUN_WORKFLOW, sandboxed=False)
class StandInRunWorkflow:
    """Stays open until signalled (like a run waiting for approval), then returns its start."""

    def __init__(self) -> None:
        self._finish = False

    @workflow.run
    async def run(self, inp: RunInput) -> str:
        await workflow.wait_condition(lambda: self._finish)
        return inp.start_stage or "literature"

    @workflow.signal
    def finish(self) -> None:
        self._finish = True


@pytest.fixture
async def temporal() -> AsyncIterator[Client]:
    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(env.client, task_queue=TASK_QUEUE, workflows=[StandInRunWorkflow]),
    ):
        yield env.client


async def test_a_retry_is_a_new_execution_once_the_previous_one_closed(temporal: Client) -> None:
    orchestrator = TemporalOrchestrator(temporal)
    run_id = uuid.uuid4()
    workflow_id = await orchestrator.start_run(run_id)
    assert workflow_id == workflow_id_for(str(run_id))
    first_run = (await temporal.get_workflow_handle(workflow_id).describe()).run_id

    with pytest.raises(WorkflowStillRunningError):
        await orchestrator.restart_run(run_id, "method")
    first = temporal.get_workflow_handle(workflow_id, run_id=first_run)
    await first.signal(StandInRunWorkflow.finish)
    assert await first.result() == "literature"

    assert await orchestrator.restart_run(run_id, "method") == workflow_id
    latest = temporal.get_workflow_handle(workflow_id)  # without a run id: the newest execution
    assert (await latest.describe()).run_id != first_run
    await latest.signal(StandInRunWorkflow.finish)
    assert await latest.result() == "method"


async def test_cancel_tells_a_missing_execution_apart(temporal: Client) -> None:
    orchestrator = TemporalOrchestrator(temporal)
    with pytest.raises(WorkflowNotFoundError):
        await orchestrator.cancel_run(uuid.uuid4())

    run_id = uuid.uuid4()
    await orchestrator.start_run(run_id)
    await orchestrator.cancel_run(run_id)
    handle = temporal.get_workflow_handle(workflow_id_for(str(run_id)))
    with pytest.raises(WorkflowFailureError):  # the outcome of a cancelled workflow
        await handle.result(rpc_timeout=timedelta(seconds=10))
    assert (await handle.describe()).status == WorkflowExecutionStatus.CANCELED


async def test_namespace_probe(temporal: Client) -> None:
    orchestrator = TemporalOrchestrator(temporal)
    await orchestrator.check_namespace()
    # The time-skipping server can't describe task queues: the worker status is unknown.
    assert await orchestrator.task_queue_pollers() is None


class _StubWorkflowService:
    def __init__(self, pollers: dict[int, int]) -> None:
        self._pollers = pollers
        self.requests: list[DescribeTaskQueueRequest] = []

    async def describe_task_queue(
        self, request: DescribeTaskQueueRequest, **options: object
    ) -> DescribeTaskQueueResponse:
        self.requests.append(request)
        count = self._pollers[request.task_queue_type]
        return DescribeTaskQueueResponse(
            pollers=[PollerInfo(identity=f"worker-{i}") for i in range(count)]
        )


class _StubClient:
    namespace = "lab"

    def __init__(self, service: _StubWorkflowService) -> None:
        self.workflow_service = service


async def test_pollers_are_counted_per_task_type() -> None:
    service = _StubWorkflowService(
        {TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW: 2, TaskQueueType.TASK_QUEUE_TYPE_ACTIVITY: 0}
    )
    orchestrator = TemporalOrchestrator(cast(Client, _StubClient(service)))
    assert await orchestrator.task_queue_pollers() == TaskQueuePollers(workflow=2, activity=0)
    assert {(r.namespace, r.task_queue.name) for r in service.requests} == {("lab", TASK_QUEUE)}

"""After a restart: requeue, adopt or reap, never a second container for a job."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import update
from sqlalchemy.exc import OperationalError

from agentic_core.contracts import EventType
from agentic_core.enums import GpuJobKind, GpuJobStatus
from agentic_core.gpu_jobs import JOB_LABEL, JOB_LOST, JOB_OOM_KILLED, job_dir
from agentic_db import append_event
from agentic_db.models import GpuJob
from agentic_executor import queue
from agentic_executor.executor import write_job_files
from agentic_executor.template import container_name
from executor_testkit import (
    SIGKILL_EXIT,
    Factory,
    FakeDocker,
    Script,
    create_job,
    epoch_events,
    epoch_line,
    epoch_record,
    eventually,
    executor_settings,
    executor_status,
    get_job,
    job_config,
    make_executor,
    results_ok,
    running,
    speed_up,
    step_line,
    wait_status,
)


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    speed_up(monkeypatch)


def _labels(job_id: object) -> dict[str, str]:
    return {JOB_LABEL: str(job_id)}


async def test_a_starting_job_loses_its_leftover_container_and_is_requeued(
    db: Factory, tmp_path: Path
) -> None:
    docker = FakeDocker()
    past = datetime.now(UTC) - timedelta(minutes=5)
    job = await create_job(db, status=GpuJobStatus.STARTING, lease_until=past)
    flagged = await create_job(db, status=GpuJobStatus.STARTING, cancel_requested=True)
    leftover = await docker.run_container(container_name(job.id), _labels(job.id))
    await make_executor(db, executor_settings(tmp_path), docker).recover()

    requeued = await get_job(db, job.id)
    assert requeued.status is GpuJobStatus.QUEUED
    assert (requeued.container_id, requeued.started_at, requeued.lease_until) == (None, None, None)
    assert (await get_job(db, flagged.id)).status is GpuJobStatus.CANCELLED
    assert docker.removed == [leftover] and docker.containers == {}


async def test_a_running_job_whose_container_runs_is_adopted(db: Factory, tmp_path: Path) -> None:
    """No second container, and the epochs reported before the restart are not sent again."""
    docker = FakeDocker()
    settings = executor_settings(tmp_path)
    job = await create_job(
        db,
        kind=GpuJobKind.TRAIN,
        status=GpuJobStatus.RUNNING,
        started_at=datetime.now(UTC),
        epochs_reported=1,
    )
    write_job_files(job_dir(settings.data_dir, job.id), job.code, job.config, job.dataset)
    async with db() as session:  # what the executor that went down sent
        await append_event(session, job.run_id, EventType.EXPERIMENT_EPOCH, {"epoch": 0})
        await session.commit()
    gate = asyncio.Event()
    steps: list[Any] = [epoch_line(0), gate, epoch_line(1), "done"]
    script = Script(steps=steps, outputs={"results.json": results_ok()})
    container_id = await docker.run_container(container_name(job.id), _labels(job.id), script)
    async with db() as session:
        await session.execute(
            update(GpuJob).where(GpuJob.id == job.id).values(container_id=container_id)
        )
        await session.commit()

    recovery = asyncio.create_task(make_executor(db, settings, docker).recover())
    await eventually(
        lambda: _following(docker, container_id), what="the adopted container to be followed"
    )
    gate.set()
    await asyncio.wait_for(recovery, 5)

    finished = await get_job(db, job.id)
    assert finished.status is GpuJobStatus.SUCCEEDED
    assert docker.ops("create", "start") == []
    events = await epoch_events(db, job.run_id)
    assert [event["epoch"] for event in events] == [0, 1]
    assert events[1]["val"] == epoch_record(1)["val"]
    assert finished.epochs_reported == 2
    assert finished.provenance is not None and finished.provenance["config_sha256"]
    assert docker.containers == {}


async def _following(docker: FakeDocker, container_id: str) -> bool:
    return ("logs", container_id) in docker.calls


async def test_an_adopted_job_that_finished_in_time_is_not_timed_out(
    db: Factory, tmp_path: Path
) -> None:
    """The executor was down past the job's deadline, but the replayed output holds ARP-DONE."""
    docker = FakeDocker()
    settings = executor_settings(tmp_path)
    job = await create_job(
        db,
        kind=GpuJobKind.TRAIN,
        status=GpuJobStatus.RUNNING,
        started_at=datetime.now(UTC) - timedelta(hours=2),
        timeout_seconds=3600,
    )
    write_job_files(job_dir(settings.data_dir, job.id), job.code, job.config, job.dataset)
    script = Script(steps=[epoch_line(0)], outputs={"results.json": results_ok()})
    container_id = await docker.run_container(container_name(job.id), _labels(job.id), script)
    async with db() as session:
        await session.execute(
            update(GpuJob).where(GpuJob.id == job.id).values(container_id=container_id)
        )
        await session.commit()
    await make_executor(db, settings, docker).recover()

    finished = await get_job(db, job.id)
    assert finished.status is GpuJobStatus.SUCCEEDED
    assert docker.ops("kill", "stop") == ["kill"]


async def test_a_running_job_without_a_container_is_lost(db: Factory, tmp_path: Path) -> None:
    job = await create_job(
        db, status=GpuJobStatus.RUNNING, started_at=datetime.now(UTC), container_id="gone"
    )
    await make_executor(db, executor_settings(tmp_path), FakeDocker()).recover()
    finished = await get_job(db, job.id)
    assert (finished.status, finished.error_code) == (GpuJobStatus.FAILED, JOB_LOST)
    assert finished.finished_at is not None and finished.lease_until is None


async def test_a_running_job_whose_container_stopped_is_failed(db: Factory, tmp_path: Path) -> None:
    """Its tmpfs output went with the container, so there is nothing to copy."""
    docker = FakeDocker()
    job = await create_job(db, status=GpuJobStatus.RUNNING, started_at=datetime.now(UTC))
    script = Script(
        steps=["epoch 0 step 0", "Killed"],
        exit_code=None,
        hold=False,
        end_exit_code=SIGKILL_EXIT,
        oom_killed=True,
    )
    container_id = await docker.run_container(container_name(job.id), _labels(job.id), script)
    await eventually(lambda: _ended(docker, container_id), what="the container to stop")
    await make_executor(db, executor_settings(tmp_path), docker).recover()

    finished = await get_job(db, job.id)
    assert (finished.status, finished.error_code) == (GpuJobStatus.FAILED, JOB_OOM_KILLED)
    assert finished.exit_code == SIGKILL_EXIT
    assert finished.log_tail == "epoch 0 step 0\nKilled"
    assert docker.downloads == [] and docker.containers == {}


async def _ended(docker: FakeDocker, container_id: str) -> bool:
    container = docker.find(container_id)
    return container is not None and container.ended.is_set()


async def test_stray_labelled_containers_are_removed(db: Factory, tmp_path: Path) -> None:
    docker = FakeDocker()
    finished = await create_job(db, status=GpuJobStatus.SUCCEEDED)
    queued = await create_job(db)
    unknown = uuid.uuid4()
    strays = [
        await docker.run_container(container_name(finished.id), _labels(finished.id)),
        await docker.run_container(container_name(unknown), _labels(unknown)),
        await docker.run_container(container_name(queued.id), _labels(queued.id), start=False),
    ]
    # Labelled, but not named as their job's container: the socket proxy refuses those names,
    # so the executor leaves them alone.
    others = [
        await docker.run_container("arp-job-garbled", {JOB_LABEL: "not-a-uuid"}),
        await docker.run_container("someone-elses-job", _labels(finished.id)),
        await docker.run_container("someone-elses", {"com.example": "x"}),
    ]
    await make_executor(db, executor_settings(tmp_path), docker).recover()

    assert sorted(docker.removed) == sorted(strays)
    assert sorted(docker.containers) == sorted(others)
    assert (await get_job(db, queued.id)).status is GpuJobStatus.QUEUED


async def test_an_idle_executor_reaps_containers_of_finished_jobs(
    db: Factory, tmp_path: Path
) -> None:
    docker = FakeDocker()
    finished = await create_job(db, status=GpuJobStatus.SUCCEEDED)
    executor = make_executor(db, executor_settings(tmp_path), docker)
    async with running(executor):
        await eventually(
            lambda: _listed(docker, 1), what="recover() to look for the last executor's containers"
        )
        stray = await docker.run_container(container_name(finished.id), _labels(finished.id))
        await eventually(lambda: _removed(docker, stray), what="the reaper")
    assert docker.calls.count(("list", JOB_LABEL)) >= 2


async def _listed(docker: FakeDocker, times: int) -> bool:
    return docker.calls.count(("list", JOB_LABEL)) >= times


async def _removed(docker: FakeDocker, container_id: str) -> bool:
    return container_id in docker.removed


async def test_a_job_that_lost_touch_with_postgres_is_recovered(
    db: Factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Postgres went away between creating the container and recording it: the job is not
    failed for that. recover() removes the container and queues the job again."""
    docker = FakeDocker()
    job = await create_job(db)
    docker.script(job.id, Script(outputs={"results.json": results_ok()}))
    record_container = queue.record_container
    calls = 0

    async def flaky(session: Any, job_id: uuid.UUID, container_id: str) -> bool | None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OperationalError("UPDATE gpu_jobs", None, ConnectionError("server closed"))
        return await record_container(session, job_id, container_id)

    monkeypatch.setattr(queue, "record_container", flaky)
    async with running(make_executor(db, executor_settings(tmp_path), docker)):
        await wait_status(db, job.id, GpuJobStatus.SUCCEEDED)

    first, second = (name for name, _ in docker.created)
    assert first == second == container_name(job.id)
    assert len(docker.removed) == 2  # the first container by recover(), the second at the end
    assert docker.containers == {}


async def test_an_executor_restarted_mid_job_adopts_its_container(
    db: Factory, tmp_path: Path
) -> None:
    """Stopping the executor leaves the job's container running; the next one adopts it, and
    each epoch is reported exactly once across the two."""
    docker = FakeDocker()
    settings = executor_settings(tmp_path)
    job = await create_job(db, kind=GpuJobKind.TRAIN, config=job_config(epochs=3))
    gate = asyncio.Event()
    steps: list[Any] = [step_line(0, 0, 1.0), epoch_line(0), gate, epoch_line(1), epoch_line(2)]
    docker.script(job.id, Script(steps=steps, outputs={"results.json": results_ok()}))

    first = make_executor(db, settings, docker)

    async def first_epoch_reported() -> bool:
        return (await get_job(db, job.id)).epochs_reported == 1

    async def on_the_gpu() -> bool:
        status = await executor_status(db)
        return status is not None and status["job_id"] == str(job.id)

    async with running(first):
        await eventually(first_epoch_reported, what="the first epoch event")
        await eventually(on_the_gpu, what="the heartbeat to name the job")
    left = await get_job(db, job.id)
    assert left.status is GpuJobStatus.RUNNING
    [(name, _)] = docker.created
    container = docker.find(name)
    assert container is not None and container.state == "running"
    assert docker.ops("stop", "kill", "remove") == []

    gate.set()  # training goes on while no executor watches
    second = make_executor(db, settings, docker)
    async with running(second):
        await wait_status(db, job.id, GpuJobStatus.SUCCEEDED)

    assert len(docker.created) == 1
    assert [event["epoch"] for event in await epoch_events(db, job.run_id)] == [0, 1, 2]
    assert docker.containers == {}

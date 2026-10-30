"""The real experiment stage through execute_stage on the test database. The test plays the
executor: it moves the training job's row as the executor's queue does, and reports its epochs as
experiment.epoch events, the way agentic_executor.queue.report_epoch writes them."""

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from llm_stages_testkit import (
    TOPIC,
    TRAIN_CONFIG_SHA256,
    TRAIN_GPU,
    TRAIN_IMAGE_ID,
    TRAIN_MODEL_PY,
    approve,
    depth_metrics,
    epoch_payload,
    failed_results,
    progress,
    stored_output,
    train_code_config,
    train_provenance,
    train_results,
    trained_coding,
    upstream,
)
from sqlalchemy import select, update
from temporalio.activity import ActivityCancellationDetails
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from agentic_core.contracts import EventType
from agentic_core.enums import GpuJobKind, GpuJobStatus
from agentic_core.schemas import ExperimentOutput
from agentic_db import append_event
from agentic_db.lab_settings import EXECUTOR_STATUS_KEY
from agentic_db.models import Dataset, GpuJob, Run, Setting
from agentic_worker.activities import StageActivities
from agentic_worker.experiment.output import code_sha256, source_hashes
from agentic_worker.experiment.runner import FINISHED, PLANNED, ExperimentRunner
from agentic_worker.gpu import QUEUED, STARTED, GpuJobs
from agentic_worker.outputs import EXPERIMENT_PROMPT_VERSION, STAGE_DEMO_REASON
from agentic_worker.stages import PipelineStageRunner
from agentic_worker.types import StageExecIn, StageResult, StageStartIn
from worker_testkit import Factory, FakePlanner, FakeValkey, create_run

# (train, val) of each of the stage's 2 epochs.
EPOCHS = [
    (depth_metrics(0.61, 0.92, 0.70, 0.25), depth_metrics(0.66, 0.98, 0.74, 0.27)),
    (depth_metrics(0.45, 0.71, 0.54, 0.19), depth_metrics(0.52, 0.80, 0.60, 0.21)),
]
TRAINED = {"model.py": TRAIN_MODEL_PY}  # what the job runs: no config.json, no README
LOG_TAIL = "epoch 1 train {...} val {...}\nwrote results.json"


async def eventually(check: Callable[[], Awaitable[bool]], seconds: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + seconds
    while not await check():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("timed out")
        await asyncio.sleep(0.02)


async def heartbeat(db: Factory, *, used_mb: int = 1024) -> None:
    """The executor's heartbeat just now, as it writes it: a 6 GB GPU with ``used_mb`` in use."""
    now = datetime.now(UTC).isoformat()
    gpu = {
        "index": 0,
        "name": TRAIN_GPU,
        "memory_total_mb": 6144,
        "memory_used_mb": used_mb,
        "utilization_percent": 1,
        "temperature_c": 40,
        "power_draw_w": 8.5,
        "power_limit_w": 120.0,
        "fan_percent": 0,
        "sampled_at": now,
    }
    value = {"alive_at": now, "gpu": gpu, "job_id": None, "waiting_for_vram": None}
    async with db() as session:
        await session.merge(Setting(key=EXECUTOR_STATUS_KEY, value=value, updated_by="executor"))
        await session.commit()


@dataclass
class Attempt:
    """The first attempt of the experiment stage of a run whose code was approved."""

    db: Factory
    run_id: str
    stage_run_id: str
    activities: StageActivities

    @property
    def request(self) -> StageExecIn:
        return StageExecIn(
            run_id=self.run_id, stage_run_id=self.stage_run_id, stage="experiment", attempt=1
        )

    def execute(
        self, environment: ActivityEnvironment | None = None
    ) -> Coroutine[Any, Any, StageResult]:
        environment = environment or ActivityEnvironment()
        return environment.run(self.activities.execute_stage, self.request)

    async def output(self) -> ExperimentOutput:
        return ExperimentOutput.model_validate(
            (await stored_output(self.db, self.stage_run_id)).data
        )

    async def lines(self) -> list[tuple[str, dict[str, Any]]]:
        return await progress(self.db, self.run_id)

    async def said(self, code: str) -> None:
        """Wait until the attempt has written the progress line ``code``."""

        async def written() -> bool:
            return code in [line for line, _ in await self.lines()]

        await eventually(written)


async def attempt(
    db: Factory,
    coding: dict[str, Any] | None = None,
    *,
    reason: str | None = None,
    edited: dict[str, Any] | None = None,
    dataset_enabled: bool = True,
) -> Attempt:
    """A run whose coding output (``coding``, by default real code that passed its smoke test)
    was approved, and its experiment attempt started. Its stage trains 2 epochs of 50 steps."""
    run_id = await create_run(db, topic=TOPIC)
    async with db() as session:  # a migration registers nyu2; the tests empty the tables after it
        nyu2 = Dataset(
            name="nyu2", version="2026.05", title="NYU Depth V2", enabled=dataset_enabled
        )
        await session.merge(nyu2)
        await session.commit()
    await approve(db, run_id, "coding", coding or trained_coding(), reason, edited)
    experiment = ExperimentRunner(
        db, GpuJobs(db, poll_seconds=0.02), epochs=2, steps_per_epoch=50, max_train_hours=0.5
    )
    runner = PipelineStageRunner(FakePlanner(), experiment=experiment, demo_stage_seconds=0)
    activities = StageActivities(db, FakeValkey(), runner)
    started = await activities.start_stage(
        StageStartIn(run_id=run_id, stage="experiment", attempt=1)
    )
    return Attempt(db, run_id, started.stage_run_id, activities)


async def jobs(db: Factory) -> list[GpuJob]:
    async with db() as session:
        return list(await session.scalars(select(GpuJob)))


@dataclass
class FakeExecutor:
    """Plays the executor for an attempt's training job (agentic_executor.queue)."""

    db: Factory
    attempt: Attempt

    async def submitted(self) -> GpuJob:
        """The attempt's job, once the stage has submitted it."""

        async def found() -> bool:
            return bool(await jobs(self.db))

        await eventually(found)
        (job,) = await jobs(self.db)
        return job

    async def start(self, job: GpuJob) -> None:
        await self._set(job, status=GpuJobStatus.RUNNING, started_at=datetime.now(UTC))

    async def report_epoch(
        self, job: GpuJob, epoch: int, train: dict[str, Any], val: dict[str, Any]
    ) -> None:
        """One epoch record, as report_epoch writes it: the run locked first, then the job."""
        async with self.db() as session:
            await session.scalar(select(Run.status).where(Run.id == job.run_id).with_for_update())
            await session.execute(
                update(GpuJob).where(GpuJob.id == job.id).values(epochs_reported=epoch + 1)
            )
            payload = epoch_payload(job.id, epoch, train, val)
            await append_event(session, job.run_id, EventType.EXPERIMENT_EPOCH, payload)
            await session.commit()

    async def finish(self, job: GpuJob, status: GpuJobStatus, **values: Any) -> None:
        await self._set(job, status=status, finished_at=datetime.now(UTC), **values)

    async def succeed(self, job: GpuJob) -> None:
        await self.finish(
            job,
            GpuJobStatus.SUCCEEDED,
            result=train_results(EPOCHS[-1][1]),
            provenance=train_provenance(job.code),
            exit_code=0,
            gpu_seconds=1_830.0,
            log_tail=LOG_TAIL,
        )

    async def _set(self, job: GpuJob, **values: Any) -> None:
        async with self.db() as session:
            await session.execute(update(GpuJob).where(GpuJob.id == job.id).values(**values))
            await session.commit()


async def execute(
    stage: Attempt, plays: Callable[[], Coroutine[Any, Any, None]] | None = None
) -> None:
    """execute_stage for the attempt, while ``plays`` plays the executor."""
    playing = asyncio.create_task(plays()) if plays is not None else None
    try:
        await asyncio.wait_for(stage.execute(), 20)
        if playing is not None:
            await asyncio.wait_for(playing, 5)
    finally:
        if playing is not None and not playing.done():
            playing.cancel()


async def test_a_training_job_trains_the_approved_code_and_reports_real_metrics(
    db: Factory,
) -> None:
    await heartbeat(db, used_mb=1024)  # 5120 MB free: 60% is room for 14 samples of 205 MB
    stage = await attempt(db)
    executor = FakeExecutor(db, stage)
    async with db() as session:  # the coding stage's smoke job reported an epoch too
        other = epoch_payload(uuid.uuid4(), 0, EPOCHS[1][0], EPOCHS[1][1]) | {"kind": "smoke"}
        await append_event(session, uuid.UUID(stage.run_id), EventType.EXPERIMENT_EPOCH, other)
        await session.commit()

    async def plays() -> None:
        job = await executor.submitted()
        await stage.said(QUEUED)
        await executor.start(job)
        await stage.said(STARTED)
        for epoch, (train, val) in enumerate(EPOCHS):
            await executor.report_epoch(job, epoch, train, val)
        await executor.succeed(job)

    await execute(stage, plays)

    (job,) = await jobs(db)
    assert (job.kind, job.ordinal, job.dataset, job.timeout_seconds) == (
        GpuJobKind.TRAIN,
        1,
        "nyu2",
        1800,
    )
    assert job.code == TRAINED
    assert job.config["data"]["batch_size"] == 8
    assert job.config["seed"] == 42
    assert job.config["model"] == {"architecture": "generated", "kwargs": {"base_channels": 16}}
    assert job.config["training"] == {
        "learning_rate": 0.0003,
        "optimizer": "adamw",
        "weight_decay": 0.0001,
        "clip_grad_norm": None,
        "loss": "l1",
        "epochs": 2,
        "max_train_steps": 50,
        "max_val_steps": None,
    }

    stored = await stored_output(db, stage.stage_run_id)
    assert (stored.degraded, stored.degraded_reason, stored.model) == (False, None, None)
    assert stored.prompt_version == EXPERIMENT_PROMPT_VERSION
    output = ExperimentOutput.model_validate(stored.data)
    assert output.status == "succeeded"
    curves = {(s.name, s.split): [(p.epoch, p.value) for p in s.points] for s in output.series}
    assert len(curves) == 8  # the smoke job's epoch is not this job's
    assert curves["abs_rel", "val"] == [(0, 0.27), (1, 0.21)]
    assert curves["loss", "train"] == [(0, 0.61), (1, 0.45)]
    assert output.final_metrics == EPOCHS[-1][1]
    assert (output.config["epochs"], output.config["steps_per_epoch"]) == (2, 50)
    assert output.config["batch_size"] == 8
    assert output.logs_tail == LOG_TAIL
    provenance = output.provenance
    assert provenance.image_digest == TRAIN_IMAGE_ID
    assert provenance.code_sha256 == code_sha256(source_hashes(TRAINED))
    assert provenance.config_sha256 == TRAIN_CONFIG_SHA256
    assert (provenance.dataset, provenance.dataset_version, provenance.seed) == (
        "nyu2",
        "2026.05",
        42,
    )
    assert (provenance.gpu_name, provenance.gpu_seconds) == (TRAIN_GPU, 1830.0)
    assert provenance.started_at == job.started_at and provenance.finished_at == job.finished_at
    assert output.summary.startswith(
        "Training on NYU Depth V2 (nyu2, version 2026.05) succeeded: 2 epochs completed. "
        "Validation after the last epoch: loss 0.52, RMSE 0.8, MAE 0.6, AbsRel 0.21."
    )
    assert output.summary.endswith(
        "60% of the 5120 MB free on the NVIDIA GeForce GTX 1060 6GB when the executor last "
        "sampled it is room for 14, rounded down to a power of two."
    )
    assert await stage.lines() == [
        (PLANNED, {"epochs": 2, "steps": 50, "batch_size": 8}),
        (QUEUED, {"kind": "train", "ordinal": 1}),
        (STARTED, {"kind": "train", "ordinal": 1}),
        (FINISHED, {"status": "succeeded", "epochs": 2}),
    ]


@pytest.mark.parametrize(
    ("status", "error_code", "error", "results", "said"),
    [
        (
            GpuJobStatus.FAILED,
            "train.oom",
            "OutOfMemoryError: CUDA out of memory. Tried to allocate 1.50 GiB",
            failed_results("train.oom", "OutOfMemoryError: CUDA out of memory."),
            "failed (train.oom) after 1 of 2 epochs: OutOfMemoryError: CUDA out of memory. "
            "Tried to allocate 1.50 GiB. Validation after the last completed epoch: loss 0.66, "
            "RMSE 0.98, MAE 0.74, AbsRel 0.27.",
        ),
        (
            GpuJobStatus.TIMEOUT,
            None,
            "Stopped at the job's time limit of 1800 s",
            None,
            "stopped at its time limit after 1 of 2 epochs: Stopped at the job's time limit of "
            "1800 s. Validation after the last completed epoch: loss 0.66,",
        ),
    ],
)
async def test_a_training_that_fails_or_times_out_is_an_output_that_says_so(
    db: Factory,
    status: GpuJobStatus,
    error_code: str | None,
    error: str,
    results: dict[str, Any] | None,
    said: str,
) -> None:
    await heartbeat(db)
    stage = await attempt(db)
    executor = FakeExecutor(db, stage)

    async def plays() -> None:
        job = await executor.submitted()
        await executor.start(job)
        await executor.report_epoch(job, 0, *EPOCHS[0])
        await executor.finish(
            job,
            status,
            error_code=error_code,
            error=error,
            result=results,
            provenance=train_provenance(job.code),
            exit_code=1 if status is GpuJobStatus.FAILED else None,
            gpu_seconds=95.0,
            log_tail="Traceback (most recent call last): ...",
        )

    await execute(stage, plays)
    output = await stage.output()
    assert output.status == status.value
    assert said in output.summary
    assert output.final_metrics == EPOCHS[0][1]
    assert [len(series.points) for series in output.series] == [1] * 8
    assert (await stage.lines())[-1] == (FINISHED, {"status": status.value, "epochs": 1})


async def test_an_attempt_that_runs_again_waits_on_the_job_it_submitted(db: Factory) -> None:
    await heartbeat(db, used_mb=1024)
    stage = await attempt(db)
    executor = FakeExecutor(db, stage)
    first = ActivityEnvironment()
    trying = asyncio.create_task(stage.execute(first))
    job = await executor.submitted()
    await stage.said(QUEUED)
    await executor.start(job)
    await stage.said(STARTED)
    await executor.report_epoch(job, 0, *EPOCHS[0])
    # The activity times out (or its worker stops): the job trains on for the next try.
    first.cancel(ActivityCancellationDetails(timed_out=True))
    with pytest.raises(asyncio.CancelledError):
        await trying
    assert (await jobs(db))[0].status is GpuJobStatus.RUNNING
    # Its own training fills the GPU now: planned again, its batch size would be 2. And the
    # dataset was disabled meanwhile, which stops new jobs only.
    await heartbeat(db, used_mb=5800)
    async with db() as session:
        await session.execute(update(Dataset).where(Dataset.name == "nyu2").values(enabled=False))
        await session.commit()

    async def plays() -> None:
        await asyncio.sleep(0.2)  # the next try finds the job and waits on it
        await executor.report_epoch(job, 1, *EPOCHS[1])
        await executor.succeed(job)

    await execute(stage, plays)
    (again,) = await jobs(db)
    assert again.id == job.id and again.config == job.config
    output = await stage.output()
    assert (output.status, output.config["batch_size"]) == ("succeeded", 8)
    assert [p.value for p in output.series[0].points] == [0.66, 0.52]
    assert output.summary.startswith("Training on nyu2 (version 2026.05) succeeded")
    assert "Batch size 8, chosen when an earlier try of this attempt submitted the job." in (
        output.summary
    )
    assert await stage.lines() == [  # each line once, though two tries ran
        (PLANNED, {"epochs": 2, "steps": 50, "batch_size": 8}),
        (QUEUED, {"kind": "train", "ordinal": 1}),
        (STARTED, {"kind": "train", "ordinal": 1}),
        (FINISHED, {"status": "succeeded", "epochs": 2}),
    ]


async def test_a_cancelled_run_cancels_its_training_job(db: Factory) -> None:
    await heartbeat(db)
    stage = await attempt(db)
    executor = FakeExecutor(db, stage)
    environment = ActivityEnvironment()
    trying = asyncio.create_task(stage.execute(environment))
    job = await executor.submitted()
    await executor.start(job)
    await stage.said(STARTED)
    environment.cancel()  # the run was cancelled

    async def stops_it() -> bool:  # as the executor does once it sees the cancel
        (current,) = await jobs(db)
        if not current.cancel_requested:
            return False
        await executor.finish(current, GpuJobStatus.CANCELLED)
        return True

    await eventually(stops_it)
    with pytest.raises(asyncio.CancelledError):
        await trying
    (cancelled,) = await jobs(db)
    assert cancelled.status is GpuJobStatus.CANCELLED
    assert FINISHED not in [line for line, _ in await stage.lines()]


async def test_demo_code_never_ran_and_is_not_trained(db: Factory) -> None:
    stage = await attempt(db, upstream()["coding"], reason=STAGE_DEMO_REASON)
    with pytest.raises(ApplicationError, match=r"^StageFailed: experiment\.demo_code: "):
        await execute(stage)
    assert await jobs(db) == []


@pytest.mark.parametrize(
    ("dataset", "enabled"),
    [("nyu2", False), ("kitti", True)],  # disabled; or a dataset the harness can't train on
)
async def test_without_a_dataset_to_train_on_the_stage_fails(
    db: Factory, dataset: str, enabled: bool
) -> None:
    coding = trained_coding(train_code_config(dataset=dataset))
    stage = await attempt(db, coding, dataset_enabled=enabled)
    with pytest.raises(
        ApplicationError, match=rf"^StageFailed: experiment\.no_dataset: '{dataset}' is not"
    ):
        await execute(stage)
    assert await jobs(db) == []


async def test_a_config_json_edited_out_of_bounds_on_approval_fails_the_stage(
    db: Factory,
) -> None:
    edited = trained_coding(train_code_config(training={"learning_rate": 5, "optimizer": "adam"}))
    stage = await attempt(db, trained_coding(), edited=edited)
    with pytest.raises(
        ApplicationError,
        match=r"^StageFailed: experiment\.invalid_code_config: config\.json: "
        r"training\.learning_rate: Input should be less than or equal to 0\.1",
    ):
        await execute(stage)
    assert await jobs(db) == []

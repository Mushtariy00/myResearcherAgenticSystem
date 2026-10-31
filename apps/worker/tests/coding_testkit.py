"""Fakes for the coding stage: answers to coding.write and coding.repair, the nyu2 dataset, an
executor that plays the GPU (it moves each smoke job's row as apps/executor does, with a
results.json like the harness writes), and a harness that runs the real stage behind
execute_stage on the test database."""

import asyncio
import contextlib
import dataclasses
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from literature_testkit import FakeGateway, fake_llms
from llm_stages_testkit import TOPIC, approve, context, gateway, inputs_for
from sqlalchemy import select, update

from agentic_core.enums import GpuJobStatus
from agentic_db.lab_settings import EXECUTOR_STATUS_KEY
from agentic_db.models import Dataset, GpuJob, Setting
from agentic_worker.activities import StageActivities
from agentic_worker.agents import StageAgents
from agentic_worker.coding.runner import CodingRunner
from agentic_worker.gpu import GpuJobs, run_cancel_requested
from agentic_worker.stages import LogEvent, PipelineStageRunner, StageContext
from agentic_worker.types import StageExecIn, StageStartIn
from worker_testkit import Factory, FakePlanner, FakeValkey, create_run

Lines = list[tuple[str, dict[str, Any]]]

# --- the answers ---------------------------------------------------------------------------------

MODEL_PY = '''"""A two-stage encoder-decoder for metric depth."""

from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F


class Block(nn.Module):
    """A 3x3 convolution with GroupNorm, stable at small batch sizes."""

    def __init__(self, in_channels: int, out_channels: int) -> None:
        super().__init__()
        self.body = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.GroupNorm(8, out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.body(x)


class Model(nn.Module):
    def __init__(self, base_channels: int = 16, max_depth: float = 10.0) -> None:
        super().__init__()
        self.max_depth = max_depth
        self.stem = Block(3, base_channels)
        self.down = Block(base_channels, base_channels * 2)
        self.head = nn.Conv2d(base_channels * 2, 1, kernel_size=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        hidden = self.down(F.max_pool2d(self.stem(x), kernel_size=2))
        hidden = F.interpolate(hidden, size=x.shape[-2:], mode="bilinear", align_corners=False)
        return self.max_depth * torch.sigmoid(self.head(hidden))
'''

LOSS_PY = '''"""L1 on the valid pixels plus a scale-invariant log term."""

import torch
from torch import nn
from torch.nn import functional as F

MIN_VALID = 1e-6


class Loss(nn.Module):
    def __init__(self, si_weight: float = 0.5) -> None:
        super().__init__()
        self.si_weight = si_weight

    def forward(
        self, prediction: torch.Tensor, target: torch.Tensor, valid_mask: torch.Tensor
    ) -> torch.Tensor:
        mask = valid_mask & (target > MIN_VALID)
        pred = prediction[mask].clamp_min(MIN_VALID)
        true = target[mask]
        log_diff = torch.log(pred) - torch.log(true)
        scale_invariant = log_diff.pow(2).mean() - self.si_weight * log_diff.mean().pow(2)
        return F.l1_loss(pred, true) + scale_invariant.clamp_min(0.0)
'''

# model.py with an import the checker refuses, on line REFUSED_LINE.
REFUSED_MODEL_PY = MODEL_PY.replace("import torch\n", "import os\nimport torch\n", 1)
REFUSED_LINE = REFUSED_MODEL_PY.splitlines().index("import os") + 1

KWARGS = {"base_channels": 16, "max_depth": 10.0}
CHOICES: dict[str, Any] = {
    "summary": (
        "A two-stage encoder-decoder with GroupNorm and a sigmoid depth head, trained with L1 "
        "and a scale-invariant log term on the valid pixels."
    ),
    "model_kwargs": KWARGS,
    "loss": "generated",
    "training": {
        "learning_rate": 0.0003,
        "optimizer": "AdamW",  # the answer's spelling; the output keeps "adamw"
        "weight_decay": 0.0001,
        "clip_grad_norm": 1.0,
    },
}
# The choices' training as the stage keeps it.
TRAINING = {
    "learning_rate": 0.0003,
    "optimizer": "adamw",
    "weight_decay": 0.0001,
    "clip_grad_norm": 1.0,
}


def coding_answer(
    prompt: str, *, model_py: str = MODEL_PY, loss_py: str | None = LOSS_PY, **choices: Any
) -> str:
    """model.py and loss.py in their blocks, then the choices (CHOICES with ``choices``), with
    prose around them."""
    blocks = [f"```python\n# file: model.py\n{model_py}```"]
    if loss_py is not None:
        blocks.append(f"```python\n# file: loss.py\n{loss_py}```")
    blocks.append(f"```json\n{json.dumps(CHOICES | choices)}\n```")
    return "I will keep the model small.\n\n" + "\n\n".join(blocks) + "\n\nThis should pass."


def coding_gateway(answers: Mapping[str, Callable[[str], str]] | None = None) -> FakeGateway:
    """The fake gateway answering both coding roles with the passing code, unless told otherwise."""
    return gateway(
        {"coding.write": coding_answer, "coding.repair": coding_answer, **(answers or {})}
    )


def prompts(fake: FakeGateway, role: str) -> list[str]:
    """The prompts of the calls for ``role``, in order (each repair repeats its request)."""
    return [call.messages[-1]["content"] for call in fake.calls if call.role == role]


# --- the dataset and the executor ----------------------------------------------------------------

# As the migration registers nyu2 (each test empties every table, so tests register it again).
NYU2_CONTRACT = {
    "inputs": "RGB uint8, 3x480x640",
    "targets": "Depth map float32, 1x480x640",
    "units": "metres",
    "valid_range": "above 0.001 m",
    "missing_values": "0 where the sensor returned no depth",
    "evaluation": "Every valid pixel of the full frame: RMSE, MAE and AbsRel",
}


async def register_nyu2(db: Factory, *, enabled: bool = True) -> None:
    # A merge: the first test of a session finds the row the migrations registered (since
    # 2026-10-31 version 2026.10), and the tests expect this one.
    async with db() as session:
        await session.merge(
            Dataset(
                name="nyu2",
                version="2026.05",
                title="NYU Depth V2",
                contract=NYU2_CONTRACT,
                details={"width": 640, "height": 480},
                enabled=enabled,
            )
        )
        await session.commit()


PASSING_LOG = "\n".join(
    [
        "2026-10-30 12:00:01 INFO epoch 0 step 0 loss 2.1734",
        'ARP-METRIC {"ts": "2026-10-30T12:00:01+00:00", "kind": "train_step", "epoch": 0, '
        '"step": 0, "loss": 2.1734}',
        'ARP-METRIC {"ts": "2026-10-30T12:00:04+00:00", "kind": "epoch", "epoch": 0, "train": '
        '{"loss": 2.05}, "val": {"loss": 1.98}}',
        "2026-10-30 12:00:04 INFO epoch 0 train {'loss': 2.05} val {'loss': 1.98}",
        'ARP-DONE {"exit_code": 0}',
    ]
)
# 700 MiB and a byte: config.json rounds it up.
PEAK_GPU_MEMORY_BYTES = 700 * 1024**2 + 1


def passing_results() -> dict[str, Any]:
    """A results.json of a dry run that passed, as harness.train writes it."""
    return {
        "status": "ok",
        "train_metrics": {"loss": 2.05, "rmse": 2.61, "mae": 2.05, "abs_rel": 0.79},
        "val_metrics": {"loss": 1.98, "rmse": 2.44, "mae": 1.98, "abs_rel": 0.74},
        "best_val_loss": 1.98,
        "dataset_warnings": [],
        "param_count": 7329,
        "steps_per_second": 3.512,
        "peak_gpu_memory_bytes": PEAK_GPU_MEMORY_BYTES,
        "provenance": {
            "harness_version": "0.3.0",
            "config_sha256": "ab" * 32,
            "seed": 42,
            "torch": "2.14.1",
            "cuda": "12.6",
            "device": "NVIDIA GeForce GTX 1060 6GB",
            "train_samples": 50688,
            "val_samples": 654,
        },
        "duration_s": 17.42,
    }


@dataclass(frozen=True)
class End:
    """How the fake executor ends a job: its status and what the executor writes with it."""

    status: GpuJobStatus
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error: str | None = None
    log_tail: str | None = None
    gpu_seconds: float | None = 13.27


def passed() -> End:
    return End(GpuJobStatus.SUCCEEDED, result=passing_results(), log_tail=PASSING_LOG)


def failed(error_code: str, error: str, log_tail: str = 'ARP-DONE {"exit_code": 1}') -> End:
    """A dry run the harness ended with a failed results.json."""
    result = {
        "status": "failed",
        "error": error,
        "error_code": error_code,
        "train_metrics": None,
        "val_metrics": None,
        "duration_s": 4.2,
    }
    return End(
        GpuJobStatus.FAILED,
        result=result,
        error_code=error_code,
        error=error,
        log_tail=log_tail,
        gpu_seconds=5.5,
    )


def timed_out() -> End:
    """What the executor writes for a job it stopped at its wall clock: no error code."""
    return End(
        GpuJobStatus.TIMEOUT,
        error="Stopped at the job's time limit of 600 s",
        log_tail="2026-10-30 12:00:01 INFO epoch 0 step 0 loss 2.1734",
        gpu_seconds=600.0,
    )


async def set_job(db: Factory, job_id: uuid.UUID, **values: Any) -> None:
    async with db() as session:
        await session.execute(update(GpuJob).where(GpuJob.id == job_id).values(**values))
        await session.commit()


@dataclass
class FakeExecutor:
    """Plays apps/executor: runs each queued job it has an end for, by its ordinal (the try), and
    ends it so; a job without one stays queued."""

    db: Factory
    ends: dict[int, End]
    ran: list[int] = field(default_factory=list)  # the ordinals of the jobs it ran, in order

    async def serve(self) -> None:
        while True:
            async with self.db() as session:
                queued = list(
                    await session.scalars(
                        select(GpuJob)
                        .where(GpuJob.status == GpuJobStatus.QUEUED)
                        .order_by(GpuJob.created_at)
                    )
                )
            for job in queued:
                end = self.ends.get(job.ordinal)
                if end is not None:
                    await self._run(job.id, job.ordinal, end)
            await asyncio.sleep(0.02)

    async def _run(self, job_id: uuid.UUID, ordinal: int, end: End) -> None:
        await set_job(self.db, job_id, status=GpuJobStatus.RUNNING, started_at=datetime.now(UTC))
        self.ran.append(ordinal)
        await asyncio.sleep(0.25)  # ten times the stage's poll, so it sees the job run
        await set_job(
            self.db,
            job_id,
            status=end.status,
            finished_at=datetime.now(UTC),
            result=end.result,
            error_code=end.error_code,
            error=end.error,
            log_tail=end.log_tail,
            gpu_seconds=end.gpu_seconds,
        )


@contextlib.asynccontextmanager
async def executing(db: Factory, ends: Mapping[int, End]) -> AsyncIterator[FakeExecutor]:
    """The fake executor, with a fresh heartbeat, serving while the block runs."""
    async with db() as session:
        await session.merge(
            Setting(
                key=EXECUTOR_STATUS_KEY,
                value={"alive_at": datetime.now(UTC).isoformat()},
                updated_by="executor",
            )
        )
        await session.commit()
    executor = FakeExecutor(db, dict(ends))
    task = asyncio.create_task(executor.serve())
    try:
        yield executor
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def jobs(db: Factory, stage_run_id: str) -> list[GpuJob]:
    """The attempt's GPU jobs, by ordinal."""
    async with db() as session:
        return list(
            await session.scalars(
                select(GpuJob)
                .where(GpuJob.stage_run_id == uuid.UUID(stage_run_id))
                .order_by(GpuJob.ordinal)
            )
        )


async def eventually(check: Callable[[], Awaitable[bool]], seconds: float = 10.0) -> None:
    deadline = asyncio.get_running_loop().time() + seconds
    while not await check():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("timed out")
        await asyncio.sleep(0.02)


# --- the stage on the test database --------------------------------------------------------------


def collect(lines: Lines) -> LogEvent:
    """A progress sink that keeps the lines' codes and params."""

    async def log(code: str, params: dict[str, Any], message: str) -> None:
        lines.append((code, params))

    return log


@dataclass
class CodingHarness:
    """The real coding stage behind execute_stage, talking to a fake gateway; its smoke jobs are
    rows a FakeExecutor runs."""

    db: Factory
    gateway: FakeGateway
    gpu: GpuJobs
    runner: CodingRunner
    activities: StageActivities

    async def start(self) -> tuple[str, str]:
        """A run with its literature and method approved and its first coding attempt started:
        (run id, stage run id)."""
        await register_nyu2(self.db)
        run_id = await create_run(self.db, topic=TOPIC)
        for stage, data in inputs_for("coding").items():
            await approve(self.db, run_id, stage, data)
        started = await self.activities.start_stage(
            StageStartIn(run_id=run_id, stage="coding", attempt=1)
        )
        return run_id, started.stage_run_id

    def execute(self, run_id: str, stage_run_id: str) -> StageExecIn:
        return StageExecIn(run_id=run_id, stage_run_id=stage_run_id, stage="coding", attempt=1)

    async def attempt(
        self,
        *,
        degraded_inputs: Mapping[str, str] | None = None,
        previous_output: dict[str, Any] | None = None,
        feedback_history: tuple[str, ...] = (),
        lines: Lines | None = None,
    ) -> StageContext:
        """A started attempt as execute_stage describes it, for running the stage directly; its
        progress lines go to ``lines``."""
        run_id, stage_run_id = await self.start()
        ctx = context(
            "coding",
            degraded_inputs=degraded_inputs,
            previous_output=previous_output,
            feedback_history=feedback_history,
            log=collect(lines if lines is not None else []),
        )
        return dataclasses.replace(ctx, run_id=run_id, stage_run_id=stage_run_id)


def coding_harness(
    db: Factory,
    fake: FakeGateway | None = None,
    *,
    cancels_job: Callable[[], bool] = run_cancel_requested,
) -> CodingHarness:
    fake = fake or coding_gateway()
    gpu = GpuJobs(db, poll_seconds=0.02, cancels_job=cancels_job)
    coding = CodingRunner(StageAgents(fake_llms(fake)), db, gpu)
    runner = PipelineStageRunner(FakePlanner(), coding=coding, demo_stage_seconds=0)
    return CodingHarness(db, fake, gpu, coding, StageActivities(db, FakeValkey(), runner))

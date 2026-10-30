"""The experiment's training run: bounded by the worker's settings, its batch size sized to the GPU.

The approved code trains with the choices its config.json carries (model kwargs, loss, optimizer)
for ARP_EXPERIMENT_EPOCHS epochs of at most ARP_EXPERIMENT_STEPS_PER_EPOCH steps, validating on
the whole validation split after each epoch, with a fixed seed. The batch size comes from what the
smoke test measured, the GPU memory a sample took, against the memory free on the GPU in the
executor's latest heartbeat. The plan says why, and the output's summary repeats it.

A reviewer may have edited config.json when approving the code, so it is validated again here.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from agentic_core.gpu_jobs import LOSS_FILE, MODEL_FILE
from agentic_core.schemas import CodingOutput
from agentic_worker.coding.config import (
    CONFIG_FILE,
    CodeConfig,
    ModelKwarg,
    SmokeMeasure,
    TrainingChoices,
)
from agentic_worker.gpu import harness_config
from agentic_worker.stages import StageFailedError

SEED = 42
# The share of the GPU's free memory a batch may take. The smoke test's peak is what PyTorch
# allocated; the CUDA context and the allocator's cache hold more on top of it.
MEMORY_SHARE = 0.6
MIN_BATCH, MAX_BATCH = 2, 16
DEFAULT_BATCH = 4  # when the smoke test measured no GPU memory
# Without a reading of the GPU: a 6 GB card (the lab's GTX 1060) with the desktop's share in use.
ASSUMED_TOTAL_MB = 6144
ASSUMED_USED_MB = 1536

INVALID_CODE_CONFIG = "experiment.invalid_code_config"


@dataclass(frozen=True)
class ApprovedCode:
    """What the training job runs: the approved model.py (and loss.py), with their config.json."""

    files: dict[str, str]  # file name to source (JobSpec.code)
    config: CodeConfig


def approved_code(coding: CodingOutput) -> ApprovedCode:
    """The approved code and its config.json, checked again. StageFailedError
    (experiment.invalid_code_config) when the code could not train as approved."""
    sources = {file.path: file.content for file in coding.files}
    if MODEL_FILE not in sources:
        raise StageFailedError(f"{INVALID_CODE_CONFIG}: the approved code has no {MODEL_FILE}")
    text = sources.get(CONFIG_FILE)
    if text is None:
        raise StageFailedError(f"{INVALID_CODE_CONFIG}: the approved code has no {CONFIG_FILE}")
    try:
        config = CodeConfig.model_validate_json(text)
    except ValidationError as exc:
        raise StageFailedError(f"{INVALID_CODE_CONFIG}: {CONFIG_FILE}: {_problems(exc)}") from exc
    if config.loss == "generated" and LOSS_FILE not in sources:
        raise StageFailedError(
            f"{INVALID_CODE_CONFIG}: {CONFIG_FILE} asks for the generated loss, and the code has "
            f"no {LOSS_FILE}"
        )
    files = {name: sources[name] for name in (MODEL_FILE, LOSS_FILE) if name in sources}
    return ApprovedCode(files=files, config=config)


def _problems(exc: ValidationError, shown: int = 3) -> str:
    errors = exc.errors()
    problems = [
        f"{'.'.join(str(part) for part in error['loc']) or 'the file'}: {error['msg']}"
        for error in errors[:shown]
    ]
    more = f" (and {len(errors) - shown} more)" if len(errors) > shown else ""
    return "; ".join(problems) + more


@dataclass(frozen=True)
class FreeMemory:
    """The GPU memory a training job can count on, and where the figure comes from."""

    mb: int
    source: str  # completes "60% of ...": "the 4608 MB free on the <GPU> when ... sampled it"


def free_memory(status: Mapping[str, Any] | None) -> FreeMemory:
    """From the executor's heartbeat (the executor.status setting): its latest nvidia-smi sample,
    total less used memory.

    Without a sample, a 6 GB card with 1.5 GB in use is assumed. A sample taken while a job ran
    counts that job's memory as used, yet the executor runs one job at a time and this one will
    have the GPU to itself: then only the card's total is read, with 1.5 GB assumed in use.
    """
    reading = _reading(status.get("gpu")) if status is not None else None
    if status is None or reading is None:
        free = ASSUMED_TOTAL_MB - ASSUMED_USED_MB
        return FreeMemory(
            free,
            f"an assumed {free} MB free (no GPU reading from the executor: a {ASSUMED_TOTAL_MB} MB "
            f"card with {ASSUMED_USED_MB} MB in use)",
        )
    name, total, used = reading
    if status.get("job_id"):
        free = max(total - ASSUMED_USED_MB, 0)
        return FreeMemory(
            free,
            f"an assumed {free} MB free on the {name} (it was running another job when last "
            f"sampled, so {ASSUMED_USED_MB} of its {total} MB are taken as in use)",
        )
    free = max(total - used, 0)
    return FreeMemory(free, f"the {free} MB free on the {name} when the executor last sampled it")


def _reading(sample: object) -> tuple[str, int, int] | None:
    """(name, total MB, used MB) of a heartbeat's GPU sample, if it has them."""
    if not isinstance(sample, Mapping):
        return None
    total, used = (
        _megabytes_of(sample.get("memory_total_mb")),
        _megabytes_of(sample.get("memory_used_mb")),
    )
    if not total or used is None:
        return None
    name = sample.get("name")
    return (name if isinstance(name, str) and name.strip() else "GPU"), total, used


def _megabytes_of(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


@dataclass(frozen=True)
class BatchSize:
    value: int
    reason: str  # a sentence for the summary


def batch_size(smoke: SmokeMeasure, memory: FreeMemory) -> BatchSize:
    """MEMORY_SHARE of the free memory over the memory a sample took in the smoke test, within
    [MIN_BATCH, MAX_BATCH] and rounded down to a power of two; DEFAULT_BATCH without a
    measurement. The memory a sample takes is overestimated (the model's own share of the peak
    is counted per sample too), which errs on the safe side."""
    peak = smoke.peak_gpu_memory_mb
    if not peak:  # None, or 0 from a run that never touched the GPU
        return BatchSize(
            DEFAULT_BATCH,
            f"Batch size {DEFAULT_BATCH}, the default: the smoke test measured no GPU memory.",
        )
    per_sample = peak / smoke.batch_size
    fits = math.floor(memory.mb * MEMORY_SHARE / per_sample)
    size = _power_of_two(min(MAX_BATCH, max(MIN_BATCH, fits)))
    if fits < MIN_BATCH:
        room = f"room for only {fits}; {MIN_BATCH} is the minimum"
    elif fits > MAX_BATCH:
        room = f"room for {fits}, more than the cap of {MAX_BATCH}"
    elif size < fits:
        room = f"room for {fits}, rounded down to a power of two"
    else:
        room = f"room for {fits}"
    samples = "1 sample" if smoke.batch_size == 1 else f"{smoke.batch_size} samples"
    return BatchSize(
        size,
        f"Batch size {size}: the smoke test peaked at {peak} MB of GPU memory with {samples}, "
        f"about {_megabytes(per_sample)} a sample, and {round(MEMORY_SHARE * 100)}% of "
        f"{memory.source} is {room}.",
    )


def _power_of_two(value: int) -> int:
    """The largest power of two at most ``value`` (which is at least 1)."""
    return 1 << (value.bit_length() - 1)


def _megabytes(value: float) -> str:
    return f"{value:,.0f} MB" if value >= 10 else f"{value:.1f} MB"


@dataclass(frozen=True)
class TrainingPlan:
    """One bounded training run of the approved code."""

    epochs: int
    steps_per_epoch: int  # at most: an epoch also ends with the training split
    batch: BatchSize
    model_kwargs: Mapping[str, ModelKwarg]
    loss: str
    training: TrainingChoices
    seed: int = SEED

    def harness_config(self, dataset: str) -> dict[str, Any]:
        """The harness's ExperimentConfig for the job, validating on the whole split."""
        return harness_config(
            dataset,
            model_kwargs=dict(self.model_kwargs),
            loss=self.loss,
            training=self.training.model_dump(),
            batch_size=self.batch.value,
            epochs=self.epochs,
            max_train_steps=self.steps_per_epoch,
            max_val_steps=None,
            seed=self.seed,
        )

    def progress(self) -> tuple[dict[str, int], str]:
        """The experiment.planned progress line: its params and English message."""
        epochs = "1 epoch" if self.epochs == 1 else f"{self.epochs} epochs"
        return (
            {"epochs": self.epochs, "steps": self.steps_per_epoch, "batch_size": self.batch.value},
            f"Training plan: {epochs} of up to {self.steps_per_epoch} steps at batch size "
            f"{self.batch.value}",
        )


def plan_training(
    config: CodeConfig, *, epochs: int, steps_per_epoch: int, memory: FreeMemory
) -> TrainingPlan:
    """The training run for the approved code's config, within the worker's settings."""
    return TrainingPlan(
        epochs=epochs,
        steps_per_epoch=steps_per_epoch,
        batch=batch_size(config.smoke, memory),
        model_kwargs=config.model_kwargs,
        loss=config.loss,
        training=config.training,
    )

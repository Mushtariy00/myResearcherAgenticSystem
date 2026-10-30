"""The experiment stage's output: what the training job ran and measured, said honestly.

It is read from the database, never from the executor's files (the worker may run on another
machine): the job's row (status, results.json, provenance, log tail, times) and the
experiment.epoch run events the executor wrote while the job ran, one per epoch. A metric that was
not measured stays None and the summary says so, never 0. A job that failed, timed out or was
cancelled is an output too: it says what happened, and keeps what its completed epochs measured.
"""

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeGuard

from agentic_core.enums import GpuJobStatus
from agentic_core.schemas import (
    ExperimentOutput,
    ExperimentStatus,
    MetricPoint,
    MetricSeries,
    MetricSplit,
    Provenance,
)
from agentic_db.models import Dataset, GpuJob
from agentic_worker.experiment.plan import SEED

type Scalar = int | float | str | bool

# The harness's metrics, in its order (sandbox/pytorch/harness/tasks.py); lower is better for all.
METRICS = ("loss", "rmse", "mae", "abs_rel")
METRIC_LABELS = {"loss": "loss", "rmse": "RMSE", "mae": "MAE", "abs_rel": "AbsRel"}
# Validation before training: the web's headline metric is the first series that is not a loss.
SPLITS: tuple[MetricSplit, ...] = ("val", "train")
STATUSES: dict[GpuJobStatus, ExperimentStatus] = {
    GpuJobStatus.SUCCEEDED: "succeeded",
    GpuJobStatus.FAILED: "failed",
    GpuJobStatus.TIMEOUT: "timeout",
    GpuJobStatus.CANCELLED: "cancelled",
}
UNKNOWN = "unknown"  # a provenance value the job never recorded
ERROR_CHARS = 400  # of the job's error, in the summary
_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class EpochRecord:
    """One epoch's metrics as the harness measured them; None where not measured."""

    epoch: int  # from 0, as the harness counts
    train: dict[str, float | None]
    val: dict[str, float | None]


def epoch_records(payloads: Iterable[Mapping[str, Any]]) -> list[EpochRecord]:
    """A job's experiment.epoch event payloads as records in epoch order, one per epoch (a later
    event for an epoch replaces an earlier one)."""
    records: dict[int, EpochRecord] = {}
    for payload in payloads:
        epoch = _whole(payload.get("epoch"))
        if epoch is not None:
            records[epoch] = EpochRecord(
                epoch, _measured(payload.get("train")), _measured(payload.get("val"))
            )
    return [records[epoch] for epoch in sorted(records)]


def metric_series(records: Sequence[EpochRecord], epochs: int) -> list[MetricSeries]:
    """One series per metric and split, with a point for each of the first ``epochs`` epochs:
    None where the metric was not measured or the epoch's record never arrived."""
    if epochs <= 0:
        return []
    by_epoch = {record.epoch: record for record in records}
    series: list[MetricSeries] = []
    for name in METRICS:
        for split in SPLITS:
            points = []
            for epoch in range(epochs):
                record = by_epoch.get(epoch)
                measured = {} if record is None else record.val if split == "val" else record.train
                points.append(MetricPoint(epoch=epoch, value=measured.get(name)))
            series.append(
                MetricSeries(name=name, split=split, higher_is_better=False, points=points)
            )
    return series


def ran_config(config: Mapping[str, Any]) -> dict[str, Scalar]:
    """A job's harness config as the flat scalars of what ran (ExperimentOutput.config)."""
    training, data = _section(config, "training"), _section(config, "data")
    kwargs = _section(_section(config, "model"), "kwargs")
    flat = {
        "epochs": training.get("epochs"),
        "steps_per_epoch": training.get("max_train_steps"),
        "batch_size": data.get("batch_size"),
        "learning_rate": training.get("learning_rate"),
        "optimizer": training.get("optimizer"),
        "weight_decay": training.get("weight_decay"),
        "clip_grad_norm": training.get("clip_grad_norm"),  # left out when unset
        "loss": training.get("loss"),
        "seed": config.get("seed"),
        **{f"model.{name}": value for name, value in kwargs.items()},
    }
    return {key: value for key, value in flat.items() if _scalar(value)}


def code_sha256(file_hashes: Mapping[str, str]) -> str:
    """One sha256 for a job's code: over the lines "<name>\\0<sha256>\\n" of its files, sorted by
    name. The executor records a sha256 per file (provenance.code_sha256); this names the set."""
    lines = "".join(f"{name}\0{digest}\n" for name, digest in sorted(file_hashes.items()))
    return hashlib.sha256(lines.encode()).hexdigest()


def source_hashes(code: Mapping[str, Any]) -> dict[str, str]:
    """Each source file's sha256 as the executor takes it: of the file it writes, in UTF-8."""
    return {
        name: hashlib.sha256(source.encode()).hexdigest()
        for name, source in code.items()
        if isinstance(source, str)
    }


def config_sha256(config: Mapping[str, Any]) -> str:
    """sha256 of a job's config as submitted, as canonical JSON (sorted keys)."""
    text = json.dumps(config, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


def experiment_output(
    job: GpuJob,
    payloads: Iterable[Mapping[str, Any]],
    *,
    dataset: Dataset | None,
    batch_reason: str | None,
) -> ExperimentOutput:
    """The output for a training job that ended, from its row and its experiment.epoch event
    payloads. ``batch_reason`` says why the job has its batch size; None when an earlier try of
    the attempt submitted the job (the summary then says only that)."""
    status = STATUSES.get(job.status)
    if status is None:
        raise ValueError(f"job {job.id} has not ended: {job.status}")
    config = ran_config(job.config)
    planned = _whole(config.get("epochs"))
    records = [r for r in epoch_records(payloads) if planned is None or r.epoch < planned]
    last = records[-1].epoch + 1 if records else 0
    # A job that succeeded ran every epoch, whether or not each epoch's record arrived.
    epochs = max(last, planned or 0) if status == "succeeded" else last
    results = job.result if isinstance(job.result, Mapping) else {}
    final, after = _final_metrics(results, records)
    provenance, gaps = _provenance(job, dataset)
    resumed = (
        f"Batch size {config.get('batch_size', '?')}, chosen when an earlier try of this attempt "
        "submitted the job."
    )
    sentences = [
        _outcome(job, status, _dataset_label(job.dataset, dataset, provenance), epochs, planned),
        _measurements(final, after, results, epochs),
        _setup(job, config, status, results, provenance),
        batch_reason or resumed,
    ]
    if len(records) < epochs:
        missing = epochs - len(records)
        sentences.append(
            f"No metrics arrived for {missing} of the {_plural(epochs, 'epoch')}, so their points "
            "in the curves are null."
        )
    if gaps:
        sentences.append(f"The job's provenance is incomplete: {'; '.join(gaps)}.")
    return ExperimentOutput(
        status=status,
        summary=" ".join(sentences),
        config=config,
        series=metric_series(records, epochs),
        final_metrics=final,
        logs_tail=job.log_tail or "",
        provenance=provenance,
    )


def finished_line(output: ExperimentOutput, error_code: str | None) -> tuple[dict[str, Any], str]:
    """The experiment.finished progress line: its params and English message."""
    epochs = max((len(series.points) for series in output.series), default=0)
    done = _plural(epochs, "epoch")
    if output.status == "succeeded":
        message = f"Training succeeded: {done}"
    elif output.status == "failed":
        message = f"Training failed{f' ({error_code})' if error_code else ''} after {done}"
    elif output.status == "timeout":
        message = f"Training stopped at its time limit after {done}"
    else:
        message = f"Training was cancelled after {done}"
    return {"status": output.status, "epochs": epochs}, message


# --- the parts of the output ---------------------------------------------------------------------


def _final_metrics(
    results: Mapping[str, Any], records: Sequence[EpochRecord]
) -> tuple[dict[str, float | None], str | None]:
    """The validation metrics after the last epoch: results.json's, else the last epoch record's.
    Also which epoch that is ("last" or "last completed"), None when there are none."""
    val = results.get("val_metrics")
    if isinstance(val, Mapping):
        return _ordered(_measured(val)), "last"
    if records:
        return _ordered(records[-1].val), "last completed"
    return {}, None


def _provenance(job: GpuJob, dataset: Dataset | None) -> tuple[Provenance, list[str]]:
    """The job's provenance, and what it lacks. A job that failed before its container started
    has no image and no hashes of its inputs: those are then of what the stage submitted."""
    recorded = job.provenance if isinstance(job.provenance, Mapping) else {}
    gaps: list[str] = []
    image = recorded.get("image_id")
    if not (isinstance(image, str) and image.strip()):
        image = UNKNOWN
        gaps.append("the image digest is unknown")
    files = recorded.get("code_sha256")
    if isinstance(files, Mapping) and files and all(_hex(digest) for digest in files.values()):
        code = code_sha256(files)
    else:
        code = code_sha256(source_hashes(job.code))
        gaps.append("the code hash is of the code as submitted")
    config = recorded.get("config_sha256")
    if not _hex(config):
        config = config_sha256(job.config)
        gaps.append("the config hash is of the config as submitted")
    version = _dataset_version(job, recorded.get("dataset"), dataset)
    if version is None:
        version = UNKNOWN
        gaps.append("the dataset version is unknown")
    if job.started_at is None:
        gaps.append("it never started, so its start time is when it was queued")
    gpu = recorded.get("gpu")
    provenance = Provenance(
        image_digest=image,
        code_sha256=code,
        config_sha256=config,
        dataset=job.dataset,
        dataset_version=version,
        seed=_seed(recorded.get("seed"), job.config),
        gpu_name=gpu if isinstance(gpu, str) and gpu.strip() else None,
        gpu_seconds=max(_number(job.gpu_seconds) or 0.0, 0.0),
        started_at=job.started_at or job.created_at,
        finished_at=job.finished_at,
    )
    return provenance, gaps


def _dataset_version(job: GpuJob, recorded: object, dataset: Dataset | None) -> str | None:
    """The version the executor recorded for the job's dataset, else the registered one."""
    version = recorded.get("version") if isinstance(recorded, Mapping) else None
    if isinstance(version, str) and version.strip():
        return version
    if dataset is not None and dataset.name == job.dataset and dataset.version.strip():
        return dataset.version
    return None


def _seed(recorded: object, config: Mapping[str, Any]) -> int:
    for seed in (recorded, config.get("seed")):
        if isinstance(seed, int) and not isinstance(seed, bool):
            return seed
    return SEED  # the harness's default too


def _dataset_label(name: str, dataset: Dataset | None, provenance: Provenance) -> str:
    version = provenance.dataset_version
    if dataset is not None and dataset.name == name and dataset.title.strip():
        return f"{dataset.title} ({name}, version {version})"
    return f"{name} (version {version})"


def _outcome(
    job: GpuJob, status: ExperimentStatus, where: str, epochs: int, planned: int | None
) -> str:
    """What happened to the training: how far it got, and the job's error code and error."""
    if status == "succeeded":
        return f"Training on {where} succeeded: {_plural(epochs, 'epoch')} completed."
    if epochs == 0:
        progress = "before its first epoch"
    elif planned:
        progress = f"after {epochs} of {_plural(planned, 'epoch')}"
    else:
        progress = f"after {_plural(epochs, 'epoch')}"
    if status == "cancelled":
        happened = f"was cancelled {progress}"
    elif status == "timeout":
        happened = f"stopped at its time limit {progress}"
    elif job.error_code:
        happened = f"failed ({job.error_code}) {progress}"
    else:
        happened = f"failed {progress}"
    error = " ".join((job.error or "").split())  # a traceback's lines, as one sentence
    if not error:
        return f"Training on {where} {happened}."
    return f"Training on {where} {happened}: {_sentence(_cut(error, ERROR_CHARS))}"


def _measurements(
    final: Mapping[str, float | None], after: str | None, results: Mapping[str, Any], epochs: int
) -> str:
    """The final validation metrics, each a value or "not measured"."""
    if after is None:
        return "Nothing was measured." if epochs == 0 else "No validation metric was recorded."
    if not final:
        return f"No validation metric was recorded after the {after} epoch."
    values = ", ".join(
        f"{METRIC_LABELS.get(name, name)} {_value(value)}" for name, value in final.items()
    )
    sentence = f"Validation after the {after} epoch: {values}."
    best = _number(results.get("best_val_loss"))
    if after == "last" and best is not None:
        sentence += f" The best validation loss was {best:.4g}."
    return sentence


def _setup(
    job: GpuJob,
    config: Mapping[str, Scalar],
    status: ExperimentStatus,
    results: Mapping[str, Any],
    provenance: Provenance,
) -> str:
    """What the job ran with, the data it saw and its GPU time."""
    epochs, steps = config.get("epochs", "?"), config.get("steps_per_epoch", "?")
    val_steps = _whole(_section(job.config, "training").get("max_val_steps"))
    validation = (
        "the whole validation split"
        if val_steps is None
        else f"up to {_plural(val_steps, 'validation step')}"
    )
    sentence = (
        f"{'It ran' if status == 'succeeded' else 'It was set to run'} "
        f"{_plural(epochs, 'epoch')} of up to {_plural(steps, 'step')} at batch size "
        f"{config.get('batch_size', '?')}, validating on {validation} after each epoch, with "
        f"seed {provenance.seed}"
    )
    harness = _section(results, "provenance")
    train, val = _whole(harness.get("train_samples")), _whole(harness.get("val_samples"))
    if train is not None and val is not None:
        sentence += f" ({train} training and {val} validation samples)"
    if provenance.gpu_seconds > 0:
        on = f" on the {provenance.gpu_name}" if provenance.gpu_name else ""
        sentence += f"; {provenance.gpu_seconds / 60:.1f} GPU-minutes{on}"
    return f"{sentence}."


# --- small helpers -------------------------------------------------------------------------------


def _section(config: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = config.get(name)
    return value if isinstance(value, Mapping) else {}


def _measured(metrics: object) -> dict[str, float | None]:
    """A metrics dict from a job, each value a finite number or None."""
    if not isinstance(metrics, Mapping):
        return {}
    return {str(name): _number(value) for name, value in metrics.items()}


def _ordered(metrics: Mapping[str, float | None]) -> dict[str, float | None]:
    """The harness's metrics first, in its order, then any others by name."""
    names = [name for name in METRICS if name in metrics]
    names += sorted(name for name in metrics if name not in METRICS)
    return {name: metrics[name] for name in names}


def _number(value: object) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return None


def _whole(value: object) -> int | None:
    """A count or an index (epochs, samples): an int from 0, else None."""
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _scalar(value: object) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    return isinstance(value, int | str)  # bool is an int


def _hex(value: object) -> TypeGuard[str]:
    """Whether ``value`` is a sha256 as the schema takes it (Sha256Hex)."""
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _value(value: float | None) -> str:
    return "not measured" if value is None else f"{value:.4g}"


def _plural(number: object, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _sentence(text: str) -> str:
    return text if text.endswith((".", "!", "?", "…")) else f"{text}."

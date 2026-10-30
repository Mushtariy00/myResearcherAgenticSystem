"""Demo experiment stage: training curves, final metrics, a log tail and provenance.

The run follows the coding output: epochs, batch size, metrics and dataset come from its
config file, and provenance hashes its files. Curves converge exponentially with noise; now and
then one validation point is missing and stays ``None`` (never 0.0), as the harness reports it.
"""

import hashlib
import math
import random
import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from agentic_core.demo._coding import GPU_NAME
from agentic_core.demo._profiles import MetricSpec, Profile, dataset_spec, metric_spec, profile_for
from agentic_core.demo._text import revision_note, rng_for, sha256_hex
from agentic_core.schemas import (
    CodingOutput,
    ExperimentOutput,
    MetricPoint,
    MetricSeries,
    MetricSplit,
    Provenance,
)

SANDBOX_IMAGE = "arp-sandbox-pytorch:2.14-cu126"
IMAGE_DIGEST = "sha256:" + hashlib.sha256(SANDBOX_IMAGE.encode()).hexdigest()
MIN_EPOCHS, MAX_EPOCHS = 12, 30

_CONFIG_LINE = re.compile(r"^\s*([A-Za-z_][\w-]*):\s*(.+?)\s*(?:#.*)?$")
# Copied from the config file into ExperimentOutput.config ("class" is the model's class).
_CONFIG_KEYS = (
    "dataset",
    "input_size",
    "batch_size",
    "epochs",
    "optimizer",
    "learning_rate",
    "weight_decay",
    "scheduler",
    "warmup_epochs",
    "amp",
    "seed",
)
_TRAIN_SAMPLES = {
    "nyu2": 50_688,
    "kitti": 23_158,
    "diode": 8_574,
    "scannet": 24_353,
    "sunrgbd": 5_285,
    "cityscapes": 2_975,
    "ade20k": 20_210,
    "voc2012": 10_582,
    "cocostuff": 118_000,
    "camvid": 367,
    "cifar100": 50_000,
    "cifar10": 50_000,
    "imagenet1k": 1_281_167,
    "tinyimagenet": 100_000,
}
# Demo timestamps without a real clock start from here (generators never read the time).
_BASE_TIME = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)


def code_hashes(coding: CodingOutput) -> tuple[str, str]:
    """(code_sha256, config_sha256) over the coding files, as recorded in the provenance."""
    code = sorted((f for f in coding.files if f.role != "config"), key=lambda f: f.path)
    config = sorted((f for f in coding.files if f.role == "config"), key=lambda f: f.path)
    return (
        sha256_hex(*(part for file in code for part in (file.path, file.content))),
        sha256_hex(*(part for file in config for part in (file.path, file.content))),
    )


def experiment(
    topic: str,
    coding: CodingOutput,
    seed: int,
    *,
    feedback: str = "",
    finished_at: datetime | None = None,
) -> ExperimentOutput:
    """One training run of the coding output. ``finished_at`` anchors the timestamps (the
    worker passes the current time); without it they are derived from ``seed``."""
    rng = rng_for(seed, "experiment")
    settings = _settings(coding)
    dataset_id = str(settings.get("dataset") or "nyu2")
    profile = profile_for(topic, dataset_id)
    dataset = dataset_spec(profile, dataset_id)
    epochs = _epochs(rng, settings)
    metrics = _metrics(profile, settings)
    model = coding.entrypoint.partition(":")[2] or profile.model_class

    tau = epochs * rng.uniform(0.18, 0.3)
    train_loss = _curve(rng, rng.uniform(1.7, 2.6), rng.uniform(0.32, 0.5), epochs, tau, 0.02)
    val_loss = _overfit(
        rng,
        _curve(
            rng,
            train_loss[0] * rng.uniform(1.02, 1.1),
            train_loss[-1] * rng.uniform(1.12, 1.35),
            epochs,
            tau,
            0.035,
        ),
    )
    values: dict[str, list[float | None]] = {}
    for spec in metrics:
        curve = _curve(rng, rng.uniform(*spec.start), rng.uniform(*spec.final), epochs, tau, 0.02)
        values[spec.name] = [min(spec.ceiling, max(spec.floor, value)) for value in curve]
    missing: tuple[MetricSpec, int] | None = None
    if epochs > 6 and rng.random() < 0.35:  # e.g. a validation batch without valid pixels
        missing = (rng.choice(metrics), rng.randint(2, epochs - 3))
        values[missing[0].name][missing[1]] = None

    series = [
        _series("loss", "train", False, train_loss),
        _series("loss", "val", False, val_loss),
        *(_series(spec.name, "val", spec.higher_is_better, values[spec.name]) for spec in metrics),
    ]
    final_metrics: dict[str, float | None] = {spec.name: values[spec.name][-1] for spec in metrics}
    final_metrics["val_loss"] = val_loss[-1]
    final_metrics["train_loss"] = train_loss[-1]
    best_epoch = min(range(epochs), key=val_loss.__getitem__)

    seconds_per_epoch = rng.uniform(32.0, 68.0)
    gpu_seconds = round(epochs * seconds_per_epoch, 1)
    startup = rng.uniform(25.0, 70.0)  # container start and dataset checks
    finished = finished_at or _BASE_TIME + timedelta(
        days=rng.randint(0, 280), minutes=rng.randint(0, 900)
    )
    started = finished - timedelta(seconds=gpu_seconds + startup)
    code_sha, config_sha = code_hashes(coding)
    config = {key: _typed(settings[key]) for key in _CONFIG_KEYS if key in settings}
    config = {"model": model, **config, "epochs": epochs, "dataset": dataset.id}

    primary = metrics[0]
    first = next(value for value in values[primary.name] if value is not None)
    last = values[primary.name][-1]
    summary = (
        f"Trained {model} for {epochs} epochs on {dataset.label} "
        f"({gpu_seconds / 60:.0f} GPU-minutes on the {GPU_NAME}). Validation {primary.label} "
        f"went from {first:.3f} to {_fmt(last)}; the best validation loss, "
        f"{val_loss[best_epoch]:.4f}, came at epoch {best_epoch}."
    )
    if missing:
        summary += (
            f" One {missing[0].label} measurement (epoch {missing[1]}) is missing and stored as "
            "null."
        )
    note = revision_note(feedback)
    return ExperimentOutput(
        status="succeeded",
        summary=f"{summary} {note}" if note else summary,
        config=config,
        series=series,
        final_metrics=final_metrics,
        logs_tail=_logs_tail(
            rng,
            started=started + timedelta(seconds=startup),
            seconds_per_epoch=seconds_per_epoch,
            steps=_steps_per_epoch(dataset.id, settings),
            train_loss=train_loss,
            val_loss=val_loss,
            values=values,
            best_epoch=best_epoch,
            gpu_seconds=gpu_seconds,
        ),
        provenance=Provenance(
            image_digest=IMAGE_DIGEST,
            code_sha256=code_sha,
            config_sha256=config_sha,
            dataset=dataset.id,
            dataset_version=dataset.version,
            seed=_int_setting(settings, "seed") or 42,
            gpu_name=GPU_NAME,
            gpu_seconds=gpu_seconds,
            started_at=started,
            finished_at=finished,
        ),
    )


def _settings(coding: CodingOutput) -> dict[str, str]:
    """First value of each ``key: value`` line in the config files (a flat read of the YAML)."""
    values: dict[str, str] = {}
    for file in coding.files:
        if file.role != "config":
            continue
        for line in file.content.splitlines():
            match = _CONFIG_LINE.match(line)
            if match and match.group(1) not in values:
                values[match.group(1)] = match.group(2).strip().strip("'\"")
    if "class" in values:
        values.setdefault("model", values["class"])
    return values


def _typed(value: str) -> int | float | str | bool:
    lowered = value.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    for cast in (int, float):
        try:
            return cast(value)
        except ValueError:
            continue
    return value


def _int_setting(settings: dict[str, str], key: str) -> int | None:
    value = _typed(settings.get(key, ""))
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _epochs(rng: random.Random, settings: dict[str, str]) -> int:
    value = _int_setting(settings, "epochs")
    if value is None:
        return rng.randint(MIN_EPOCHS, MAX_EPOCHS)
    return min(MAX_EPOCHS, max(MIN_EPOCHS, value))


def _metrics(profile: Profile, settings: dict[str, str]) -> list[MetricSpec]:
    """The config's metrics the profile knows (2-3), topped up with the profile's defaults."""
    names = [name.strip() for name in settings.get("metrics", "").strip("[]").split(",")]
    specs = [spec for name in names if (spec := metric_spec(profile, name)) is not None][:3]
    for spec in profile.metrics:
        if len(specs) >= 2:
            break
        if spec not in specs:
            specs.append(spec)
    return specs


def _curve(
    rng: random.Random, start: float, final: float, epochs: int, tau: float, noise: float
) -> list[float]:
    """Exponential convergence from ``start`` to ``final`` with multiplicative noise."""
    values = []
    for epoch in range(epochs):
        value = start + (final - start) * (1 - math.exp(-epoch / tau))
        values.append(round(max(0.0, value * (1 + rng.gauss(0, noise))), 4))
    return values


def _overfit(rng: random.Random, values: list[float]) -> list[float]:
    """Validation loss often creeps up over the last quarter of training."""
    rise = rng.uniform(0.0, 0.05)
    onset = int(len(values) * 0.75)
    span = max(1, len(values) - onset)
    return [
        round(value * (1 + rise * max(0, epoch - onset) / span), 4)
        for epoch, value in enumerate(values)
    ]


def _series(
    name: str, split: MetricSplit, higher: bool, values: Sequence[float | None]
) -> MetricSeries:
    return MetricSeries(
        name=name,
        split=split,
        higher_is_better=higher,
        points=[MetricPoint(epoch=epoch, value=value) for epoch, value in enumerate(values)],
    )


def _steps_per_epoch(dataset: str, settings: dict[str, str]) -> int:
    batch = _int_setting(settings, "batch_size")
    size = batch if batch and batch > 0 else 8
    return max(20, min(_TRAIN_SAMPLES.get(dataset, 20_000) // size, 2_000))


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _stamp(moment: datetime) -> str:
    """The harness log format (Python logging's asctime): 2026-10-30 01:12:04,512."""
    return f"{moment:%Y-%m-%d %H:%M:%S},{moment.microsecond // 1000:03d}"


def _logs_tail(
    rng: random.Random,
    *,
    started: datetime,
    seconds_per_epoch: float,
    steps: int,
    train_loss: list[float],
    val_loss: list[float],
    values: dict[str, list[float | None]],
    best_epoch: int,
    gpu_seconds: float,
) -> str:
    epochs = len(train_loss)
    lines = []
    for epoch in range(max(0, epochs - 3), epochs):
        epoch_start = started + timedelta(seconds=epoch * seconds_per_epoch)
        for index in range(5):
            step = index * (steps // 5)
            moment = epoch_start + timedelta(seconds=seconds_per_epoch * 0.17 * index)
            loss = train_loss[epoch] * (1 + rng.gauss(0, 0.06))
            lines.append(f"{_stamp(moment)} INFO epoch {epoch} step {step} loss {loss:.4f}")
        val = {"loss": val_loss[epoch]} | {name: series[epoch] for name, series in values.items()}
        moment = epoch_start + timedelta(seconds=seconds_per_epoch * 0.97)
        lines.append(
            f"{_stamp(moment)} INFO epoch {epoch} train {{'loss': {train_loss[epoch]}}} val {val}"
        )
    end = started + timedelta(seconds=gpu_seconds)
    memory = rng.uniform(3.1, 5.4)
    lines += [
        f"{_stamp(end)} INFO saved checkpoints/best.pt (val loss {val_loss[best_epoch]:.4f} at "
        f"epoch {best_epoch})",
        f"{_stamp(end)} INFO training finished: {epochs} epochs in {gpu_seconds:.1f} s, peak "
        f"GPU memory {memory:.2f} GB",
        f"{_stamp(end + timedelta(milliseconds=180))} INFO wrote results.json",
    ]
    return "\n".join(lines)

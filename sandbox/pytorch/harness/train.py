"""Sandbox entry point: `python -m harness.train --config CONFIG [--out DIR] [--dry-run]`.

Writes, under --out:
  results.json   status ("ok" | "failed"), final metrics (None when not measured), provenance;
                 on failure, error_code and (for a refused module) the checker findings
  metrics.jsonl  one line per logged step and per epoch, for live charts
  checkpoints/   last.pt and best.pt (state dicts only)

Every metric record also goes out as an `ARP-METRIC <json>` line, flushed, for live curves
(docs/design/experiments.md): to the pipe harness.job reads when it started this process
(ARP_METRIC_FD), otherwise to stdout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

import numpy as np
import torch
import yaml
from torch.utils.data import DataLoader

from harness import __version__
from harness.config import ExperimentConfig
from harness.data import build_dataset, depth_scale_warnings
from harness.generated import (
    CodeRefused,
    ForwardFailed,
    GeneratedCodeError,
    ShapeMismatch,
    ModelTooLarge,
    load_generated_loss,
    load_generated_model,
)
from harness.limits import MAX_PARAMS
from harness.models import build_model
from harness.tasks import MIN_VALID_DEPTH_M, DepthMetrics, depth_loss
from harness.trace import ShapeTrace

log = logging.getLogger("harness")
LOG_EVERY_STEPS = 20

# A loss the harness can call with (prediction, target); it hides whether the loss is built in or
# generated. Generated losses take a valid_mask, which the harness supplies.
LossFn = Callable[[torch.Tensor, torch.Tensor], torch.Tensor]


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def _optimizer(config: ExperimentConfig, model: torch.nn.Module) -> torch.optim.Optimizer:
    t = config.training
    if t.optimizer == "sgd":
        return torch.optim.SGD(model.parameters(), lr=t.learning_rate, momentum=0.9, weight_decay=t.weight_decay)
    if t.optimizer == "adamw":
        return torch.optim.AdamW(model.parameters(), lr=t.learning_rate, weight_decay=t.weight_decay)
    return torch.optim.Adam(model.parameters(), lr=t.learning_rate, weight_decay=t.weight_decay)


def _build_model(config: ExperimentConfig, device: torch.device) -> tuple[torch.nn.Module, int]:
    if config.model.architecture == "generated":
        model = load_generated_model(config.model.code_dir, config.model.kwargs)
    else:
        model = build_model(config.model.architecture, **config.model.kwargs)
    model = model.to(device)
    params = sum(p.numel() for p in model.parameters())
    if params > MAX_PARAMS:
        raise ModelTooLarge(f"Model has {params:,} parameters, over the {MAX_PARAMS:,} limit")
    return model, params


def _build_loss(config: ExperimentConfig, device: torch.device) -> LossFn:
    if config.training.loss == "generated":
        module = load_generated_loss(config.model.code_dir).to(device)

        def generated_loss(prediction: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
            valid_mask = target > MIN_VALID_DEPTH_M
            return module(prediction, target, valid_mask)

        return generated_loss

    kind = config.training.loss

    def builtin_loss(prediction: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        return depth_loss(prediction, target, kind)

    return builtin_loss


def _smoke_probe(
    model: torch.nn.Module, loss_fn_factory: Callable[[], LossFn], loader: DataLoader, device: torch.device
) -> LossFn:
    """First-batch checks before training spends GPU time: output shape then a finite loss.

    The shape is checked before ``loss_fn_factory`` runs, so a wrong-shape model is reported as a
    shape mismatch rather than a loss that fails to load. A forward pass that raises, or gives the
    wrong shape, is reported with its shape trace (harness.trace).
    """
    try:
        images, depths = next(iter(loader))
    except StopIteration:
        raise RuntimeError("The training split produced no batches") from None
    images, depths = images.to(device), depths.to(device)
    was_training = model.training
    model.eval()
    with torch.no_grad(), ShapeTrace(model) as trace:
        try:
            prediction = model(images)
        except Exception as exc:
            if _is_cuda_oom(exc):
                raise  # train.oom: the batch size, not the code
            raise ForwardFailed(exc, trace.report()) from exc
    model.train(was_training)
    if prediction.shape != depths.shape:
        raise ShapeMismatch(
            f"Model output {tuple(prediction.shape)} does not match target "
            f"{tuple(depths.shape)}\n{trace.report()}"
        )
    loss_fn = loss_fn_factory()
    if not torch.isfinite(loss_fn(prediction, depths)):
        raise FloatingPointError("The loss on the first batch is not finite")
    return loss_fn


_metric_channel: TextIO | None = None


def _metrics_out() -> TextIO:
    """Where ARP-METRIC lines go: harness.job's pipe when it set ARP_METRIC_FD, else stdout."""
    global _metric_channel
    if _metric_channel is None:
        fd = os.environ.get("ARP_METRIC_FD")
        _metric_channel = os.fdopen(int(fd), "w", encoding="utf-8") if fd else sys.stdout
    return _metric_channel


def _emit(stream: TextIO, **record: Any) -> None:
    line = json.dumps({"ts": datetime.now(UTC).isoformat(), **record})
    stream.write(line + "\n")
    stream.flush()
    print(f"ARP-METRIC {line}", file=_metrics_out(), flush=True)


def _run_epoch(
    *,
    model: torch.nn.Module,
    loss_fn: LossFn,
    loader: DataLoader,
    device: torch.device,
    optimizer: torch.optim.Optimizer | None,
    clip_grad_norm: float | None,
    max_steps: int | None,
    epoch: int,
    stream: TextIO,
) -> tuple[dict[str, float | None], int]:
    training = optimizer is not None
    model.train(training)
    metrics = DepthMetrics()
    with torch.set_grad_enabled(training):
        for step, (images, depths) in enumerate(loader):
            if max_steps is not None and step >= max_steps:
                break
            images, depths = images.to(device, non_blocking=True), depths.to(device, non_blocking=True)
            prediction = model(images)
            loss = loss_fn(prediction, depths)
            if not torch.isfinite(loss):
                raise FloatingPointError(f"Non-finite loss at epoch {epoch} step {step}")
            if optimizer is not None:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                if clip_grad_norm is not None:
                    torch.nn.utils.clip_grad_norm_(model.parameters(), clip_grad_norm)
                optimizer.step()
            loss_value = loss.item()
            metrics.update(prediction.detach(), depths, loss_value)
            if training and step % LOG_EVERY_STEPS == 0:
                log.info("epoch %d step %d loss %.4f", epoch, step, loss_value)
                _emit(stream, kind="train_step", epoch=epoch, step=step, loss=loss_value)
    return metrics.compute(), metrics.batches


def run(config: ExperimentConfig, out_dir: Path, config_sha256: str) -> dict[str, Any]:
    _seed_everything(config.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if config.require_gpu and device.type != "cuda":
        raise RuntimeError("This job requires a GPU but CUDA is not available in the sandbox")
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats()

    model, param_count = _build_model(config, device)
    loader_args = {
        "batch_size": config.data.batch_size,
        "num_workers": config.data.num_workers,
        "pin_memory": device.type == "cuda",
    }
    train_set = build_dataset(config.data, "train")
    val_set = build_dataset(config.data, "val")
    dataset_warnings = depth_scale_warnings(train_set, val_set)
    for warning in dataset_warnings:
        log.warning(warning)
    train_loader = DataLoader(train_set, shuffle=True, drop_last=True, **loader_args)
    val_loader = DataLoader(val_set, shuffle=False, **loader_args)

    loss_fn = _smoke_probe(model, lambda: _build_loss(config, device), train_loader, device)
    optimizer = _optimizer(config, model)

    checkpoints = out_dir / "checkpoints"
    checkpoints.mkdir(parents=True, exist_ok=True)
    best_val_loss = float("inf")
    train_metrics: dict[str, float | None] = {}
    val_metrics: dict[str, float | None] = {}
    train_steps = 0
    train_seconds = 0.0

    with (out_dir / "metrics.jsonl").open("a", encoding="utf-8") as stream:
        for epoch in range(config.training.epochs):
            common = {"model": model, "loss_fn": loss_fn, "device": device, "epoch": epoch, "stream": stream}
            started = time.monotonic()
            train_metrics, steps = _run_epoch(
                loader=train_loader,
                optimizer=optimizer,
                clip_grad_norm=config.training.clip_grad_norm,
                max_steps=config.training.max_train_steps,
                **common,
            )
            train_seconds += time.monotonic() - started
            train_steps += steps
            val_metrics, _ = _run_epoch(
                loader=val_loader, optimizer=None, clip_grad_norm=None, max_steps=config.training.max_val_steps, **common
            )
            _emit(stream, kind="epoch", epoch=epoch, train=train_metrics, val=val_metrics)
            log.info("epoch %d train %s val %s", epoch, train_metrics, val_metrics)

            torch.save({"epoch": epoch, "model_state_dict": model.state_dict()}, checkpoints / "last.pt")
            val_loss = val_metrics.get("loss")
            if val_loss is not None and val_loss < best_val_loss:
                best_val_loss = val_loss
                torch.save({"epoch": epoch, "model_state_dict": model.state_dict()}, checkpoints / "best.pt")

    peak_gpu_memory = torch.cuda.max_memory_allocated() if device.type == "cuda" else None
    return {
        "status": "ok",
        "train_metrics": train_metrics,
        "val_metrics": val_metrics,
        "best_val_loss": best_val_loss if best_val_loss != float("inf") else None,
        "dataset_warnings": dataset_warnings,
        "param_count": param_count,
        "steps_per_second": round(train_steps / train_seconds, 3) if train_seconds > 0 else None,
        "peak_gpu_memory_bytes": peak_gpu_memory,
        "provenance": {
            "harness_version": __version__,
            "config_sha256": config_sha256,
            "seed": config.seed,
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "device": torch.cuda.get_device_name(0) if device.type == "cuda" else "cpu",
            "train_samples": len(train_set),
            "val_samples": len(val_set),
        },
    }


def _is_cuda_oom(exc: BaseException) -> bool:
    oom = getattr(torch.cuda, "OutOfMemoryError", None)
    if oom is not None and isinstance(exc, oom):
        return True
    return isinstance(exc, RuntimeError) and "out of memory" in str(exc).lower()


def _error_code(exc: BaseException) -> str:
    if isinstance(exc, GeneratedCodeError):
        return exc.error_code
    if isinstance(exc, FloatingPointError):
        return "train.non_finite"
    if _is_cuda_oom(exc):
        return "train.oom"
    return "train.error"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one sandboxed training job.")
    parser.add_argument("--config", required=True, type=Path, help="Experiment YAML")
    parser.add_argument("--out", default=Path("/workspace/out"), type=Path, help="Output folder")
    parser.add_argument("--dry-run", action="store_true", help="1 epoch, 2 train and 2 val batches")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    args.out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    result: dict[str, Any]
    try:
        raw = args.config.read_bytes()
        config = ExperimentConfig.model_validate(yaml.safe_load(raw))
        if args.dry_run:
            config = config.as_dry_run()
        result = run(config, args.out, hashlib.sha256(raw).hexdigest())
    except Exception as exc:
        log.exception("training failed")
        result = {
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "error_code": _error_code(exc),
            "train_metrics": None,
            "val_metrics": None,
        }
        if isinstance(exc, CodeRefused):
            result["findings"] = [
                {"line": f.line, "code": f.code, "message": f.message} for f in exc.findings
            ]
    result["duration_s"] = round(time.monotonic() - started, 2)
    (args.out / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())

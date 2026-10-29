"""Sandbox entry point: `python -m harness.train --config CONFIG [--out DIR] [--dry-run]`.

Writes, under --out:
  results.json   status ("ok" | "failed"), final metrics (None when not measured), provenance
  metrics.jsonl  one line per logged step and per epoch, for live charts
  checkpoints/   last.pt and best.pt (state dicts only)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import sys
import time
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
from harness.models import build_model
from harness.tasks import DepthMetrics, depth_loss

log = logging.getLogger("harness")
LOG_EVERY_STEPS = 20


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


def _emit(stream: TextIO, **record: Any) -> None:
    stream.write(json.dumps({"ts": datetime.now(UTC).isoformat(), **record}) + "\n")
    stream.flush()


def _run_epoch(
    *,
    config: ExperimentConfig,
    model: torch.nn.Module,
    loader: DataLoader,
    device: torch.device,
    optimizer: torch.optim.Optimizer | None,
    max_steps: int | None,
    epoch: int,
    stream: TextIO,
) -> dict[str, float | None]:
    training = optimizer is not None
    model.train(training)
    metrics = DepthMetrics()
    with torch.set_grad_enabled(training):
        for step, (images, depths) in enumerate(loader):
            if max_steps is not None and step >= max_steps:
                break
            images, depths = images.to(device, non_blocking=True), depths.to(device, non_blocking=True)
            prediction = model(images)
            loss = depth_loss(prediction, depths, config.training.loss)
            if not torch.isfinite(loss):
                raise FloatingPointError(f"Non-finite loss at epoch {epoch} step {step}")
            if optimizer is not None:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                if config.training.clip_grad_norm is not None:
                    torch.nn.utils.clip_grad_norm_(model.parameters(), config.training.clip_grad_norm)
                optimizer.step()
            loss_value = loss.item()
            metrics.update(prediction.detach(), depths, loss_value)
            if training and step % LOG_EVERY_STEPS == 0:
                log.info("epoch %d step %d loss %.4f", epoch, step, loss_value)
                _emit(stream, kind="train_step", epoch=epoch, step=step, loss=loss_value)
    return metrics.compute()


def run(config: ExperimentConfig, out_dir: Path, config_sha256: str) -> dict[str, Any]:
    _seed_everything(config.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if config.require_gpu and device.type != "cuda":
        raise RuntimeError("This job requires a GPU but CUDA is not available in the sandbox")

    model = build_model(config.model.architecture, **config.model.kwargs).to(device)
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
    optimizer = _optimizer(config, model)

    checkpoints = out_dir / "checkpoints"
    checkpoints.mkdir(parents=True, exist_ok=True)
    best_val_loss = float("inf")
    train_metrics: dict[str, float | None] = {}
    val_metrics: dict[str, float | None] = {}

    with (out_dir / "metrics.jsonl").open("a", encoding="utf-8") as stream:
        for epoch in range(config.training.epochs):
            common = {"config": config, "model": model, "device": device, "epoch": epoch, "stream": stream}
            train_metrics = _run_epoch(
                loader=train_loader, optimizer=optimizer, max_steps=config.training.max_train_steps, **common
            )
            val_metrics = _run_epoch(
                loader=val_loader, optimizer=None, max_steps=config.training.max_val_steps, **common
            )
            _emit(stream, kind="epoch", epoch=epoch, train=train_metrics, val=val_metrics)
            log.info("epoch %d train %s val %s", epoch, train_metrics, val_metrics)

            torch.save({"epoch": epoch, "model_state_dict": model.state_dict()}, checkpoints / "last.pt")
            val_loss = val_metrics.get("loss")
            if val_loss is not None and val_loss < best_val_loss:
                best_val_loss = val_loss
                torch.save({"epoch": epoch, "model_state_dict": model.state_dict()}, checkpoints / "best.pt")

    return {
        "status": "ok",
        "train_metrics": train_metrics,
        "val_metrics": val_metrics,
        "best_val_loss": best_val_loss if best_val_loss != float("inf") else None,
        "dataset_warnings": dataset_warnings,
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
            "train_metrics": None,
            "val_metrics": None,
        }
    result["duration_s"] = round(time.monotonic() - started, 2)
    (args.out / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())

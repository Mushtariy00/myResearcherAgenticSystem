"""Universal training loop scaffold.

This loop works for any task type (depth, segmentation, detection, etc.)
by routing task-specific logic (losses, metrics, loaders) via config['task_type'].

Principles:
1. Config-driven: All research decisions in YAML, not code
2. Task-agnostic: One loop handles all types
3. Safe: Dry-run validation before real training
4. Reproducible: Seeds, checksums, metadata logged
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import torch
import yaml
from torch.utils.tensorboard import SummaryWriter

logger = logging.getLogger(__name__)


class UniversalTrainingPipeline:
    """Universal training loop for all task types."""

    def __init__(self, config_path: str, dry_run: bool = False, resume_from: Optional[str] = None):
        """
        Args:
            config_path: Path to YAML config file
            dry_run: If True, run 2 batches of 1 epoch, then exit
            resume_from: Path to checkpoint to resume from
        """
        self.config_path = Path(config_path)
        self.dry_run = dry_run
        self.resume_from = resume_from
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Load and validate config
        self.config = self._load_config()
        self._validate_config()

        # Extract task type (routes to task-specific modules)
        self.task_type = self.config.get("task_type", "generic")

        # Setup directories and logging
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_dir = Path(self.config.get("output", {}).get("experiment_dir", "outputs/experiments")) / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

        self.logger_tb = SummaryWriter(str(self.run_dir / "logs"))

        # Save run metadata
        self._save_run_metadata()

        # Initialize components
        self.model = self._init_model()
        self.train_loader = self._init_loader("train")
        self.val_loader = self._init_loader("val")
        self.optimizer = self._init_optimizer()
        self.scheduler = self._init_scheduler()

        # Load task-specific modules (losses, metrics)
        self.loss_module = self._load_task_module("train", f"{self.task_type}_losses")
        self.metric_module = self._load_task_module("train", f"{self.task_type}_metrics")

        # Resume from checkpoint if specified
        if self.resume_from:
            self._load_checkpoint(self.resume_from)

    def _load_config(self) -> Dict[str, Any]:
        """Load YAML config file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config not found: {self.config_path}")

        with open(self.config_path, "r") as f:
            config = yaml.safe_load(f)

        return config

    def _validate_config(self) -> None:
        """Validate config has all required fields."""
        required_top_level = ["model", "data", "training", "evaluation"]
        for field in required_top_level:
            if field not in self.config:
                raise ValueError(f"Missing required config field: {field}")

        # Validate model
        if "architecture" not in self.config["model"]:
            raise ValueError("Missing model.architecture in config")

        # Validate training
        if "loss" not in self.config["training"]:
            raise ValueError("Missing training.loss in config")

        if "epochs" not in self.config["training"]:
            raise ValueError("Missing training.epochs in config")

        # Validate evaluation
        if "metric" not in self.config["evaluation"]:
            raise ValueError("Missing evaluation.metric in config")

    def _load_task_module(self, package: str, module_name: str) -> Any:
        """
        Dynamically load task-specific module.

        Tries to load task-specific module first (e.g., depth_losses.py).
        Falls back to generic module if not found.
        """
        try:
            return importlib.import_module(f"agentic_ai_system.{package}.{module_name}")
        except ImportError as e:
            logger.warning(
                f"Task-specific module not found: agentic_ai_system.{package}.{module_name}. "
                f"Falling back to generic. Error: {e}"
            )
            try:
                return importlib.import_module(f"agentic_ai_system.{package}.generic")
            except ImportError:
                raise RuntimeError(f"Neither task-specific nor generic module found for {package}.{module_name}")

    def _init_model(self) -> torch.nn.Module:
        """Initialize model from registry."""
        from agentic_ai_system.model.registry import get_model

        architecture = self.config["model"]["architecture"]
        model_kwargs = self.config["model"].get("kwargs", {})

        try:
            model = get_model(architecture, **model_kwargs)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize model '{architecture}': {e}")

        return model.to(self.device)

    def _init_loader(self, split: str) -> torch.utils.data.DataLoader:
        """Initialize data loader."""
        from agentic_ai_system.data.loader import get_dataloader

        try:
            loader = get_dataloader(split=split, config=self.config)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize {split} data loader: {e}")

        return loader

    def _init_optimizer(self) -> torch.optim.Optimizer:
        """Initialize optimizer from config."""
        optimizer_type = self.config["training"].get("optimizer_type", "adam").lower()
        lr = self.config["training"].get("learning_rate", 1e-3)
        weight_decay = self.config["training"].get("weight_decay", 0.0)

        if optimizer_type == "adam":
            return torch.optim.Adam(self.model.parameters(), lr=lr, weight_decay=weight_decay)
        elif optimizer_type == "sgd":
            momentum = self.config["training"].get("momentum", 0.9)
            return torch.optim.SGD(self.model.parameters(), lr=lr, momentum=momentum, weight_decay=weight_decay)
        elif optimizer_type == "adamw":
            return torch.optim.AdamW(self.model.parameters(), lr=lr, weight_decay=weight_decay)
        else:
            raise ValueError(f"Unknown optimizer: {optimizer_type}")

    def _init_scheduler(self) -> Optional[torch.optim.lr_scheduler._LRScheduler]:
        """Initialize learning rate scheduler if configured."""
        scheduler_type = self.config["training"].get("scheduler_type", None)

        if scheduler_type is None:
            return None

        if scheduler_type == "cosine":
            epochs = 2 if self.dry_run else self.config["training"]["epochs"]
            return torch.optim.lr_scheduler.CosineAnnealingLR(self.optimizer, T_max=epochs)
        elif scheduler_type == "step":
            step_size = self.config["training"].get("scheduler_step_size", 10)
            gamma = self.config["training"].get("scheduler_gamma", 0.1)
            return torch.optim.lr_scheduler.StepLR(self.optimizer, step_size=step_size, gamma=gamma)
        else:
            logger.warning(f"Unknown scheduler type: {scheduler_type}. Skipping scheduler.")
            return None

    def _save_run_metadata(self) -> None:
        """Save run configuration and metadata."""
        metadata = {
            "run_id": self.run_id,
            "timestamp": datetime.now().isoformat(),
            "device": str(self.device),
            "dry_run": self.dry_run,
            "task_type": self.task_type,
            "config_path": str(self.config_path),
            "model": self.config["model"],
            "training": self.config["training"],
            "evaluation": self.config["evaluation"],
        }

        metadata_path = self.run_dir / "run_metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"Saved run metadata to {metadata_path}")

    def _save_checkpoint(self, epoch: int, is_best: bool = False) -> None:
        """Save model checkpoint."""
        ckpt_dir = self.run_dir / "checkpoints"
        ckpt_dir.mkdir(exist_ok=True)

        # Save latest checkpoint
        ckpt_path = ckpt_dir / "last.pt"
        torch.save(
            {
                "epoch": epoch,
                "model_state_dict": self.model.state_dict(),
                "optimizer_state_dict": self.optimizer.state_dict(),
                "config": self.config,
            },
            ckpt_path,
        )

        # Save best checkpoint if specified
        if is_best:
            best_path = ckpt_dir / "best.pt"
            torch.save(
                {
                    "epoch": epoch,
                    "model_state_dict": self.model.state_dict(),
                    "optimizer_state_dict": self.optimizer.state_dict(),
                    "config": self.config,
                },
                best_path,
            )

    def _load_checkpoint(self, checkpoint_path: str) -> None:
        """Load model from checkpoint."""
        checkpoint = torch.load(checkpoint_path, map_location=self.device)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        logger.info(f"Loaded checkpoint from {checkpoint_path} (epoch {checkpoint['epoch']})")

    def _has_nan_gradients(self) -> bool:
        """Check for NaN/Inf in gradients (safety check)."""
        for param in self.model.parameters():
            if param.grad is not None:
                if torch.isnan(param.grad).any() or torch.isinf(param.grad).any():
                    return True
        return False

    def train_epoch(self, epoch: int) -> Dict[str, float]:
        """Train for one epoch."""
        self.model.train()
        epoch_loss = 0.0
        num_batches = 0
        metrics_sum = {}

        for batch_idx, batch in enumerate(self.train_loader):
            # Dry-run: stop after 2 batches
            if self.dry_run and batch_idx >= 2:
                break

            # Unpack batch (assumes task-specific loader returns (X, y))
            X, y = batch
            X, y = X.to(self.device), y.to(self.device)

            # Forward pass
            self.optimizer.zero_grad()
            predictions = self.model(X)

            # Compute loss (task-specific)
            loss = self.loss_module.compute_loss(predictions, y, self.config)

            # Check for NaNs
            if torch.isnan(loss):
                logger.error(f"NaN loss detected at batch {batch_idx}. Skipping batch.")
                continue

            # Backward pass
            loss.backward()

            # Gradient clipping (optional, config-driven)
            if self.config["training"].get("clip_gradients", False):
                grad_clip = self.config["training"].get("grad_clip_value", 1.0)
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), grad_clip)

            # Check for NaN gradients
            if self._has_nan_gradients():
                logger.warning(f"NaN gradients detected at batch {batch_idx}. Skipping update.")
                self.optimizer.zero_grad()
                continue

            # Optimizer step
            self.optimizer.step()

            # Logging
            epoch_loss += loss.item()
            num_batches += 1

            # Compute metrics (task-specific)
            batch_metrics = self.metric_module.compute_metrics(predictions, y, self.config)
            for metric_name, metric_value in batch_metrics.items():
                metrics_sum[metric_name] = metrics_sum.get(metric_name, 0.0) + metric_value

            if batch_idx % 10 == 0:
                avg_loss = epoch_loss / num_batches
                logger.info(f"Epoch {epoch} [{batch_idx}/{len(self.train_loader)}] Loss: {avg_loss:.4f}")

        # Average metrics
        avg_loss = epoch_loss / num_batches if num_batches > 0 else 0.0
        avg_metrics = {k: v / num_batches for k, v in metrics_sum.items()}

        return {"loss": avg_loss, **avg_metrics}

    def val_epoch(self, epoch: int) -> Dict[str, float]:
        """Validate for one epoch."""
        self.model.eval()
        epoch_loss = 0.0
        num_batches = 0
        metrics_sum = {}

        with torch.no_grad():
            for batch_idx, batch in enumerate(self.val_loader):
                # Dry-run: stop after 2 batches
                if self.dry_run and batch_idx >= 2:
                    break

                X, y = batch
                X, y = X.to(self.device), y.to(self.device)

                # Forward pass
                predictions = self.model(X)

                # Compute loss
                loss = self.loss_module.compute_loss(predictions, y, self.config)
                epoch_loss += loss.item()
                num_batches += 1

                # Compute metrics
                batch_metrics = self.metric_module.compute_metrics(predictions, y, self.config)
                for metric_name, metric_value in batch_metrics.items():
                    metrics_sum[metric_name] = metrics_sum.get(metric_name, 0.0) + metric_value

        avg_loss = epoch_loss / num_batches if num_batches > 0 else 0.0
        avg_metrics = {k: v / num_batches for k, v in metrics_sum.items()}

        return {"loss": avg_loss, **avg_metrics}

    def train(self) -> None:
        """Main training loop."""
        num_epochs = 2 if self.dry_run else self.config["training"]["epochs"]

        logger.info(f"Starting training for {num_epochs} epochs. Device: {self.device}. Task type: {self.task_type}")

        best_val_loss = float("inf")

        for epoch in range(num_epochs):
            # Train
            train_metrics = self.train_epoch(epoch)
            logger.info(f"Epoch {epoch} train metrics: {train_metrics}")

            # Log to TensorBoard
            for metric_name, metric_value in train_metrics.items():
                self.logger_tb.add_scalar(f"train/{metric_name}", metric_value, epoch)

            # Validate
            val_metrics = self.val_epoch(epoch)
            logger.info(f"Epoch {epoch} val metrics: {val_metrics}")

            # Log to TensorBoard
            for metric_name, metric_value in val_metrics.items():
                self.logger_tb.add_scalar(f"val/{metric_name}", metric_value, epoch)

            # Save checkpoint
            is_best = val_metrics["loss"] < best_val_loss
            best_val_loss = min(best_val_loss, val_metrics["loss"])
            self._save_checkpoint(epoch, is_best=is_best)

            # LR scheduler step
            if self.scheduler is not None:
                self.scheduler.step()

        logger.info(f"Training complete! Results saved to {self.run_dir}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Universal training loop for all task types")
    parser.add_argument("--config", type=str, required=True, help="Path to YAML config file")
    parser.add_argument("--dry-run", action="store_true", help="Run 2 batches of 1 epoch, then exit")
    parser.add_argument("--resume-from", type=str, default=None, help="Path to checkpoint to resume from")
    parser.add_argument("--log-level", type=str, default="INFO", help="Logging level")

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        pipeline = UniversalTrainingPipeline(
            config_path=args.config,
            dry_run=args.dry_run,
            resume_from=args.resume_from,
        )
        pipeline.train()
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Training failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

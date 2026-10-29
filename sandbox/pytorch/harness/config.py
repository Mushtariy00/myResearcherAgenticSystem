"""Typed, bounded experiment config. Agents propose values; the bounds keep jobs small and safe."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelSection(_Strict):
    architecture: str = Field(min_length=1)
    kwargs: dict[str, int | float | str | bool] = Field(default_factory=dict)


class DataSection(_Strict):
    dataset: Literal["nyu2"]
    root: Path
    # Optional list of files per split; "{root}" and "{split}" are substituted.
    split_file_template: str | None = None
    batch_size: int = Field(ge=1, le=64)
    num_workers: int = Field(default=2, ge=0, le=8)
    normalize_rgb: bool = True


class TrainingSection(_Strict):
    loss: Literal["l1", "mse", "smooth_l1"] = "l1"
    epochs: int = Field(ge=1, le=50)
    learning_rate: float = Field(gt=0, le=1.0)
    optimizer: Literal["adam", "adamw", "sgd"] = "adam"
    weight_decay: float = Field(default=0.0, ge=0, le=1.0)
    clip_grad_norm: float | None = Field(default=None, gt=0)
    # Caps per epoch, for smoke tests and bounded jobs. None means the full split.
    max_train_steps: int | None = Field(default=None, ge=1)
    max_val_steps: int | None = Field(default=None, ge=1)


class ExperimentConfig(_Strict):
    task: Literal["nyu2_depth"]
    seed: int = 42
    require_gpu: bool = True
    model: ModelSection
    data: DataSection
    training: TrainingSection

    def as_dry_run(self) -> ExperimentConfig:
        """Two train and two validation batches of one epoch: proves the pipeline end to end."""
        training = self.training.model_copy(update={"epochs": 1, "max_train_steps": 2, "max_val_steps": 2})
        return self.model_copy(update={"training": training})

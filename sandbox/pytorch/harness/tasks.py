"""Task losses and metrics. Metrics belong to the harness so generated code cannot fake them."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import torch
from torch.nn import functional as F

MIN_VALID_DEPTH_M = 1e-3  # zero depth marks missing sensor readings


def depth_loss(prediction: torch.Tensor, target: torch.Tensor, kind: str) -> torch.Tensor:
    mask = target > MIN_VALID_DEPTH_M
    if not mask.any():
        raise ValueError("Batch has no valid depth pixels")
    pred, true = prediction[mask], target[mask]
    if kind == "mse":
        return F.mse_loss(pred, true)
    if kind == "smooth_l1":
        return F.smooth_l1_loss(pred, true)
    return F.l1_loss(pred, true)


@dataclass
class DepthMetrics:
    """Accumulates exact RMSE / MAE / AbsRel over all valid pixels of a split."""

    squared_error: float = 0.0
    absolute_error: float = 0.0
    relative_error: float = 0.0
    pixels: int = 0
    loss_sum: float = 0.0
    batches: int = field(default=0)

    @torch.no_grad()
    def update(self, prediction: torch.Tensor, target: torch.Tensor, loss: float) -> None:
        mask = target > MIN_VALID_DEPTH_M
        diff = prediction[mask] - target[mask]
        self.squared_error += float((diff**2).sum())
        self.absolute_error += float(diff.abs().sum())
        self.relative_error += float((diff.abs() / target[mask]).sum())
        self.pixels += int(mask.sum())
        self.loss_sum += loss
        self.batches += 1

    def compute(self) -> dict[str, float | None]:
        # None (not 0.0) when nothing was measured: the legacy runner reported fake zeros.
        if self.pixels == 0 or self.batches == 0:
            return {"loss": None, "rmse": None, "mae": None, "abs_rel": None}
        return {
            "loss": self.loss_sum / self.batches,
            "rmse": math.sqrt(self.squared_error / self.pixels),
            "mae": self.absolute_error / self.pixels,
            "abs_rel": self.relative_error / self.pixels,
        }

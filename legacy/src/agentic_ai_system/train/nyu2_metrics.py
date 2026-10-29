"""NYU2 depth metrics."""

from __future__ import annotations

import torch


def compute_metrics(predictions: torch.Tensor, targets: torch.Tensor, config: dict) -> dict[str, float]:
    mse = torch.nn.functional.mse_loss(predictions, targets)
    rmse = torch.sqrt(mse)
    mae = torch.nn.functional.l1_loss(predictions, targets)
    return {
        "rmse": rmse.item(),
        "mae": mae.item(),
    }

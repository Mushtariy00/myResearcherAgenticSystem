"""NYU2 depth losses."""

from __future__ import annotations

import torch


def compute_loss(predictions: torch.Tensor, targets: torch.Tensor, config: dict) -> torch.Tensor:
    loss_type = config.get("training", {}).get("loss", "l1").lower()
    if loss_type == "mse":
        return torch.nn.functional.mse_loss(predictions, targets)
    if loss_type == "smooth_l1":
        return torch.nn.functional.smooth_l1_loss(predictions, targets)
    return torch.nn.functional.l1_loss(predictions, targets)

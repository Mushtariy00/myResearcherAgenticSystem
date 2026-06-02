"""Generic task-agnostic losses for smoke testing.

Task-specific losses are implemented in {task_type}_losses.py modules.
This generic module provides fallback implementations.
"""

from __future__ import annotations

import torch
from typing import Any


def compute_loss(predictions: torch.Tensor, targets: torch.Tensor, config: dict) -> torch.Tensor:
    """
    Generic loss computation.

    Args:
        predictions: Model output tensor
        targets: Ground truth tensor
        config: Training config dict

    Returns:
        Scalar loss tensor
    """
    loss_type = config.get("training", {}).get("loss", "mse").lower()

    if loss_type == "mse":
        return torch.nn.functional.mse_loss(predictions, targets)
    elif loss_type == "l1":
        return torch.nn.functional.l1_loss(predictions, targets)
    elif loss_type == "smooth_l1":
        return torch.nn.functional.smooth_l1_loss(predictions, targets)
    else:
        # Default to MSE
        return torch.nn.functional.mse_loss(predictions, targets)

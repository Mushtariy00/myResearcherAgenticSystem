"""Generic task-agnostic metrics for smoke testing.

Task-specific metrics are implemented in {task_type}_metrics.py modules.
This generic module provides fallback implementations.
"""

from __future__ import annotations

import torch
from typing import Any, Dict


def compute_metrics(predictions: torch.Tensor, targets: torch.Tensor, config: dict) -> Dict[str, float]:
    """
    Generic metrics computation.

    Args:
        predictions: Model output tensor
        targets: Ground truth tensor
        config: Training config dict

    Returns:
        Dict of metric_name -> metric_value
    """
    # Compute MSE as default metric
    mse = torch.nn.functional.mse_loss(predictions, targets).item()

    # Compute MAE as fallback
    mae = torch.nn.functional.l1_loss(predictions, targets).item()

    return {
        "mse": mse,
        "mae": mae,
    }

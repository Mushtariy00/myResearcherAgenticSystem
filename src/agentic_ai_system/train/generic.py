"""Generic fallback for losses and metrics."""

from __future__ import annotations

from .generic_losses import compute_loss
from .generic_metrics import compute_metrics

__all__ = ["compute_loss", "compute_metrics"]

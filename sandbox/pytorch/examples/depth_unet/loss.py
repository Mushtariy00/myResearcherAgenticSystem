"""A masked depth loss, written to the generated-code contract.

forward(prediction, target, valid_mask) returns a scalar. The harness supplies valid_mask and keeps
computing its own metrics, so a custom loss can shape training but cannot fake the reported numbers.
"""

from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F

MIN_VALID = 1e-6


class Loss(nn.Module):
    """L1 on the valid pixels plus a small scale-invariant log term (Eigen et al., 2014)."""

    def __init__(self, si_weight: float = 0.5) -> None:
        super().__init__()
        self.si_weight = si_weight

    def forward(
        self, prediction: torch.Tensor, target: torch.Tensor, valid_mask: torch.Tensor
    ) -> torch.Tensor:
        mask = valid_mask & (target > MIN_VALID)
        if not bool(mask.any()):
            return prediction.sum() * 0.0
        pred = prediction[mask].clamp_min(MIN_VALID)
        true = target[mask]
        log_diff = torch.log(pred) - torch.log(true)
        scale_invariant = log_diff.pow(2).mean() - self.si_weight * log_diff.mean().pow(2)
        return F.l1_loss(pred, true) + scale_invariant.clamp_min(0.0)

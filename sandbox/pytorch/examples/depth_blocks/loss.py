"""The scale-invariant log loss plus an edge term, from the harness's blocks (harness.blocks)."""

from __future__ import annotations

import torch
from torch import nn

from harness.blocks import gradient_loss, silog_loss

GRADIENT_WEIGHT = 0.5


class Loss(nn.Module):
    def forward(
        self, prediction: torch.Tensor, target: torch.Tensor, valid_mask: torch.Tensor
    ) -> torch.Tensor:
        edges = gradient_loss(prediction, target, valid_mask)
        return silog_loss(prediction, target, valid_mask) + GRADIENT_WEIGHT * edges

"""A model that passes the checker but downsamples by 2 and never upsamples.

Its output is (B, 1, H/2, W/2), so the harness's first-batch shape check fails with error_code
code.shape_mismatch. Used by the smoke test.
"""

from __future__ import annotations

import torch
from torch import nn


class Model(nn.Module):
    def __init__(self, base_channels: int = 16) -> None:
        super().__init__()
        self.stem = nn.Conv2d(3, base_channels, kernel_size=3, stride=2, padding=1)
        self.head = nn.Conv2d(base_channels, 1, kernel_size=1)

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        return self.head(self.stem(image))

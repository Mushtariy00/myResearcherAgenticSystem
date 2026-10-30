"""A small U-Net-style depth model, written to the generated-code contract.

It maps a (B, 3, H, W) RGB batch to (B, 1, H, W) metric depth, at the same resolution. Only the
allowed imports are used, there are no underscore attributes beyond super().__init__, and it does
no I/O: the harness owns the data, the metrics and the training loop.
"""

from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F


class ConvBlock(nn.Module):
    """A 3x3 convolution with GroupNorm (stable at the small batch sizes a 6 GB GPU allows)."""

    def __init__(self, in_channels: int, out_channels: int) -> None:
        super().__init__()
        self.body = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.GroupNorm(8, out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.body(x)


class Model(nn.Module):
    """One downsampling stage with a skip connection, upsampled back to the input resolution."""

    def __init__(self, base_channels: int = 16, max_depth: float = 10.0) -> None:
        super().__init__()
        self.max_depth = max_depth
        self.stem = ConvBlock(3, base_channels)
        self.down = ConvBlock(base_channels, base_channels * 2)
        self.up = ConvBlock(base_channels * 2 + base_channels, base_channels)
        self.head = nn.Conv2d(base_channels, 1, kernel_size=1)

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        skip = self.stem(image)
        hidden = self.down(F.max_pool2d(skip, kernel_size=2))
        hidden = F.interpolate(hidden, size=skip.shape[-2:], mode="bilinear", align_corners=False)
        fused = self.up(torch.cat([hidden, skip], dim=1))
        return self.max_depth * torch.sigmoid(self.head(fused))

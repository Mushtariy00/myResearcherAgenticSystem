"""A model whose decoder gets its skip's channel count wrong: it says 32, the encoder's middle stage
gives 24. Its first forward pass fails, and the harness reports where, with the shapes
(harness.trace): scripts/sandbox-smoke.sh checks the report.
"""

from __future__ import annotations

import torch
from torch import nn

from harness.blocks import DepthHead, Encoder, UpBlock


class Model(nn.Module):
    def __init__(self, base_channels: int = 16, max_depth: float = 10.0) -> None:
        super().__init__()
        self.encoder = Encoder(channels=(base_channels, 24, 32), depths=(1, 2, 2))
        self.up = UpBlock(32, 32, 16)  # wrong: the stage before the last has 24 channels
        self.head = DepthHead(16, max_depth)

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        f0, f1, f2 = self.encoder(image)
        return self.head(self.up(f2, f1), image.shape[-2:])

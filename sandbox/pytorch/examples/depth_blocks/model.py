"""A small encoder-decoder depth model built from the harness's blocks (harness.blocks).

A MobileNet-style encoder, self-attention on its coarsest stage, a decoder that fuses each finer
stage and then the image itself, and a metric depth head. The blocks keep the shapes right; the
model only wires them. The coding prompt shows it as the example (agentic_worker.coding.code).
"""

from __future__ import annotations

import torch
from torch import nn

from harness.blocks import DepthHead, Encoder, FeatureAttention, GuidedUpsample, UpBlock


class Model(nn.Module):
    def __init__(self, base_channels: int = 16, max_depth: float = 10.0, heads: int = 4) -> None:
        super().__init__()
        c = base_channels
        self.encoder = Encoder(channels=(c, 2 * c, 3 * c, 4 * c, 6 * c))  # strides 2 to 32
        self.attention = FeatureAttention(6 * c, heads=heads)  # 15 x 20 positions at 480 x 640
        self.up3 = UpBlock(6 * c, 4 * c, 4 * c)
        self.up2 = UpBlock(4 * c, 3 * c, 3 * c)
        self.up1 = UpBlock(3 * c, 2 * c, 2 * c)
        self.up0 = UpBlock(2 * c, c, c)
        self.refine = GuidedUpsample(c, 3, c)  # back to the full frame, guided by the image
        self.head = DepthHead(c, max_depth)

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        f0, f1, f2, f3, f4 = self.encoder(image)
        x = self.attention(f4)
        x = self.up3(x, f3)
        x = self.up2(x, f2)
        x = self.up1(x, f1)
        x = self.up0(x, f0)
        x = self.refine(x, image)
        return self.head(x, image.shape[-2:])

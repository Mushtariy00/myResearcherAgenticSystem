"""Simple NYU2 depth architectures."""

from __future__ import annotations

import torch
import torch.nn as nn

from .registry import register_architecture


class SimpleDepthNet(nn.Module):
    """Lightweight encoder-decoder for depth prediction."""

    def __init__(self, input_dim: int = 3, base_channels: int = 16, output_dim: int = 1):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Conv2d(input_dim, base_channels, kernel_size=3, padding=1),
            nn.ReLU(inplace=True),
            nn.Conv2d(base_channels, base_channels * 2, kernel_size=3, stride=2, padding=1),
            nn.ReLU(inplace=True),
            nn.Conv2d(base_channels * 2, base_channels * 4, kernel_size=3, stride=2, padding=1),
            nn.ReLU(inplace=True),
        )
        self.decoder = nn.Sequential(
            nn.ConvTranspose2d(base_channels * 4, base_channels * 2, kernel_size=4, stride=2, padding=1),
            nn.ReLU(inplace=True),
            nn.ConvTranspose2d(base_channels * 2, base_channels, kernel_size=4, stride=2, padding=1),
            nn.ReLU(inplace=True),
            nn.Conv2d(base_channels, output_dim, kernel_size=1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        features = self.encoder(x)
        return self.decoder(features)


register_architecture("nyu2_simple", SimpleDepthNet)

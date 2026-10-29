"""Model registry. Phase 3 adds allowlisted, generated model modules next to the built-in ones."""

from __future__ import annotations

from typing import Any

import torch
from torch import nn


class SimpleDepthNet(nn.Module):
    """Lightweight encoder-decoder for depth prediction (ported from the legacy nyu2_simple)."""

    def __init__(self, input_dim: int = 3, base_channels: int = 16, output_dim: int = 1) -> None:
        super().__init__()
        c = base_channels
        self.encoder = nn.Sequential(
            nn.Conv2d(input_dim, c, kernel_size=3, padding=1),
            nn.ReLU(inplace=True),
            nn.Conv2d(c, c * 2, kernel_size=3, stride=2, padding=1),
            nn.ReLU(inplace=True),
            nn.Conv2d(c * 2, c * 4, kernel_size=3, stride=2, padding=1),
            nn.ReLU(inplace=True),
        )
        self.decoder = nn.Sequential(
            nn.ConvTranspose2d(c * 4, c * 2, kernel_size=4, stride=2, padding=1),
            nn.ReLU(inplace=True),
            nn.ConvTranspose2d(c * 2, c, kernel_size=4, stride=2, padding=1),
            nn.ReLU(inplace=True),
            nn.Conv2d(c, output_dim, kernel_size=1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.decoder(self.encoder(x))


ARCHITECTURES: dict[str, type[nn.Module]] = {"nyu2_simple": SimpleDepthNet}


def build_model(architecture: str, **kwargs: Any) -> nn.Module:
    try:
        model_class = ARCHITECTURES[architecture]
    except KeyError:
        available = ", ".join(sorted(ARCHITECTURES))
        raise ValueError(f"Unknown architecture '{architecture}'. Available: {available}") from None
    return model_class(**kwargs)

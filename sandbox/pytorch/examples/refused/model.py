"""A model that breaks the contract by importing a forbidden module.

The allowlist checker refuses it (import of 'os'), so the harness fails with error_code
code.refused and never trains. Used by the smoke test.
"""

from __future__ import annotations

import os

import torch
from torch import nn


class Model(nn.Module):
    def __init__(self, base_channels: int = 16) -> None:
        super().__init__()
        self.head = nn.Conv2d(3, 1, kernel_size=1)
        self.workdir = os.getcwd()

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        return self.head(image)

"""Model registry: maps architecture names to model classes.

This is where all architectures (depth, segmentation, detection) are registered.
Task-specific architectures are registered here but imported from their modules.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Type

import torch.nn as nn

logger = logging.getLogger(__name__)

# Registry: architecture_name -> model_class
REGISTERED_ARCHITECTURES: Dict[str, Type[nn.Module]] = {}


def register_architecture(name: str, model_class: Type[nn.Module]) -> None:
    """Register a model architecture."""
    if name in REGISTERED_ARCHITECTURES:
        logger.warning(f"Architecture '{name}' is already registered. Overwriting...")
    REGISTERED_ARCHITECTURES[name] = model_class
    logger.info(f"Registered architecture: {name}")


def get_model(architecture: str, **kwargs) -> nn.Module:
    """Get model class from registry and instantiate it."""
    if architecture not in REGISTERED_ARCHITECTURES:
        available = ", ".join(sorted(REGISTERED_ARCHITECTURES.keys()))
        raise ValueError(
            f"Unknown architecture: '{architecture}'. "
            f"Available architectures: {available}"
        )

    model_class = REGISTERED_ARCHITECTURES[architecture]
    try:
        model = model_class(**kwargs)
        logger.info(f"Initialized model: {architecture}")
        return model
    except Exception as e:
        raise RuntimeError(f"Failed to instantiate model '{architecture}' with kwargs {kwargs}: {e}")


def list_architectures() -> list[str]:
    """List all registered architectures."""
    return sorted(REGISTERED_ARCHITECTURES.keys())


# Placeholder: import task-specific architectures
# These imports will register architectures via @register_architecture decorator
# Example:
# from agentic_ai_system.model.depth_architectures import *
# from agentic_ai_system.model.segmentation_architectures import *
# from agentic_ai_system.model.detection_architectures import *
from agentic_ai_system.model.nyu2_architectures import *  # noqa: F401,F403

# For now, register a dummy model for smoke testing
class DummyModel(nn.Module):
    """Minimal model for smoke testing."""

    def __init__(self, input_dim: int = 3, output_dim: int = 1, **kwargs):
        super().__init__()
        self.proj = nn.Conv2d(input_dim, output_dim, kernel_size=1)

    def forward(self, x):
        return self.proj(x)


register_architecture("dummy", DummyModel)

"""Universal data loading interface.

Routes to task-specific loaders based on config['task_type'].
All loaders must implement the same interface: __getitem__ and __len__.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Optional

import torch
from torch.utils.data import DataLoader, Dataset

logger = logging.getLogger(__name__)


class SyntheticDataset(Dataset):
    """Synthetic dataset for smoke testing."""

    def __init__(self, split: str = "train", config: Optional[dict] = None, num_samples: int = 16):
        self.split = split
        self.config = config or {}
        self.num_samples = num_samples

        # Get input/output shapes from config or use defaults
        self.input_shape = tuple(self.config.get("data", {}).get("input_shape", [3, 224, 224]))
        self.output_shape = tuple(self.config.get("data", {}).get("output_shape", [1, 224, 224]))

    def __len__(self) -> int:
        return self.num_samples

    def __getitem__(self, idx: int):
        # Generate random tensors of correct shape
        X = torch.randn(self.input_shape)
        y = torch.randn(self.output_shape)
        return X, y


def get_dataloader(split: str = "train", config: Optional[dict] = None) -> DataLoader:
    """
    Universal data loader factory.

    Routes to task-specific loader if available, otherwise uses synthetic data.
    """
    if config is None:
        config = {}

    task_type = config.get("task_type", "generic")
    batch_size = config.get("data", {}).get("batch_size", 32)
    num_workers = config.get("data", {}).get("num_workers", 0)
    synthetic = config.get("data", {}).get("synthetic", True)

    # Try to load task-specific loader
    if not synthetic:
        try:
            loader_module = importlib.import_module(f"agentic_ai_system.data.{task_type}_loader")
            if hasattr(loader_module, "get_dataset"):
                dataset = loader_module.get_dataset(split=split, config=config)
                logger.info(f"Loaded task-specific dataset: {task_type}")
                return DataLoader(dataset, batch_size=batch_size, num_workers=num_workers, shuffle=(split == "train"))
        except ImportError as e:
            logger.warning(
                f"Task-specific loader not found for {task_type}. Falling back to synthetic. Error: {e}"
            )

    # Fallback to synthetic data
    logger.info(f"Using synthetic data for {split} split (task_type={task_type})")
    dataset = SyntheticDataset(split=split, config=config)
    return DataLoader(dataset, batch_size=batch_size, num_workers=num_workers, shuffle=(split == "train"))

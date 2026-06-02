"""NYU2 metric-ready dataset loader."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import h5py
import numpy as np
import torch
from torch.utils.data import Dataset


def _resolve_path(raw_path: str, root: Optional[str], split: str) -> Path:
    candidate = Path(raw_path)
    if candidate.exists():
        return candidate

    if raw_path.startswith("/mnt/windows_d/"):
        rewritten = Path(raw_path.replace("/mnt/windows_d/", "/mnt/d/"))
        if rewritten.exists():
            return rewritten

    if root:
        filename = Path(raw_path).name
        fallback = Path(root) / "h5" / split / filename
        if fallback.exists():
            return fallback

    return candidate


def _split_file_path(split: str, config: dict) -> Optional[Path]:
    data_cfg = config.get("data", {})
    template = data_cfg.get("split_file_template")
    if template:
        return Path(template.format(split=split))
    if data_cfg.get("split_file"):
        return Path(data_cfg["split_file"])
    return None


def _collect_files(split: str, config: dict) -> list[Path]:
    data_cfg = config.get("data", {})
    root = data_cfg.get("root")
    split_file = _split_file_path(split, config)
    if split_file and split_file.exists():
        raw_lines = [line.strip() for line in split_file.read_text().splitlines() if line.strip()]
        return [_resolve_path(line, root, split) for line in raw_lines]

    if not root:
        raise ValueError("NYU2 loader requires data.root or a split file.")

    split_dir = Path(root) / "h5" / split
    if not split_dir.exists():
        raise FileNotFoundError(f"NYU2 split directory not found: {split_dir}")

    return sorted(split_dir.glob("*.h5"))


class NYU2MetricDataset(Dataset):
    """Loads NYU2 metric-ready RGB/depth pairs from H5 files."""

    def __init__(self, split: str = "train", config: Optional[dict] = None):
        self.split = split
        self.config = config or {}
        self.files = _collect_files(split, self.config)
        self.normalize_rgb = self.config.get("data", {}).get("normalize_rgb", True)

    def __len__(self) -> int:
        return len(self.files)

    def __getitem__(self, idx: int):
        path = self.files[idx]
        with h5py.File(path, "r") as f:
            rgb = f["rgb"][:]
            depth = f["depth"][:]

        if rgb.ndim == 3 and rgb.shape[0] not in (1, 3) and rgb.shape[-1] in (1, 3):
            rgb = np.transpose(rgb, (2, 0, 1))

        rgb = rgb.astype(np.float32)
        if self.normalize_rgb:
            rgb = rgb / 255.0

        depth = depth.astype(np.float32)
        if depth.ndim == 2:
            depth = depth[None, :, :]

        return torch.from_numpy(rgb), torch.from_numpy(depth)


def get_dataset(split: str = "train", config: Optional[dict] = None) -> Dataset:
    return NYU2MetricDataset(split=split, config=config)

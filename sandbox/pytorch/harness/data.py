"""Datasets owned by the harness. Generated code never touches data loading or splits."""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import torch
from torch.utils.data import Dataset

from harness.config import DataSection


class NYU2Dataset(Dataset[tuple[torch.Tensor, torch.Tensor]]):
    """NYU Depth v2 "metric-ready" H5 files with `rgb` (HxWx3 uint8) and `depth` (HxW, meters)."""

    def __init__(self, root: Path, split: str, split_file: Path | None, normalize_rgb: bool) -> None:
        self.files = _list_files(root, split, split_file)
        if not self.files:
            raise FileNotFoundError(f"No NYU2 files for split '{split}' under {root}")
        self.normalize_rgb = normalize_rgb

    def __len__(self) -> int:
        return len(self.files)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        path = self.files[index]
        if not path.is_file():
            raise FileNotFoundError(f"Dataset file missing: {path}")
        with h5py.File(path, "r") as handle:
            rgb = np.asarray(handle["rgb"])
            depth = np.asarray(handle["depth"])

        if rgb.ndim == 3 and rgb.shape[0] not in (1, 3) and rgb.shape[-1] in (1, 3):
            rgb = np.transpose(rgb, (2, 0, 1))
        rgb = rgb.astype(np.float32)
        if self.normalize_rgb:
            rgb /= 255.0
        depth = depth.astype(np.float32)
        if depth.ndim == 2:
            depth = depth[None, :, :]
        return torch.from_numpy(rgb), torch.from_numpy(depth)


def _list_files(root: Path, split: str, split_file: Path | None) -> list[Path]:
    if split_file is not None and split_file.is_file():
        # Split files list absolute paths from the machine that built the dataset. Inside the
        # sandbox the dataset is mounted at `root`, so keep only the file names. Existence is
        # checked lazily: stat-ing 50k files up front is slow on network or WSL drives.
        names = [Path(line.strip()).name for line in split_file.read_text().splitlines() if line.strip()]
        return [root / "h5" / split / name for name in names]
    return sorted((root / "h5" / split).glob("*.h5"))


def depth_scale_warnings(train: NYU2Dataset, val: NYU2Dataset, samples: int = 8) -> list[str]:
    """Spot-check that both splits use the same depth units (the data contract says meters).

    A unit mismatch makes every validation metric meaningless, so it is reported in results.json.
    """
    train_median = _median_depth(train, samples)
    val_median = _median_depth(val, samples)
    ratio = max(train_median, val_median) / max(min(train_median, val_median), 1e-6)
    if ratio <= 4:
        return []
    return [
        f"Depth scale differs between splits: median train {train_median:.3f} vs val "
        f"{val_median:.3f} (about x{ratio:.0f}). Check the dataset units before trusting val metrics."
    ]


def _median_depth(dataset: NYU2Dataset, samples: int) -> float:
    stride = max(len(dataset) // samples, 1)
    medians = [float(dataset[i][1].median()) for i in range(0, len(dataset), stride)[:samples]]
    return float(np.median(medians))


def build_dataset(data: DataSection, split: str) -> NYU2Dataset:
    split_file = None
    if data.split_file_template:
        split_file = Path(data.split_file_template.format(root=data.root, split=split))
    return NYU2Dataset(data.root, split, split_file, data.normalize_rgb)

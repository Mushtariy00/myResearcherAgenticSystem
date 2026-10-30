"""A copy of the lab's NYU2 metric-ready export with the training split's depth in metres.

The export's training depths are the NYU2 training set's 8-bit PNG depth values divided by 1000,
as if they were millimetres like the validation set's 16-bit PNGs. The training set's PNGs hold
depth as value / 255 x 10 m. So every training depth is a multiple of 0.001 no larger than
0.255, and the fix is exact: metres = stored x 1000 / 255 x 10. The harness flagged it: median
training depth 0.076 against 2.75 m for validation.

The validation split, the RGB images and the split files are copied unchanged; the source is
only read. A training file whose depths don't fit the pattern stops the copy rather than being
guessed at. Files are written under a temporary name and renamed, so a run that stops can be
started again and goes on where it was.

Runs in the sandbox image, which has h5py (make nyu2-fix).
Usage: python nyu2-fix-depth.py SOURCE DEST [--workers N]
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import h5py
import numpy as np

SCALE = np.float32(10000 / 255)  # stored (8-bit PNG value / 1000) to metres
LARGEST_STORED = 0.2555  # 255 / 1000, with float32 slack


def fix_training_file(source: Path, dest: Path) -> float:
    """Write ``source`` to ``dest`` with its depth in metres; the median depth after."""
    tmp = dest.with_name(f".{dest.name}.tmp")
    with h5py.File(source, "r") as src:
        depth = np.asarray(src["depth"], dtype=np.float32)
        if depth.max() > LARGEST_STORED:
            raise ValueError(f"{source.name}: depth up to {depth.max()}, not 8-bit values / 1000")
        with h5py.File(tmp, "w") as out:
            for key in src:
                stored = src[key]
                values = depth * SCALE if key == "depth" else np.asarray(stored)
                out.create_dataset(
                    key,
                    data=values.astype(stored.dtype),
                    chunks=stored.chunks,
                    compression=stored.compression,
                    compression_opts=stored.compression_opts,
                    shuffle=stored.shuffle,
                    fletcher32=stored.fletcher32,
                )
            for name, value in src.attrs.items():
                out.attrs[name] = value
    os.replace(tmp, dest)
    valid = depth[depth > 1e-3]
    return float(np.median(valid) * SCALE) if valid.size else 0.0


def copy_file(source: Path, dest: Path) -> float:
    tmp = dest.with_name(f".{dest.name}.tmp")
    shutil.copyfile(source, tmp)
    os.replace(tmp, dest)
    return 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("source", type=Path)
    parser.add_argument("dest", type=Path)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    started = time.monotonic()
    shutil.copytree(args.source / "splits", args.dest / "splits", dirs_exist_ok=True)
    medians: list[float] = []
    for split, work in (("val", copy_file), ("train", fix_training_file)):
        source_dir, dest_dir = args.source / "h5" / split, args.dest / "h5" / split
        dest_dir.mkdir(parents=True, exist_ok=True)
        names = sorted(path.name for path in source_dir.glob("*.h5"))
        todo = [name for name in names if not (dest_dir / name).exists()]
        print(f"{split}: {len(names)} files, {len(names) - len(todo)} done before", flush=True)
        with ProcessPoolExecutor(args.workers) as pool:
            jobs = pool.map(
                work,
                [source_dir / name for name in todo],
                [dest_dir / name for name in todo],
                chunksize=16,
            )
            for done, median in enumerate(jobs, start=1):
                if split == "train":
                    medians.append(median)
                if done % 2000 == 0 or done == len(todo):
                    minutes = (time.monotonic() - started) / 60
                    print(f"  {split}: {done}/{len(todo)} in {minutes:.1f} min", flush=True)
    (args.dest / "FIXED.txt").write_text(
        "A copy of the NYU2 metric-ready export with the training split's depth in metres:\n"
        "stored x 1000 / 255 x 10 (it held 8-bit PNG values / 1000). Made by\n"
        "scripts/nyu2-fix-depth.py from the export as it was; validation copied unchanged.\n"
    )
    if medians:
        print(
            f"training depth after the fix: median of the files' medians {np.median(medians):.3f} m"
        )
    print(f"done in {(time.monotonic() - started) / 60:.1f} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())

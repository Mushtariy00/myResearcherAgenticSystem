"""Train the generated Survey monocular depth estimation 2023-2025 scaffold."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from lct_depth.lct_depth_model import build_model


def main() -> None:
    model = build_model()
    sample = "monocular depth estimation scaffold"
    print("trainable scaffold ready")
    print(f"prediction: {model.predict(sample)}")


if __name__ == "__main__":
    main()

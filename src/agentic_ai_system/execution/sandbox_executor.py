from __future__ import annotations

import json
import py_compile
import re
import subprocess
from datetime import datetime
from pathlib import Path

from agentic_ai_system.schemas.models import CodingExecutionResult, CodingStageOutput, MethodStageOutput


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "topic"


def _default_file_list() -> list[str]:
    return [
        "src/lct_depth/__init__.py",
        "src/lct_depth/conv_encoder.py",
        "src/lct_depth/token_sparsifier.py",
        "src/lct_depth/decoder.py",
        "src/lct_depth/lct_depth_model.py",
        "train_lct_depth.py",
        "benchmark.py",
        "README.md",
    ]


def _content_for_init() -> str:
    return '"""Generated research package."""\n'


def _content_for_conv_encoder(topic: str) -> str:
    return f'''"""Feature encoder for the {topic} scaffold."""

from __future__ import annotations


class ConvEncoder:
    def __init__(self) -> None:
        self.name = "ConvEncoder"

    def encode(self, sample: str) -> list[str]:
        return [token for token in sample.lower().split() if token]
'''


def _content_for_token_sparsifier(topic: str) -> str:
    return f'''"""Token sparsifier for the {topic} scaffold."""

from __future__ import annotations


class TokenSparsifier:
    def __init__(self, keep_ratio: float = 0.3) -> None:
        self.keep_ratio = keep_ratio

    def sparsify(self, tokens: list[str]) -> list[str]:
        if not tokens:
            return []
        count = max(1, int(len(tokens) * self.keep_ratio))
        return tokens[:count]
'''


def _content_for_decoder(topic: str) -> str:
    return f'''"""Output decoder for the {topic} scaffold."""

from __future__ import annotations


class DepthDecoder:
    def __init__(self) -> None:
        self.name = "DepthDecoder"

    def decode(self, features: list[str]) -> str:
        return " | ".join(features) if features else "no-features"
'''


def _content_for_lct_depth_model(topic: str, method_output: MethodStageOutput) -> str:
    focus = method_output.implementation_focus or method_output.recommended_option or "n/a"
    return f'''"""End-to-end depth model scaffold for {topic}."""

from __future__ import annotations

from .conv_encoder import ConvEncoder
from .decoder import DepthDecoder
from .token_sparsifier import TokenSparsifier


class LCTDepthModel:
    def __init__(self) -> None:
        self.encoder = ConvEncoder()
        self.sparsifier = TokenSparsifier()
        self.decoder = DepthDecoder()
        self.recommended_method = {focus!r}

    def predict(self, sample: str) -> str:
        features = self.encoder.encode(sample)
        sparse_features = self.sparsifier.sparsify(features)
        return self.decoder.decode(sparse_features)


def build_model() -> LCTDepthModel:
    return LCTDepthModel()
'''


def _content_for_train_script(topic: str) -> str:
    return f'''"""Train the generated {topic} scaffold."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from lct_depth.lct_depth_model import build_model


def main() -> None:
    model = build_model()
    sample = "monocular depth estimation scaffold"
    print("trainable scaffold ready")
    print(f"prediction: {{model.predict(sample)}}")


if __name__ == "__main__":
    main()
'''


def _content_for_benchmark(topic: str) -> str:
    return f'''"""Benchmark the generated {topic} scaffold."""

from __future__ import annotations

import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from lct_depth.lct_depth_model import build_model


def main() -> None:
    model = build_model()
    sample = "monocular depth estimation scaffold benchmark"
    t0 = time.perf_counter()
    y = model.predict(sample)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    print(f"latency_ms={{elapsed_ms:.3f}}")
    print(f"prediction={{y}}")


if __name__ == "__main__":
    main()
'''


def _content_for_readme(topic: str, method_output: MethodStageOutput) -> str:
    return (
        "# Sandbox Artifact\n\n"
        f"Topic: {topic}\n\n"
        f"Recommended method: {method_output.implementation_focus or method_output.recommended_option or 'n/a'}\n\n"
        "Run:\n"
        "```bash\n"
        "python train_lct_depth.py\n"
        "python benchmark.py\n"
        "```\n"
    )


def _content_for_file(path: str, topic: str, method_output: MethodStageOutput) -> str:
    name = Path(path).name.lower()
    if name == "__init__.py":
        return _content_for_init()
    if name == "conv_encoder.py":
        return _content_for_conv_encoder(topic)
    if name == "token_sparsifier.py":
        return _content_for_token_sparsifier(topic)
    if name == "decoder.py":
        return _content_for_decoder(topic)
    if name == "lct_depth_model.py":
        return _content_for_lct_depth_model(topic, method_output)
    if name == "train_lct_depth.py":
        return _content_for_train_script(topic)
    if name == "benchmark.py":
        return _content_for_benchmark(topic)
    if name == "readme.md":
        return _content_for_readme(topic, method_output)
    if name == "setup.py":
        return (
            "from setuptools import find_packages, setup\n\n"
            "setup(name='lct_depth', version='0.1.0', package_dir={'': 'src'}, packages=find_packages('src'))\n"
        )
    if name.endswith(".py"):
        return _content_for_train_script(topic)
    return _content_for_readme(topic, method_output)


def execute_coding_stage(
    topic: str,
    coding_output: CodingStageOutput,
    method_output: MethodStageOutput,
    base_dir: Path | None = None,
) -> CodingExecutionResult:
    root = base_dir or Path.cwd()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sandbox_dir = root / "sandbox" / f"{_slugify(topic)}_{timestamp}"
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    files = coding_output.files_to_create or _default_file_list()
    normalized_files = list(files)
    if any(path.startswith("src/lct_depth/") for path in normalized_files) and "src/lct_depth/__init__.py" not in normalized_files:
        normalized_files.insert(0, "src/lct_depth/__init__.py")
    created_files: list[str] = []
    validated_files: list[str] = []
    validation_errors: list[str] = []

    for rel_path in normalized_files:
        rel = rel_path.strip().lstrip("/")
        if not rel:
            continue
        file_path = sandbox_dir / rel
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(_content_for_file(rel, topic, method_output), encoding="utf-8")
        created_files.append(str(file_path))

        if file_path.suffix == ".py":
            try:
                py_compile.compile(str(file_path), doraise=True)
                validated_files.append(str(file_path))
            except Exception as exc:
                validation_errors.append(f"{file_path}: {exc}")

    for runnable in ("train_lct_depth.py", "benchmark.py"):
        script_path = sandbox_dir / runnable
        if not script_path.exists():
            continue
        result = subprocess.run(
            ["python3", runnable],
            cwd=sandbox_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            validated_files.append(str(script_path))
        else:
            validation_errors.append(
                f"{script_path}: runtime validation failed with code {result.returncode}: {result.stderr.strip()}"
            )

    manifest_path = sandbox_dir / "coding_execution_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "sandbox_plan": coding_output.sandbox_plan,
                "validation_steps": coding_output.validation_steps,
                "created_files": created_files,
                "validated_files": validated_files,
                "validation_errors": validation_errors,
            },
            indent=2,
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    return CodingExecutionResult(
        sandbox_dir=str(sandbox_dir),
        created_files=created_files,
        validated_files=validated_files,
        validation_errors=validation_errors,
    )

from __future__ import annotations

import json
import os
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
        "README.md",
        "config/base.yaml",
        "config/smoke.yaml",
        "src/agentic_ai_system/__init__.py",
        "src/agentic_ai_system/data/__init__.py",
        "src/agentic_ai_system/data/loader.py",
        "src/agentic_ai_system/data/transforms.py",
        "src/agentic_ai_system/model/__init__.py",
        "src/agentic_ai_system/model/base.py",
        "src/agentic_ai_system/model/registry.py",
        "src/agentic_ai_system/train/__init__.py",
        "src/agentic_ai_system/train/loop.py",
        "src/agentic_ai_system/train/generic_losses.py",
        "src/agentic_ai_system/train/generic_metrics.py",
        "src/agentic_ai_system/train/metrics.py",
        "src/agentic_ai_system/train/evaluate.py",
    ]


def _allowed_task_files(topic: str) -> set[str]:
    task_slug = _slugify(topic)
    return {
        f"src/agentic_ai_system/data/{task_slug}_loader.py",
        f"src/agentic_ai_system/model/{task_slug}_architectures.py",
        f"src/agentic_ai_system/train/{task_slug}_losses.py",
        f"src/agentic_ai_system/train/{task_slug}_metrics.py",
        f"config/{task_slug}.yaml",
    }


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_repo_file(rel_path: str) -> str:
    repo_path = _repo_root() / rel_path
    return repo_path.read_text(encoding="utf-8")


def _content_for_readme(topic: str, method_output: MethodStageOutput) -> str:
    focus = method_output.implementation_focus or method_output.recommended_option or "n/a"
    return (
        "# Sandbox Pipeline Scaffold\n\n"
        f"Topic: {topic}\n\n"
        f"Recommended method focus: {focus}\n\n"
        "Run smoke test:\n"
        "```bash\n"
        "PYTHONPATH=src python -m agentic_ai_system.train.loop --config config/smoke.yaml --dry-run\n"
        "```\n\n"
        "Run full config:\n"
        "```bash\n"
        "PYTHONPATH=src python -m agentic_ai_system.train.loop --config config/base.yaml\n"
        "```\n"
    )


def _content_for_base_config(method_output: MethodStageOutput) -> str:
    focus = method_output.implementation_focus or method_output.recommended_option or "n/a"
    return f"""task_type: generic
notes: "{focus}"
model:
  architecture: dummy
  kwargs:
    input_dim: 3
    output_dim: 1
data:
  synthetic: true
  batch_size: 8
  num_workers: 0
  input_shape: [3, 64, 64]
  output_shape: [1, 64, 64]
training:
  loss: mse
  epochs: 2
  learning_rate: 0.001
  optimizer_type: adam
evaluation:
  metric: mse
output:
  experiment_dir: outputs/experiments
"""


def _content_for_smoke_config(method_output: MethodStageOutput) -> str:
    focus = method_output.implementation_focus or method_output.recommended_option or "n/a"
    return f"""task_type: generic
notes: "smoke test for {focus}"
model:
  architecture: dummy
  kwargs:
    input_dim: 3
    output_dim: 1
data:
  synthetic: true
  batch_size: 4
  num_workers: 0
  input_shape: [3, 64, 64]
  output_shape: [1, 64, 64]
training:
  loss: mse
  epochs: 1
  learning_rate: 0.001
evaluation:
  metric: mse
output:
  experiment_dir: outputs/experiments
"""


def _content_for_transforms() -> str:
    return '''"""Identity transforms placeholder."""

from __future__ import annotations


def build_transforms(config: dict | None = None):
    return lambda x: x
'''


def _content_for_base_model() -> str:
    return '''"""Base model interface placeholder."""

from __future__ import annotations

import torch.nn as nn


class BaseModel(nn.Module):
    def forward(self, x):  # type: ignore[override]
        raise NotImplementedError
'''


def _content_for_metrics_stub() -> str:
    return '''"""Metrics stub for future expansion."""

from __future__ import annotations

from .generic_metrics import get_metric

__all__ = ["get_metric"]
'''


def _content_for_evaluate_stub() -> str:
    return '''"""Evaluation stub for future expansion."""

from __future__ import annotations


def evaluate(*args, **kwargs):
    return {}
'''


def _content_for_file(path: str, topic: str, method_output: MethodStageOutput) -> str:
    normalized = path.replace("\\", "/")
    name = Path(normalized).name.lower()
    if normalized == "config/base.yaml":
        return _content_for_base_config(method_output)
    if normalized == "config/smoke.yaml":
        return _content_for_smoke_config(method_output)
    if normalized == "src/agentic_ai_system/data/loader.py":
        return _read_repo_file("src/agentic_ai_system/data/loader.py")
    if normalized == "src/agentic_ai_system/model/registry.py":
        return _read_repo_file("src/agentic_ai_system/model/registry.py")
    if normalized == "src/agentic_ai_system/train/loop.py":
        return _read_repo_file("src/agentic_ai_system/train/loop.py")
    if normalized == "src/agentic_ai_system/train/generic_losses.py":
        return _read_repo_file("src/agentic_ai_system/train/generic_losses.py")
    if normalized == "src/agentic_ai_system/train/generic_metrics.py":
        return _read_repo_file("src/agentic_ai_system/train/generic_metrics.py")
    if normalized == "src/agentic_ai_system/data/transforms.py":
        return _content_for_transforms()
    if normalized == "src/agentic_ai_system/model/base.py":
        return _content_for_base_model()
    if normalized == "src/agentic_ai_system/train/metrics.py":
        return _content_for_metrics_stub()
    if normalized == "src/agentic_ai_system/train/evaluate.py":
        return _content_for_evaluate_stub()
    if name == "readme.md":
        return _content_for_readme(topic, method_output)
    if name == "__init__.py":
        return '"""Generated research package."""\n'
    if name.endswith(".py"):
        return '"""Placeholder generated by coding stage."""\n'
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

    base_files = _default_file_list()
    allowed_files = _allowed_task_files(topic)
    requested_files = [path for path in (coding_output.files_to_create or []) if path]
    extra_files = [path for path in requested_files if path not in base_files and path in allowed_files]
    normalized_files = [*base_files, *extra_files]
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

    ignored_files = [path for path in requested_files if path not in base_files and path not in allowed_files]
    if ignored_files:
        validation_errors.append(
            "ignored_unapproved_files: "
            + ", ".join(sorted(set(ignored_files)))
        )

    smoke_cmd = [
        "python3",
        "-m",
        "agentic_ai_system.train.loop",
        "--config",
        "config/smoke.yaml",
        "--dry-run",
    ]
    env = {**os.environ, "PYTHONPATH": str(sandbox_dir / "src")}
    result = subprocess.run(
        smoke_cmd,
        cwd=sandbox_dir,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode == 0:
        validated_files.append(str(sandbox_dir / "config/smoke.yaml"))
    else:
        stderr = result.stderr.strip() or result.stdout.strip()
        validation_errors.append(
            "smoke_test: runtime validation failed "
            f"with code {result.returncode}: {stderr}"
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

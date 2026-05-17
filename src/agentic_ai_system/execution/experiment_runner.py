from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path

from agentic_ai_system.schemas.models import (
    CodingExecutionResult,
    ExperimentExecutionResult,
    ExperimentStageOutput,
)


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "topic"


def run_experiment_stage(
    topic: str,
    experiment_output: ExperimentStageOutput,
    coding_result: CodingExecutionResult,
    base_dir: Path | None = None,
) -> ExperimentExecutionResult:
    root = base_dir or Path.cwd()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = root / "outputs" / "experiments" / f"{_slugify(topic)}_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    created_files = len(coding_result.created_files)
    validated_files = len(coding_result.validated_files)
    validation_rate = (validated_files / created_files) if created_files else 0.0
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    metrics: dict[str, float] = {
        "sandbox_created_files": float(created_files),
        "sandbox_validated_python_files": float(validated_files),
        "sandbox_validation_rate": round(validation_rate, 4),
        "runner_latency_ms": round(elapsed_ms, 3),
    }
    for metric_name in experiment_output.metrics_to_track:
        normalized = re.sub(r"[^a-z0-9]+", "_", metric_name.lower()).strip("_")
        metrics.setdefault(normalized, 0.0)

    summary_file = run_dir / "experiment_summary.json"
    summary_file.write_text(
        json.dumps(
            {
                "goal": experiment_output.experiment_goal,
                "config": experiment_output.run_config,
                "metrics": metrics,
                "sandbox_dir": coding_result.sandbox_dir,
                "validation_errors": coding_result.validation_errors,
            },
            indent=2,
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )

    return ExperimentExecutionResult(
        run_dir=str(run_dir),
        metrics=metrics,
        summary_file=str(summary_file),
    )

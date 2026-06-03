from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

import yaml

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

    sandbox_dir = Path(coding_result.sandbox_dir)
    config_path = sandbox_dir / "config" / "experiment.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Merge run_config with defaults if needed
    run_config = experiment_output.run_config or {}
    if "output" not in run_config:
        run_config["output"] = {"experiment_dir": "outputs/experiments"}
    
    config_path.write_text(yaml.dump(run_config), encoding="utf-8")

    t0 = time.perf_counter()

    # Run the training loop in dry-run mode for the experiment stage
    cmd = [
        "python3",
        "-m",
        "agentic_ai_system.train.loop",
        "--config",
        "config/experiment.yaml",
        "--dry-run",
    ]
    env = {**os.environ, "PYTHONPATH": str(sandbox_dir / "src")}
    
    try:
        result = subprocess.run(
            cmd,
            cwd=sandbox_dir,
            capture_output=True,
            text=True,
            env=env,
            timeout=120, # 2 minute timeout for dry run
        )
        status = "ok" if result.returncode == 0 else "failed"
        stderr = result.stderr.strip()
    except subprocess.TimeoutExpired:
        status = "timeout"
        stderr = "Experiment timed out after 120 seconds"
    except Exception as e:
        status = "error"
        stderr = str(e)

    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    # Try to find the results.json in the sandbox's experiment output dir
    experiment_metrics: dict[str, float] = {}
    actual_run_dir = ""
    
    if status == "ok":
        # The loop saves to outputs/experiments/<run_id>/results.json
        exp_base = sandbox_dir / "outputs" / "experiments"
        if exp_base.exists():
            # Get the most recent run_id directory
            runs = sorted(exp_base.glob("20*"), reverse=True)
            if runs:
                actual_run_dir = str(runs[0])
                results_json = runs[0] / "results.json"
                if results_json.exists():
                    try:
                        data = json.loads(results_json.read_text(encoding="utf-8"))
                        # Extract validation metrics
                        val_metrics = data.get("val_metrics", {})
                        for k, v in val_metrics.items():
                            experiment_metrics[f"val_{k}"] = float(v)
                        # Extract train metrics
                        train_metrics = data.get("train_metrics", {})
                        for k, v in train_metrics.items():
                            experiment_metrics[f"train_{k}"] = float(v)
                    except Exception as e:
                        stderr += f"\nFailed to parse results.json: {e}"

    created_files = len(coding_result.created_files)
    validated_files = len(coding_result.validated_files)
    validation_rate = (validated_files / created_files) if created_files else 0.0

    metrics: dict[str, float] = {
        "sandbox_created_files": float(created_files),
        "sandbox_validated_python_files": float(validated_files),
        "sandbox_validation_rate": round(validation_rate, 4),
        "runner_latency_ms": round(elapsed_ms, 3),
        "experiment_status": 1.0 if status == "ok" else 0.0,
    }
    metrics.update(experiment_metrics)

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
                "actual_run_dir": actual_run_dir,
                "status": status,
                "stderr": stderr,
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

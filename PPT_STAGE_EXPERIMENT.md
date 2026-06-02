# PPT Stage Guide — Experiment
> Agentic Research System
> Status: Partially implemented (summary-only runner)

---

## 1. Slide summary (1–2 bullets)
- Converts coding outputs into a reproducible experiment plan.
- Generates run summaries and placeholder metrics.

---

## 2. Purpose
Provide an experiment plan and a minimal execution summary to validate readiness for real runs.

---

## 3. Inputs
- **Coding stage output** (sandbox plan)
- **Coding execution result** (sandbox dir + validation results)

---

## 4. Outputs
- **ExperimentStageOutput** (goal, run_config, metrics list)
- **ExperimentExecutionResult** with summary JSON
- **Stage manifest** (`outputs/artifacts/*/experiment.json`)

---

## 5. Detailed flow (stage logic)
1. LLM generates a structured experiment plan JSON.
2. Runner creates an experiment summary with:
   - sandbox validation stats
   - placeholder metrics and runtime info
3. Persist summary and stage manifest.
4. **Approval gate** at stage completion.

---

## 6. Tools and modules (for PPT citation)
- `orchestration/research_pipeline.py` (`run_experiment_stage_flow`)
- `execution/experiment_runner.py`
- `schemas/models.py` (`ExperimentStageOutput`, `ExperimentExecutionResult`)

---

## 7. Current limitations (honest slide)
- Does not execute real training or evaluation yet.
- Metrics are placeholder values derived from scaffold validation.

---

## 8. Planned enhancements
- Replace summary-only runner with real training/evaluation execution.
- Integrate MLflow or structured experiment tracking.
- Add dataset-driven evaluation harness.

---

## 9. Demo snippets
```bash
run_flow "Survey monocular depth estimation 2023-2025"
```
- Show: `outputs/experiments/*/experiment_summary.json`


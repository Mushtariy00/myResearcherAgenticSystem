# Session Log (append-only, newest first)

## 2026-06-03
- Added `tools/model_checker.py` to list and test free models from OpenRouter.
- Added `tools/update_model.py` to automatically switch `agents.yaml` to the best available free model.
- Successfully migrated agents to `openrouter/owl-alpha` after verifying `openai/gpt-oss-120b:free` outage.
- Wired Experiment stage to actual training loop execution.
- Modified `train/loop.py` to save `results.json` with final metrics.
- Updated `execution/experiment_runner.py` to trigger dry-run training in sandbox and capture metrics (loss, mse, mae).
- Stabilized Streamlit approvals (manual approvals now persist in flow state).
- Fixed auto-mode propagation and approval UI rendering.
- Adjusted resume visibility logic and derived completed stages from outputs.
- Restricted coding stage to task-specific module allowlist; blocked extra files.
- Added literature-stage caching from latest output to speed reruns.
- Added UI identity footer with student/class info.
- Updated docs structure plan and began consolidation into `docs/`.
- Key files touched: `train/loop.py`, `execution/experiment_runner.py`, `ui/runtime.py`, `ui/app.py`, `ui/components.py`, `orchestration/literature_pipeline.py`, `execution/sandbox_executor.py`, `tools/model_checker.py`, `tools/update_model.py`, `config/agents.yaml`.

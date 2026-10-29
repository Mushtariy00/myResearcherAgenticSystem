# Project Overview — Agentic Research System

**Purpose:** A CLI-first agentic research pipeline with optional Streamlit UI that turns a topic into structured outputs (literature → method → coding → experiment → writing) with approval checkpoints.

## Entry points
- **CLI flow:** `run_flow "<topic>"`
- **UI:** `run_ui`

## Core structure (high-level)
- `src/agentic_ai_system/orchestration/`: supervisor flow + stage pipelines
- `src/agentic_ai_system/config/`: agent/task configs
- `src/agentic_ai_system/execution/`: sandbox + experiment runners
- `outputs/`: persisted artifacts + `flow_runs.db`
- `sandbox/`: coding-stage scaffold output

## Outputs
- Literature: `outputs/literature/*.json`
- Flow metadata: `outputs/flow_runs.db`
- Coding sandbox: `sandbox/<topic>_<timestamp>/`
- Experiments: `outputs/experiments/<topic>_<timestamp>/`
- Writing: `outputs/writing/<topic>_<timestamp>/`

## “Start here” (for every session)
1. Read `PROJECT_STATUS.md`
2. Read the latest entry in `SESSION_LOG.md`

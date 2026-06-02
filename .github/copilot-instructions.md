# Copilot instructions for AgenticAiSystem

## Build, test, and lint commands
- **Run all tests (unittest):** `python -m unittest`
- **Run a single test file:** `python -m unittest tests/test_reliability.py`
- **Run a single test case:** `python -m unittest tests.test_reliability.ReliabilityTests.test_parser_handles_non_strict_json`

## High-level architecture
- **Supervisor flow** orchestrates the entire pipeline and approval gates: `src/agentic_ai_system/orchestration/supervisor_flow.py`.
- **Stage implementations** live in:
  - Literature: `orchestration/literature_pipeline.py`
  - Method/Coding/Experiment/Writing: `orchestration/research_pipeline.py`
- **Agent factory + roles** are defined in `src/agentic_ai_system/crew.py` and `src/agentic_ai_system/config/agents.yaml`.
- **Artifacts + run metadata** are persisted via `storage/*` and `storage/run_persistence.py` into `outputs/` and `outputs/flow_runs.db`.
- **Tools** for literature search and PDF retrieval are in `src/agentic_ai_system/tools/`.

## Key conventions
- **CrewAI version discipline:** Follow the mandatory "check version / changelog / docs" workflow in `AGENTS.md` before modifying CrewAI code.
- **Stage outputs are typed** with Pydantic models in `src/agentic_ai_system/schemas/` and parsed via `flow_utils.parse_model_output`.
- **Approval gates** are centralized in `orchestration/flow_utils.py` and control stage progression.
- **Artifacts go to outputs/** and sandbox artifacts go to `sandbox/`; avoid writing stage outputs to repo root.
- **Entry points** for running the system are `run_flow` (CLI) and `run_ui` (Streamlit), as defined in `pyproject.toml`.

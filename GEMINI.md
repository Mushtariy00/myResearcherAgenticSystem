# Agentic Research System — GEMINI.md

This project is a CLI-first agentic research pipeline that automates the transition from a research topic to structured outputs (literature review, methodology, coding scaffolds, experiments, and writing).

## Project Overview

*   **Purpose:** Automate the end-to-end research lifecycle using specialized agents.
*   **Architecture:** Multi-stage supervisor flow coordinated by CrewAI.
*   **Stages:**
    1.  **Literature:** Screening and selecting relevant papers.
    2.  **PDF Fetch:** Retrieving full-text papers via multiple adapters (arXiv, Unpaywall, etc.).
    3.  **Method:** Gap analysis and methodology proposal.
    4.  **Coding:** Generating task-specific modules and data contracts.
    5.  **Experiment:** Executing training/evaluation and capturing metrics.
    6.  **Writing:** Drafting prose with linked citations.
*   **Core Technologies:**
    *   **Orchestration:** [CrewAI](https://docs.crewai.com) (Flows, Agents, Tasks).
    *   **Dependency Management:** `uv`.
    *   **Memory:** Persistent context across sessions via `agentmemory` (MCP/REST).
    *   **UI:** Streamlit-based dashboard for visualization and approvals.

## Building and Running

### Installation
Ensure Python >=3.10 <3.14 and `uv` are installed.
```bash
uv sync
crewai install
```

### Execution
*   **CLI Flow:** `run_flow "<topic>"`
*   **Streamlit UI:** `run_ui`
*   **Alternative Run:** `python -m agentic_ai_system.main:run_flow`

### Testing
```bash
pytest
```

### Experimental Training Loop
```bash
PYTHONPATH=src python -m agentic_ai_system.train.loop --config config/nyu2.yaml --dry-run
```

## Model Management

If the default free model is experiencing outages (503 errors), use these utilities:

*   **List and Test Free Models:**
    ```bash
    python3 src/agentic_ai_system/tools/model_checker.py --test
    ```
*   **Auto-Update to Best Working Model:**
    ```bash
    python3 src/agentic_ai_system/tools/update_model.py
    ```

## Development Conventions

### Authoritative Documentation Hierarchy
For project state and instructions, refer to files in this order:
1.  `PROJECT_OVERVIEW.md`: High-level purpose and structure.
2.  `PROJECT_STATUS.md`: Current stage status and active roadmap.
3.  `SESSION_LOG.md`: Latest session updates.
4.  `docs/DOC_INDEX.md`: Deep documentation.

### Core Rules
*   **Outputs:** All stage artifacts must be written to `outputs/` or `sandbox/`. Never write to the repository root.
*   **Approvals:** The supervisor flow includes human-in-the-loop checkpoints. Respect `CheckpointRejected` exceptions.
*   **Coding Stage Guardrails:** Coding agents only generate task-specific modules. They must pass method approval, environment manifest, and data contract gates.
*   **CrewAI Patterns:** 
    *   Always use `crewai.LLM` for model configuration.
    *   Agents and Tasks should be defined in YAML files (`src/agentic_ai_system/config/`).
    *   Use `@CrewBase` and lifecycle hooks (`@before_kickoff`, `@after_kickoff`).

### Memory Integration
*   The system uses `agentmemory` to save findings and recall context.
*   Memory operations are non-blocking and fail gracefully.
*   See `AGENTMEMORY_INTEGRATION.md` for detailed save/recall patterns.

## Repository Structure

*   `src/agentic_ai_system/orchestration/`: Supervisor flow and stage logic.
*   `src/agentic_ai_system/config/`: Agent and task YAML configurations.
*   `src/agentic_ai_system/execution/`: Experiment runners and sandbox management.
*   `src/agentic_ai_system/ui/`: Streamlit application files.
*   `outputs/`: Persisted research artifacts and the `flow_runs.db` database.
*   `sandbox/`: Temporary scaffolds for the coding stage.
*   `tests/`: Suite of unit and integration tests.

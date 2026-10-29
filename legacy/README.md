# AgenticAiSystem

Agentic research pipeline with a CLI-first supervisor flow, optional Streamlit UI, and modular stage helpers for literature, method, coding, experiment, and writing.

## Start here (every session)
1. `PROJECT_OVERVIEW.md`
2. `PROJECT_STATUS.md`
3. Latest entry in `SESSION_LOG.md`
4. For deep docs, see `docs/DOC_INDEX.md`

## Installation

Ensure you have Python >=3.10 <3.14 installed on your system. This project uses [UV](https://docs.astral.sh/uv/) for dependency management and package handling, offering a seamless setup and execution experience.

First, if you haven't already, install uv:

```bash
pip install uv
```

Next, navigate to your project directory and install the dependencies:

(Optional) Lock the dependencies and install them by using the CLI command:
```bash
crewai install
```
### Customizing

**Add your `OPENAI_API_KEY` into the `.env` file**

- Modify `src/agentic_ai_system/config/agents.yaml` to define your agents
- Modify `src/agentic_ai_system/orchestration/supervisor_flow.py` to change stage logic and approvals
- Modify `src/agentic_ai_system/main.py` to add custom inputs for your entrypoints

## Running the Project

To run the CLI-first supervisor flow with approval checkpoints:

```bash
$ run_flow "Survey monocular depth estimation 2023-2025"
```

To run the Streamlit UI:

```bash
$ run_ui
```

The current default model is configured as `openai/gpt-oss-120b:free` (set via `MODEL` / agent `llm` config).
Literature outputs from the supervisor flow are persisted to `outputs/literature/*.json`.
Flow run metadata, stage events, and approvals are persisted to `outputs/flow_runs.db`.
Coding-stage sandbox artifacts are written to `sandbox/<topic>_<timestamp>/`.
Experiment-stage execution summaries are written to `outputs/experiments/<topic>_<timestamp>/`.
Writing-stage section drafts are written to `outputs/writing/<topic>_<timestamp>/`.
Generated artifacts stay in `sandbox/` and `outputs/`; the repo root is not used for stage outputs.

## Understanding the system

The system is composed of modular stage helpers plus CrewAI agents used by the supervisor flow. The `config/agents.yaml` file defines agent roles, while the supervisor flow coordinates them with explicit checkpoints.

## Support

For support, questions, or feedback regarding AgenticAiSystem or crewAI.
- Visit our [documentation](https://docs.crewai.com)
- Reach out to us through our [GitHub repository](https://github.com/joaomdmoura/crewai)
- [Join our Discord](https://discord.com/invite/X4JWnZnxPb)
- [Chat with our docs](https://chatg.pt/DWjSBZn)

Let's create wonders together with the power and simplicity of crewAI.

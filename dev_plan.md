# CrewAI Dev Plan — Agentic Research System (CLI-first)

## Problem & approach
Build a semi-autonomous research pipeline in CrewAI that preserves human approval gates while reducing custom orchestration code. Use a **Flow as supervisor** (routing + checkpoints), specialized CrewAI tools for each stage, and keep CLI approvals as the default human-in-the-loop interface.

## Updated goals (May 2026)
- Integrate a persistent memory (agentmemory) via MCP to avoid re-explaining context across sessions
- Implement a robust literature pipeline with PDF retrieval waterfall and cached storage
- Make every stage modular (agent per stage) with explicit Flow-state contracts and approval checkpoints
- Keep sandboxed code generation and experiment execution safe by default

## Architecture target
- Flow (supervisor): stage transitions, approvals, retry paths, persisted flow state
- Crew agents: one agent per stage (literature, pdf-fetcher, method, coding, experiment, writing, memory)
- Tools: search adapters (arXiv, Semantic Scholar), PDF fetcher (Unpaywall/OpenAlex/CORE/PMC), sandbox runner, MLflow adapter, agentmemory MCP
- Persistence: outputs/ for artifacts, SQLite for flow-run metadata, agentmemory for long-term recall

## Overall integration roadmap
Phases and deliverables with checkpoints and approximate effort (working days):

Phase 0 — Validation & baseline (0.5–1d)
- Verify installed CrewAI & tools, read changelog (AGENTS.md guidance)
- Confirm MODEL, .env keys, and OpenRouter connectivity
- Smoke test crew kickoff and supervisor Flow

Phase 1 — Core foundation (2–3d)
- Finalize Literature agent (search + normalized metadata)
- Add PDF-Fetcher agent (arXiv direct + Unpaywall/OpenAlex MVP)
- Integrate agentmemory MCP (hooks and explicit save/recall usage)
- Write unit tests for search & fetch

Phase 2 — Method + Sandbox (3–4d)
- Implement Method agent producing structured proposals
- Implement Coding/Sandbox agent with diff preview and sandbox runner
- Approval gates for publishing sandbox artifacts to repo

Phase 3 — Experiments + Writing (2–3d)
- Experiment agent (run configs, dry-run, metrics capture)
- Writing agent (section drafts, per-section approvals)
- Post-stage summarizers and export utilities

Phase 4 — Reliability & QA (2–3d)
- Add retries, fallback models, logging, guardrails, and tests
- E2E dry-run and a manual approval walkthrough

Phase 5 — Optional UI & Deployment (2–4d)
- Streamlit UI reusing Flow/crew interfaces (optional)
- Deployment packaging and docs

## Per-agent plans (goal, inputs, outputs, steps, tests, estimate)

1) Literature Agent (0.5–1d)
- Goal: discover candidate papers and produce normalized metadata
- Inputs: topic query; Outputs: list of papers saved under outputs/literature/
- Steps: finalize arXiv and Semantic Scholar tools, normalize schema, unit tests
- Tests: mock API responses, schema validation

2) PDF-Fetcher Agent (MVP 1d; full 2–3d)
- Goal: waterfall PDF retrieval and caching per literature_sources_plan
- Inputs: paper metadata (arXiv ID / DOI / url); Outputs: cached PDF + provenance
- Steps (MVP): arXiv direct PDF builder + Unpaywall/OpenAlex calls; validation (Content-Type, size); caching by DOI/ID
- Full: CORE, PMC, bioRxiv adapters, robust retry/backoff and rate-limiting
- Tests: adapter unit tests and waterfall integration test

3) Memory Agent (configuration + wiring 0.5–1d)
- Goal: persist session observations and provide recall/smart_search
- Inputs: stage outputs, approvals, important decisions; Outputs: memory entries
- Steps: ensure MCP entry, add explicit save calls at stage checkpoints, implement recall usage in literature/method agents
- Tests: write/save/recall roundtrip tests

4) Method Agent (1d)
- Goal: analyze literature to produce gap analysis and 2–3 method proposals
- Inputs: literature outputs + memory context; Outputs: structured proposals saved to outputs/method/
- Steps: define Pydantic model, implement agent prompt + guardrails, approval checkpoint
- Tests: model validation and integration test

5) Coding / Sandbox Agent (2–4d)
- Goal: generate sandboxed code artifacts and diffs for approval
- Inputs: chosen method + task spec; Outputs: sandbox/<topic>_<ts>/ with diffs and logs
- Steps: sandbox runner, diff preview tool, approvals to apply changes
- Tests: run generated unit tests in isolated venv

6) Experiment Agent (1–2d)
- Goal: orchestrate experiments (dry runs first), capture metrics
- Inputs: sandbox artifacts; Outputs: outputs/experiments/<topic>_<ts>/ metrics + summaries
- Steps: experiment schema, MLflow/simple adapter, approval before launch
- Tests: dry-run metadata generation

7) Writing Agent (1–2d)
- Goal: synthesize drafts from stage outputs with section-level approvals
- Inputs: prior stage outputs; Outputs: outputs/writing/<topic>_<ts>/ versioned sections
- Steps: structured section model, regenerate on feedback, export MD/JSON
- Tests: guardrail checks (length, references)

## Cross-cutting items
- Centralize config (.env) for MODEL, API keys, email parameters, CORE key
- Enforce PII redaction in memory and outputs; never store API secrets in memory
- Add guardrails and unit/integration tests per agent
- Supervisor Flow: wire each agent as a Crew task and add approval checkpoints

## Immediate next steps (first sprint)
1. Implement PDF-Fetcher MVP (arXiv direct + Unpaywall/OpenAlex) and unit tests
2. Finalize agentmemory wiring (explicit save/recall at literature/method)
3. Update supervisor Flow to call PDF-Fetcher after literature search and persist results

## Risks & mitigation
- Missing API keys → mock adapters and graceful fallbacks
- PDF fetch fails → abstract-only fallback, do not block pipeline
- Unsafe code writes → sandbox-only by default; require explicit repo-apply approval

---

Updated: May 2026 — integrated per-agent plans and MVP-first roadmap.  
Use this as the single source of truth for sprint planning and Flow checkpoints.

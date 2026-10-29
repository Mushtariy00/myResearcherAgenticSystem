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

## Per-stage plans (goal, inputs, outputs, implementation status)

1) Literature Stage
- Goal: discover candidate papers and produce normalized metadata + synthesis.
- Inputs: topic query; Outputs: outputs/literature/* (sources, abstracts, synthesis).
- Implementation status: implemented search → screen → fetch open-access text → analyze → synthesize.
- Gaps: full PDF waterfall; tests; richer metadata normalization and caching.
- Next steps: wire Unpaywall/OpenAlex/CORE/PMC waterfall; add unit/integration tests.

2) PDF Fetch Stage
- Goal: retrieve PDFs with provenance and cache them for downstream stages.
- Inputs: paper metadata (arXiv ID / DOI / url); Outputs: cached PDF + provenance records.
- Implementation status: open-access fetch exists; no waterfall or robust retry/backoff.
- Gaps: full adapter set, content validation, rate limiting, reliability tests.
- Next steps: add waterfall adapters and retries; validate content type/size and cache by DOI/ID.

3) Memory Stage
- Goal: persist session observations and provide recall/smart_search to later stages.
- Inputs: stage outputs, approvals, decisions; Outputs: memory entries.
- Implementation status: save/recall hooks are stubbed.
- Gaps: MCP-backed persistence and active recall in literature/method.
- Next steps: wire MCP client, add explicit save/recall calls, add roundtrip tests.

4) Method Stage
- Goal: analyze literature to produce gap analysis and 2–3 method proposals.
- Inputs: literature outputs + memory context; Outputs: structured proposals in outputs/method/.
- Implementation status: implemented with approval gate and structured JSON output.
- Gaps: memory recall not active; tighter guardrails for structured outputs.
- Next steps: enable memory recall and add schema validation tests.

5) Coding Stage
- Goal: turn approved method into runnable code via a sandboxed, diff-only workflow.
- Inputs: chosen method + task spec; Outputs: sandbox/<topic>_<ts>/, diffs, logs.
- Implementation status: universal train scaffold is generated in the sandbox; env/data gates exist; LLM is restricted to task-specific modules only.
- Gaps: diff-only enforcement, data integration layer (data_report.json), and stricter validation of task-specific modules.
- Next steps: add data_report.json + parity checks, enforce diff-only patch application, expand smoke tests to cover task-specific wiring.

6) Experiment Stage
- Goal: orchestrate experiments (dry-run first), capture metrics and reports.
- Inputs: sandbox artifacts; Outputs: outputs/experiments/<topic>_<ts>/ metrics + summaries.
- Implementation status: summary-only (no real training/eval); approvals + persistence exist.
- Gaps: real execution hooks, meaningful metrics capture, report generation.
- Next steps: wire training/eval execution, capture metrics, generate eval reports.

7) Writing Stage
- Goal: synthesize drafts from stage outputs with section-level approvals.
- Inputs: prior stage outputs; Outputs: outputs/writing/<topic>_<ts>/ sections and exports.
- Implementation status: outline and section stubs only; approvals + persistence exist.
- Gaps: full prose generation with evidence linking and citations.
- Next steps: expand section drafting, add reference linking and style guardrails.

8) Supervisor Flow (Orchestration)
- Goal: manage stage transitions, approvals, retries, persisted flow state.
- Inputs: stage outputs; Outputs: flow state + run metadata in outputs/flow_runs.db.
- Implementation status: end-to-end flow exists; approvals integrated; UI resume support exists.
- Gaps: stage-specific resume from persisted checkpoints (beyond UI), richer failure diagnostics.
- Next steps: add stage resume from persisted checkpoints and enhance error reporting.

9) UI (Streamlit)
- Goal: provide approval gates, logs, and resume controls without CLI.
- Inputs: flow state + approvals; Outputs: UI state + interaction logs.
- Implementation status: UI exists with approvals and resume selection.
- Gaps: clearer gating messages + validation feedback, better run history visualization.
- Next steps: improve validation UX and stage resume messaging.

## Cross-cutting items
- Centralize config (.env) for MODEL, API keys, and external service keys.
- Enforce PII redaction in memory and outputs; never store API secrets in memory.
- Add guardrails and unit/integration tests per stage.

---

Updated: May 2026 — per-stage plan with status and gaps.  
Use this as the single source of truth for sprint planning and Flow checkpoints.

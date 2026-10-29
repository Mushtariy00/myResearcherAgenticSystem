# Project Status (Authoritative)

**Session start (read order):** `PROJECT_OVERVIEW.md` → `PROJECT_STATUS.md` → latest entry in `SESSION_LOG.md`.

## Snapshot
- **Goal:** Agentic research pipeline with approvals and persisted artifacts.
- **Current focus:** Stabilize UI + approvals, finish coding-stage guardrails, improve literature speed and PDF waterfall.

## Stage status (summary)

| Stage | Status | Gaps | Next actions |
| --- | --- | --- | --- |
| Literature | Implemented | Full PDF waterfall, tests, richer metadata caching | Wire Unpaywall/OpenAlex/CORE/PMC waterfall; add tests |
| PDF Fetch | Partial | Adapter set, validation, retry/backoff | Add waterfall adapters + content validation |
| Memory | Stubbed | MCP persistence + recall | Wire MCP save/recall + tests |
| Method | Implemented | Memory recall + stricter schema validation | Enable recall; add validation tests |
| Coding | Partial | Diff-only enforcement, data_report.json parity checks, stricter task-module validation | Enforce diff-only; add data report + parity checks |
| Experiment | Implemented | Metrics visualization in UI | Add charts/plots to UI for metrics |
| Writing | Stubbed | Full prose drafting with citations | Expand drafting + citation linking |
| Supervisor Flow | Implemented | Stage resume from persisted checkpoints, better diagnostics | Add resume from checkpoints + error reporting |
| UI | Implemented | Clearer gating messages + run history UX | Improve validation messaging + run history view |

## Key rules
- Outputs go to `outputs/` and `sandbox/` only.
- Coding stage must pass method approval + env manifest + data contract gates.
- Coding agent only generates task-specific modules (no base pipeline rewrites).

**Last updated:** 2026-06-03

# CrewAI Dev Plan — Agentic Research System (CLI-first)

## Problem & approach
Build a semi-autonomous research pipeline in CrewAI that preserves human approval gates while reducing custom orchestration code.  
Use a **Flow as supervisor** (routing + checkpoints), specialized CrewAI tools for each stage, and start with **CLI approvals** before any UI.

## Assumptions confirmed
- Phase 1 checkpoint interface: **CLI prompts only**
- Primary model for now: **OpenRouter `openai/gpt-oss-120b:free`**

## Scope (in)
- Literature search/summarization
- Gap analysis and method proposal
- Sandbox-first code generation
- Experiment run orchestration with approval before launch
- Draft writing with section-level approvals
- End-to-end CLI workflow with persistent state and logs

## Scope (out, initial)
- Streamlit/web dashboard in Phase 1
- Full production deployment hardening
- Multi-tenant auth/access control

## Architecture target
- **Flow layer (supervisor):** stage transitions, routing, approval checkpoints, retry paths
- **Crew layer:** specialist agents + YAML tasks per stage
- **Tools layer:** arXiv/Semantic Scholar search, PDF parse, sandbox runner, MLflow adapter, memory adapters
- **State & memory:** Flow persisted state + SQLite for structured runs + Crew knowledge/memory for retrieval
- **Model policy:** OpenRouter primary with fallback model chain configured in one place

## Implementation phases
1. **Phase 0 — Baseline & validation**
   - Confirm installed CrewAI version, compare with latest, read changelog, pin compatible patterns.
   - Define provider config for OpenRouter and test a minimal kickoff call.
2. **Phase 1 — Foundation (CLI-first)**
   - Create Flow skeleton with checkpoint gates and CLI approval prompts.
   - Implement Literature pipeline (search → parse → summarize → persist).
   - Add structured state models and persistent flow state.
3. **Phase 2 — Core reasoning/build**
   - Implement Method stage (gap analysis + 2–3 proposals).
   - Implement Coding stage with sandbox-only writes and diff preview approval.
4. **Phase 3 — Experiment + writing**
   - Implement Experiment stage with run config confirmation and metrics capture.
   - Implement Writing stage with per-section approve/regenerate loop.
5. **Phase 4 — Reliability**
   - Add robust retries, fallback model logic, logging/audit, and failure recovery paths.
   - Add end-to-end and component tests for major flows.
6. **Phase 5 — Optional UX**
   - Add Streamlit UI reusing existing Flow/crew interfaces.

## Todos
- Define OpenRouter/CrewAI model config and fallback policy.
- Build Flow supervisor with explicit approval gates.
- Implement Literature tools and storage.
- Implement Method proposal stage with selectable options.
- Implement sandboxed Coding stage with diff approval.
- Implement Experiment stage with MLflow + metrics schema.
- Implement Writing stage with section-by-section review.
- Add persistence, logging, retries, and error strategy.
- Add test suite for phase gates and end-to-end pipeline.
- Prepare optional Streamlit integration after CLI baseline is stable.

## Notes
- Keep agent boundaries strict; all inter-stage coordination goes through Flow state.
- Keep dangerous actions gated (code writes to real repo, GPU launches).
- Prefer structured outputs (`output_pydantic`) between stages to reduce parsing fragility.

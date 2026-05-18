# Agentic Research System — PPT Preparation Guide

This document is designed to be directly converted into a class presentation.

---

## 1. One-slide project summary

**Project name:** AgenticAiSystem  
**Goal:** Build an agentic research pipeline that turns a topic into structured research outputs (literature, method, coding, experiment, writing) with optional human approvals between stages.  
**Core idea:** Multiple specialized LLM agents are orchestrated by a supervisor flow, while deterministic modules handle artifact generation, persistence, and validation.

---

## 2. Problem statement (why this system exists)

Traditional LLM workflows are often:
1. Single-shot prompts
2. Hard to trace
3. Hard to recover on failure
4. Weak on reproducibility

This project addresses those by using:
1. **Stage-wise orchestration** (not one giant prompt)
2. **Structured JSON outputs** per stage
3. **Persistent artifacts/logs** to inspect and continue
4. **Human approval checkpoints** for control and safety

---

## 3. What makes it “agentic”

This is agentic because it has:
1. **Role-specialized agents** (`researcher`, `method_analyst`, `coding_architect`, `experiment_designer`, `writing_strategist`)
2. **Autonomous stage progression** with memory/state
3. **Tool use** for literature search and full-text fetch
4. **Feedback gates** (approve/reject or auto mode)
5. **Self-recovery patterns** (retry + fallback synthesis)

Agent definitions are in:  
`src/agentic_ai_system/config/agents.yaml`

Factory that builds agents:  
`src/agentic_ai_system/crew.py`

---

## 4. System architecture (high-level)

```text
User Topic
   |
   v
ResearchSupervisorFlow (orchestration/supervisor_flow.py)
   |
   +--> Literature Pipeline (search -> screen -> fetch -> analyze -> synthesize)
   |
   +--> Method Stage
   |
   +--> Coding Stage (sandbox artifact generation + validation)
   |
   +--> Experiment Stage
   |
   +--> Writing Stage
   |
   v
Persisted Outputs (outputs/, sandbox/, flow_runs.db)
```

Key orchestration modules:
1. `src/agentic_ai_system/orchestration/supervisor_flow.py` (thin coordinator)
2. `src/agentic_ai_system/orchestration/literature_pipeline.py`
3. `src/agentic_ai_system/orchestration/research_pipeline.py`
4. `src/agentic_ai_system/orchestration/flow_utils.py`
5. `src/agentic_ai_system/orchestration/exceptions.py`

---

## 5. Entry points (how system runs)

From `pyproject.toml`:
1. `run_flow` → CLI supervisor flow
2. `run_ui` → Streamlit interface

Main CLI entry:
`src/agentic_ai_system/main.py`

UI entry:
`src/agentic_ai_system/run_ui.py`  
Streamlit app:
`src/agentic_ai_system/ui/app.py`

---

## 6. Stage-by-stage pipeline (core slide set)

## Stage A: Literature

Implemented in:  
`orchestration/literature_pipeline.py`

Flow:
1. Build multi-query search set (`build_literature_queries`)
2. Collect papers from:
   - `ArxivSearchTool`
   - `SemanticScholarSearchTool`
3. Rank/deduplicate results
4. Compact candidate bundle for efficient screening
5. LLM screen pass selects best indices
6. Fetch full text for selected papers (`PaperFullTextFetchTool`)
7. Chunk text for context control
8. LLM per-paper analysis pass
9. LLM synthesis pass to produce final literature summary
10. Persist artifacts + manifest

Why this matters:
1. Keeps LLM in the core loop
2. Reduces timeout risk by splitting work
3. Gives traceable intermediate outputs

---

## Stage B: Method

Implemented in:  
`orchestration/research_pipeline.py` (`run_method_stage`)

Input: literature synthesis JSON  
Output: research gaps + method proposals + recommended option  
Persistence: `storage/method_storage.py` + stage artifact manifest

---

## Stage C: Coding

Implemented in:  
`orchestration/research_pipeline.py` (`run_coding_stage`)  
Execution helper:
`execution/sandbox_executor.py`

Behavior:
1. Agent generates coding plan
2. Deterministic scaffold files are generated in `sandbox/...`
3. Python compile checks run
4. Runtime smoke scripts run (`train_lct_depth.py`, `benchmark.py`)
5. Manifest saved with created/validated/error files

Key value:
1. Converts plan into runnable artifacts
2. Ensures output is not only text but executable scaffold

---

## Stage D: Experiment

Implemented in:  
`orchestration/research_pipeline.py` (`run_experiment_stage_flow`)  
Runner:
`execution/experiment_runner.py`

Output:
1. Experiment goal
2. Run config
3. Metrics list
4. Execution summary files in `outputs/experiments/...`

---

## Stage E: Writing

Implemented in:  
`orchestration/research_pipeline.py` (`run_writing_stage`)

Output:
1. Section-wise writing plan
2. Output format + review focus
3. Draft files under `outputs/writing/...`

---

## 7. Human-in-the-loop control

Approval logic is centralized:
`orchestration/flow_utils.py` (`approval_gate`)

Modes:
1. **Manual**: each stage pauses for approval
2. **Auto mode**: stage approvals are auto-accepted

UI integration:
`ui/runtime.py` patches flow approval gate to Streamlit event-driven approvals.

---

## 8. Reliability and robustness design

Key reliability mechanisms:
1. **Retry wrapper** for LLM kickoff (`kickoff_with_retry`)
2. **Robust JSON parsing** (`parse_model_output`) with:
   - strict JSON
   - JSON5 fallback
   - safe literal fallback
3. **Deterministic fallback synthesis** when LLM fails/timeouts
4. **Persistent run log DB** (`outputs/flow_runs.db`) with:
   - runs
   - stage_events
   - approvals
5. **Artifact manifests** for every stage

Persistence implementation:
`storage/run_persistence.py`

---

## 9. Data and artifact layout

Main directories:
1. `outputs/literature/` — final literature JSON
2. `outputs/literature_screen/` — screening output
3. `outputs/literature_fetch/` — full text files + fetch manifest
4. `outputs/literature_analysis/` — per-paper analyses
5. `outputs/artifacts/` — stage manifests
6. `outputs/experiments/` — experiment summaries
7. `outputs/writing/` — writing drafts
8. `sandbox/...` — generated runnable coding scaffold

This is a strong presentation point: **the system is inspectable and reproducible**.

---

## 10. Why modularization was important

Earlier concern: `supervisor_flow.py` became too large.

Now:
1. `supervisor_flow.py` is a coordinator
2. Literature logic moved to `literature_pipeline.py`
3. Method/coding/experiment/writing moved to `research_pipeline.py`
4. Shared utilities moved to `flow_utils.py`
5. Shared flow exception in `exceptions.py`

Benefits:
1. Easier maintenance
2. Cleaner tests
3. Lower risk while editing
4. Better readability for teammates and evaluators

---

## 11. Tools used in literature intelligence

Search tools:
1. `ArxivSearchTool` (`tools/literature_tools.py`)
2. `SemanticScholarSearchTool` (`tools/literature_tools.py`)

Full-text fetch:
1. `PaperFullTextFetchTool` (`tools/paper_fetch_tools.py`)
2. Open-access PDF resolution
3. PDF extraction via `fitz` (PyMuPDF)

Important design choice:
1. Retrieval is broad
2. LLM decides relevance
3. Deep analysis only on selected papers

---

## 12. Validation and tests (for credibility slide)

Reliability tests:
`tests/test_reliability.py`

Covers:
1. JSON parser robustness
2. Run persistence DB writes
3. Artifact generation
4. Auto mode approval behavior
5. Runnable scaffold generation
6. Literature timeout fallback behavior
7. Compact prompt behavior
8. Multi-pass literature stage behavior
9. PDF text extraction path

Class presentation message:
**We didn’t just build a pipeline; we validated failure modes and recovery paths.**

---

## 13. Suggested PPT structure (ready-to-use)

Use this exact 14-slide order:
1. Title + team + project goal
2. Problem with normal LLM workflows
3. What “agentic” means in our design
4. End-to-end architecture diagram
5. Supervisor flow + state machine
6. Literature pipeline (2-pass + full-text)
7. Method stage
8. Coding + sandbox validation
9. Experiment + writing stages
10. Human approval + auto mode
11. Reliability mechanisms + persistence DB
12. Demo outputs/artifacts screenshot slide
13. Limitations and future improvements
14. Conclusion + Q&A

---

## 14. Demo script for your class (2–3 minutes)

1. Show command:
   ```bash
   run_flow "Survey monocular depth estimation 2023-2025"
   ```
2. Explain stage transitions and approvals
3. Show generated paths under `outputs/` and `sandbox/`
4. Show one literature JSON + one coding manifest
5. Show recent runs from `outputs/flow_runs.db`

Optional UI demo:
```bash
run_ui
```

---

## 15. Limitations (honest academic discussion)

1. Literature quality depends on external source APIs and network conditions
2. Open-access fetch cannot cover paywalled papers
3. Generated coding artifacts are scaffolds, not full production training systems
4. LLM outputs can still vary by model behavior and prompt sensitivity

---

## 16. Future work ideas (good for professor questions)

1. Add retrieval quality metrics and paper relevance scoring benchmarks
2. Add citation graph expansion after initial screening
3. Add stronger experiment execution adapters for real training frameworks
4. Add provenance linking from each synthesis claim to evidence snippets
5. Add configurable model routing per stage (fast/strong models)

---

## 17. Short viva / Q&A answers

**Q: Why is this agentic and not just chained prompts?**  
A: It has role-specialized agents, shared state, stage control logic, tool-augmented retrieval, explicit approvals, and persisted autonomous progress.

**Q: How do you handle failures?**  
A: Retry wrappers, robust parser fallback, deterministic literature fallback, and complete run/event logging.

**Q: How is reproducibility handled?**  
A: Every stage writes artifacts and manifests, plus flow metadata in SQLite.

**Q: Why split literature into multiple passes?**  
A: To reduce context overload, avoid timeouts, and let the model focus first on relevance, then deep analysis.

---

## 18. Key files to cite in your report/presentation

1. `src/agentic_ai_system/orchestration/supervisor_flow.py`
2. `src/agentic_ai_system/orchestration/literature_pipeline.py`
3. `src/agentic_ai_system/orchestration/research_pipeline.py`
4. `src/agentic_ai_system/orchestration/flow_utils.py`
5. `src/agentic_ai_system/tools/literature_tools.py`
6. `src/agentic_ai_system/tools/paper_fetch_tools.py`
7. `src/agentic_ai_system/storage/run_persistence.py`
8. `tests/test_reliability.py`

---

If you want, you can now copy each numbered section above into one slide (or one slide group) with almost no rewriting.

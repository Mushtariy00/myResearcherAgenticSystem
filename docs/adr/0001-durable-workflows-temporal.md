# ADR 0001 — Temporal owns runs; CrewAI only runs agent steps

- Status: accepted (2026-10-30)
- Deciders: project team

## Context
Runs take hours and wait days for human approval. They must survive API and worker restarts, and
they need real cancel and retry. In the legacy system the CrewAI Flow ran inside the Streamlit
process. 9 of 31 recorded runs stayed "running" forever after the process died, and Stop and
Pause did nothing while a stage was busy.

CrewAI 1.15 Flows have `@persist` and `@human_feedback`. Both are single-process and
SQLite-backed, with no worker leases, cancel API or cross-worker recovery.

## Decision
- **Temporal** (server 1.32, `temporalio` 1.35) owns the run lifecycle: one workflow per run,
  one child workflow per stage, and activities for every side effect.
- **Approvals** are Temporal *Updates*. A validator rejects a wrong stage, a stale output hash or
  an unauthorized actor before anything is recorded.
- **Cancel** reaches activities through heartbeats. **Rate-limit and budget waits** are workflow
  timers.
- **CrewAI 1.15.33** (exact pin) is used only *inside* activities, through `Agent.kickoff` with
  a Pydantic `response_format`. CrewAI Flows are not used.
- **Dev** uses `temporal server start-dev` (SQLite, light on RAM). **Prod** uses the Temporal
  server with Postgres.

## Consequences
- Workflow code must be deterministic: no I/O, no CrewAI imports, and payloads limited to ids and
  paths (Temporal's limit is 2 MB per payload).
- Code changes need `workflow.patched()` or worker versioning, because runs outlive deploys.
- Two extra containers (server and UI); the Web UI is free and helps debugging.

## Alternatives considered
- **DBOS Transact** (Postgres-only library, `fork_workflow`). Lighter, but the production
  management UI (Conductor) needs a licence when self-hosted, and its community is smaller. It is
  the fallback if RAM proves too tight.
- **LangGraph** interrupts + checkpointers: would mean rewriting the agents.
- **Celery / Arq / Taskiq**: cannot wait durably for days, so we would rebuild a state machine.

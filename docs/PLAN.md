# Agentic Research Platform v2 — approved plan (2026-10-30)

## Context
The current system (`~/projects/crewAI_agenticsys/agentic_ai_system`, WSL Ubuntu) is a single-user
prototype:
- **Back end:** a CrewAI 1.14 Flow with 6 agents.
- **UI:** Streamlit on localhost, with in-process threads and one global queue for every tab.
  Stop/Pause don't stop anything, and the page reruns every 0.3 s.
- **Storage:** SQLite plus JSON files.
- **Code execution:** generated code runs as a plain subprocess with the user's full environment.

The assessment and the run history show the problems:
- 9 of 31 past runs are stuck in "running", because their process died.
- All 13 LLM errors were 503s from free models.
- The coding agent's files are always rejected, because of an underscore/hyphen mismatch.
- The sandbox smoke test always fails, because `nyu2_architectures` is missing.
- Failed experiments report 0.0 metrics.

The team's own roadmap asks for this upgrade:
- **Class deck, slide 16:** React UI, FastAPI REST API, background worker, login, PostgreSQL
  tables.
- **`docs/PPT_PROJECT_GUIDE_FUTURE.md`:** durable orchestration, verification, containerized
  experiments, RBAC, observability.

**Decisions (2026-10-30):**
- **Users:** a lab team of 5–30.
- **Hosting:** one GPU server running Docker Compose.
- **Experiments:** real GPU runs in isolated containers.
- **LLMs:** OpenRouter. **Paid models while the user's budget allows, free models otherwise.**
- **Login:** email + password, admin invites.
- **UI languages:** English + Korean.
- **Where:** branch **`v2`** of the existing repo (`Mushtariy00/myResearcherAgenticSystem`).

**Outcome:** on `v2`, a monorepo with:
- a Next.js front end (no Streamlit);
- a FastAPI back end;
- durable Temporal workflows;
- a budget-aware LLM gateway;
- a hardened GPU executor.

`main` keeps the old system. On `v2`, the old code first moves to `legacy/` (with `git mv`) as a
reference, and `legacy/` is deleted after Phase 3. Logic is ported, not copied wholesale.

## Constraints
- **Dev box:** WSL2 Ubuntu 24.04, **7.7 GiB RAM**, 4 cores, GTX 1060 6 GB.
  - Every service gets a `mem_limit`, and Postgres is protected from the OOM killer.
  - The user raises WSL memory to about 12 GB in `.wslconfig`.
- **Not installed:** Docker and the NVIDIA Container Toolkit. Node is v18 (too old), and
  pnpm/uv are missing. The user runs a Phase 0 prerequisites checklist (needs sudo).
- **Production host:** a bare-metal Ubuntu server with an NVIDIA GPU. The WSL2 PC is dev/staging
  only, because of Windows reboots, NAT networking and no auto-start.
- **Pascal end of support:** PyTorch 2.15 (28 Oct 2026) dropped cu126, R580 is the last Pascal
  driver branch, and gVisor's GPU support doesn't cover Pascal. The image therefore pins
  **PyTorch 2.14 + cu126**. A Turing-or-newer GPU (ideally Ampere, at least 16 GB) is recommended
  for the server.
- **Dataset:** NYU2 lives on `/mnt/d` (slow from WSL). Copy it onto the Linux disk and register it
  as a read-only dataset.

## Tech stack (versions verified Oct 2026)
| Layer | Choice |
|---|---|
| Front end | **Next.js 16.4** (App Router, `output: "standalone"`) · React 19.3 · TypeScript 6.0 · Node 24 LTS · pnpm |
| UI | **shadcn/ui on Base UI** · Tailwind 4.3 · TanStack Query 5 + **Hey API** client generated from OpenAPI (exact pin) · Zustand 5 · TanStack Table 9 · ECharts 6 (training curves) + shadcn charts · Shiki 4 + lazy Monaco DiffEditor · react-pdf 11 · Streamdown 2.7 / react-markdown + KaTeX (sanitized, no raw HTML) · react-hook-form + zod 4 · **next-intl 4** (en, ko) |
| Auth | **Better Auth 1.7** in Next.js: email/password, admin plugin, organization plugin (invites, lab roles). FastAPI checks the session cookie through Better Auth's `get-session` endpoint, cached ≤60 s. No JWTs, so native `EventSource` works. |
| API | **FastAPI 0.162** (built-in SSE) · Pydantic 2.14 · SQLAlchemy 2.1 async · Alembic 1.20 |
| Workflows | **Temporal** server 1.32, `temporalio` 1.35. Dev uses `temporal server start-dev`; prod uses Postgres. |
| Agents | **CrewAI 1.15.33**, exact pin. Telemetry and tracing off; no `litellm` extra. A custom `BaseLLM` sends calls to the gateway. |
| LLM | Own **gateway service** → OpenRouter. No LiteLLM: it had malicious releases and critical CVEs in 2026. |
| Data | **PostgreSQL 18** (full-text search for papers) · **Valkey 9** (rate-limit buckets, wake-ups) · **filesystem volume** behind a storage interface (S3-compatible SeaweedFS or cloud S3 later) |
| Literature | arXiv, Semantic Scholar, OpenAlex, Crossref, Unpaywall, CORE clients · **GROBID 0.9.1** + **Docling 2.145** (CPU) |
| GPU | Docker + NVIDIA Container Toolkit **≥1.20.1** · pinned PyTorch 2.14+cu126 image |
| Ops | **Caddy 2.11** (TLS, HTTP/2, SSE unbuffered) · SOPS + age → Docker secret files · GitHub Actions → GHCR (actions pinned by SHA, attested images) → SSH deploy behind an environment approval · pgBackRest (WAL-G fallback) + restic off-box · Renovate |
| Tooling | uv 0.13 workspace (hash-locked) · ruff · pyright · pytest 9 · Biome 2.6 · Vitest 5 · Playwright 1.64 |

## Architecture and trust zones
```text
Browser ──HTTPS/2──► Caddy ─┬─ /api/v1/* ─► api (FastAPI: authz, CRUD, approvals, SSE)
                            └─ /*, /api/auth/* ─► web (Next.js + Better Auth)
api ──► Postgres ◄── workers;  api ──start/update/cancel──► temporal (+ temporal-ui)
temporal ◄── worker-flow    (workflow code only: deterministic, no I/O, no secrets)
         ◄── worker-agents  (CrewAI steps; NO provider keys) ──HTTP──► gateway (the ONLY holder of OpenRouter keys + KEK)
         ◄── worker-fetch   (PDF fetch + GROBID/Docling; egress-only network, SSRF guard, NO secrets)
         ◄── worker-gpu     (concurrency 1) ──► executor (the ONLY Docker access; fixed template) ──► sandbox (GPU, no network)
```
- **Zones:**
  - The gateway holds the keys.
  - The fetcher can reach only the internet, and only public IPs, checked after DNS and after
    every redirect, with size and time caps.
  - The executor launches only its own container template. Mounts come only from the `datasets`
    registry, and its Docker access goes through a socket proxy.
  - Nothing ever aliases the OpenRouter key into `OPENAI_API_KEY` (the legacy `env_setup.py`
    did).
- **Events:**
  - Every state change writes a `run_events` row with a **per-run sequence number** in the same
    transaction.
  - Valkey pub/sub only wakes up the SSE endpoint.
  - SSE replays rows where `seq` > `Last-Event-ID`, with heartbeats and proxy buffering off.
- **Temporal rules:**
  - Each stage is a child workflow.
  - Payloads carry ids and paths only.
  - Long activities heartbeat, so cancel works.
  - Rate-limit and budget waits are workflow timers.
  - Code changes use `workflow.patched()` / worker versioning, because runs wait days for
    approval.
- Compose profiles: `core`, `gpu`, `dev` (Mailpit), `obs` (Phase 4). Each service has a RAM
  budget; dev uses about 4 GiB, plus about 1 GiB for `next dev`. GROBID and Docling run on demand.

## Run and stage state machine
- **Run:** `queued → running ⇄ awaiting_approval → completed | rejected | failed | cancelled`.
  `paused_budget` is entered only when the *lab account* balance is exhausted.
- **Stage attempt:** `pending → running → output_ready → approved | changes_requested (new
  attempt, capped at 3, cost shown) | rejected | failed (retryable) | cancelled`.
- **Approve with edits** saves a new output version, which is then approved.
- **Approvals bind to `stage_output_id` + content sha256.** A stale or duplicate approval returns
  **409**. The Temporal Update validator re-checks stage, actor and hash.
- **Retrying stage N invalidates the outputs of stages N+1 onward.**
- **GPU job id = stage attempt id.** It is the container label, so the executor adopts or reaps
  containers at startup, and cancel is a compare-and-set.
- **Approval waits:** a reminder after 24 h; the run is auto-cancelled after 7 days, as a project
  setting.
- **Coding stage:** never auto-approved.

## Permissions (enforced in FastAPI and re-checked in Update validators)
| Action | Lab admin | Project owner | Researcher | Viewer |
|---|---|---|---|---|
| Invite/offboard users, budgets, model routing, paid-model kill switch | ✓ | | | |
| Create project, manage its members and settings | ✓ | own | | |
| Start a run (charged to the starter's budget) | ✓ | ✓ | ✓ | |
| Approve, request changes, retry, cancel (charged to the run owner) | ✓ | ✓ | own runs | |
| View runs, papers, artifacts; comment | ✓ | ✓ | ✓ | ✓ |

## Domain model (PostgreSQL; Alembic from Phase 1; Better Auth owns the `auth` schema)
- `projects` (+ `privacy: standard | confidential`, `allow_free_models`)
- `project_members` (role)
- `runs` (topic, typed config, status, owner, workflow_id, `llm_policy: auto | free`,
  budget_cap_usd, `last_event_seq`)
- `stage_runs` (run, stage, attempt, status, error)
- `stage_outputs` (stage_run, version, data JSONB, sha256, schema_version, prompt_version, model,
  `degraded` + reason)
- `approvals` (stage_output_id, sha256, decision, comment, actor, at)
- `run_events` (run_id, seq, type, payload; PK run_id + seq)
- `audit_log` (separate from events)
- `papers` (unique DOI/arXiv/S2 id; metadata)
- `paper_texts` (parsed sections JSONB, `tsvector`)
- `run_papers` (score, screening decision, reason)
- `datasets` (name, version, host path, checksum, data contract; ports `data_contract.json`)
- `artifacts` (kind, path, sha256, size, retention)
- `gpu_jobs` (id = stage attempt, status, container_id, **provenance:** image digest, code and
  config sha256, dataset version, seed; metrics JSONB with `null` for missing values; exit code;
  GPU-seconds)
- `llm_calls` — a **journal:** idempotency key, state `reserved → sent → settled | unknown |
  released`, reserved_usd, cost_usd, unique `generation_id`, lease, tokens, latency, error class,
  tier
- `budgets` (user, monthly_usd, UTC-month period)
- `provider_keys` (per-user OpenRouter key, encrypted with the KEK)
- `model_catalog` (prices, context length, passive health)
- `settings` (paid-models kill switch)

## LLM gateway: paid if the budget allows, otherwise free
Facts (OpenRouter docs, Oct 2026):
- Every key can have a credit `limit` with a monthly reset (UTC), managed with a management key.
- `usage` in each response reports the actual cost; `/generation?id=` returns exact cost later.
- A key over its limit gets **402** with `limit_source: openrouter_key_limit`.
- Free models allow **20 requests/min and 50/day per account**, or 1,000/day after a lifetime
  $10 purchase. Extra keys don't add capacity, so the lab should buy $10 once.

How the gateway works:
1. **Holds all keys:**
   - the lab management key;
   - one provisioned key per user, whose limit equals the user's monthly budget.
   - **Auto top-up stays OFF.** The management key can raise any limit, so the prepaid balance is
     the true lab cap, with an alert at a balance floor.
2. **Journal per call:**
   - Reserve input tokens plus the role's **max output tokens** × price, against the minimum of
     the user's budget and the run cap.
   - Send with an idempotency key and OpenRouter's `max_price`.
   - Settle from `usage`.
   - A sweeper reconciles calls left in `unknown` through `/generation`.
3. **Routing:**
   - If the reservation succeeds and the kill switch is off → the role's paid chain.
   - Otherwise → the role's free chain, after checking that the free model's context length fits.
   - Run policy is **Auto** (default) or **Free only**.
   - Cheap roles (query expansion, screening) can be configured to stay on free models.
4. **402 handling:**
   - A user key limit → the rest of the run continues on free models, and the UI marks
     "switched to free".
   - An exhausted lab balance (free models fail too) → `paused_budget`, and admins get an alert.
5. **Free quota:** one account-wide bucket (20/min, 1,000/day) with a **per-user fair share**.
   Model health comes from real call outcomes plus a daily `/models` refresh; there are no
   quota-burning probes.
6. **Privacy:**
   - `confidential` projects route with `data_collection: deny`, which may exclude most free
     models; the UI says so.
   - `allow_free_models=false` disables free models entirely.
7. **Crash replay reuses already-paid responses** (keyed by stage attempt + call index). A
   deliberate retry is a new attempt, so it is never served from cache.
8. **Visibility:**
   - an estimated cost range in the run wizard;
   - live spend per run;
   - a spend dashboard (user, run, model; paid vs free);
   - alerts at 80% and 100% of budget.
9. **Port from legacy:** `orchestration/flow_utils.py` `extract_json_candidate` /
   `parse_model_output`, plus **strict schemas** (required fields, `extra="forbid"`) and one
   repair retry.

## Literature pipeline (worker-fetch + worker-agents)
- **Sources** use lab-level keys and shared token buckets, because all users share one IP:
  - OpenAlex: a free key gives $1/day; search costs $1 per 1,000.
  - Semantic Scholar: 1 req/s.
  - arXiv: 1 request / 3 s, and PDFs are never served publicly.
  - Crossref: 10 req/s.
  - Unpaywall/CORE: open-access waterfall.
  - PMC: the Cloud Service, since the OA FTP service was retired on 24 Aug 2026.
- **The waterfall is ported** from `tools/paper_fetch_tools.py` and
  `docs/literature_sources_plan.md`. Each PDF is validated (magic bytes, type, size), parsed with
  GROBID (header, references) + Docling (sections, tables, formulas), and falls back to the
  abstract when parsing fails. That fixes "23 of 32 text files empty".
- **No silent placeholders:** legacy fallback papers and "Fallback analysis…" text become errors
  or outputs flagged `degraded`.
- **Citations:** each must match a retrieved `papers` row, or resolve by DOI/arXiv id or title
  match (≥0.9, same first author, year ±1). Retractions are flagged.
- **Paper text is delimited data.** Agents that read papers have no tools.

## GPU experiments (executor)
- **Harness:** the base image owns data splits, the loader, metrics and the training loop
  (`train/loop.py`). Silent fallbacks to `generic` or `synthetic` are removed, and
  `torch.load(weights_only=True)` is used only inside the sandbox.
  - The **coding agent writes only model and loss modules** (allowlisted, one validated slug).
  - Experiment config is a **typed, bounded** model with epoch, batch and learning-rate ranges.
  - A capped coding → smoke-test → repair loop runs at most 3 times. Generated code is reviewed in
    a Monaco diff.
- **Container flags:**
  - `--network none --read-only --tmpfs /tmp --user 10001 --cap-drop ALL`
  - `--security-opt no-new-privileges`, default seccomp
  - `--pids-limit`, `--memory` = `--memory-swap`, `--cpus`, `--shm-size 2g`
  - `--gpus device=0`
  - dataset mounted `:ro`; per-job output with a size quota
  - wall-clock kill
  - **no secrets, no docker.sock, no `--privileged`**
- **Queue:** a Postgres `SKIP LOCKED` queue with concurrency 1, leases, a VRAM preflight check and
  checkpoints. **GPU policy:** a max runtime, a per-user queue limit, a GPU-hours quota, and a
  visible queue.
- **Results:** honest status. Missing metrics are `null`, never 0.0, and full provenance is
  stored.
- **Later:** switch to gVisor `runsc --nvproxy` once the server has a supported GPU, and use
  Kubernetes Jobs or SkyPilot if needed.

## Front end (pages)
- **Access:** login and invite acceptance (with a copyable link when there is no SMTP), profile.
- **Dashboard:** projects, recent runs, GPU queue, spend.
- **Project:**
  - a runs table;
  - a paper library (full-text search across runs);
  - members;
  - settings (privacy, free models, auto-approve, approval expiry).
- **New run wizard:** topic, years, sources, number of papers, stages, dataset, LLM policy, cost
  cap, plus the estimated cost.
- **Run detail (core screen):**
  - a live stage timeline;
  - an event log (LLM calls with paid/free tier, retries, rate-limit waits);
  - an approval panel (preview, diff, edit, comment, approve / request changes / reject);
  - cancel and retry;
  - live spend.
- **Stage views:**
  - Literature: a papers table, a PDF viewer with evidence, and analyses.
  - Method: proposal cards.
  - Code: a file tree and Monaco diff.
  - Experiment: ECharts curves, logs, provenance.
  - Writing: the draft with linked citations, plus export.
- **Admin:**
  - users and invites;
  - budgets and the kill switch;
  - model routing per role;
  - lab balance;
  - system health;
  - the audit log.
- **Notifications** (in-app, plus email via SMTP; Mailpit in dev): approval needed or expiring,
  run done or failed, budget alerts, GPU job started.
- **Browser hardening:**
  - a strict CSP and sanitized Markdown;
  - files streamed by the API with `nosniff` and `attachment`;
  - API errors and events sent as **message codes** translated by next-intl. Drafts stay English
    unless a project sets otherwise.

## API surface (`/api/v1`, OpenAPI → generated TS client)
- `/me`, `/me/notifications`
- `/projects` (+ `/members`, `/settings`)
- `/runs` (create, list)
- `/runs/{id}` (+ `/cancel`, `/retry?stage=`, `/approvals`, `/stages/{stage}`)
- `GET /runs/{id}/events` (SSE)
- `/papers?q=`, `/papers/{id}` (+ `/file`), `/artifacts/{id}` (streamed)
- `/datasets`, `/gpu/queue`, `/usage`
- `/admin/{users,budgets,models,settings,audit}`

Every state-changing request checks `Origin` (CSRF) and uses SameSite=Lax cookies.

## Port map from `legacy/`
| Old | New |
|---|---|
| `config/agents.yaml` roles and prompts | `packages/agents` (versioned prompt registry) |
| `orchestration/literature_pipeline.py` (queries, ranking, screening, chunking, prompts) | `packages/agents/literature` |
| `tools/literature_tools.py`, `tools/paper_fetch_tools.py`, sources plan | `packages/scholarly` |
| `orchestration/flow_utils.py` JSON hardening | `apps/gateway` / `packages/llm` |
| `schemas/*.py` | `packages/core/schemas` (made strict) |
| `train/loop.py`, `model/registry.py`, `data/nyu2_loader.py`, `model/nyu2_architectures.py` | `sandbox/pytorch` harness |
| `tools/model_checker.py`, `tools/update_model.py` | model catalog refresh |
| `data_contract.json`, `env_manifest.json` | `datasets` row, image metadata |
| mocked tests | pytest per package |

Dropped:
- Streamlit `ui/` and its `bridge.py` globals
- SQLite persistence
- the agentmemory MCP stub; project memory comes back later on pgvector, from approved outputs
  only
- committed artifacts (`outputsv1/`, `sandbox1/`, `outputs/flow_runs.db`, `*:Zone.Identifier`)

An optional script imports the old runs.

## Repo layout (`v2`)
```text
apps/web, apps/api, apps/gateway, apps/worker (flow|agents|fetch|gpu roles), apps/executor
packages/core, db, workflows, agents, llm (client used by workers), scholarly, events
sandbox/pytorch (not a uv member) · infra/compose (+ Caddyfile, SOPS secrets) · docs/adr · legacy/
```

## Roadmap — each phase ships its own controls and tests
| Phase | Scope | Exit criteria |
|---|---|---|
| **0. Foundations + risk spikes** | User prerequisites (Docker + NVIDIA toolkit ≥1.20.1 in WSL, Node 24, pnpm, uv, `.wslconfig`, dataset copy). Branch `v2`, `legacy/`, monorepo scaffold, compose dev stack with RAM limits, CI, ADRs (Temporal vs DBOS, Next vs Vite, auth, storage). **Spike:** the hardened PyTorch 2.14 image trains on the 1060. | `compose up` is healthy within budget; CI green; **one NYU2 epoch trains in the hardened container** with metrics; `curl` is blocked inside |
| **1. Platform core** | Better Auth (invites, roles, CLI bootstrap of the first admin, offboarding that deletes keys), projects and permissions, runs, state machine, Temporal skeleton, approvals with hash binding, cancel, events + SSE. **Gateway:** per-user keys, budgets, journal, paid/free routing, 402 handling. **One real CrewAI step through `BaseLLM` → gateway.** Web: login, projects, wizard, run detail with live timeline and approvals; en/ko scaffolding. | In the browser: a run makes a real LLM call, waits, is approved; another run is cancelled mid-call; killing a worker resumes the run; ledger = OpenRouter usage; stale approval → 409; viewer can't approve |
| **2. Literature → method → writing** | worker-fetch zone (SSRF guard), scholarly clients and buckets, waterfall, GROBID + Docling, paper library (full-text search), strict schemas and `degraded` flags, citation verification, method and writing stages, spend dashboard, notifications, approval reminders and expiry. **Then:** Caddy TLS on the server, off-box backups and a restore drill. | A full run works on a paid budget and on free only; every citation resolves; SSRF tests pass; restore drill succeeds; **first lab users onboarded** |
| **3. Real experiments** | Executor (template only, dataset registry, labels, adopt/reap, CAS cancel, GPU policy), harness-owned data and metrics, model/loss-only coding agent, bounded config, repair loop, provenance, ECharts metrics, Monaco diff review. Delete `legacy/`. | NYU2 run from the UI → real metrics + provenance; fork-bomb, disk-fill, no-network and no-secrets tests pass; cancel kills the job in ≤5 s; worker restart never duplicates a container |
| **4. Hardening + observability** | Prod compose on the Linux GPU server, CD with an approval step, `obs` profile (OpenTelemetry → otel-lgtm), alerts (balance floor, failures, GPU), OWASP LLM + Agentic Top 10 (2026) review, artifact retention jobs, Renovate, load test, runbooks | Alerts fire in drills; about 10 concurrent users without errors; runbooks reviewed |
| **5. Later** | pgvector semantic search and project memory, BYOK, project budgets, paid-only mode, pause, fork from stage, evaluator / LLM-as-judge agents, citation graph, gVisor after a GPU upgrade, Helm/k3s, Langfuse, CopilotKit chat panel | — |

## Verification
- **Unit (pytest):**
  - gateway routing, reservation and settlement, sweeper reconciliation;
  - 402 classification and fair-share bucket;
  - JSON hardening and strict schemas;
  - scholarly clients (mocked HTTP).
- **Workflow (Temporal time-skipping test environment):**
  - approve, request-changes and reject paths;
  - stale approval → 409;
  - retry invalidates later stages;
  - cancel during an LLM call and during a GPU job;
  - crash mid-stage → resume without paying twice;
  - budget exhausted → switches to free; lab balance exhausted → `paused_budget`.
- **API** (pytest + httpx + testcontainers Postgres):
  - the permission matrix;
  - CSRF/Origin checks;
  - SSE replay with `Last-Event-ID`, with no gaps under concurrent writes.
- **Security tests:**
  - SSRF to `169.254.169.254`, `localhost` and redirect chains;
  - a raw-HTML/XSS payload in an LLM output renders inert;
  - sandbox: fork bomb, disk fill, `curl`, `env` without secrets, writes outside the output
    folder.
- **E2E (Playwright** against compose with a fake OpenRouter): invite → login → run → live
  events → approve → papers, method and draft pages → cancel; plus the Korean locale.
- **Live checks on this PC:**
  - an NYU2 run from the UI;
  - a $0.05 budget cap, where the ledger matches OpenRouter `/key` usage and the run continues on
    free models.
- **CI on every PR:** Biome, ruff, pyright, unit, API, E2E (fake LLM), plus the image build.

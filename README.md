# Agentic Research Platform (v2)

A multi-user web platform that turns a research topic into reviewed outputs:
literature → method → coding → experiment → writing. A human approves each stage, and experiments
run on a GPU in locked-down containers.

This branch (`v2`) is a production rebuild of the CrewAI + Streamlit prototype on `main`.
- **What and why:** [docs/PLAN.md](docs/PLAN.md).
- **Key decisions:** [docs/adr/](docs/adr/).
- **Old code:** kept read-only in [legacy/](legacy/) while its logic is ported. It is deleted
  after Phase 3.

**Status:** Phase 0 (foundations and risk spikes).

## Stack
| Part | Choice |
|---|---|
| Front end | Next.js 16.4 · React 19 · TypeScript 6 · shadcn/ui · TanStack Query · next-intl (en/ko) |
| API | FastAPI 0.162 · Pydantic 2 · SQLAlchemy 2 + Alembic (Phase 1) |
| Workflows | Temporal (approvals, cancel, retries; runs survive restarts) |
| Agents | CrewAI 1.15 inside Temporal activities, through a budget-aware OpenRouter gateway |
| Data | PostgreSQL 18 · Valkey 9 · filesystem volume (S3-compatible later) |
| GPU | Hardened Docker + NVIDIA Container Toolkit, PyTorch 2.14 / CUDA 12.6 image |

## Layout
```text
apps/api            FastAPI service            (Python, uv workspace member)
apps/web            Next.js front end          (pnpm workspace member)
packages/core       shared stages + strict stage-output schemas
sandbox/pytorch     GPU training image + harness (data, metrics, loop)
infra/compose       dev infrastructure (compose.yaml, Caddyfile.dev)
scripts/            setup, doctor, sandbox smoke test, backup / restore / restore drill
docs/               plan, ADRs and runbooks (docs/runbooks/backup-restore.md)
legacy/             the old system, for reference while porting
```

## Getting started (WSL2 Ubuntu 24.04)
1. **One-time setup.** Run the script yourself; it asks for your sudo password:
   ```bash
   bash scripts/setup-prereqs.sh
   ```
   It installs Docker, the NVIDIA Container Toolkit, uv, Node 24 and pnpm. Then open a new
   terminal. Giving WSL more memory is recommended; the script prints how.
2. **Check the machine:**
   ```bash
   make doctor
   ```
3. **Install dependencies.** This creates `uv.lock` and `pnpm-lock.yaml`, which you commit:
   ```bash
   make setup
   ```
4. **Start the infrastructure** (Postgres, Valkey, Temporal, Mailpit, proxy), create `.env`, and
   migrate the database:
   ```bash
   make up && make env && make migrate
   ```
   Paste your OpenRouter key into `ARP_OPENROUTER_API_KEY` in `.env`.
5. **Create the first admin.** It prompts for a password:
   ```bash
   make bootstrap-admin email=you@lab.kr name="Your Name"
   ```
6. **Run the services**, one terminal each: `make api`, `make gateway`, `make worker`, `make web`.
   With no OpenRouter quota left, run `make fake-openrouter` and start the gateway with
   `ARP_OPENROUTER_BASE_URL=http://127.0.0.1:8199/api/v1 make gateway`.
7. **Open the app** at http://localhost:8080. Sign in, create a project, start a run, and approve
   or cancel it.
   - Temporal UI: http://localhost:8233
   - Mailpit (invite emails): http://localhost:8025
8. **Run the GPU spike:**
   ```bash
   make sandbox-smoke
   ```
   It proves that the hardened container sees the GPU, has no network or secrets, and trains on
   NYU2 with real metrics.

`make help` lists every target.

## Phase 0 exit criteria
- `make up` is healthy within the memory budget, and CI is green.
- `make sandbox-smoke` passes all 6 checks. `make sandbox-epoch` trains one full NYU2 epoch in the
  hardened container. Copy the dataset to the Linux disk first and set `DATASET_DIR`; reading
  from `D:` is slow.

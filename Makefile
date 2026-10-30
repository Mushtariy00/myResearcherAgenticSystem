SHELL := /usr/bin/env bash
COMPOSE := docker compose -f infra/compose/compose.yaml --env-file infra/compose/.env --profile dev
ALEMBIC := uv run alembic -c packages/db/alembic.ini
# Settings for the services run on the host (created from .env.example by `make env`).
-include .env
export
# Temporal's dev server writes its state as the host user (see infra/compose/compose.yaml).
export ARP_UID := $(shell id -u)
export ARP_GID := $(shell id -g)

.DEFAULT_GOAL := help
.PHONY: help doctor setup env up down ps logs migrate migration bootstrap-admin demo-seed client api gateway worker fake-openrouter web lint format typecheck test sandbox-build sandbox-smoke sandbox-epoch

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

doctor: ## Check that this machine has everything installed
	@bash scripts/doctor.sh

setup: ## Install Python and web dependencies (writes uv.lock / pnpm-lock.yaml)
	uv sync --all-packages
	pnpm install

infra/compose/.env:
	cp infra/compose/.env.example $@
	@echo "Created $@ - change the dev password if you like."

env: .env ## Create .env (app settings) from .env.example

.env:
	cp .env.example $@
	@echo "Created $@ - paste your OpenRouter key into ARP_OPENROUTER_API_KEY."

migrate: .env ## Apply database migrations (ours, then Better Auth's auth schema)
	$(ALEMBIC) upgrade head
	pnpm --filter @agentic/web auth:migrate

bootstrap-admin: .env ## Create the first admin (prompts for a password): make bootstrap-admin email=you@lab.kr name="Your Name"
	@test -n "$(email)" -a -n "$(name)" || { echo 'usage: make bootstrap-admin email=you@lab.kr name="Your Name"'; exit 1; }
	@read -rsp "Password for $(email) (at least 12 characters): " pw && echo && \
		BOOTSTRAP_ADMIN_PASSWORD="$$pw" pnpm --silent --filter @agentic/web bootstrap-admin -- --email "$(email)" --name "$(name)"

demo-seed: .env ## Demo users, projects and runs for the UI (needs make up, migrate and a worker)
	pnpm --filter @agentic/web exec node scripts/seed-demo-users.ts
	uv run --package agentic-worker python -m agentic_worker.seed_demo

client: ## Regenerate the TypeScript API client from FastAPI's OpenAPI
	pnpm --filter @agentic/web gen:openapi
	pnpm --filter @agentic/web gen:client

migration: .env ## Create a migration from model changes: make migration m="add x"
	$(ALEMBIC) revision --autogenerate -m "$(m)"

up: infra/compose/.env ## Start dev infrastructure (Postgres, Valkey, Temporal, Mailpit, proxy)
	mkdir -p .data/temporal
	$(COMPOSE) up -d --wait

down: ## Stop dev infrastructure (data is kept)
	$(COMPOSE) down

ps: ## Show infrastructure status
	$(COMPOSE) ps

logs: ## Follow infrastructure logs
	$(COMPOSE) logs -f --tail=100

api: ## Run the API with reload on 127.0.0.1:8000 (browse via http://localhost:8080)
	uv run --package agentic-api uvicorn agentic_api.main:app --reload --host 127.0.0.1 --port 8000

gateway: .env ## Run the internal LLM gateway on 127.0.0.1:8100 (workers call it; holds the OpenRouter key)
	uv run --package agentic-gateway uvicorn agentic_gateway.app:app --reload --host 127.0.0.1 --port 8100

fake-openrouter: ## Run a fake OpenRouter on 127.0.0.1:8199 (set ARP_OPENROUTER_BASE_URL=http://127.0.0.1:8199/api/v1)
	uv run uvicorn fake_openrouter_server:app --app-dir apps/gateway/tests --host 127.0.0.1 --port 8199

worker: .env ## Run the Temporal worker (run workflows and stage activities)
	uv run --package agentic-worker python -m agentic_worker

web: ## Run the Next.js dev server on 127.0.0.1:3000 (browse via http://localhost:8080)
	pnpm --filter @agentic/web dev

lint: ## Lint Python and web code
	uv run ruff check .
	uv run ruff format --check .
	pnpm lint

format: ## Auto-format Python and web code
	uv run ruff format .
	uv run ruff check --fix .
	pnpm format

typecheck: ## Type-check Python and web code
	uv run pyright
	pnpm --filter @agentic/web typecheck

test: ## Run Python tests
	uv run pytest

sandbox-build: ## Build the GPU sandbox image
	docker build -t arp-sandbox-pytorch:dev sandbox/pytorch

sandbox-smoke: ## Phase 0 spike: hardened GPU container trains 200 NYU2 steps
	bash scripts/sandbox-smoke.sh nyu2-smoke.yaml

sandbox-epoch: ## Phase 0 exit check: one full NYU2 epoch in the sandbox (slow)
	bash scripts/sandbox-smoke.sh nyu2-epoch.yaml

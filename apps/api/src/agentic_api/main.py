"""API entry point. Every route lives under ``/api/v1`` (Caddy routes that prefix here)."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx
import redis.asyncio as redis
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio.client import Client

from agentic_api import __version__
from agentic_api.auth import SessionVerifier
from agentic_api.orchestrator import Orchestrator, TemporalOrchestrator
from agentic_api.routers import admin, events, projects, runs
from agentic_api.settings import Settings, get_settings
from agentic_core import NEVER_AUTO_APPROVE, STAGE_ORDER
from agentic_core.contracts import DecisionInput
from agentic_db import create_engine, session_factory

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str


class StageInfo(BaseModel):
    id: str
    position: int
    auto_approvable: bool


class LazyTemporalOrchestrator:
    """Connects to Temporal on first use, so the API starts even while Temporal is down."""

    def __init__(self, address: str) -> None:
        self._address = address
        self._inner: TemporalOrchestrator | None = None
        self._lock = asyncio.Lock()

    async def _get(self) -> TemporalOrchestrator:
        async with self._lock:
            if self._inner is None:
                self._inner = TemporalOrchestrator(await Client.connect(self._address))
            return self._inner

    async def start_run(self, run_id: uuid.UUID) -> str:
        return await (await self._get()).start_run(run_id)

    async def decide(self, run_id: uuid.UUID, decision: DecisionInput) -> None:
        await (await self._get()).decide(run_id, decision)

    async def cancel_run(self, run_id: uuid.UUID) -> None:
        await (await self._get()).cancel_run(run_id)


@dataclass
class AppState:
    sessions: async_sessionmaker[AsyncSession] | None
    session_verifier: Any  # SessionVerifier or a test double with the same verify()
    valkey: Any
    orchestrator: Orchestrator


def attach_state(app: FastAPI, state: AppState) -> None:
    app.state.sessions = state.sessions
    app.state.session_verifier = state.session_verifier
    app.state.valkey = state.valkey
    app.state.orchestrator = state.orchestrator


def create_app(settings: Settings | None = None, *, state: AppState | None = None) -> FastAPI:
    """Build the app. Tests pass `state` to supply their own database, auth and orchestrator."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if state is not None:
            attach_state(app, state)
            yield
            return
        engine = create_engine(settings.database_url) if settings.database_url else None
        http = httpx.AsyncClient(timeout=10)
        valkey = redis.from_url(settings.valkey_url)
        attach_state(
            app,
            AppState(
                sessions=session_factory(engine) if engine else None,
                session_verifier=SessionVerifier(
                    settings.auth_url, settings.auth_cache_seconds, http
                ),
                valkey=valkey,
                orchestrator=LazyTemporalOrchestrator(settings.temporal_address),
            ),
        )
        try:
            yield
        finally:
            await http.aclose()
            await valkey.aclose()
            if engine is not None:
                await engine.dispose()

    app = FastAPI(
        title="Agentic Research Platform API",
        version=__version__,
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    if state is not None:
        attach_state(app, state)  # also usable without running the lifespan

    @app.middleware("http")
    async def require_same_origin(request: Request, call_next: Any) -> Any:
        """CSRF guard: browsers send Origin on state-changing requests; it must be ours."""
        if (
            request.method not in SAFE_METHODS
            and request.headers.get("origin") != settings.public_origin
        ):
            return JSONResponse({"detail": "csrf.origin_mismatch"}, status_code=403)
        return await call_next(request)

    system = APIRouter(prefix="/api/v1", tags=["system"])

    @system.get("/health", operation_id="getHealth")
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__, environment=settings.environment)

    @system.get("/stages", operation_id="listStages")
    async def list_stages() -> list[StageInfo]:
        return [
            StageInfo(
                id=stage.value, position=index, auto_approvable=stage not in NEVER_AUTO_APPROVE
            )
            for index, stage in enumerate(STAGE_ORDER)
        ]

    app.include_router(system)
    app.include_router(projects.router)
    app.include_router(runs.router)
    app.include_router(events.router)
    app.include_router(admin.router)
    return app


app = create_app()

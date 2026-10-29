"""API entry point. Every route lives under ``/api/v1`` (Caddy routes that prefix here)."""

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from agentic_api import __version__
from agentic_api.settings import Settings, get_settings
from agentic_core import NEVER_AUTO_APPROVE, STAGE_ORDER


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str


class StageInfo(BaseModel):
    id: str
    position: int
    auto_approvable: bool


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="Agentic Research Platform API",
        version=__version__,
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
    )
    router = APIRouter(prefix="/api/v1")

    @router.get("/health", tags=["system"], operation_id="getHealth")
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__, environment=settings.environment)

    @router.get("/stages", tags=["runs"], operation_id="listStages")
    async def list_stages() -> list[StageInfo]:
        return [
            StageInfo(
                id=stage.value, position=index, auto_approvable=stage not in NEVER_AUTO_APPROVE
            )
            for index, stage in enumerate(STAGE_ORDER)
        ]

    app.include_router(router)
    return app


app = create_app()

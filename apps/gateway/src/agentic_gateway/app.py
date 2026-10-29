"""Internal HTTP API for workers. Not routed by Caddy; listens on 127.0.0.1 and needs a token."""

import asyncio
import contextlib
import hmac
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Annotated, Literal, cast

import httpx
import redis.asyncio as redis
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from agentic_core.enums import LlmPolicy, LlmTier
from agentic_db import create_engine, session_factory
from agentic_gateway.catalog import Catalog
from agentic_gateway.openrouter import (
    AccountBalanceError,
    AuthError,
    FreeDailyLimitError,
    OpenRouterClient,
    UpstreamRateLimitError,
)
from agentic_gateway.quota import Counter, FreeQuota, QuotaExhaustedError
from agentic_gateway.service import (
    CompletionRequest,
    FreeModelsDisabledError,
    NoModelAvailableError,
    Router,
)
from agentic_gateway.settings import GatewaySettings, get_settings

log = logging.getLogger(__name__)
SWEEP_SECONDS = 300


class MessageIn(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class CompleteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=1, max_length=180)
    user_id: str = Field(min_length=1, max_length=64)
    role: str = Field(min_length=1, max_length=64)
    messages: list[MessageIn] = Field(min_length=1)
    run_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    policy: LlmPolicy = LlmPolicy.AUTO
    budget_cap_usd: Decimal | None = Field(default=None, ge=0)
    max_output_tokens: int = Field(default=2048, ge=16, le=32_000)
    json_mode: bool = False


class CompleteOut(BaseModel):
    content: str
    model: str
    tier: LlmTier
    cost_usd: Decimal
    prompt_tokens: int | None
    completion_tokens: int | None
    switched_to_free: bool
    replayed: bool


def _split(value: str) -> list[str] | None:
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or None


def create_app(settings: GatewaySettings | None = None, *, router: Router | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if router is not None:
            app.state.router = router
            yield
            return
        engine = create_engine(settings.database_url)
        http = httpx.AsyncClient()
        valkey = redis.from_url(settings.valkey_url)
        api_key = settings.openrouter_api_key.get_secret_value()
        app.state.router = Router(
            session_factory(engine),
            Catalog(http, settings.openrouter_base_url),
            OpenRouterClient(http, settings.openrouter_base_url, api_key, settings.public_origin),
            FreeQuota(
                cast(Counter, valkey),
                settings.free_requests_per_minute,
                settings.free_requests_per_day,
                settings.free_requests_per_user_per_day,
            ),
            paid_models=_split(settings.paid_models),
            free_models=_split(settings.free_models),
            timeout=settings.request_timeout_seconds,
            lease_seconds=settings.lease_seconds,
        )

        async def sweeper() -> None:
            while True:
                await asyncio.sleep(SWEEP_SECONDS)
                try:
                    await app.state.router.sweep(http, settings.openrouter_base_url, api_key)
                except Exception:
                    log.exception("sweep failed")

        task = asyncio.create_task(sweeper())
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            await http.aclose()
            await valkey.aclose()
            await engine.dispose()

    app = FastAPI(
        title="Agentic Research Platform LLM gateway",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    if router is not None:
        app.state.router = router

    async def require_token(authorization: Annotated[str, Header()] = "") -> None:
        expected = settings.gateway_token.get_secret_value()
        if not expected or not hmac.compare_digest(
            authorization.encode(), f"Bearer {expected}".encode()
        ):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "gateway.token_required")

    @app.get("/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/complete", response_model=CompleteOut, dependencies=[Depends(require_token)])
    async def complete(body: CompleteIn, request: Request) -> CompleteOut | JSONResponse:
        try:
            result = await request.app.state.router.complete(
                CompletionRequest(
                    idempotency_key=body.idempotency_key,
                    user_id=body.user_id,
                    role=body.role,
                    messages=[m.model_dump() for m in body.messages],
                    run_id=body.run_id,
                    project_id=body.project_id,
                    policy=body.policy,
                    budget_cap_usd=body.budget_cap_usd,
                    max_output_tokens=body.max_output_tokens,
                    json_mode=body.json_mode,
                )
            )
        except (QuotaExhaustedError, UpstreamRateLimitError, FreeDailyLimitError) as exc:
            code = {
                QuotaExhaustedError: "free_quota.exhausted",
                FreeDailyLimitError: "free_quota.daily_exhausted",
            }.get(type(exc), "upstream.rate_limited")
            return JSONResponse(
                {"detail": code, "retry_after": exc.retry_after},
                status_code=429,
                headers={"Retry-After": str(int(exc.retry_after))},
            )
        except AccountBalanceError:
            return JSONResponse({"detail": "lab_balance.exhausted"}, status_code=402)
        except AuthError:
            log.error("OpenRouter rejected the API key (HTTP 401); check ARP_OPENROUTER_API_KEY")
            return JSONResponse({"detail": "upstream.auth_failed"}, status_code=502)
        except FreeModelsDisabledError:
            return JSONResponse({"detail": "free_models.disabled"}, status_code=403)
        except NoModelAvailableError:
            return JSONResponse({"detail": "upstream.unavailable"}, status_code=502)
        return CompleteOut(**result.__dict__)

    return app


app = create_app()

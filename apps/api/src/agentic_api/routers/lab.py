"""Lab administration views over the LLM setup: model routing and the OpenRouter balance."""

from datetime import UTC, datetime, time
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_api.auth import CurrentUser, current_user
from agentic_api.authz import get_db, require_admin
from agentic_api.demo.balance import ALERT_FLOOR_USD, balance
from agentic_api.demo.catalog import (
    DEFAULT_FREE_MODELS,
    DEFAULT_PAID_MODELS,
    model_chain,
    role_routing,
)
from agentic_api.schemas import LabBalanceOut, ModelRoutingOut
from agentic_db.lab_settings import paid_models_enabled
from agentic_db.spend import month_start
from agentic_db.usage import free_requests_since, lab_month_spend

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
User = Annotated[CurrentUser, Depends(current_user)]
Db = Annotated[AsyncSession, Depends(get_db)]


@router.get("/models", operation_id="getModelRouting")
async def get_model_routing(request: Request, user: User, db: Db) -> ModelRoutingOut:
    """Per agent role, the paid and free model chains the gateway tries, with catalog details,
    and the real state of the paid-models kill switch."""
    require_admin(user)
    settings = request.app.state.settings
    return ModelRoutingOut(
        paid_models_enabled=await paid_models_enabled(db),
        roles=role_routing(
            model_chain(settings.paid_models, DEFAULT_PAID_MODELS),
            model_chain(settings.free_models, DEFAULT_FREE_MODELS),
        ),
        demo=True,
    )


@router.get("/balance", operation_id="getLabBalance")
async def get_lab_balance(request: Request, user: User, db: Db) -> LabBalanceOut:
    """The lab's prepaid OpenRouter balance (generated until the gateway reads it), with the
    real paid spend this month and the real free-tier use today."""
    require_admin(user)
    now = datetime.now(UTC)
    spent = await lab_month_spend(db, now)
    left = balance(now, spent)
    return LabBalanceOut(
        balance_usd=left,
        month=month_start(now).strftime("%Y-%m"),
        spent_this_month_usd=spent,
        free_daily_limit=request.app.state.settings.free_requests_per_day,
        free_calls_today=await free_requests_since(
            db, datetime.combine(now.date(), time(), tzinfo=UTC)
        ),
        auto_top_up=False,
        alert_floor_usd=ALERT_FLOOR_USD,
        below_floor=left < ALERT_FLOOR_USD,
        checked_at=now,
        demo=True,
    )

"""Lab administration over the LLM setup: model routing and the OpenRouter balance."""

from collections.abc import Mapping
from datetime import UTC, datetime, time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_api.auth import CurrentUser, current_user
from agentic_api.authz import get_db, require_admin
from agentic_api.llm_routing import (
    lab_free_chain,
    lab_paid_chain,
    role_routing,
    routed_model,
)
from agentic_api.schemas import (
    AgentRole,
    LabBalanceOut,
    ModelCatalogOut,
    ModelRoutingOut,
    RoleModelsIn,
)
from agentic_api.settings import Settings
from agentic_db.lab_settings import (
    MODEL_ROUTING_KEY,
    CatalogModel,
    lab_account,
    model_catalog,
    model_routing,
    paid_models_enabled,
)
from agentic_db.models import AuditLog, Setting
from agentic_db.spend import month_start
from agentic_db.usage import free_requests_since, lab_month_spend

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
User = Annotated[CurrentUser, Depends(current_user)]
Db = Annotated[AsyncSession, Depends(get_db)]


async def _routing(db: AsyncSession, settings: Settings) -> ModelRoutingOut:
    catalog = await model_catalog(db)
    models = catalog.models if catalog else {}
    return ModelRoutingOut(
        paid_models_enabled=await paid_models_enabled(db),
        roles=role_routing(settings, await model_routing(db), models),
        lab_paid=[routed_model(model_id, models) for model_id in lab_paid_chain(settings)],
        lab_free=[routed_model(model_id, models) for model_id in lab_free_chain(settings)],
        catalog_checked_at=catalog.checked_at if catalog else None,
        demo=False,
    )


@router.get("/models", operation_id="getModelRouting")
async def get_model_routing(request: Request, user: User, db: Db) -> ModelRoutingOut:
    """Per agent role, the paid and free model chains the gateway tries, with what its catalog
    says about each model, and the state of the paid-models kill switch."""
    require_admin(user)
    return await _routing(db, request.app.state.settings)


@router.get("/models/catalog", operation_id="getModelCatalog")
async def get_model_catalog(user: User, db: Db) -> ModelCatalogOut:
    """The text models OpenRouter offers, to choose chains from."""
    require_admin(user)
    catalog = await model_catalog(db)
    if catalog is None:
        return ModelCatalogOut(models=[], checked_at=None)
    return ModelCatalogOut(
        models=[routed_model(model_id, catalog.models) for model_id in catalog.models],
        checked_at=catalog.checked_at,
    )


def _check_chain(
    chain: list[str] | None, *, free: bool, models: Mapping[str, CatalogModel] | None
) -> None:
    """Every model must be one OpenRouter offers, and of the chain's kind. Before the gateway has
    read the catalog, the name is all there is to go by."""
    for model_id in chain or []:
        if models is not None and model_id not in models:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "routing.unknown_model")
        is_free = models[model_id].free if models is not None else model_id.endswith(":free")
        if is_free != free:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "routing.wrong_tier")


@router.put("/models/{role}", operation_id="setRoleModels")
async def set_role_models(
    role: AgentRole, body: RoleModelsIn, request: Request, user: User, db: Db
) -> ModelRoutingOut:
    """Give an agent role its own model chains, which its next call uses; both null puts it back
    on the lab's. 422 ``routing.unknown_model`` for a model OpenRouter doesn't offer, and
    ``routing.wrong_tier`` for a free model in the paid chain or the other way round."""
    require_admin(user)
    catalog = await model_catalog(db)
    models = catalog.models if catalog else None
    _check_chain(body.paid, free=False, models=models)
    _check_chain(body.free, free=True, models=models)

    # The row exists before it is locked, so two admins saving at once both keep their changes.
    await db.execute(
        insert(Setting)
        .values(key=MODEL_ROUTING_KEY, value={"roles": {}}, updated_by=user.id)
        .on_conflict_do_nothing(index_elements=[Setting.key])
    )
    setting = (
        await db.execute(select(Setting).where(Setting.key == MODEL_ROUTING_KEY).with_for_update())
    ).scalar_one()
    roles = dict(setting.value.get("roles", {}))
    if body.paid is None and body.free is None:
        roles.pop(role, None)
    else:
        roles[role] = {"paid": body.paid, "free": body.free}
    setting.value = {"roles": roles}
    setting.updated_by = user.id
    db.add(
        AuditLog(
            actor_id=user.id,
            action="settings.model_routing",
            target_type="setting",
            target_id=MODEL_ROUTING_KEY,
            details={"role": role, "paid": body.paid, "free": body.free},
        )
    )
    await db.commit()
    return await _routing(db, request.app.state.settings)


@router.get("/balance", operation_id="getLabBalance")
async def get_lab_balance(request: Request, user: User, db: Db) -> LabBalanceOut:
    """The lab's OpenRouter credit as the gateway last read it, every user's paid spend this
    month, and the free-tier use today."""
    require_admin(user)
    settings = request.app.state.settings
    now = datetime.now(UTC)
    account = await lab_account(db)
    balance = account.balance_usd if account else None
    free_tier = account.free_tier if account else False
    floor = settings.balance_alert_floor_usd
    limit = account.free_daily_limit if account else None
    return LabBalanceOut(
        balance_usd=balance,
        free_tier=free_tier,
        month=month_start(now).strftime("%Y-%m"),
        spent_this_month_usd=await lab_month_spend(db, now),
        free_daily_limit=limit if limit is not None else settings.free_requests_per_day,
        free_calls_today=await free_requests_since(
            db, datetime.combine(now.date(), time(), tzinfo=UTC)
        ),
        auto_top_up=False,
        alert_floor_usd=floor,
        below_floor=balance is not None and not free_tier and balance < floor,
        checked_at=account.checked_at if account else None,
        demo=False,
    )

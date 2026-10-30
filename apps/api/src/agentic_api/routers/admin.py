from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_api.auth import CurrentUser, current_user
from agentic_api.authz import get_db, require_admin
from agentic_api.health import system_health
from agentic_api.schemas import (
    AuditEntryOut,
    AuditPage,
    BudgetIn,
    BudgetOut,
    MeOut,
    PaidModelsSetting,
    SystemHealthOut,
)
from agentic_api.users import users_by_id
from agentic_db.lab_settings import PAID_MODELS_KEY, paid_models_enabled
from agentic_db.models import AuditLog, Budget, Setting
from agentic_db.spend import month_spend, monthly_budget

router = APIRouter(prefix="/api/v1", tags=["admin"])
User = Annotated[CurrentUser, Depends(current_user)]
Db = Annotated[AsyncSession, Depends(get_db)]


@router.get("/me", operation_id="getMe")
async def get_me(user: User, db: Db) -> MeOut:
    return MeOut(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        budget_usd=await monthly_budget(db, user.id),
        spent_usd=await month_spend(db, user.id),
    )


@router.get("/admin/budgets", operation_id="listBudgets")
async def list_budgets(user: User, db: Db) -> list[BudgetOut]:
    require_admin(user)
    budgets = (await db.scalars(select(Budget).order_by(Budget.user_id))).all()
    return [
        BudgetOut(
            user_id=b.user_id, monthly_usd=b.monthly_usd, spent_usd=await month_spend(db, b.user_id)
        )
        for b in budgets
    ]


@router.put("/admin/budgets/{user_id}", operation_id="setBudget")
async def set_budget(user_id: str, body: BudgetIn, user: User, db: Db) -> BudgetOut:
    require_admin(user)
    budget = await db.get(Budget, user_id)
    if budget is None:
        db.add(Budget(user_id=user_id, monthly_usd=body.monthly_usd, updated_by=user.id))
    else:
        budget.monthly_usd = body.monthly_usd
        budget.updated_by = user.id
    db.add(
        AuditLog(
            actor_id=user.id,
            action="budget.set",
            target_type="user",
            target_id=user_id,
            details={"monthly_usd": str(body.monthly_usd)},
        )
    )
    await db.commit()
    return BudgetOut(
        user_id=user_id, monthly_usd=body.monthly_usd, spent_usd=await month_spend(db, user_id)
    )


@router.get("/admin/settings/paid-models", operation_id="getPaidModels")
async def get_paid_models(user: User, db: Db) -> PaidModelsSetting:
    require_admin(user)
    return PaidModelsSetting(enabled=await paid_models_enabled(db))


@router.put("/admin/settings/paid-models", operation_id="setPaidModels")
async def set_paid_models(body: PaidModelsSetting, user: User, db: Db) -> PaidModelsSetting:
    """Kill switch: when off, every call uses free models regardless of budgets."""
    require_admin(user)
    setting = await db.get(Setting, PAID_MODELS_KEY)
    if setting is None:
        db.add(Setting(key=PAID_MODELS_KEY, value={"enabled": body.enabled}, updated_by=user.id))
    else:
        setting.value = {"enabled": body.enabled}
        setting.updated_by = user.id
    db.add(
        AuditLog(
            actor_id=user.id,
            action="settings.paid_models",
            target_type="setting",
            target_id=PAID_MODELS_KEY,
            details={"enabled": body.enabled},
        )
    )
    await db.commit()
    return body


@router.get("/admin/audit", operation_id="listAuditLog")
async def list_audit_log(
    user: User,
    db: Db,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    action: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
) -> AuditPage:
    """Audit log entries, newest first; ``action`` keeps one action (e.g. ``run.cancel``)."""
    require_admin(user)
    filters = [AuditLog.action == action] if action else []
    total = await db.scalar(select(func.count()).select_from(AuditLog).where(*filters))
    entries = (
        await db.scalars(
            select(AuditLog)
            .where(*filters)
            .order_by(AuditLog.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    actors = await users_by_id(db, [entry.actor_id for entry in entries])
    return AuditPage(
        items=[
            AuditEntryOut(
                id=entry.id,
                actor_id=entry.actor_id,
                actor_name=actors[entry.actor_id].name if entry.actor_id in actors else None,
                actor_email=actors[entry.actor_id].email if entry.actor_id in actors else None,
                action=entry.action,
                target_type=entry.target_type,
                target_id=entry.target_id,
                details=entry.details,
                created_at=entry.created_at,
            )
            for entry in entries
        ],
        total=total or 0,
    )


@router.get("/admin/health", operation_id="getSystemHealth")
async def get_system_health(request: Request, user: User) -> SystemHealthOut:
    """Probes Postgres, Valkey, Temporal, the gateway and the workers concurrently."""
    require_admin(user)
    state = request.app.state
    return await system_health(
        sessions=state.sessions,
        valkey=state.valkey,
        orchestrator=state.orchestrator,
        http=state.http,
        gateway_url=state.settings.gateway_url,
    )

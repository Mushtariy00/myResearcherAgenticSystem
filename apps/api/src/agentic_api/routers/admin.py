from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_api.auth import CurrentUser, current_user
from agentic_api.authz import get_db
from agentic_api.schemas import BudgetIn, BudgetOut, MeOut, PaidModelsSetting
from agentic_db.models import AuditLog, Budget, Setting
from agentic_db.spend import month_spend, monthly_budget

router = APIRouter(prefix="/api/v1", tags=["admin"])
User = Annotated[CurrentUser, Depends(current_user)]
Db = Annotated[AsyncSession, Depends(get_db)]
PAID_MODELS_KEY = "paid_models_enabled"


def _require_admin(user: CurrentUser) -> None:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "permission.denied")


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
    _require_admin(user)
    budgets = (await db.scalars(select(Budget).order_by(Budget.user_id))).all()
    return [
        BudgetOut(
            user_id=b.user_id, monthly_usd=b.monthly_usd, spent_usd=await month_spend(db, b.user_id)
        )
        for b in budgets
    ]


@router.put("/admin/budgets/{user_id}", operation_id="setBudget")
async def set_budget(user_id: str, body: BudgetIn, user: User, db: Db) -> BudgetOut:
    _require_admin(user)
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
    _require_admin(user)
    setting = await db.get(Setting, PAID_MODELS_KEY)
    return PaidModelsSetting(enabled=bool(setting.value.get("enabled", True)) if setting else True)


@router.put("/admin/settings/paid-models", operation_id="setPaidModels")
async def set_paid_models(body: PaidModelsSetting, user: User, db: Db) -> PaidModelsSetting:
    """Kill switch: when off, every call uses free models regardless of budgets."""
    _require_admin(user)
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

"""LLM usage from the spend journal (real figures) and run cost estimates (a heuristic)."""

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_api.auth import CurrentUser, current_user
from agentic_api.authz import get_db, require_admin
from agentic_api.demo.catalog import DEFAULT_PAID_MODELS, model_chain
from agentic_api.estimates import estimate_run
from agentic_api.schemas import (
    BudgetStatusOut,
    RunEstimateIn,
    RunEstimateOut,
    UsageDayOut,
    UsageModelOut,
    UsageOut,
    UsageRunOut,
    UsageScope,
    UsageTotalsOut,
    UsageUserOut,
)
from agentic_api.users import users_by_id
from agentic_db.lab_settings import paid_models_enabled
from agentic_db.spend import month_spend, month_start, monthly_budget
from agentic_db.usage import (
    Usage,
    Window,
    usage_by_day,
    usage_by_model,
    usage_by_run,
    usage_by_user,
    usage_total,
)

router = APIRouter(prefix="/api/v1", tags=["usage"])
User = Annotated[CurrentUser, Depends(current_user)]
Db = Annotated[AsyncSession, Depends(get_db)]
TOP_RUNS = 10
_ZERO = Usage(paid_usd=Decimal(0), paid_calls=0, free_calls=0, prompt_tokens=0, completion_tokens=0)


def _totals(usage: Usage) -> dict[str, Any]:
    """The UsageTotalsOut fields of ``usage``, for the models that extend it."""
    return {
        "paid_usd": usage.paid_usd,
        "paid_calls": usage.paid_calls,
        "free_calls": usage.free_calls,
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
    }


async def _remaining_budget(db: AsyncSession, user_id: str) -> tuple[Decimal, Decimal, Decimal]:
    """(monthly budget, spent this month, left), as the gateway counts them for routing."""
    budget = await monthly_budget(db, user_id)
    spent = await month_spend(db, user_id)
    return budget, spent, max(Decimal(0), budget - spent)


@router.get("/usage", operation_id="getUsage")
async def get_usage(
    user: User,
    db: Db,
    scope: UsageScope = "me",
    days: Annotated[int, Query(ge=7, le=90)] = 30,
) -> UsageOut:
    """Paid spend and call counts over the last ``days`` UTC days, today included: the caller's
    own calls ("me"), or every user's ("lab", lab admins only). Real figures, zeros included."""
    if scope == "lab":
        require_admin(user)
    today = datetime.now(UTC).date()
    since = datetime.combine(today - timedelta(days=days - 1), time(), tzinfo=UTC)
    until = datetime.combine(today + timedelta(days=1), time(), tzinfo=UTC)
    window = Window(since=since, until=until, user_id=user.id if scope == "me" else None)

    per_day = await usage_by_day(db, window)
    by_user: list[UsageUserOut] = []
    if scope == "lab":
        spenders = await usage_by_user(db, window)
        accounts = await users_by_id(db, [user_id for user_id, _ in spenders])
        by_user = [
            UsageUserOut(
                user_id=user_id,
                name=accounts[user_id].name if user_id in accounts else None,
                email=accounts[user_id].email if user_id in accounts else None,
                **_totals(usage),
            )
            for user_id, usage in spenders
        ]
    budget, spent, remaining = await _remaining_budget(db, user.id)
    return UsageOut(
        scope=scope,
        days=days,
        since=since,
        until=until,
        totals=UsageTotalsOut(**_totals(await usage_total(db, window))),
        by_day=[
            UsageDayOut(day=day, **_totals(per_day.get(day, _ZERO)))
            for day in (since.date() + timedelta(days=offset) for offset in range(days))
        ],
        by_model=[
            UsageModelOut(model=row.model, tier=row.tier, **_totals(row.usage))
            for row in await usage_by_model(db, window)
        ],
        top_runs=[
            UsageRunOut(
                run_id=row.run_id,
                topic=row.topic,
                project_id=row.project_id,
                project_name=row.project_name,
                **_totals(row.usage),
            )
            for row in await usage_by_run(db, window, limit=TOP_RUNS)
        ],
        by_user=by_user,
        budget=BudgetStatusOut(
            month=month_start().strftime("%Y-%m"),
            monthly_usd=budget,
            spent_usd=spent,
            remaining_usd=remaining,
        ),
        demo=False,
    )


@router.post("/runs/estimate", operation_id="estimateRunCost")
async def estimate_run_cost(
    body: RunEstimateIn, request: Request, user: User, db: Db
) -> RunEstimateOut:
    """What a run with these options would likely cost the caller, and why: calls per stage
    times typical tokens times the paid chain's prices. Free when it can't use paid models."""
    _, _, remaining = await _remaining_budget(db, user.id)
    return estimate_run(
        body.config,
        body.llm_policy,
        paid_chain=model_chain(request.app.state.settings.paid_models, DEFAULT_PAID_MODELS),
        paid_models_enabled=await paid_models_enabled(db),
        budget_remaining_usd=remaining,
        budget_cap_usd=body.budget_cap_usd,
    )

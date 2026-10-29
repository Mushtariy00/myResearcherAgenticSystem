"""Paid-model spend per user and UTC month, shared by the API (display) and gateway (routing)."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_core.enums import LlmCallState, LlmTier
from agentic_db.models import Budget, LlmCall

# Calls that hold or have spent money. Settled calls count their real cost; the rest count
# their reservation until the sweeper settles them.
_COMMITTED_STATES = (LlmCallState.RESERVED, LlmCallState.SENT, LlmCallState.UNKNOWN)


def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def month_spend(session: AsyncSession, user_id: str, now: datetime | None = None) -> Decimal:
    """Settled cost plus open reservations for the user's paid calls this UTC month."""
    since = month_start(now)
    settled = select(func.coalesce(func.sum(LlmCall.cost_usd), 0)).where(
        LlmCall.user_id == user_id,
        LlmCall.tier == LlmTier.PAID,
        LlmCall.state == LlmCallState.SETTLED,
        LlmCall.created_at >= since,
    )
    reserved = select(func.coalesce(func.sum(LlmCall.reserved_usd), 0)).where(
        LlmCall.user_id == user_id,
        LlmCall.tier == LlmTier.PAID,
        LlmCall.state.in_(_COMMITTED_STATES),
        LlmCall.created_at >= since,
    )
    settled_usd = (await session.execute(settled)).scalar_one()
    reserved_usd = (await session.execute(reserved)).scalar_one()
    return Decimal(settled_usd or 0) + Decimal(reserved_usd or 0)


async def run_spend(session: AsyncSession, run_id: object) -> Decimal:
    """Settled cost plus open reservations for one run's paid calls (for the per-run cap)."""
    settled = select(func.coalesce(func.sum(LlmCall.cost_usd), 0)).where(
        LlmCall.run_id == run_id,
        LlmCall.tier == LlmTier.PAID,
        LlmCall.state == LlmCallState.SETTLED,
    )
    reserved = select(func.coalesce(func.sum(LlmCall.reserved_usd), 0)).where(
        LlmCall.run_id == run_id,
        LlmCall.tier == LlmTier.PAID,
        LlmCall.state.in_(_COMMITTED_STATES),
    )
    settled_usd = (await session.execute(settled)).scalar_one()
    reserved_usd = (await session.execute(reserved)).scalar_one()
    return Decimal(settled_usd or 0) + Decimal(reserved_usd or 0)


async def monthly_budget(session: AsyncSession, user_id: str) -> Decimal:
    budget = await session.get(Budget, user_id)
    return budget.monthly_usd if budget else Decimal(0)

"""Paid-model spend per user and UTC month, shared by the API (display) and gateway (routing)."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from agentic_core.enums import LlmCallState, LlmTier
from agentic_db.models import Budget, LlmCall

# Calls that hold money. Settled calls count their real cost; these count their reservation until
# the sweeper settles them. Released calls cost nothing.
_OPEN_STATES = (LlmCallState.RESERVED, LlmCallState.SENT, LlmCallState.UNKNOWN)


def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _spent_usd() -> ColumnElement[Any]:
    # Both parts in one sum, so one statement and one snapshot: a call that settles while it
    # runs is counted once, not missed between two reads.
    amount = case(
        (LlmCall.state == LlmCallState.SETTLED, func.coalesce(LlmCall.cost_usd, 0)),
        (LlmCall.state.in_(_OPEN_STATES), LlmCall.reserved_usd),
        else_=0,
    )
    return func.coalesce(func.sum(amount), 0)


async def month_spend(session: AsyncSession, user_id: str, now: datetime | None = None) -> Decimal:
    """Settled cost plus open reservations for the user's paid calls this UTC month."""
    query = select(_spent_usd()).where(
        LlmCall.user_id == user_id,
        LlmCall.tier == LlmTier.PAID,
        LlmCall.created_at >= month_start(now),
    )
    return Decimal(await session.scalar(query) or 0)


async def run_spend(session: AsyncSession, run_id: object) -> Decimal:
    """Settled cost plus open reservations for one run's paid calls (for the per-run cap)."""
    query = select(_spent_usd()).where(LlmCall.run_id == run_id, LlmCall.tier == LlmTier.PAID)
    return Decimal(await session.scalar(query) or 0)


async def monthly_budget(session: AsyncSession, user_id: str) -> Decimal:
    budget = await session.get(Budget, user_id)
    return budget.monthly_usd if budget else Decimal(0)

"""Aggregates of the spend journal (``llm_calls``) for the usage dashboards and the lab balance.

Amounts count as in agentic_db.spend: a paid call's settled cost, or its reservation while the
call is still open (reserved, sent, unknown). Released calls never cost anything, so they are
neither money nor calls here.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, Select, and_, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from agentic_core.enums import LlmCallState, LlmTier
from agentic_db.models import LlmCall, Project, Run
from agentic_db.spend import month_start

OPEN_STATES = (LlmCallState.RESERVED, LlmCallState.SENT, LlmCallState.UNKNOWN)
COUNTED_STATES = (LlmCallState.SETTLED, *OPEN_STATES)


@dataclass(frozen=True)
class Usage:
    paid_usd: Decimal
    paid_calls: int
    free_calls: int
    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True)
class ModelUsage:
    model: str
    tier: LlmTier
    usage: Usage


@dataclass(frozen=True)
class RunUsage:
    run_id: uuid.UUID
    topic: str
    project_id: uuid.UUID
    project_name: str
    usage: Usage


@dataclass(frozen=True)
class Window:
    """Calls created in ``[since, until)``, charged to ``user_id`` (None: every user)."""

    since: datetime
    until: datetime
    user_id: str | None = None


def _paid_usd() -> ColumnElement[Any]:
    paid = LlmCall.tier == LlmTier.PAID
    amount = case(
        (and_(paid, LlmCall.state == LlmCallState.SETTLED), func.coalesce(LlmCall.cost_usd, 0)),
        (and_(paid, LlmCall.state.in_(OPEN_STATES)), LlmCall.reserved_usd),
        else_=0,
    )
    return func.coalesce(func.sum(amount), 0)


def _usage_columns() -> list[ColumnElement[Any]]:
    return [
        _paid_usd().label("paid_usd"),
        func.count().filter(LlmCall.tier == LlmTier.PAID).label("paid_calls"),
        func.count().filter(LlmCall.tier == LlmTier.FREE).label("free_calls"),
        func.coalesce(func.sum(LlmCall.prompt_tokens), 0).label("prompt_tokens"),
        func.coalesce(func.sum(LlmCall.completion_tokens), 0).label("completion_tokens"),
    ]


def _usage(row: Any) -> Usage:
    return Usage(
        paid_usd=Decimal(row.paid_usd),
        paid_calls=row.paid_calls,
        free_calls=row.free_calls,
        prompt_tokens=int(row.prompt_tokens),
        completion_tokens=int(row.completion_tokens),
    )


def _in_window(query: Select[Any], window: Window) -> Select[Any]:
    query = query.where(
        LlmCall.state.in_(COUNTED_STATES),
        LlmCall.created_at >= window.since,
        LlmCall.created_at < window.until,
    )
    return query.where(LlmCall.user_id == window.user_id) if window.user_id is not None else query


async def usage_total(session: AsyncSession, window: Window) -> Usage:
    row = (await session.execute(_in_window(select(*_usage_columns()), window))).one()
    return _usage(row)


async def usage_by_day(session: AsyncSession, window: Window) -> dict[date, Usage]:
    """Usage per UTC calendar day; days without calls are missing (the caller fills zeros)."""
    day = cast(func.timezone("UTC", LlmCall.created_at), Date).label("day")
    rows = await session.execute(
        _in_window(select(day, *_usage_columns()), window).group_by(day).order_by(day)
    )
    return {row.day: _usage(row) for row in rows}


async def usage_by_model(session: AsyncSession, window: Window) -> list[ModelUsage]:
    """Usage per model and tier, the most expensive first."""
    columns = _usage_columns()
    rows = await session.execute(
        _in_window(select(LlmCall.model, LlmCall.tier, *columns), window)
        .group_by(LlmCall.model, LlmCall.tier)
        .order_by(columns[0].desc(), func.count().desc(), LlmCall.model)
    )
    return [ModelUsage(model=row.model, tier=LlmTier(row.tier), usage=_usage(row)) for row in rows]


async def usage_by_run(session: AsyncSession, window: Window, limit: int = 10) -> list[RunUsage]:
    """The runs that cost the most (then made the most calls); calls without a run are left
    out, as are runs that have been deleted."""
    columns = _usage_columns()
    rows = await session.execute(
        _in_window(
            select(Run.id, Run.topic, Run.project_id, Project.name, *columns)
            .join(Run, Run.id == LlmCall.run_id)
            .join(Project, Project.id == Run.project_id),
            window,
        )
        .group_by(Run.id, Project.id)
        .order_by(columns[0].desc(), func.count().desc(), Run.id)
        .limit(limit)
    )
    return [
        RunUsage(
            run_id=row.id,
            topic=row.topic,
            project_id=row.project_id,
            project_name=row.name,
            usage=_usage(row),
        )
        for row in rows
    ]


async def usage_by_user(session: AsyncSession, window: Window) -> list[tuple[str, Usage]]:
    """Usage per user the calls were charged to, the biggest spender first."""
    columns = _usage_columns()
    rows = await session.execute(
        _in_window(select(LlmCall.user_id, *columns), window)
        .group_by(LlmCall.user_id)
        .order_by(columns[0].desc(), func.count().desc(), LlmCall.user_id)
    )
    return [(row.user_id, _usage(row)) for row in rows]


async def lab_month_spend(session: AsyncSession, now: datetime | None = None) -> Decimal:
    """Paid spend of every user this UTC month (agentic_db.spend.month_spend, lab-wide)."""
    query = select(_paid_usd()).where(
        LlmCall.state.in_(COUNTED_STATES), LlmCall.created_at >= month_start(now)
    )
    return Decimal(await session.scalar(query) or 0)


async def free_requests_since(session: AsyncSession, since: datetime) -> int:
    """Free-tier requests made since ``since``. Each one took a slot of the free quota before it
    was recorded, so released (failed) requests count too."""
    query = (
        select(func.count())
        .select_from(LlmCall)
        .where(LlmCall.tier == LlmTier.FREE, LlmCall.created_at >= since)
    )
    return await session.scalar(query) or 0

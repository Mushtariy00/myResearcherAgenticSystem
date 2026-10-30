"""agentic_db.spend: what the budget checks and the run detail count."""

import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

import psycopg
from sqlalchemy import event, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from agentic_core.enums import LlmCallState, LlmTier, RunStatus
from agentic_db.models import LlmCall, Project, Run
from agentic_db.spend import month_spend, run_spend

Factory = async_sessionmaker[AsyncSession]
Read = Callable[[AsyncSession], Awaitable[Decimal]]


async def add_run(db: Factory) -> uuid.UUID:
    async with db() as session:
        project = Project(name="Lab", created_by="bob")
        session.add(project)
        await session.flush()
        run = Run(project_id=project.id, owner_id="bob", topic="Depth", status=RunStatus.RUNNING)
        session.add(run)
        await session.commit()
    return run.id


async def add_call(
    db: Factory, run_id: uuid.UUID, state: LlmCallState, reserved: str, cost: str | None = None
) -> None:
    async with db() as session:
        session.add(
            LlmCall(
                idempotency_key=f"{uuid.uuid4()}:call-1#1",
                run_id=run_id,
                user_id="bob",
                role="researcher",
                tier=LlmTier.PAID,
                model="paid/good",
                state=state,
                reserved_usd=Decimal(reserved),
                cost_usd=Decimal(cost) if cost is not None else None,
            )
        )
        await session.commit()


async def test_settled_calls_count_their_cost_open_ones_their_reservation(db: Factory) -> None:
    run_id = await add_run(db)
    await add_call(db, run_id, LlmCallState.SETTLED, "0.004", cost="0.001")
    await add_call(db, run_id, LlmCallState.RESERVED, "0.010")
    await add_call(db, run_id, LlmCallState.SENT, "0.020")
    await add_call(db, run_id, LlmCallState.UNKNOWN, "0.040")
    await add_call(db, run_id, LlmCallState.RELEASED, "0.080")
    async with db() as session:
        assert await run_spend(session, run_id) == Decimal("0.071")
        assert await month_spend(session, "bob") == Decimal("0.071")


async def read_mid_settle(db: Factory, engine: AsyncEngine, dsn: str, read: Read) -> Decimal:
    """Read spend while the sent call settles right after the first statement on the journal."""
    settled: list[str] = []

    def settle(_conn: Any, _cursor: Any, statement: str, *_: Any) -> None:
        if settled or "FROM llm_calls" not in statement:
            return
        settled.append(statement)
        with psycopg.connect(dsn, autocommit=True) as other:
            other.execute(
                "UPDATE llm_calls SET state = 'settled', cost_usd = 0.007 WHERE state = 'sent'"
            )

    event.listen(engine.sync_engine, "after_cursor_execute", settle)
    try:
        async with db() as session:
            spent = await read(session)
    finally:
        event.remove(engine.sync_engine, "after_cursor_execute", settle)
    assert settled
    async with db() as session, session.begin():  # sent again, for the next read
        await session.execute(
            update(LlmCall)
            .where(LlmCall.cost_usd == Decimal("0.007"))
            .values(state=LlmCallState.SENT, cost_usd=None)
        )
    return spent


async def test_a_call_settling_during_the_read_is_counted_once(
    db: Factory, db_engine: AsyncEngine, database_url: str
) -> None:
    run_id = await add_run(db)
    await add_call(db, run_id, LlmCallState.SETTLED, "0.004", cost="0.002")
    await add_call(db, run_id, LlmCallState.SENT, "0.010")
    dsn = make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)
    month = await read_mid_settle(db, db_engine, dsn, lambda session: month_spend(session, "bob"))
    run = await read_mid_settle(db, db_engine, dsn, lambda session: run_spend(session, run_id))
    # One snapshot sees the call sent, at its reservation. Settled costs and reservations read in
    # two statements would see it in neither: 0.002.
    assert month == run == Decimal("0.012")

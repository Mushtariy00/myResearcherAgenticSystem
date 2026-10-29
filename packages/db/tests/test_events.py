import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_db import append_event
from agentic_db.models import Project, Run

Factory = async_sessionmaker[AsyncSession]


async def _new_run(db: Factory) -> uuid.UUID:
    async with db() as session:
        project = Project(name="Depth estimation", created_by="user-1")
        session.add(project)
        await session.flush()
        run = Run(project_id=project.id, owner_id="user-1", topic="Monocular depth 2023-2025")
        session.add(run)
        await session.commit()
        return run.id


async def test_events_get_gap_free_sequence_numbers(db: Factory) -> None:
    run_id = await _new_run(db)
    async with db() as session:
        seqs = [await append_event(session, run_id, "stage.started", {"i": i}) for i in range(3)]
        await session.commit()
    assert seqs == [1, 2, 3]


async def test_concurrent_writers_never_reuse_or_skip_a_sequence(db: Factory) -> None:
    run_id = await _new_run(db)

    async def append_many(count: int) -> list[int]:
        async with db() as session:
            seqs = [await append_event(session, run_id, "log", {}) for _ in range(count)]
            await session.commit()
            return seqs

    first, second = await asyncio.gather(append_many(5), append_many(5))
    assert sorted(first + second) == list(range(1, 11))


async def test_rolled_back_events_free_their_sequence(db: Factory) -> None:
    run_id = await _new_run(db)
    async with db() as session:
        await append_event(session, run_id, "discarded", {})
        await session.rollback()
    async with db() as session:
        seq = await append_event(session, run_id, "kept", {})
        await session.commit()
    assert seq == 1  # no gap, so SSE replay with Last-Event-ID never waits for a missing id


async def test_status_columns_reject_unknown_values(db: Factory) -> None:
    run_id = await _new_run(db)
    async with db() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                text("UPDATE runs SET status = 'bogus' WHERE id = :id"), {"id": run_id}
            )

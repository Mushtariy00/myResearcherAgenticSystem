"""Run events: the source of truth for live progress, SSE replay and the run timeline."""

import uuid
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_db.models import Run, RunEvent


async def append_event(
    session: AsyncSession, run_id: uuid.UUID, event_type: str, payload: dict[str, Any]
) -> int:
    """Append an event with the run's next sequence number, inside the caller's transaction.

    The UPDATE locks the run row until commit, so sequence numbers are gap-free and become
    visible in order. That is what makes SSE replay with Last-Event-ID lossless.
    """
    result = await session.execute(
        update(Run)
        .where(Run.id == run_id)
        .values(last_event_seq=Run.last_event_seq + 1)
        .returning(Run.last_event_seq)
    )
    seq = result.scalar_one()
    session.add(RunEvent(run_id=run_id, seq=seq, type=event_type, payload=payload))
    return seq

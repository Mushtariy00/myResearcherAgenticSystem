"""Live run events over SSE. Postgres is the source of truth; Valkey pub/sub only wakes us up."""

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_api.auth import CurrentUser, current_user
from agentic_api.authz import get_db, load_run
from agentic_core.enums import RunStatus
from agentic_db.models import Run, RunEvent

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["runs"])
HEARTBEAT_SECONDS = 15.0
BATCH = 500


def wake_channel(run_id: uuid.UUID | str) -> str:
    """Valkey channel workers publish to after committing a run event."""
    return f"run-events:{run_id}"


def _format(event: RunEvent) -> str:
    data = json.dumps(
        {
            "seq": event.seq,
            "type": event.type,
            "payload": event.payload,
            "created_at": event.created_at.isoformat(),
        }
    )
    return f"id: {event.seq}\ndata: {data}\n\n"


async def _events(
    sessions: async_sessionmaker[AsyncSession], run_id: uuid.UUID, after: int
) -> tuple[list[RunEvent], bool]:
    async with sessions() as session:
        rows = (
            await session.scalars(
                select(RunEvent)
                .where(RunEvent.run_id == run_id, RunEvent.seq > after)
                .order_by(RunEvent.seq)
                .limit(BATCH)
            )
        ).all()
        status = await session.scalar(select(Run.status).where(Run.id == run_id))
    return list(rows), status is not None and RunStatus(status).is_terminal


async def _stream(request: Request, run_id: uuid.UUID, after: int) -> AsyncIterator[str]:
    sessions = request.app.state.sessions
    pubsub = request.app.state.valkey.pubsub()
    try:
        await pubsub.subscribe(wake_channel(run_id))
    except Exception:  # Valkey down: fall back to polling
        log.warning("valkey unavailable; SSE for run %s falls back to polling", run_id)
        pubsub = None

    cursor = after
    yield "retry: 3000\n\n"
    try:
        while not await request.is_disconnected():
            events, finished = await _events(sessions, run_id, cursor)
            for event in events:
                cursor = event.seq
                yield _format(event)
            if finished and len(events) < BATCH:
                yield "event: end\ndata: {}\n\n"
                return
            if len(events) == BATCH:
                continue  # more to replay
            woke = await _wait(pubsub)
            if not woke:
                yield ": ping\n\n"
    finally:
        if pubsub is not None:
            await pubsub.aclose()


async def _wait(pubsub: Any | None) -> bool:
    """Wait for a wake-up message; False after the heartbeat interval passes quietly."""
    if pubsub is None:
        await asyncio.sleep(2.0)
        return True
    try:
        message = await pubsub.get_message(
            ignore_subscribe_messages=True, timeout=HEARTBEAT_SECONDS
        )
    except Exception:
        await asyncio.sleep(2.0)
        return True
    return message is not None


@router.get(
    "/runs/{run_id}/events", operation_id="streamRunEvents", response_class=StreamingResponse
)
async def stream_run_events(
    run_id: uuid.UUID,
    request: Request,
    user: Annotated[CurrentUser, Depends(current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    last_event_id: Annotated[str | None, Header()] = None,
    after: Annotated[int, Query(ge=0)] = 0,
) -> StreamingResponse:
    await load_run(db, run_id, user)  # any project member may watch
    start = int(last_event_id) if last_event_id and last_event_id.isdigit() else after
    return StreamingResponse(
        _stream(request, run_id, start),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

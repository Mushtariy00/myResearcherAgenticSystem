"""Live run events over SSE. Postgres is the source of truth; Valkey pub/sub only wakes us up."""

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

import anyio
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_api.auth import CurrentUser, current_user
from agentic_api.authz import get_db, load_run
from agentic_core.contracts import events_channel
from agentic_core.enums import RunStatus
from agentic_db.models import Run, RunEvent

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["runs"])
HEARTBEAT_SECONDS = 15.0
BATCH = 500
CLOSE_SECONDS = 5.0  # for returning the pub/sub connection to the pool
MAX_SEQ = 2**31 - 1  # run_events.seq is an int4


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
        # The status first: a run's final status commits together with its final event, so once
        # the status reads terminal, the events read next include that event.
        status = await session.scalar(select(Run.status).where(Run.id == run_id))
        rows = (
            await session.scalars(
                select(RunEvent)
                .where(RunEvent.run_id == run_id, RunEvent.seq > after)
                .order_by(RunEvent.seq)
                .limit(BATCH)
            )
        ).all()
    return list(rows), status is not None and RunStatus(status).is_terminal


async def _still_allowed(state: Any, run_id: uuid.UUID, cookie_header: str) -> bool:
    """Whether the stream's session still exists and its user may still open the run."""
    try:
        user = await state.session_verifier.verify(cookie_header)
        if user is None:
            return False
        async with state.sessions() as session:
            await load_run(session, run_id, user)
    except HTTPException:  # signed out, no longer a member, or auth unavailable
        return False
    return True


async def _stream(request: Request, run_id: uuid.UUID, after: int) -> AsyncIterator[str]:
    state = request.app.state
    cookie_header = request.headers.get("cookie", "")
    # Authorization is checked again this often, so a revoked session or a removed member
    # stops receiving events about as soon as their regular requests start failing.
    recheck_seconds = state.settings.auth_cache_seconds
    checked_at = time.monotonic()
    pubsub = state.valkey.pubsub()
    listening = False
    try:
        try:
            await pubsub.subscribe(events_channel(run_id))
            listening = True
        except Exception:  # Valkey down: fall back to polling
            log.warning("valkey unavailable; SSE for run %s falls back to polling", run_id)
        yield "retry: 3000\n\n"
        cursor = after
        while not await request.is_disconnected():
            if time.monotonic() - checked_at >= recheck_seconds:
                if not await _still_allowed(state, run_id, cookie_header):
                    return  # the browser reconnects, and that request is authorized afresh
                checked_at = time.monotonic()
            events, finished = await _events(state.sessions, run_id, cursor)
            for event in events:
                cursor = event.seq
                yield _format(event)
            if finished and len(events) < BATCH:
                yield "event: end\ndata: {}\n\n"
                return
            if len(events) == BATCH:
                continue  # more to replay
            woke = await _wait(pubsub if listening else None)
            if not woke:
                yield ": ping\n\n"
    finally:
        await _close(pubsub)


async def _close(pubsub: Any) -> None:
    """Return the pub/sub connection to the pool, also when the client went away. Starlette
    then cancels the stream, and anyio cancels again at every await of a cancelled scope, so
    an unshielded close would stop halfway and leak the connection."""
    with anyio.move_on_after(CLOSE_SECONDS, shield=True):
        try:
            await pubsub.aclose()
        except Exception:
            log.warning("could not close the pub/sub connection", exc_info=True)


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


def _resume_after(last_event_id: str | None, after: int) -> int:
    """The seq to replay after: the browser's Last-Event-ID on a reconnect, else ``after``.

    Only plain ASCII digits that fit the seq column are an event id we sent; anything else is
    ignored (``isdigit`` alone also passes "²", and digit strings too long for ``int``).
    """
    if (
        last_event_id
        and last_event_id.isascii()
        and last_event_id.isdecimal()
        and len(last_event_id) <= len(str(MAX_SEQ))
        and int(last_event_id) <= MAX_SEQ
    ):
        return int(last_event_id)
    return min(after, MAX_SEQ)


@router.get(
    "/runs/{run_id}/events", operation_id="streamRunEvents", response_class=StreamingResponse
)
async def stream_run_events(
    run_id: uuid.UUID,
    request: Request,
    user: Annotated[CurrentUser, Depends(current_user)],
    # Function scope: the session closes when this handler returns, not when the stream ends
    # (which can be days later); the stream reads with short sessions of its own.
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
    last_event_id: Annotated[str | None, Header()] = None,
    after: Annotated[int, Query(ge=0)] = 0,
) -> StreamingResponse:
    await load_run(db, run_id, user)  # any project member may watch
    return StreamingResponse(
        _stream(request, run_id, _resume_after(last_event_id, after)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

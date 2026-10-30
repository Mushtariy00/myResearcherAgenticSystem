"""The live event stream: what it holds while open, who may keep it, and how it ends."""

import asyncio
import uuid
from typing import Any

import httpx
import psycopg
import pytest
from fastapi import FastAPI
from sqlalchemy import delete, event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import QueuePool
from starlette.types import Message, Scope

from agentic_api.settings import Settings
from agentic_core.enums import RunStatus
from agentic_db.models import ProjectMember
from api_testkit import (
    FakePubSub,
    FakeValkey,
    FakeVerifier,
    as_user,
    set_run_status,
    start_run,
    team_project,
)

Factory = async_sessionmaker[AsyncSession]
# What finish_run commits in one transaction: the final status and its event.
FINISH_RUN = """
WITH bumped AS (
    UPDATE runs SET status = 'completed', last_event_seq = last_event_seq + 1
    WHERE id = %(run_id)s RETURNING last_event_seq
)
INSERT INTO run_events (run_id, seq, type, payload)
SELECT %(run_id)s, last_event_seq, 'run.status', '{"status": "completed", "error": null}'::jsonb
FROM bumped
"""


def _url(run_id: str) -> str:
    return f"/api/v1/runs/{run_id}/events"


async def test_a_stream_holds_no_database_connection_while_it_waits(
    client: httpx.AsyncClient, db: Factory, db_engine: AsyncEngine, valkey: FakeValkey
) -> None:
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    pool = db_engine.pool
    assert isinstance(pool, QueuePool)
    checked_out: list[int] = []

    async def look_then_finish() -> None:
        checked_out.append(pool.checkedout())
        await set_run_status(db, run_id, RunStatus.COMPLETED)  # ends the stream

    valkey.on_wait = look_then_finish
    response = await client.get(_url(run_id), headers=as_user("vera"))
    assert response.text.rstrip().endswith("event: end\ndata: {}")
    assert checked_out == [0]  # not even the one the request was authorized with


async def test_streams_are_authorized_again_while_they_last(
    client: httpx.AsyncClient,
    db: Factory,
    valkey: FakeValkey,
    verifier: FakeVerifier,
    settings: Settings,
) -> None:
    settings.auth_cache_seconds = 0  # check again before every read
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    waits = 0

    async def after_two_waits_finish() -> None:
        nonlocal waits
        waits += 1
        if waits == 2:
            await set_run_status(db, run_id, RunStatus.COMPLETED)

    valkey.on_wait = after_two_waits_finish
    response = await client.get(_url(run_id), headers=as_user("vera"))
    assert response.text.rstrip().endswith("event: end\ndata: {}")  # still allowed: to the end
    assert verifier.calls > 2

    # Signed out (an admin banned her, say) or removed from the project: the stream stops.
    async def sign_out() -> None:
        verifier.signed_out.add("vera")

    async def remove_from_project() -> None:
        async with db() as session:
            await session.execute(delete(ProjectMember).where(ProjectMember.user_id == "vera"))
            await session.commit()

    for revoke in (sign_out, remove_from_project):
        verifier.signed_out.clear()
        await set_run_status(db, run_id, RunStatus.RUNNING)
        waits = 0

        async def revoke_then_finish(revoke: Any = revoke) -> None:
            nonlocal waits
            waits += 1
            await revoke()
            if waits == 3:  # a stream that never checks again would only end here
                await set_run_status(db, run_id, RunStatus.COMPLETED)

        valkey.on_wait = revoke_then_finish
        response = await client.get(_url(run_id), headers=as_user("vera"))
        assert response.status_code == 200
        assert "event: end" not in response.text, revoke.__name__
        assert waits == 1, revoke.__name__


async def test_the_final_event_comes_before_the_end(
    client: httpx.AsyncClient, db_engine: AsyncEngine, database_url: str
) -> None:
    """The run finishes between the stream's two reads of a poll. Whichever it reads first,
    the run's final event must reach the client before ``end`` does."""
    project_id = await team_project(client)
    run_id = uuid.UUID(await start_run(client, project_id))
    dsn = make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)
    finished = False

    def finish_after_the_first_read(_conn: Any, _cursor: Any, statement: str, *_: Any) -> None:
        nonlocal finished
        if finished or not (
            statement.startswith("SELECT runs.status") or "FROM run_events" in statement
        ):
            return
        finished = True
        with psycopg.connect(dsn, autocommit=True) as other:
            other.execute(FINISH_RUN, {"run_id": run_id})

    event.listen(db_engine.sync_engine, "after_cursor_execute", finish_after_the_first_read)
    try:
        response = await client.get(_url(str(run_id)), headers=as_user("vera"))
    finally:
        event.remove(db_engine.sync_engine, "after_cursor_execute", finish_after_the_first_read)
    body = response.text
    assert finished
    assert '"status": "completed"' in body
    assert body.index('"status": "completed"') < body.index("event: end")


class _SlowToClose(FakePubSub):
    """Waits for a message until cancelled; closing takes a moment, like a real connection."""

    def __init__(self) -> None:
        super().__init__()
        self.waiting = asyncio.Event()

    async def get_message(self, ignore_subscribe_messages: bool, timeout: float) -> None:  # noqa: ASYNC109 (mirrors redis)
        self.waiting.set()
        await asyncio.sleep(3600)

    async def aclose(self) -> None:
        await asyncio.sleep(0.05)
        self.closed = True


async def test_a_client_that_goes_away_still_frees_the_pubsub_connection(
    app: FastAPI, client: httpx.AsyncClient, valkey: FakeValkey, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Driven the way uvicorn drives it (ASGI spec 2.3): on a disconnect Starlette cancels the
    stream, and anyio cancels it again at every await until it leaves the cancelled scope."""
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    pubsub = _SlowToClose()
    monkeypatch.setattr(valkey, "pubsub", lambda: pubsub)
    path = _url(run_id)
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [(b"host", b"test"), (b"cookie", b"test-user=vera:user")],
        "client": ("127.0.0.1", 50000),
        "server": ("test", 80),
    }
    gone = asyncio.Event()
    requested = False

    async def receive() -> Message:
        nonlocal requested
        if not requested:
            requested = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await gone.wait()
        return {"type": "http.disconnect"}

    sent: list[Message] = []

    async def send(message: Message) -> None:
        sent.append(message)

    stream = asyncio.create_task(app(scope, receive, send))
    async with asyncio.timeout(5):
        await pubsub.waiting.wait()
        gone.set()
        await stream
    assert sent[0]["status"] == 200
    assert pubsub.closed


@pytest.mark.parametrize(
    "last_event_id",
    [b"\xb2", b"9" * 5000, b"99999999999", b"3000000000", b"-1", b"1e3", b" 2"],
)
async def test_last_event_ids_we_never_sent_are_ignored(
    client: httpx.AsyncClient, db: Factory, last_event_id: bytes
) -> None:
    """ "²" passes isdigit(), and 5,000 digits are too many for int()."""
    project_id = await team_project(client)
    run_id = await start_run(client, project_id)
    await set_run_status(db, run_id, RunStatus.COMPLETED)  # the stream ends after its replay
    response = await client.get(
        _url(run_id),
        headers=[(b"cookie", b"test-user=vera:user"), (b"last-event-id", last_event_id)],
    )
    assert response.status_code == 200
    assert "id: 1\n" in response.text  # replayed from the start

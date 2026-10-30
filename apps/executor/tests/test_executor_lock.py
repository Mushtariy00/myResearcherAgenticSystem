"""One executor per GPU host: a second one waits for the advisory lock, and one that loses its
lock stops."""

import asyncio

from sqlalchemy.ext.asyncio import AsyncEngine

from agentic_executor.__main__ import hold_executor_lock, watch_executor_lock


async def test_a_second_executor_waits_until_the_first_lets_go(db_engine: AsyncEngine) -> None:
    stopping = asyncio.Event()
    async with db_engine.connect() as first_conn, db_engine.connect() as second_conn:
        first = await first_conn.execution_options(isolation_level="AUTOCOMMIT")
        second = await second_conn.execution_options(isolation_level="AUTOCOMMIT")
        assert await hold_executor_lock(first, stopping)
        waiting = asyncio.create_task(hold_executor_lock(second, stopping, retry_seconds=0.05))
        await asyncio.sleep(0.3)
        assert not waiting.done()
        await first.invalidate()  # the first executor's connection closes: its lock goes
        assert await asyncio.wait_for(waiting, 5)
        await second.invalidate()


async def test_a_waiting_executor_gives_up_when_stopped(db_engine: AsyncEngine) -> None:
    stopping = asyncio.Event()
    async with db_engine.connect() as first_conn, db_engine.connect() as second_conn:
        first = await first_conn.execution_options(isolation_level="AUTOCOMMIT")
        second = await second_conn.execution_options(isolation_level="AUTOCOMMIT")
        assert await hold_executor_lock(first, stopping)
        waiting = asyncio.create_task(hold_executor_lock(second, stopping, retry_seconds=30))
        await asyncio.sleep(0.1)
        stopping.set()
        assert await asyncio.wait_for(waiting, 5) is False
        await first.invalidate()


async def test_an_executor_whose_lock_connection_drops_stops(db_engine: AsyncEngine) -> None:
    stopping = asyncio.Event()
    lost = asyncio.Event()
    async with db_engine.connect() as conn:
        lock = await conn.execution_options(isolation_level="AUTOCOMMIT")
        assert await hold_executor_lock(lock, stopping)
        watch = asyncio.create_task(
            watch_executor_lock(lock, stopping, lost.set, check_seconds=0.05)
        )
        await asyncio.sleep(0.2)
        assert not lost.is_set()  # the connection is open: the lock holds
        await lock.invalidate()  # as when Postgres restarts
        await asyncio.wait_for(watch, 5)
        assert lost.is_set()


async def test_the_lock_watch_ends_quietly_on_stop(db_engine: AsyncEngine) -> None:
    stopping = asyncio.Event()
    lost = asyncio.Event()
    async with db_engine.connect() as conn:
        lock = await conn.execution_options(isolation_level="AUTOCOMMIT")
        assert await hold_executor_lock(lock, stopping)
        watch = asyncio.create_task(watch_executor_lock(lock, stopping, lost.set, check_seconds=30))
        stopping.set()
        await asyncio.wait_for(watch, 5)
        assert not lost.is_set()
        await lock.invalidate()

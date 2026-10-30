"""Run the executor: `python -m agentic_executor` (see `make executor`).

One executor runs per GPU host: it holds a Postgres advisory lock for as long as it runs, and a
second one waits for it. SIGTERM or SIGINT stops it gracefully: it claims nothing more and leaves
a running job's container running, for the next executor to adopt. Should it lose the lock (its
connection dropped, as when Postgres restarts), it stops the same way and exits with status 1.
"""

import asyncio
import logging
import signal
import sys
from collections.abc import Callable

import redis.asyncio as redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from agentic_db import create_engine, session_factory
from agentic_executor.docker import DockerClient
from agentic_executor.executor import Executor
from agentic_executor.gpu import NvidiaSmi
from agentic_executor.settings import ExecutorSettings

log = logging.getLogger("agentic_executor")
LOCK_KEY = "arp.executor"
LOCK_RETRY_SECONDS = 30.0
LOCK_CHECK_SECONDS = 15.0


async def hold_executor_lock(
    conn: AsyncConnection, stopping: asyncio.Event, *, retry_seconds: float = LOCK_RETRY_SECONDS
) -> bool:
    """Take the executor's advisory lock on ``conn``, which holds it until it closes, waiting
    while another executor holds it. False when ``stopping`` is set first."""
    while True:
        locked = await conn.scalar(
            text("SELECT pg_try_advisory_lock(hashtext(:key))"), {"key": LOCK_KEY}
        )
        if locked:
            return True
        log.info("another executor is running; trying again in %.0f s", retry_seconds)
        try:
            await asyncio.wait_for(stopping.wait(), retry_seconds)
        except TimeoutError:
            continue
        return False


async def watch_executor_lock(
    conn: AsyncConnection,
    stopping: asyncio.Event,
    on_lost: Callable[[], None],
    *,
    check_seconds: float = LOCK_CHECK_SECONDS,
) -> None:
    """Every ``check_seconds`` until ``stopping``, check that ``conn`` is still open: the lock
    lasts as long as its connection. When it isn't, another executor could take the lock, so
    ``on_lost`` stops this one."""
    while True:
        try:
            await asyncio.wait_for(stopping.wait(), check_seconds)
            return
        except TimeoutError:
            pass
        try:
            await conn.scalar(text("SELECT 1"))
        except Exception as exc:
            log.error("lost the executor lock with its connection (%s): stopping", exc)
            on_lost()
            return


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = ExecutorSettings()
    engine = create_engine(settings.database_url)
    sessions = session_factory(engine)
    docker = DockerClient(settings.docker_socket, api_version=settings.docker_api_version)
    gpu = NvidiaSmi(settings.nvidia_smi, device=settings.gpu_device)
    # Wake-ups only spare SSE a poll: a Valkey that hangs must not hold up a job.
    valkey = redis.from_url(settings.valkey_url, socket_connect_timeout=2, socket_timeout=2)
    executor = Executor(settings, sessions, docker, gpu, valkey)
    stopping = asyncio.Event()

    def stop() -> None:
        log.info("stopping: a running job's container keeps running")
        stopping.set()
        executor.stop()

    lost = False

    def lock_lost() -> None:
        nonlocal lost
        lost = True
        stop()

    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop)
    try:
        async with engine.connect() as conn:
            # Autocommit: the lock is the session's, and the connection never idles in a
            # transaction while it holds it.
            lock = await conn.execution_options(isolation_level="AUTOCOMMIT")
            if not await hold_executor_lock(lock, stopping):
                return
            log.info(
                "executor running: image %s, GPU %s, Docker at %s",
                settings.sandbox_image,
                settings.gpu_device,
                settings.docker_socket,
            )
            watchdog = asyncio.create_task(watch_executor_lock(lock, stopping, lock_lost))
            try:
                await executor.run()
            finally:
                watchdog.cancel()
                await asyncio.gather(watchdog, return_exceptions=True)
    finally:
        await docker.aclose()
        await valkey.aclose()
        await engine.dispose()
    if lost:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

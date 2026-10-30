"""System health for lab admins: every dependency is probed at once, each with a short timeout."""

import asyncio
import logging
import time
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_api.orchestrator import Orchestrator
from agentic_api.schemas import HealthCheckName, HealthCheckOut, HealthStatus, SystemHealthOut

log = logging.getLogger(__name__)
PROBE_TIMEOUT_SECONDS = 2.0
SLOW_MS = 1000.0  # a dependency that answers slower than this is degraded


@dataclass(frozen=True)
class _Probe:
    status: HealthStatus
    detail: str | None = None


_OK = _Probe("ok")


async def _postgres(sessions: async_sessionmaker[AsyncSession] | None) -> _Probe:
    if sessions is None:
        return _Probe("down", "db.unavailable")
    async with sessions() as session:
        await session.execute(text("SELECT 1"))
    return _OK


async def _valkey(valkey: Any) -> _Probe:
    await valkey.ping()
    return _OK


async def _temporal(orchestrator: Orchestrator) -> _Probe:
    await orchestrator.check_namespace()
    return _OK


async def _gateway(http: httpx.AsyncClient | None, gateway_url: str) -> _Probe:
    if http is None:
        return _Probe("unknown", "health.unconfigured")
    response = await http.get(f"{gateway_url.rstrip('/')}/v1/health")
    return _OK if response.status_code == 200 else _Probe("down", "health.bad_status")


async def _worker(orchestrator: Orchestrator) -> _Probe:
    pollers = await orchestrator.task_queue_pollers()
    if pollers is None:
        return _Probe("unknown", "health.unsupported")
    if pollers.workflow and pollers.activity:
        return _OK
    if pollers.workflow or pollers.activity:
        return _Probe("degraded", "health.partial_pollers")
    return _Probe("down", "health.no_pollers")


async def _check(
    name: HealthCheckName, probe: Coroutine[Any, Any, _Probe], failure: HealthStatus = "down"
) -> HealthCheckOut:
    started = time.perf_counter()
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            result = await probe
    except TimeoutError:
        result = _Probe(failure, "health.timeout")
    except Exception:
        log.warning("health probe %s failed", name, exc_info=True)
        result = _Probe(failure, "health.unreachable")
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    if result.status == "ok" and latency_ms > SLOW_MS:
        result = _Probe("degraded", "health.slow")
    return HealthCheckOut(
        name=name, status=result.status, latency_ms=latency_ms, detail=result.detail
    )


def _overall(checks: list[HealthCheckOut]) -> HealthStatus:
    """The worst status. Unknown checks don't count: nothing is known about them either way."""
    worst_first: tuple[HealthStatus, ...] = ("down", "degraded", "ok")
    for status in worst_first:
        if any(check.status == status for check in checks):
            return status
    return "unknown"


async def system_health(
    *,
    sessions: async_sessionmaker[AsyncSession] | None,
    valkey: Any,
    orchestrator: Orchestrator,
    http: httpx.AsyncClient | None,
    gateway_url: str,
) -> SystemHealthOut:
    checks = list(
        await asyncio.gather(
            _check("postgres", _postgres(sessions)),
            _check("valkey", _valkey(valkey)),
            _check("temporal", _temporal(orchestrator)),
            _check("gateway", _gateway(http, gateway_url)),
            # Pollers are read through Temporal: when it can't answer, the workers are unknown.
            _check("worker", _worker(orchestrator), failure="unknown"),
        )
    )
    return SystemHealthOut(status=_overall(checks), checked_at=datetime.now(UTC), checks=checks)

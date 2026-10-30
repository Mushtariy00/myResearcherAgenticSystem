"""Rate limits per source, shared by every worker process through Valkey.

All lab users share one IP address, so a source's limit is a lab-wide budget: the token bucket
lives in Valkey and an atomic Lua script reserves tokens. The in-memory implementation has the
same interface for tests and single-process use.

Buckets reserve: a caller always gets a token and is told how long to wait for it, so waiters
are served in arrival order and nobody polls. The bucket holds up to ``requests`` tokens and
refills at ``requests / per_seconds`` tokens a second.
"""

import asyncio
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Protocol

from redis.asyncio import Redis


@dataclass(frozen=True, slots=True)
class Limit:
    """``requests`` per ``per_seconds``; also the largest burst."""

    requests: int
    per_seconds: float = 1.0

    def __post_init__(self) -> None:
        if self.requests < 1 or self.per_seconds <= 0:
            raise ValueError("a limit needs at least one request per positive period")

    @property
    def rate(self) -> float:
        """Tokens added per second."""
        return self.requests / self.per_seconds


# Published limits (docs/design/literature.md). Unpaywall asks for under 100,000 calls a day
# and CORE free keys allow about 10 a minute; the waterfall calls them once per paper at most.
SOURCE_LIMITS: Final[Mapping[str, Limit]] = MappingProxyType(
    {
        "openalex": Limit(10),
        "semantic_scholar": Limit(1),
        "arxiv": Limit(1, 3.0),
        "crossref": Limit(10),
        "unpaywall": Limit(10),
        "core": Limit(1, 6.0),
    }
)
OPENALEX_WITH_KEY: Final = Limit(30)


def source_limits(*, openalex_key: bool = False) -> dict[str, Limit]:
    """The default limits, with OpenAlex's higher limit when the lab has an API key."""
    limits = dict(SOURCE_LIMITS)
    if openalex_key:
        limits["openalex"] = OPENALEX_WITH_KEY
    return limits


class RateLimiter(Protocol):
    async def acquire(self, source: str) -> None:
        """Wait until the source's bucket grants one request."""
        ...


class Mutex(Protocol):
    def hold(self) -> AbstractAsyncContextManager[None]:
        """Hold the lock for the duration of the ``async with`` block."""
        ...


@asynccontextmanager
async def throttled(
    limiter: RateLimiter, source: str, mutex: Mutex | None = None
) -> AsyncIterator[None]:
    """One request's worth of permission: a token, and the mutex for the request's duration.

    The mutex is taken before the token, so the token's spacing counts from when the previous
    holder finished rather than from when this caller started queueing.
    """
    if mutex is None:
        await limiter.acquire(source)
        yield
        return
    async with mutex.hold():
        await limiter.acquire(source)
        yield


def _limit_for(limits: Mapping[str, Limit], source: str) -> Limit:
    try:
        return limits[source]
    except KeyError:
        raise KeyError(f"no rate limit configured for source {source!r}") from None


class MemoryRateLimiter:
    """Token buckets in this process only."""

    def __init__(
        self,
        limits: Mapping[str, Limit] = SOURCE_LIMITS,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._limits = dict(limits)
        self._clock = clock
        self._sleep = sleep
        self._buckets: dict[str, tuple[float, float]] = {}

    async def acquire(self, source: str) -> None:
        wait = self.reserve(source)
        if wait > 0:
            await self._sleep(wait)

    def reserve(self, source: str) -> float:
        """Take a token now and return the seconds to wait before using it."""
        limit = _limit_for(self._limits, source)
        now = self._clock()
        tokens, stamp = self._buckets.get(source, (float(limit.requests), now))
        tokens = min(float(limit.requests), tokens + (now - stamp) * limit.rate) - 1
        self._buckets[source] = (tokens, now)
        return -tokens / limit.rate if tokens < 0 else 0.0


# KEYS[1] is the bucket; ARGV[1] its capacity and ARGV[2] its refill rate in tokens per second.
# Valkey's clock is the only clock, so workers on other hosts cannot skew the bucket. The reply
# is the wait in milliseconds (integer replies truncate Lua numbers).
_RESERVE: Final = """
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + math.floor(tonumber(clock[2]) / 1000)
local state = redis.call('HMGET', KEYS[1], 'tokens', 'stamp')
local tokens = tonumber(state[1])
local stamp = tonumber(state[2])
if tokens == nil or stamp == nil then
  tokens = capacity
  stamp = now
end
tokens = math.min(capacity, tokens + math.max(0, now - stamp) * rate / 1000) - 1
redis.call('HSET', KEYS[1], 'tokens', tostring(tokens), 'stamp', tostring(now))
redis.call('PEXPIRE', KEYS[1], math.ceil((capacity - tokens) * 1000 / rate) + 1000)
if tokens < 0 then
  return math.ceil(-tokens * 1000 / rate)
end
return 0
"""


class ValkeyRateLimiter:
    """Token buckets in Valkey, one key per source (``<prefix>:<source>``), shared lab-wide."""

    def __init__(
        self,
        redis: Redis,
        limits: Mapping[str, Limit] = SOURCE_LIMITS,
        *,
        prefix: str = "arp:ratelimit",
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._limits = dict(limits)
        self._prefix = prefix
        self._sleep = sleep
        self._reserve = redis.register_script(_RESERVE)

    async def acquire(self, source: str) -> None:
        wait = await self.reserve(source)
        if wait > 0:
            await self._sleep(wait)

    async def reserve(self, source: str) -> float:
        """Take a token now and return the seconds to wait before using it."""
        limit = _limit_for(self._limits, source)
        waited_ms = await self._reserve(
            keys=[f"{self._prefix}:{source}"], args=[limit.requests, limit.rate]
        )
        return int(waited_ms) / 1000


class MemoryMutex:
    """A mutex for one process (an asyncio lock)."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def hold(self) -> AsyncIterator[None]:
        async with self._lock:
            yield


# Deletes the lock only if this holder still owns it (its lease may have expired meanwhile).
_RELEASE: Final = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


class ValkeyMutex:
    """A lock shared by every worker process, for arXiv's one-connection-at-a-time rule.

    The lock is a key with a lease, so a process that dies while holding it blocks the others
    for ``lease_seconds`` at most. The lease must outlast the longest hold, or a second
    connection gets in: a PDF download (fetch's 60 s deadline) plus the wait for its arXiv token.
    Coroutines in one process queue on a local lock first, so only one of them polls Valkey.
    """

    def __init__(
        self,
        redis: Redis,
        name: str,
        *,
        prefix: str = "arp:mutex",
        lease_seconds: float = 120.0,
        poll_seconds: float = 0.1,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._redis = redis
        self._key = f"{prefix}:{name}"
        self._lease_ms = int(lease_seconds * 1000)
        self._poll_seconds = poll_seconds
        self._sleep = sleep
        self._local = asyncio.Lock()
        self._release = redis.register_script(_RELEASE)

    @asynccontextmanager
    async def hold(self) -> AsyncIterator[None]:
        async with self._local:
            token = secrets.token_hex(16)
            while not await self._redis.set(self._key, token, nx=True, px=self._lease_ms):
                await self._sleep(self._poll_seconds)
            try:
                yield
            finally:
                await self._release(keys=[self._key], args=[token])

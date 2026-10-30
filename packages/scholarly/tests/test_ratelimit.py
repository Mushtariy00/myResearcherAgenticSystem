import asyncio
import os
import time
import uuid
from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis
from redis.exceptions import RedisError

from agentic_scholarly.ratelimit import (
    OPENALEX_WITH_KEY,
    SOURCE_LIMITS,
    Limit,
    MemoryMutex,
    MemoryRateLimiter,
    ValkeyMutex,
    ValkeyRateLimiter,
    source_limits,
    throttled,
)
from agentic_scholarly.testing import RecordingSleep


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_defaults_match_the_published_limits() -> None:
    assert SOURCE_LIMITS["openalex"].rate == 10
    assert SOURCE_LIMITS["semantic_scholar"].rate == 1
    assert SOURCE_LIMITS["arxiv"] == Limit(1, 3.0)
    assert SOURCE_LIMITS["crossref"].rate == 10
    assert source_limits(openalex_key=True)["openalex"] == OPENALEX_WITH_KEY
    assert OPENALEX_WITH_KEY.rate == 30
    assert source_limits()["openalex"] == SOURCE_LIMITS["openalex"]
    with pytest.raises(ValueError, match="at least one request"):
        Limit(0)


def test_memory_bucket_allows_a_burst_then_spaces_requests() -> None:
    clock = FakeClock()
    limiter = MemoryRateLimiter({"source": Limit(2, 1.0)}, clock=clock)
    assert [limiter.reserve("source") for _ in range(4)] == [0.0, 0.0, 0.5, 1.0]
    clock.now += 10
    assert limiter.reserve("source") == 0.0


def test_arxiv_bucket_spaces_requests_three_seconds_apart() -> None:
    clock = FakeClock()
    limiter = MemoryRateLimiter(clock=clock)
    assert limiter.reserve("arxiv") == 0.0
    assert limiter.reserve("arxiv") == pytest.approx(3.0)
    clock.now += 1.5
    assert limiter.reserve("arxiv") == pytest.approx(4.5)


async def test_acquire_sleeps_for_its_reservation() -> None:
    sleeps = RecordingSleep()
    limiter = MemoryRateLimiter({"source": Limit(1, 2.0)}, clock=FakeClock(), sleep=sleeps)
    await limiter.acquire("source")
    await limiter.acquire("source")
    assert sleeps.waits == [pytest.approx(2.0)]


def test_unknown_sources_have_no_silent_default() -> None:
    with pytest.raises(KeyError, match="no rate limit"):
        MemoryRateLimiter().reserve("scihub")


async def test_the_mutex_keeps_requests_from_overlapping() -> None:
    limiter = MemoryRateLimiter({"arxiv": Limit(100)})
    mutex = MemoryMutex()
    active = 0
    peak = 0

    async def one_request() -> None:
        nonlocal active, peak
        async with throttled(limiter, "arxiv", mutex):
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1

    await asyncio.gather(*(one_request() for _ in range(5)))
    assert peak == 1


@pytest.fixture
async def valkey() -> AsyncIterator[Redis]:
    url = os.environ.get("ARP_VALKEY_URL")
    if not url:
        pytest.skip("set ARP_VALKEY_URL to run the Valkey rate-limit tests")
    client = Redis.from_url(url)
    try:
        # execute_command, because redis-py types ping() as sync-or-async.
        await client.execute_command("PING")
    except (RedisError, OSError) as exc:
        await client.aclose()
        pytest.skip(f"Valkey is not reachable at ARP_VALKEY_URL ({exc})")
    yield client
    await client.aclose()


@pytest.fixture
async def prefix(valkey: Redis) -> AsyncIterator[str]:
    """A key prefix of this test's own; every key under it is deleted afterwards."""
    prefix = f"arp-test:scholarly:{uuid.uuid4().hex}"
    yield prefix
    keys = [key async for key in valkey.scan_iter(match=f"{prefix}:*")]
    if keys:
        await valkey.delete(*keys)


async def test_valkey_bucket_is_shared_and_spaces_requests(valkey: Redis, prefix: str) -> None:
    limits = {"source": Limit(2, 1.0)}
    first = ValkeyRateLimiter(valkey, limits, prefix=prefix)
    second = ValkeyRateLimiter(valkey, limits, prefix=prefix)
    waits = [await first.reserve("source"), await second.reserve("source")]
    waits.append(await first.reserve("source"))
    assert waits[:2] == [0.0, 0.0]
    # Both limiters drew from one bucket, so the third request waits about half a second.
    assert 0.3 < waits[2] <= 0.5
    assert await valkey.exists(f"{prefix}:source") == 1
    assert 0 < await valkey.pttl(f"{prefix}:source") <= 3000


async def test_valkey_acquire_waits_out_the_reservation(valkey: Redis, prefix: str) -> None:
    sleeps = RecordingSleep()
    limiter = ValkeyRateLimiter(valkey, {"arxiv": Limit(1, 3.0)}, prefix=prefix, sleep=sleeps)
    await limiter.acquire("arxiv")
    await limiter.acquire("arxiv")
    assert len(sleeps.waits) == 1
    assert 2.5 < sleeps.waits[0] <= 3.0


async def test_valkey_mutex_excludes_other_holders_and_releases(valkey: Redis, prefix: str) -> None:
    first = ValkeyMutex(valkey, "arxiv", prefix=prefix, poll_seconds=0.01)
    second = ValkeyMutex(valkey, "arxiv", prefix=prefix, poll_seconds=0.01)
    order: list[str] = []

    async def hold(mutex: ValkeyMutex, name: str, seconds: float) -> None:
        async with mutex.hold():
            order.append(f"{name} in")
            await asyncio.sleep(seconds)
            order.append(f"{name} out")

    started = time.monotonic()
    await asyncio.gather(hold(first, "first", 0.1), hold(second, "second", 0.0))
    assert order in (
        ["first in", "first out", "second in", "second out"],
        ["second in", "second out", "first in", "first out"],
    )
    assert time.monotonic() - started >= 0.1
    assert await valkey.exists(f"{prefix}:arxiv") == 0

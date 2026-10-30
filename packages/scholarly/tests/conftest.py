"""Shared fixtures. No test reaches the network: API calls go to respx routes and PDF fetches
to agentic_scholarly.testing.FakeNetwork."""

import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from agentic_scholarly.http import RetryPolicy, make_client
from agentic_scholarly.ratelimit import SOURCE_LIMITS, Limit, MemoryRateLimiter
from agentic_scholarly.testing import RecordingSleep

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with make_client("tests@example.invalid") as client:
        yield client


@pytest.fixture
def limiter() -> MemoryRateLimiter:
    """Limits high enough that no test waits for a token."""
    return MemoryRateLimiter({source: Limit(1000) for source in SOURCE_LIMITS})


@pytest.fixture
def sleeps() -> RecordingSleep:
    return RecordingSleep()


@pytest.fixture
def retry(sleeps: RecordingSleep) -> RetryPolicy:
    """The default retry policy without real waits."""
    return RetryPolicy(sleep=sleeps)


@pytest.fixture
def fixture_bytes() -> Callable[[str], bytes]:
    return lambda name: (FIXTURES / name).read_bytes()


@pytest.fixture
def fixture_json() -> Callable[[str], Any]:
    return lambda name: json.loads((FIXTURES / name).read_text("utf-8"))

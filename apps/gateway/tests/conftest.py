from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_gateway.catalog import Catalog
from agentic_gateway.openrouter import OpenRouterClient
from agentic_gateway.quota import FreeQuota
from agentic_gateway.service import Router
from gateway_testkit import BASE_URL, FREE_A, FREE_B, PAID, PAID_BACKUP, FakeCounter, FakeOpenRouter


@pytest.fixture
def upstream() -> FakeOpenRouter:
    return FakeOpenRouter()


@pytest.fixture
def counter() -> FakeCounter:
    return FakeCounter()


@pytest.fixture
async def router(
    db: async_sessionmaker[AsyncSession], upstream: FakeOpenRouter, counter: FakeCounter
) -> AsyncIterator[Router]:
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream.handler)) as http:
        yield Router(
            db,
            Catalog(http, BASE_URL),
            OpenRouterClient(http, BASE_URL, "test-key", "http://localhost:8080"),
            FreeQuota(counter, per_minute=20, per_day=1000, per_user_per_day=300),
            paid_models=[PAID, PAID_BACKUP],
            free_models=[FREE_A, FREE_B],
            timeout=5,
            lease_seconds=60,
        )

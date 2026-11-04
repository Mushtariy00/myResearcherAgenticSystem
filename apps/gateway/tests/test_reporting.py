"""The gateway tells the API what OpenRouter says, through the settings table."""

from collections.abc import AsyncIterator
from decimal import Decimal

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_db.lab_settings import LabAccount, ModelCatalog, lab_account, model_catalog
from agentic_gateway.catalog import Catalog
from agentic_gateway.reporting import Reporter
from gateway_testkit import AUDIO, AUTO_ROUTER, BASE_URL, FREE_A, PAID, FakeOpenRouter

Factory = async_sessionmaker[AsyncSession]


@pytest.fixture
async def reporter(db: Factory, upstream: FakeOpenRouter) -> AsyncIterator[Reporter]:
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream.handler)) as http:
        yield Reporter(db, Catalog(http, BASE_URL), http, BASE_URL, "test-key")


async def account_of(db: Factory) -> LabAccount | None:
    async with db() as session:
        return await lab_account(session)


async def catalog_of(db: Factory) -> ModelCatalog | None:
    async with db() as session:
        return await model_catalog(session)


async def test_the_account_is_what_openrouter_says(
    reporter: Reporter, upstream: FakeOpenRouter, db: Factory
) -> None:
    await reporter.report()
    account = await account_of(db)
    assert account is not None
    assert account.balance_usd == Decimal("17.5")  # 25 bought, 7.5 used
    assert (account.free_tier, account.free_daily_limit) == (False, 1000)
    assert set(upstream.account_keys) == {"Bearer test-key"}


async def test_an_account_that_never_bought_credits_is_on_the_free_tier(
    reporter: Reporter, upstream: FakeOpenRouter, db: Factory
) -> None:
    upstream.credits = (200, {"data": {"total_credits": 0, "total_usage": 0}})
    upstream.key = (
        200,
        {
            "data": {
                "is_free_tier": True,
                "free_model_daily_requests": {"used": 9, "limit": 50, "remaining": 41},
            }
        },
    )
    await reporter.report()
    account = await account_of(db)
    assert account is not None
    assert (account.balance_usd, account.free_tier, account.free_daily_limit) == (0, True, 50)


async def test_where_credits_are_refused_the_keys_own_limit_stands_in(
    reporter: Reporter, upstream: FakeOpenRouter, db: Factory
) -> None:
    refused = {"error": {"code": 403, "message": "Only management keys"}}
    upstream.credits = (403, refused)
    upstream.key = (200, {"data": {"is_free_tier": False, "limit_remaining": 4.25}})
    await reporter.report()
    account = await account_of(db)
    assert account is not None
    assert (account.balance_usd, account.free_daily_limit) == (Decimal("4.25"), None)

    upstream.key = (200, {"data": {"is_free_tier": False, "limit_remaining": None}})
    await reporter.report()
    account = await account_of(db)
    assert account is not None
    assert account.balance_usd is None  # unknown is not zero


async def test_the_last_report_stays_when_openrouter_answers_nothing(
    reporter: Reporter, upstream: FakeOpenRouter, db: Factory
) -> None:
    await reporter.report()
    first = await account_of(db)
    down = {"error": {"code": 503, "message": "down"}}
    upstream.credits, upstream.key = (503, down), (503, down)
    await reporter.report()
    assert await account_of(db) == first


async def test_no_key_means_no_account_calls(db: Factory, upstream: FakeOpenRouter) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream.handler)) as http:
        await Reporter(db, Catalog(http, BASE_URL), http, BASE_URL, "").report()
    assert upstream.account_keys == []
    assert await catalog_of(db) is not None  # /models needs no key


async def test_the_catalog_lists_text_models_with_prices_per_million_tokens(
    reporter: Reporter, db: Factory
) -> None:
    await reporter.report()
    catalog = await catalog_of(db)
    assert catalog is not None
    paid = catalog.models[PAID]
    assert (paid.free, paid.context_length) == (False, 128_000)
    assert (paid.prompt_usd_per_mtok, paid.completion_usd_per_mtok) == (Decimal(1), Decimal(2))
    assert catalog.models[FREE_A].free is True
    assert AUDIO not in catalog.models  # music, whatever it costs
    assert AUTO_ROUTER not in catalog.models


async def test_each_catalog_read_is_stored_once(reporter: Reporter, db: Factory) -> None:
    await reporter.report()
    first = await catalog_of(db)
    await reporter.report()
    second = await catalog_of(db)
    assert first is not None
    assert second is not None
    assert second.checked_at == first.checked_at

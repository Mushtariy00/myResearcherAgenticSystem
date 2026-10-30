"""The model catalog: one fetch at a time, and a bad refresh never takes routing down."""

import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest

from agentic_gateway.catalog import Catalog, CatalogUnavailableError
from gateway_testkit import BASE_URL, CATALOG, PAID


class Models:
    """OpenRouter's /models: the catalog, unless `answers` queues something else."""

    def __init__(self) -> None:
        self.fetches = 0
        self.answers: list[httpx.Response | Exception] = []

    async def handler(self, request: httpx.Request) -> httpx.Response:
        self.fetches += 1
        await asyncio.sleep(0.01)  # long enough for concurrent lookups to pile up
        if self.answers:
            answer = self.answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer
        return httpx.Response(200, json=CATALOG)


@pytest.fixture
def models() -> Models:
    return Models()


@pytest.fixture
async def catalog(models: Models) -> AsyncIterator[Catalog]:
    async with httpx.AsyncClient(transport=httpx.MockTransport(models.handler)) as http:
        yield Catalog(http, BASE_URL)


def expire(catalog: Catalog) -> None:
    catalog._next_refresh = 0.0  # as if the hour were up


@pytest.mark.parametrize(
    "failure",
    [
        httpx.Response(503, text="upstream overloaded"),
        httpx.Response(200, text="<html>maintenance</html>"),  # not JSON
        httpx.Response(200, json={"data": []}),
        httpx.ReadTimeout("slow"),
    ],
)
async def test_a_failed_refresh_keeps_the_catalog_and_waits_before_the_next_try(
    catalog: Catalog, models: Models, failure: httpx.Response | Exception
) -> None:
    await catalog.models()
    expire(catalog)
    models.answers.append(failure)
    assert PAID in await catalog.models()
    assert PAID in await catalog.models()
    assert models.fetches == 2  # the second lookup did not fetch again


async def test_concurrent_lookups_share_one_fetch(catalog: Catalog, models: Models) -> None:
    results = await asyncio.gather(*(catalog.models() for _ in range(5)))
    assert all(PAID in result for result in results)
    assert models.fetches == 1


async def test_without_a_catalog_lookups_fail_fast_until_the_retry(
    catalog: Catalog, models: Models
) -> None:
    models.answers.append(httpx.ConnectError("connection refused"))
    with pytest.raises(CatalogUnavailableError):
        await catalog.models()
    with pytest.raises(CatalogUnavailableError):
        await catalog.models()
    assert models.fetches == 1
    expire(catalog)
    assert PAID in await catalog.models()

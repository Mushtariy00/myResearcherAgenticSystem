from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx

from agentic_scholarly.clients import OpenAlexClient, SourceError
from agentic_scholarly.clients.openalex import parse_work, rebuild_abstract, year_filter
from agentic_scholarly.http import RetryPolicy
from agentic_scholarly.models import SearchQuery
from agentic_scholarly.ratelimit import MemoryRateLimiter

WORKS = "https://api.openalex.org/works"


async def test_search_parses_works(
    respx_mock: respx.MockRouter,
    http: httpx.AsyncClient,
    limiter: MemoryRateLimiter,
    fixture_json: Callable[[str], Any],
) -> None:
    route = respx_mock.get(WORKS).mock(
        return_value=httpx.Response(200, json=fixture_json("openalex_works.json"))
    )
    client = OpenAlexClient(http, limiter)
    papers = await client.search(SearchQuery(text="attention", year_from=2017, year_to=2018))

    params = route.calls.last.request.url.params
    assert params["search"] == "attention"
    assert params["filter"] == "publication_year:2017-2018"
    assert params["per_page"] == "25"
    assert "abstract_inverted_index" in params["select"].split(",")
    assert "authorization" not in route.calls.last.request.headers
    assert client.name == "openalex"

    # The paratext record is not a paper.
    assert [paper.openalex_id for paper in papers] == ["W2963403868", "W2612613542"]
    preprint, review = papers
    assert preprint.doi == "10.48550/arxiv.1706.03762"
    assert preprint.arxiv_id == "1706.03762"
    assert preprint.authors == ["Ashish Vaswani", "Noam Shazeer"]
    assert preprint.year == 2017
    assert preprint.venue == "arXiv (Cornell University)"
    assert preprint.abstract is not None
    assert preprint.abstract.startswith("The dominant sequence transduction models are based")
    assert preprint.citation_count == 6147
    assert preprint.url == "https://doi.org/10.48550/arxiv.1706.03762"
    # http PDF links are upgraded: the fetcher only speaks https.
    assert [c.url for c in preprint.oa_candidates] == ["https://arxiv.org/pdf/1706.03762"]
    assert preprint.hits[0].model_dump() == {
        "source": "openalex",
        "query": "attention",
        "position": 1,
    }

    assert review.pmcid == "PMC6455466"
    assert review.venue == "Briefings in Bioinformatics"
    assert review.abstract is None
    # The publisher's PDF is not open access; the Europe PMC copy is.
    assert [c.url for c in review.oa_candidates] == [
        "https://europepmc.org/articles/pmc6455466?pdf=render"
    ]
    assert review.hits[0].position == 2


async def test_api_key_travels_as_a_bearer_token(
    respx_mock: respx.MockRouter, http: httpx.AsyncClient, limiter: MemoryRateLimiter
) -> None:
    route = respx_mock.get(WORKS).mock(return_value=httpx.Response(200, json={"results": []}))
    client = OpenAlexClient(http, limiter, api_key="secret-key")
    assert await client.search(SearchQuery(text="depth")) == []
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer secret-key"
    assert "secret-key" not in str(request.url)
    assert "filter" not in request.url.params


async def test_rate_limit_answers_become_source_errors(
    respx_mock: respx.MockRouter, http: httpx.AsyncClient, limiter: MemoryRateLimiter
) -> None:
    respx_mock.get(WORKS).mock(
        return_value=httpx.Response(429, headers={"Retry-After": "120"}, json={"error": "limit"})
    )
    client = OpenAlexClient(http, limiter, retry=RetryPolicy(tries=1))
    with pytest.raises(SourceError) as caught:
        await client.search(SearchQuery(text="depth"))
    assert caught.value.code == "source.rate_limited"
    assert caught.value.source == "openalex"
    assert caught.value.retry_after == 120.0


async def test_a_spent_daily_budget_is_its_own_error(
    respx_mock: respx.MockRouter, http: httpx.AsyncClient, limiter: MemoryRateLimiter
) -> None:
    # The headers OpenAlex sends with every answer (live check, October 2026), budget spent.
    headers = {
        "x-ratelimit-limit-usd": "0.1",
        "x-ratelimit-remaining-usd": "0",
        "x-ratelimit-cost-usd": "0.001",
        "x-ratelimit-reset": "66209",
    }
    respx_mock.get(WORKS).mock(return_value=httpx.Response(429, headers=headers))
    client = OpenAlexClient(http, limiter, retry=RetryPolicy(tries=1))
    with pytest.raises(SourceError) as caught:
        await client.search(SearchQuery(text="depth"))
    assert caught.value.code == "source.quota_exhausted"
    assert caught.value.retry_after == 66209.0

    respx_mock.get(WORKS).mock(
        return_value=httpx.Response(429, headers={**headers, "x-ratelimit-remaining-usd": "0.09"})
    )
    with pytest.raises(SourceError) as caught:
        await client.search(SearchQuery(text="depth"))
    assert caught.value.code == "source.rate_limited"
    assert caught.value.retry_after is None


async def test_unexpected_bodies_become_source_errors(
    respx_mock: respx.MockRouter, http: httpx.AsyncClient, limiter: MemoryRateLimiter
) -> None:
    respx_mock.get(WORKS).mock(return_value=httpx.Response(200, text="<html>maintenance</html>"))
    with pytest.raises(SourceError) as caught:
        await OpenAlexClient(http, limiter).search(SearchQuery(text="depth"))
    assert caught.value.code == "source.bad_response"


def test_titles_lose_inline_markup() -> None:
    paper = parse_work(
        {"title": "<i>In vivo</i> depth &amp; motion", "id": "https://openalex.org/W1"}, "q", 1
    )
    assert paper is not None
    assert paper.title == "In vivo depth & motion"
    assert paper.url == "https://openalex.org/W1"


def test_year_filters_cover_open_ranges() -> None:
    assert year_filter(2019, 2024) == "publication_year:2019-2024"
    assert year_filter(2019, None) == "publication_year:>2018"
    assert year_filter(None, 2024) == "publication_year:<2025"
    assert year_filter(None, None) is None


def test_abstracts_rebuild_in_word_order() -> None:
    index = {"world": [1], "hello": [0, 2], "bad": ["x"], 3: [3]}
    assert rebuild_abstract(index) == "hello world hello"
    assert rebuild_abstract(None) is None
    assert rebuild_abstract({}) is None

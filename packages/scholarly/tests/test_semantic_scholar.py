from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx

from agentic_scholarly.clients import SemanticScholarClient, SourceError
from agentic_scholarly.clients.semantic_scholar import year_range
from agentic_scholarly.http import RetryPolicy
from agentic_scholarly.models import SearchQuery
from agentic_scholarly.ratelimit import MemoryRateLimiter

SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"


async def test_search_parses_papers(
    respx_mock: respx.MockRouter,
    http: httpx.AsyncClient,
    limiter: MemoryRateLimiter,
    fixture_json: Callable[[str], Any],
) -> None:
    route = respx_mock.get(SEARCH).mock(
        return_value=httpx.Response(200, json=fixture_json("semantic_scholar_search.json"))
    )
    client = SemanticScholarClient(http, limiter, api_key="s2-key")
    papers = await client.search(
        SearchQuery(text="self-attention transformers", year_from=2017, limit=10)
    )

    request = route.calls.last.request
    # Hyphenated terms match nothing in S2's relevance search.
    assert request.url.params["query"] == "self attention transformers"
    assert request.url.params["year"] == "2017-"
    assert request.url.params["limit"] == "10"
    fields = request.url.params["fields"].split(",")
    assert {"externalIds", "openAccessPdf", "citationCount", "year", "venue"} <= set(fields)
    assert request.headers["x-api-key"] == "s2-key"
    assert client.name == "semantic_scholar"

    transformer, review = papers
    assert transformer.s2_id == "204e3073870fae3d05bcbc2f6a8e263d9b72e776"
    assert transformer.arxiv_id == "1706.03762"
    assert transformer.doi is None
    assert transformer.venue == "Neural Information Processing Systems"
    assert transformer.citation_count == 151234
    assert transformer.url == (
        "https://www.semanticscholar.org/paper/204e3073870fae3d05bcbc2f6a8e263d9b72e776"
    )
    # An empty openAccessPdf.url means no open-access PDF.
    assert transformer.oa_candidates == []
    assert transformer.hits[0].source == "semantic_scholar"

    assert review.doi == "10.1093/bib/bbx044"
    assert review.pmcid == "PMC6455466"
    assert review.venue == "Briefings in Bioinformatics"
    assert review.url == "https://doi.org/10.1093/bib/bbx044"
    assert [(c.url, c.source) for c in review.oa_candidates] == [
        (
            "https://academic.oup.com/bib/article-pdf/19/6/1236/27119184/bbx044.pdf",
            "semantic_scholar",
        )
    ]


async def test_keyless_requests_send_no_key(
    respx_mock: respx.MockRouter, http: httpx.AsyncClient, limiter: MemoryRateLimiter
) -> None:
    route = respx_mock.get(SEARCH).mock(return_value=httpx.Response(200, json={"total": 0}))
    assert await SemanticScholarClient(http, limiter).search(SearchQuery(text="depth")) == []
    assert "x-api-key" not in route.calls.last.request.headers
    assert "year" not in route.calls.last.request.url.params


async def test_the_shared_pool_answering_429_is_a_source_error(
    respx_mock: respx.MockRouter, http: httpx.AsyncClient, limiter: MemoryRateLimiter
) -> None:
    respx_mock.get(SEARCH).mock(
        return_value=httpx.Response(429, json={"message": "Too Many Requests"})
    )
    client = SemanticScholarClient(http, limiter, retry=RetryPolicy(tries=1))
    with pytest.raises(SourceError) as caught:
        await client.search(SearchQuery(text="depth"))
    assert caught.value.code == "source.rate_limited"
    assert caught.value.status == 429


def test_year_ranges() -> None:
    assert year_range(2019, 2023) == "2019-2023"
    assert year_range(None, 2023) == "-2023"
    assert year_range(None, None) is None

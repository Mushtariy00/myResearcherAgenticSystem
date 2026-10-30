"""Unpaywall, CORE, Europe PMC and the PMC Cloud Service: the open-access lookups."""

from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx

from agentic_scholarly.clients import CoreClient, UnpaywallClient, europepmc, pmc
from agentic_scholarly.ratelimit import MemoryRateLimiter

UNPAYWALL = "https://api.unpaywall.org/v2/10.1093/bib/bbx044"
CORE = "https://api.core.ac.uk/v3/search/works"
REVIEW_TITLE = "Deep learning for healthcare: review, opportunities and challenges"


async def test_unpaywall_lists_pdf_locations(
    respx_mock: respx.MockRouter,
    http: httpx.AsyncClient,
    limiter: MemoryRateLimiter,
    fixture_json: Callable[[str], Any],
) -> None:
    route = respx_mock.get(UNPAYWALL).mock(
        return_value=httpx.Response(200, json=fixture_json("unpaywall.json"))
    )
    client = UnpaywallClient(http, limiter, email="lab@example.org")
    assert client.enabled
    found = await client.oa_for_doi("https://doi.org/10.1093/BIB/BBX044")
    assert route.calls.last.request.url.params["email"] == "lab@example.org"
    # Best location first, duplicates and locations without a PDF dropped, http upgraded.
    assert [(c.url, c.source) for c in found] == [
        ("https://pmc.ncbi.nlm.nih.gov/articles/PMC6455466/pdf/bbx044.pdf", "unpaywall"),
        ("https://europepmc.org/articles/pmc6455466?pdf=render", "unpaywall"),
    ]


async def test_unpaywall_without_an_email_asks_nothing(
    respx_mock: respx.MockRouter, http: httpx.AsyncClient, limiter: MemoryRateLimiter
) -> None:
    client = UnpaywallClient(http, limiter, email=" ")
    assert not client.enabled
    assert await client.oa_for_doi("10.1093/bib/bbx044") == []
    assert respx_mock.calls.call_count == 0


async def test_unpaywall_unknown_dois_have_no_locations(
    respx_mock: respx.MockRouter, http: httpx.AsyncClient, limiter: MemoryRateLimiter
) -> None:
    respx_mock.get(UNPAYWALL).mock(return_value=httpx.Response(404, json={"error": True}))
    client = UnpaywallClient(http, limiter, email="lab@example.org")
    assert await client.oa_for_doi("10.1093/bib/bbx044") == []


async def test_core_keeps_only_the_same_paper(
    respx_mock: respx.MockRouter,
    http: httpx.AsyncClient,
    limiter: MemoryRateLimiter,
    fixture_json: Callable[[str], Any],
) -> None:
    route = respx_mock.get(CORE).mock(
        return_value=httpx.Response(200, json=fixture_json("core_search.json"))
    )
    client = CoreClient(http, limiter, api_key="core-key")
    found = await client.oa_for_title(f'{REVIEW_TITLE} "quoted"', year=2018)
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer core-key"
    assert request.url.params["q"] == f'title:"{REVIEW_TITLE} quoted"'
    assert found == []

    found = await client.oa_for_title(REVIEW_TITLE, year=2018)
    # The case study with a similar title is another paper; the download link is deduplicated.
    assert [(c.url, c.source) for c in found] == [
        ("https://core.ac.uk/download/158905312.pdf", "core")
    ]


async def test_core_without_a_key_asks_nothing(
    respx_mock: respx.MockRouter, http: httpx.AsyncClient, limiter: MemoryRateLimiter
) -> None:
    client = CoreClient(http, limiter, api_key=None)
    assert not client.enabled
    assert await client.oa_for_title(REVIEW_TITLE) == []
    assert respx_mock.calls.call_count == 0


def test_pmcid_candidates_need_no_request() -> None:
    assert europepmc.pdf_candidate("6455466").url == (
        "https://europepmc.org/articles/PMC6455466?pdf=render"
    )
    assert pmc.pdf_candidate("PMC6455466").url == (
        "https://pmc-oa-opendata.s3.amazonaws.com/PMC6455466.1/PMC6455466.1.pdf"
    )
    assert pmc.pdf_candidate("PMC6455466", version=2).source == "pmc"
    with pytest.raises(ValueError, match="PMCID"):
        europepmc.pdf_candidate("not-an-id")

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import httpx
import pytest
import respx

from agentic_scholarly.clients import ArxivClient, SourceError
from agentic_scholarly.clients.arxiv import keywords, parse_feed, search_query
from agentic_scholarly.models import SearchQuery
from agentic_scholarly.ratelimit import MemoryRateLimiter

API = "https://export.arxiv.org/api/query"
EMPTY_FEED = b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'


class RecordingMutex:
    def __init__(self) -> None:
        self.holds = 0

    @asynccontextmanager
    async def hold(self) -> AsyncIterator[None]:
        self.holds += 1
        yield


async def test_search_parses_the_atom_feed(
    respx_mock: respx.MockRouter,
    http: httpx.AsyncClient,
    limiter: MemoryRateLimiter,
    fixture_bytes: Callable[[str], bytes],
) -> None:
    route = respx_mock.get(API).mock(
        return_value=httpx.Response(200, content=fixture_bytes("arxiv_search.xml"))
    )
    mutex = RecordingMutex()
    client = ArxivClient(http, limiter, mutex=mutex)
    papers = await client.search(
        SearchQuery(text="Attention transformers 2017-2021", year_from=2017, year_to=2021)
    )

    params = route.calls.last.request.url.params
    assert params["search_query"] == (
        "all:attention AND all:transformers AND submittedDate:[201701010000 TO 202112312359]"
    )
    assert params["sortBy"] == "relevance"
    assert params["max_results"] == "25"
    assert mutex.holds == 1
    assert client.name == "arxiv"

    transformer, midas = papers
    assert transformer.arxiv_id == "1706.03762"
    assert transformer.title == "Attention Is All You Need"
    assert transformer.year == 2017
    assert transformer.venue == "arXiv"
    assert transformer.doi is None
    assert transformer.abstract is not None
    assert transformer.abstract.startswith("The dominant sequence transduction models")
    assert "\n" not in transformer.abstract
    assert transformer.url == "https://arxiv.org/abs/1706.03762"
    assert [c.url for c in transformer.oa_candidates] == ["https://arxiv.org/pdf/1706.03762"]

    assert midas.title == (
        "Towards Robust Monocular Depth Estimation: Mixing Datasets for Zero-shot "
        "Cross-dataset Transfer"
    )
    assert midas.authors == ["René Ranftl", "Katrin Lasinger"]
    assert midas.doi == "10.1109/tpami.2020.3019967"
    assert midas.venue == "IEEE Transactions on Pattern Analysis and Machine Intelligence 2022"
    assert midas.year == 2019
    assert midas.hits[0].position == 2


async def test_no_results_relax_the_query_once(
    respx_mock: respx.MockRouter,
    http: httpx.AsyncClient,
    limiter: MemoryRateLimiter,
    fixture_bytes: Callable[[str], bytes],
) -> None:
    route = respx_mock.get(API).mock(
        side_effect=[
            httpx.Response(200, content=EMPTY_FEED),
            httpx.Response(200, content=fixture_bytes("arxiv_search.xml")),
        ]
    )
    papers = await ArxivClient(http, limiter).search(
        SearchQuery(text="attention transformer unicorn rainbow")
    )
    assert route.call_count == 2
    assert route.calls.last.request.url.params["search_query"] == (
        "(all:attention OR all:transformer OR all:unicorn)"
    )
    assert len(papers) == 2


async def test_results_outside_the_years_are_dropped(
    respx_mock: respx.MockRouter,
    http: httpx.AsyncClient,
    limiter: MemoryRateLimiter,
    fixture_bytes: Callable[[str], bytes],
) -> None:
    respx_mock.get(API).mock(
        return_value=httpx.Response(200, content=fixture_bytes("arxiv_search.xml"))
    )
    papers = await ArxivClient(http, limiter).search(SearchQuery(text="depth", year_from=2018))
    assert [paper.arxiv_id for paper in papers] == ["1907.01341"]


def test_error_entries_raise(fixture_bytes: Callable[[str], bytes]) -> None:
    with pytest.raises(SourceError) as caught:
        parse_feed(fixture_bytes("arxiv_error.xml"), "q")
    assert caught.value.code == "source.bad_response"
    assert "max_results" in str(caught.value)


def test_entity_tricks_are_refused() -> None:
    bomb = (
        b'<?xml version="1.0"?><!DOCTYPE feed [<!ENTITY a "aaaaaaaaaa">'
        b'<!ENTITY b "&a;&a;&a;&a;&a;">]><feed xmlns="http://www.w3.org/2005/Atom">&b;</feed>'
    )
    with pytest.raises(SourceError):
        parse_feed(bomb, "q")


def test_keywords_and_queries() -> None:
    assert keywords("A survey of 3D depth estimation in 2019-2024") == [
        "survey",
        "3d",
        "depth",
        "estimation",
    ]
    assert keywords("what is it") == ["what", "is", "it"]
    assert search_query(["depth"], None, 2020) == (
        "all:depth AND submittedDate:[199101010000 TO 202012312359]"
    )
    assert search_query(["depth", "stereo"], None, None, any_term=True) == (
        "(all:depth OR all:stereo)"
    )

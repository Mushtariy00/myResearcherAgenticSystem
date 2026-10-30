from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx

from agentic_scholarly.clients import CrossrefClient, SourceError
from agentic_scholarly.http import RetryPolicy
from agentic_scholarly.models import SearchQuery
from agentic_scholarly.ratelimit import MemoryRateLimiter

WORKS = "https://api.crossref.org/works"


async def test_search_parses_works_and_drops_retraction_notices(
    respx_mock: respx.MockRouter,
    http: httpx.AsyncClient,
    limiter: MemoryRateLimiter,
    fixture_json: Callable[[str], Any],
) -> None:
    route = respx_mock.get(WORKS).mock(
        return_value=httpx.Response(200, json=fixture_json("crossref_works.json"))
    )
    client = CrossrefClient(http, limiter)
    papers = await client.search(SearchQuery(text="deep learning", year_from=2015, year_to=2024))

    request = route.calls.last.request
    params = request.url.params
    assert params["query"] == "deep learning"
    assert params["rows"] == "25"
    filters = params["filter"].split(",")
    assert "from-pub-date:2015" in filters
    assert "until-pub-date:2024" in filters
    assert "type:journal-article" in filters
    assert {"updated-by", "update-to", "abstract"} <= set(params["select"].split(","))
    # Crossref's polite pool keys on the mailto in the User-Agent.
    assert "mailto:tests@example.invalid" in request.headers["user-agent"]
    assert client.name == "crossref"

    resnet, retracted = papers
    assert resnet.doi == "10.1109/cvpr.2016.90"
    assert resnet.authors == ["Kaiming He", "Xiangyu Zhang"]
    assert resnet.year == 2016
    assert resnet.venue == "2016 IEEE Conference on Computer Vision and Pattern Recognition (CVPR)"
    assert resnet.citation_count == 151002
    assert resnet.arxiv_id == "1512.03385"
    assert resnet.url == "https://doi.org/10.1109/cvpr.2016.90"
    assert resnet.retracted is False
    assert resnet.oa_candidates == []

    assert retracted.retracted is True
    assert retracted.title.startswith("RETRACTED: Myc is a prognostic biomarker")
    assert retracted.authors == ["Yu Chen", "Osteosarcoma Study Group"]
    assert retracted.abstract == "Background: Myc is a proto-oncogene & a transcription factor."
    assert retracted.hits[0].position == 2


async def test_lookup_reads_updated_by(
    respx_mock: respx.MockRouter,
    http: httpx.AsyncClient,
    limiter: MemoryRateLimiter,
    fixture_json: Callable[[str], Any],
) -> None:
    respx_mock.get(f"{WORKS}/10.1177/1758835920922055").mock(
        return_value=httpx.Response(200, json=fixture_json("crossref_work.json"))
    )
    respx_mock.get(f"{WORKS}/10.1000/missing").mock(
        return_value=httpx.Response(404, text="Resource not found.")
    )
    client = CrossrefClient(http, limiter)
    paper = await client.lookup("https://doi.org/10.1177/1758835920922055")
    assert paper is not None
    assert paper.retracted is True
    assert paper.hits == []
    assert await client.lookup("10.1000/missing") is None
    with pytest.raises(ValueError, match="not a DOI"):
        await client.lookup("missing")


async def test_retraction_notices_are_found_through_update_to(
    respx_mock: respx.MockRouter,
    http: httpx.AsyncClient,
    limiter: MemoryRateLimiter,
    fixture_json: Callable[[str], Any],
) -> None:
    updates = fixture_json("crossref_updates.json")
    route = respx_mock.get(WORKS).mock(
        side_effect=[
            httpx.Response(200, json=updates),
            httpx.Response(200, json={"status": "ok", "message": {"items": []}}),
        ]
    )
    client = CrossrefClient(http, limiter)
    assert await client.is_retracted("10.1177/1758835920922055") is True
    assert route.calls.last.request.url.params["filter"] == "updates:10.1177/1758835920922055"
    assert await client.is_retracted("10.1109/CVPR.2016.90") is False


async def test_server_errors_become_source_errors(
    respx_mock: respx.MockRouter, http: httpx.AsyncClient, limiter: MemoryRateLimiter
) -> None:
    respx_mock.get(WORKS).mock(return_value=httpx.Response(502))
    client = CrossrefClient(http, limiter, retry=RetryPolicy(tries=1))
    with pytest.raises(SourceError) as caught:
        await client.search(SearchQuery(text="depth"))
    assert caught.value.code == "source.http_status"
    assert caught.value.status == 502


async def test_network_failures_become_source_errors(
    respx_mock: respx.MockRouter, http: httpx.AsyncClient, limiter: MemoryRateLimiter
) -> None:
    respx_mock.get(WORKS).mock(side_effect=httpx.ConnectError("no route"))
    client = CrossrefClient(http, limiter, retry=RetryPolicy(tries=1))
    with pytest.raises(SourceError) as caught:
        await client.search(SearchQuery(text="depth"))
    assert caught.value.code == "source.network"

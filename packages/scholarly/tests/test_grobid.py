from collections.abc import Callable

import httpx
import pytest
import respx

from agentic_scholarly.grobid import GrobidClient, GrobidError, parse_tei
from agentic_scholarly.http import RetryPolicy
from agentic_scholarly.testing import RecordingSleep, make_pdf

GROBID = "http://grobid:8070"
FULLTEXT = f"{GROBID}/api/processFulltextDocument"


def test_tei_header(fixture_bytes: Callable[[str], bytes]) -> None:
    header = parse_tei(fixture_bytes("grobid_fulltext.tei.xml")).header
    assert header.title == "Attention Is All You Need"
    assert header.authors == ["Ashish Vaswani", "Noam Shazeer", "Aidan N Gomez"]
    assert header.year == 2017
    assert header.doi == "10.48550/arxiv.1706.03762"
    assert header.arxiv_id == "1706.03762"
    assert header.venue is None
    assert header.abstract is not None
    assert header.abstract.startswith("The dominant sequence transduction models")


def test_tei_sections(fixture_bytes: Callable[[str], bytes]) -> None:
    sections = parse_tei(fixture_bytes("grobid_fulltext.tei.xml")).sections
    # Empty sections, figures, acknowledgements and references are not paper text; the
    # appendix is.
    assert [section.title for section in sections] == [
        "Introduction",
        "Scaled Dot-Product Attention",
        "A Attention Visualizations",
    ]
    introduction = sections[0].text
    assert introduction.split("\n\n") == [
        "Recurrent neural networks, long short-term memory [13] and gated recurrent [7] neural "
        "networks in particular, have been firmly established as state of the art approaches in "
        "sequence modeling.",
        "In this work we propose the Transformer, a model architecture eschewing recurrence and "
        "instead relying entirely on an attention mechanism.",
    ]
    assert "softmax" not in sections[1].text


def test_tei_references(fixture_bytes: Callable[[str], bytes]) -> None:
    references = parse_tei(fixture_bytes("grobid_fulltext.tei.xml")).references
    assert [(r.title, r.year, r.doi) for r in references] == [
        ("Layer normalization", 2016, None),
        ("Long short-term memory", 1997, "10.1162/neco.1997.9.8.1735"),
        ("Deep Learning", 2016, None),
    ]
    assert references[0].authors == ["Jimmy Lei Ba", "Jamie Ryan Kiros", "Geoffrey E Hinton"]
    assert references[1].authors == ["Sepp Hochreiter", "Jürgen Schmidhuber"]
    assert references[2].authors == ["Ian Goodfellow"]


@pytest.mark.parametrize(
    "xml",
    [
        b"<TEI xmlns='http://www.tei-c.org/ns/1.0'><unclosed>",
        b"<html><body>Service Unavailable</body></html>",
        b'<?xml version="1.0"?><!DOCTYPE TEI [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        b"<TEI xmlns='http://www.tei-c.org/ns/1.0'>&x;</TEI>",
    ],
)
def test_bad_tei_is_an_error(xml: bytes) -> None:
    with pytest.raises(GrobidError) as caught:
        parse_tei(xml)
    assert caught.value.code == "grobid.bad_tei"


def test_minimal_tei_parses_to_empty_parts() -> None:
    document = parse_tei(b"<TEI xmlns='http://www.tei-c.org/ns/1.0'/>")
    assert document.header.title is None
    assert document.sections == []
    assert document.references == []


async def test_fulltext_posts_the_pdf_without_consolidation(
    respx_mock: respx.MockRouter, http: httpx.AsyncClient, fixture_bytes: Callable[[str], bytes]
) -> None:
    route = respx_mock.post(FULLTEXT).mock(
        return_value=httpx.Response(
            200,
            content=fixture_bytes("grobid_fulltext.tei.xml"),
            headers={"Content-Type": "application/xml"},
        )
    )
    pdf = make_pdf(["A page."])
    document = await GrobidClient(f"{GROBID}/", http).fulltext(pdf)
    assert document.header.title == "Attention Is All You Need"
    request = route.calls.last.request
    assert request.headers["content-type"].startswith("multipart/form-data; boundary=")
    body = request.content
    assert b'name="input"; filename="paper.pdf"' in body
    assert pdf in body
    for field in (b"consolidateHeader", b"consolidateCitations", b"consolidateFunders"):
        assert b'name="' + field + b'"\r\n\r\n0\r\n' in body


async def test_a_busy_grobid_is_retried_then_reported(
    respx_mock: respx.MockRouter, http: httpx.AsyncClient, fixture_bytes: Callable[[str], bytes]
) -> None:
    sleeps = RecordingSleep()
    retry = RetryPolicy(tries=3, backoff_seconds=5.0, statuses=frozenset({503}), sleep=sleeps)
    route = respx_mock.post(FULLTEXT).mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, content=fixture_bytes("grobid_fulltext.tei.xml")),
        ]
    )
    client = GrobidClient(GROBID, http, retry=retry)
    assert (await client.fulltext(b"%PDF-1.4")).references
    assert route.call_count == 2
    assert sleeps.waits == [5.0]

    respx_mock.post(FULLTEXT).mock(return_value=httpx.Response(503))
    with pytest.raises(GrobidError) as caught:
        await client.fulltext(b"%PDF-1.4")
    assert caught.value.code == "grobid.unavailable"


@pytest.mark.parametrize(
    ("status", "code"), [(204, "grobid.no_content"), (500, "grobid.failed"), (400, "grobid.failed")]
)
async def test_errors_are_reported_without_retrying(
    respx_mock: respx.MockRouter, http: httpx.AsyncClient, status: int, code: str
) -> None:
    sleeps = RecordingSleep()
    route = respx_mock.post(FULLTEXT).mock(return_value=httpx.Response(status))
    client = GrobidClient(GROBID, http, retry=RetryPolicy(statuses=frozenset({503}), sleep=sleeps))
    with pytest.raises(GrobidError) as caught:
        await client.fulltext(b"%PDF-1.4")
    assert caught.value.code == code
    assert caught.value.status == status
    assert route.call_count == 1


async def test_a_down_grobid_is_unavailable(
    respx_mock: respx.MockRouter, http: httpx.AsyncClient
) -> None:
    respx_mock.post(FULLTEXT).mock(side_effect=httpx.ConnectError("refused"))
    sleeps = RecordingSleep()
    client = GrobidClient(GROBID, http, retry=RetryPolicy(tries=2, sleep=sleeps))
    with pytest.raises(GrobidError) as caught:
        await client.fulltext(b"%PDF-1.4")
    assert caught.value.code == "grobid.unavailable"


async def test_is_alive(respx_mock: respx.MockRouter, http: httpx.AsyncClient) -> None:
    route = respx_mock.get(f"{GROBID}/api/isalive")
    client = GrobidClient(GROBID, http)
    route.mock(return_value=httpx.Response(200, text="true"))
    assert await client.is_alive() is True
    route.mock(return_value=httpx.Response(503, text="false"))
    assert await client.is_alive() is False
    route.mock(side_effect=httpx.ConnectError("refused"))
    assert await client.is_alive() is False

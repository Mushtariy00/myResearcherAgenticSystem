import hashlib
from typing import Any

import httpx
import respx

from agentic_scholarly.clients import CoreClient, UnpaywallClient
from agentic_scholarly.fetch import FetchedPdf, FetchFailed, FetchRefused
from agentic_scholarly.http import RetryPolicy
from agentic_scholarly.models import OaCandidate, PaperMeta
from agentic_scholarly.ratelimit import Limit, MemoryRateLimiter
from agentic_scholarly.testing import make_pdf
from agentic_scholarly.waterfall import candidates, resolve

PDF = make_pdf(["A valid page of text."])


def oa(url: str, source: str) -> OaCandidate:
    return OaCandidate.model_validate({"url": url, "source": source})


def paper(**fields: Any) -> PaperMeta:
    fields.setdefault("title", "Deep learning for healthcare")
    return PaperMeta.model_validate(fields)


class FakeFetch:
    """fetch_pdf stand-in: URLs map to bytes (served) or errors (raised)."""

    def __init__(self, results: dict[str, bytes | Exception]) -> None:
        self.results = results
        self.urls: list[str] = []

    async def __call__(self, url: str) -> FetchedPdf:
        self.urls.append(url)
        result = self.results.get(url, FetchFailed("fetch.http_status", status=404))
        if isinstance(result, Exception):
            raise result
        return FetchedPdf(
            data=result,
            final_url=url,
            content_type="application/pdf",
            sha256=hashlib.sha256(result).hexdigest(),
        )


def test_candidates_follow_the_waterfall_order() -> None:
    found = candidates(
        paper(
            arxiv_id="1706.03762",
            pmcid="PMC6455466",
            oa_candidates=[
                oa("https://core.ac.uk/download/1.pdf", "core"),
                oa("https://pdfs.semanticscholar.org/x.pdf", "semantic_scholar"),
                oa("https://arxiv.org/pdf/1706.03762v7", "openalex"),
                oa("https://repository.example.edu/paper.pdf", "openalex"),
                oa("https://pmc.ncbi.nlm.nih.gov/articles/PMC6455466/pdf/a.pdf", "unpaywall"),
                oa("https://sci-hub.example/10.1093/bib/bbx044", "openalex"),
                oa("https://europepmc.org/articles/pmc6455466?pdf=render", "openalex"),
            ],
        )
    )
    assert [(c.source, c.url) for c in found] == [
        ("arxiv", "https://arxiv.org/pdf/1706.03762"),
        ("pmc", "https://pmc-oa-opendata.s3.amazonaws.com/PMC6455466.1/PMC6455466.1.pdf"),
        ("europepmc", "https://europepmc.org/articles/PMC6455466?pdf=render"),
        ("unpaywall", "https://pmc.ncbi.nlm.nih.gov/articles/PMC6455466/pdf/a.pdf"),
        ("openalex", "https://repository.example.edu/paper.pdf"),
        ("semantic_scholar", "https://pdfs.semanticscholar.org/x.pdf"),
        ("core", "https://core.ac.uk/download/1.pdf"),
    ]


def test_a_paper_without_ids_or_links_has_no_candidates() -> None:
    assert candidates(paper()) == []


async def test_resolve_stops_at_the_first_valid_pdf(
    respx_mock: respx.MockRouter, http: httpx.AsyncClient, limiter: MemoryRateLimiter
) -> None:
    fetch = FakeFetch(
        {
            "https://arxiv.org/pdf/1706.03762": FetchRefused("fetch.not_pdf"),
            "https://repository.example.edu/a.pdf": b"%PDF-1.4 but not really a PDF" * 500,
            "https://repository.example.edu/b.pdf": PDF,
            "https://repository.example.edu/c.pdf": PDF,
        }
    )
    unpaywall = UnpaywallClient(http, limiter, email="lab@example.org")
    result = await resolve(
        paper(
            arxiv_id="1706.03762",
            doi="10.1093/bib/bbx044",
            oa_candidates=[
                oa("https://repository.example.edu/a.pdf", "openalex"),
                oa("https://repository.example.edu/b.pdf", "openalex"),
                oa("https://repository.example.edu/c.pdf", "semantic_scholar"),
            ],
        ),
        fetch,
        unpaywall=unpaywall,
    )
    assert result.pdf is not None
    assert result.pdf.data == PDF
    assert result.candidate == oa("https://repository.example.edu/b.pdf", "openalex")
    assert [(a.candidate.source, a.error) for a in result.attempts] == [
        ("arxiv", "fetch.not_pdf"),
        ("openalex", "pdf.invalid"),
        ("openalex", None),
    ]
    # A cheap candidate worked, so Unpaywall was never asked.
    assert respx_mock.calls.call_count == 0


async def test_unpaywall_then_core_are_asked_only_when_the_rest_failed(
    respx_mock: respx.MockRouter, http: httpx.AsyncClient, limiter: MemoryRateLimiter
) -> None:
    respx_mock.get("https://api.unpaywall.org/v2/10.1093/bib/bbx044").mock(
        return_value=httpx.Response(
            200,
            json={
                "best_oa_location": {"url_for_pdf": "https://repository.example.edu/a.pdf"},
                "oa_locations": [{"url_for_pdf": "https://journal.example.org/u.pdf"}],
            },
        )
    )
    respx_mock.get("https://api.core.ac.uk/v3/search/works").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Deep learning for healthcare",
                        "downloadUrl": "https://core.ac.uk/download/7.pdf",
                    }
                ]
            },
        )
    )
    fetch = FakeFetch({"https://core.ac.uk/download/7.pdf": PDF})
    result = await resolve(
        paper(
            doi="10.1093/bib/bbx044",
            oa_candidates=[oa("https://repository.example.edu/a.pdf", "openalex")],
        ),
        fetch,
        unpaywall=UnpaywallClient(http, limiter, email="lab@example.org"),
        core=CoreClient(http, limiter, api_key="core-key"),
    )
    assert result.candidate == oa("https://core.ac.uk/download/7.pdf", "core")
    # The Unpaywall link already tried through OpenAlex is not fetched twice.
    assert fetch.urls == [
        "https://repository.example.edu/a.pdf",
        "https://journal.example.org/u.pdf",
        "https://core.ac.uk/download/7.pdf",
    ]


async def test_no_pdf_anywhere_is_an_answer_too(
    respx_mock: respx.MockRouter, http: httpx.AsyncClient, limiter: MemoryRateLimiter
) -> None:
    respx_mock.get("https://api.unpaywall.org/v2/10.1093/bib/bbx044").mock(
        return_value=httpx.Response(429)
    )
    unpaywall = UnpaywallClient(http, limiter, email="lab@example.org", retry=RetryPolicy(tries=1))
    result = await resolve(paper(doi="10.1093/bib/bbx044"), FakeFetch({}), unpaywall=unpaywall)
    assert result.pdf is None
    assert result.candidate is None
    assert result.attempts == ()
    assert result.lookup_errors == ("unpaywall:source.rate_limited",)


async def test_arxiv_pdfs_spend_arxiv_tokens() -> None:
    reservations: list[str] = []

    class CountingLimiter(MemoryRateLimiter):
        def reserve(self, source: str) -> float:
            reservations.append(source)
            return super().reserve(source)

    limiter = CountingLimiter({"arxiv": Limit(100)})
    fetch = FakeFetch({"https://repository.example.edu/a.pdf": PDF})
    result = await resolve(
        paper(
            arxiv_id="2301.07041",
            oa_candidates=[oa("https://repository.example.edu/a.pdf", "openalex")],
        ),
        fetch,
        limiter=limiter,
    )
    assert result.candidate is not None
    assert result.candidate.source == "openalex"
    assert reservations == ["arxiv"]

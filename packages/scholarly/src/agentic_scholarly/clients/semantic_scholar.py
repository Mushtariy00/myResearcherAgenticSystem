"""Semantic Scholar paper search (Graph API v1): external ids, open-access PDF, citations."""

from typing import Any, Final, Literal

import httpx

from agentic_scholarly.clients.base import (
    SourceClient,
    as_dict,
    as_list,
    build_paper,
    int_or_none,
    landing_url,
    pdf_candidate,
    text_or_none,
    year_or_none,
)
from agentic_scholarly.http import DEFAULT_RETRY, RetryPolicy
from agentic_scholarly.ids import (
    normalize_arxiv_id,
    normalize_doi,
    normalize_pmcid,
    normalize_s2_id,
)
from agentic_scholarly.models import PaperMeta, SearchQuery, SourceHit
from agentic_scholarly.ratelimit import RateLimiter

SEARCH_URL: Final = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS: Final = ",".join(
    (
        "paperId",
        "externalIds",
        "url",
        "title",
        "abstract",
        "venue",
        "publicationVenue",
        "year",
        "citationCount",
        "openAccessPdf",
        "authors",
    )
)


class SemanticScholarClient(SourceClient):
    """Search Semantic Scholar. Without a key requests share a public pool and often get 429."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        limiter: RateLimiter,
        *,
        api_key: str | None = None,
        retry: RetryPolicy = DEFAULT_RETRY,
    ) -> None:
        super().__init__(http, limiter, retry=retry)
        self._headers = {"x-api-key": api_key} if api_key else None

    @property
    def name(self) -> Literal["semantic_scholar"]:
        return "semantic_scholar"

    async def search(self, query: SearchQuery) -> list[PaperMeta]:
        # The relevance search has no query syntax, and hyphenated terms match nothing, so
        # hyphens become spaces as the API documentation advises.
        params: dict[str, str | int] = {
            "query": query.text.replace("-", " "),
            "limit": query.limit,
            "fields": FIELDS,
        }
        years = year_range(query.year_from, query.year_to)
        if years:
            params["year"] = years
        response = await self._get(SEARCH_URL, params=params, headers=self._headers)
        data = as_list(self._json(response).get("data"))
        papers = (
            parse_paper(as_dict(item), query.text, position)
            for position, item in enumerate(data, start=1)
        )
        return [paper for paper in papers if paper is not None]


def year_range(year_from: int | None, year_to: int | None) -> str | None:
    """The ``year`` parameter: 2019-2023, 2019- (since) or -2023 (until)."""
    if year_from is None and year_to is None:
        return None
    return f"{year_from or ''}-{year_to or ''}"


def parse_paper(item: dict[str, Any], query: str, position: int) -> PaperMeta | None:
    title = text_or_none(item.get("title"))
    if title is None:
        return None
    external = as_dict(item.get("externalIds"))
    doi = normalize_doi(external.get("DOI"))
    authors = [text_or_none(as_dict(author).get("name")) for author in as_list(item.get("authors"))]
    venue = text_or_none(item.get("venue")) or text_or_none(
        as_dict(item.get("publicationVenue")).get("name")
    )
    # openAccessPdf is present with an empty url when the paper has no open-access PDF.
    candidate = pdf_candidate(as_dict(item.get("openAccessPdf")).get("url"), "semantic_scholar")
    return build_paper(
        "semantic_scholar",
        {
            "title": title,
            "authors": [author for author in authors if author],
            "year": year_or_none(item.get("year")),
            "venue": venue,
            "abstract": text_or_none(item.get("abstract")),
            "doi": doi,
            "arxiv_id": normalize_arxiv_id(external.get("ArXiv")),
            "s2_id": normalize_s2_id(item.get("paperId")),
            "pmcid": normalize_pmcid(external.get("PubMedCentral")),
            "citation_count": int_or_none(item.get("citationCount")),
            "url": landing_url(doi, item.get("url")),
            "oa_candidates": [candidate] if candidate else [],
            "hits": [SourceHit(source="semantic_scholar", query=query, position=position)],
        },
    )

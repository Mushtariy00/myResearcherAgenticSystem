"""arXiv search through the export.arxiv.org Atom API.

arXiv asks for one request every 3 seconds and one connection at a time, so every request
holds the arXiv mutex (cross-process in the worker) and then takes a token from the arXiv bucket.
"""

from contextlib import AbstractAsyncContextManager
from typing import Final, Literal
from xml.etree.ElementTree import Element, ParseError

import httpx
from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring

from agentic_scholarly.clients.base import (
    SourceClient,
    SourceError,
    build_paper,
    text_or_none,
    year_or_none,
)
from agentic_scholarly.http import DEFAULT_RETRY, RetryPolicy
from agentic_scholarly.ids import normalize_arxiv_id, normalize_doi
from agentic_scholarly.models import OaCandidate, PaperMeta, SearchQuery, SourceHit
from agentic_scholarly.ratelimit import MemoryMutex, Mutex, RateLimiter, throttled
from agentic_scholarly.terms import terms

API_URL: Final = "https://export.arxiv.org/api/query"
_ATOM: Final = "{http://www.w3.org/2005/Atom}"
_ARXIV: Final = "{http://arxiv.org/schemas/atom}"
# Every term is ANDed, so long queries quickly match nothing.
_MAX_TERMS: Final = 8
_FIRST_YEAR: Final = 1991


def pdf_url(arxiv_id: str) -> str:
    """The arXiv PDF of the latest version."""
    return f"https://arxiv.org/pdf/{arxiv_id}"


class ArxivClient(SourceClient):
    """Search arXiv. Pass the worker's cross-process mutex; the default only serialises this
    process."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        limiter: RateLimiter,
        *,
        mutex: Mutex | None = None,
        retry: RetryPolicy = DEFAULT_RETRY,
    ) -> None:
        super().__init__(http, limiter, retry=retry)
        self._mutex = mutex if mutex is not None else MemoryMutex()

    @property
    def name(self) -> Literal["arxiv"]:
        return "arxiv"

    def _gate(self) -> AbstractAsyncContextManager[None]:
        return throttled(self._limiter, self.name, self._mutex)

    async def search(self, query: SearchQuery) -> list[PaperMeta]:
        terms = keywords(query.text)
        if not terms:
            return []
        papers = await self._query(search_query(terms, query.year_from, query.year_to), query)
        if not papers and len(terms) >= 2:
            # An AND over every term often finds nothing; retry with any of the first three.
            relaxed = search_query(terms[:3], query.year_from, query.year_to, any_term=True)
            papers = await self._query(relaxed, query)
        return papers

    async def _query(self, expression: str, query: SearchQuery) -> list[PaperMeta]:
        params: dict[str, str | int] = {
            "search_query": expression,
            "start": 0,
            "max_results": query.limit,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
        response = await self._get(API_URL, params=params)
        papers = parse_feed(response.content, query.text)
        # submittedDate already filters; the check guards against feeds that ignore it.
        return [paper for paper in papers if _in_years(paper.year, query)]


def keywords(text: str) -> list[str]:
    """Search terms: words without stopwords and bare numbers (years, ranges), at most eight.

    A query made only of stopwords keeps them rather than searching for nothing.
    """
    words = [word for word in terms(text) if not word.isdigit()]
    if not words:
        words = [word for word in terms(text, keep_stopwords=True) if not word.isdigit()]
    return words[:_MAX_TERMS]


def search_query(
    terms: list[str], year_from: int | None, year_to: int | None, *, any_term: bool = False
) -> str:
    """An arXiv search_query: every term (or any term) in any field, within submission dates."""
    clause = (" OR " if any_term else " AND ").join(f"all:{term}" for term in terms)
    if any_term and len(terms) > 1:
        clause = f"({clause})"
    if year_from is None and year_to is None:
        return clause
    start = year_from if year_from is not None else _FIRST_YEAR
    end = year_to if year_to is not None else 9999
    return f"{clause} AND submittedDate:[{start}01010000 TO {end}12312359]"


def parse_feed(xml: bytes, query: str) -> list[PaperMeta]:
    """Papers from an Atom feed; an error entry (bad query) raises SourceError."""
    try:
        root = fromstring(xml, forbid_dtd=True)
    except (ParseError, DefusedXmlException) as exc:
        raise SourceError("arxiv", "source.bad_response", "unreadable Atom feed") from exc
    papers: list[PaperMeta] = []
    for position, entry in enumerate(root.findall(f"{_ATOM}entry"), start=1):
        if "/api/errors" in (_text(entry, f"{_ATOM}id") or ""):
            detail = _text(entry, f"{_ATOM}summary") or "query error"
            raise SourceError("arxiv", "source.bad_response", detail)
        paper = parse_entry(entry, query, position)
        if paper is not None:
            papers.append(paper)
    return papers


def parse_entry(entry: Element, query: str, position: int) -> PaperMeta | None:
    arxiv_id = normalize_arxiv_id(_text(entry, f"{_ATOM}id"))
    title = _text(entry, f"{_ATOM}title")
    if arxiv_id is None or title is None:
        return None
    authors = [_text(author, f"{_ATOM}name") for author in entry.findall(f"{_ATOM}author")]
    # arxiv:doi occasionally lists several DOIs separated by spaces; the first is the article.
    doi_text = _text(entry, f"{_ARXIV}doi")
    return build_paper(
        "arxiv",
        {
            "title": title,
            "authors": [author for author in authors if author],
            "year": year_or_none(_text(entry, f"{_ATOM}published")),
            "venue": _text(entry, f"{_ARXIV}journal_ref") or "arXiv",
            "abstract": _text(entry, f"{_ATOM}summary"),
            "doi": normalize_doi(doi_text.split()[0]) if doi_text else None,
            "arxiv_id": arxiv_id,
            "url": f"https://arxiv.org/abs/{arxiv_id}",
            "oa_candidates": [OaCandidate(url=pdf_url(arxiv_id), source="arxiv")],
            "hits": [SourceHit(source="arxiv", query=query, position=position)],
        },
    )


def _text(element: Element, path: str) -> str | None:
    return text_or_none(element.findtext(path))


def _in_years(year: int | None, query: SearchQuery) -> bool:
    if year is None:
        return query.year_from is None and query.year_to is None
    if query.year_from is not None and year < query.year_from:
        return False
    return query.year_to is None or year <= query.year_to

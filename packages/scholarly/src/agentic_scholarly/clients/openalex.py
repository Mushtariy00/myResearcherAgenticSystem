"""OpenAlex works search: publication-year filter, open-access locations, rebuilt abstracts."""

from typing import Any, Final, Literal

import httpx

from agentic_scholarly.clients.base import (
    SourceClient,
    SourceError,
    as_dict,
    as_list,
    build_paper,
    int_or_none,
    landing_url,
    pdf_candidate,
    strip_markup,
    text_or_none,
    unique_candidates,
    year_or_none,
)
from agentic_scholarly.http import DEFAULT_RETRY, RetryPolicy
from agentic_scholarly.ids import (
    arxiv_id_from_doi,
    normalize_arxiv_id,
    normalize_doi,
    normalize_openalex_id,
    normalize_pmcid,
)
from agentic_scholarly.models import PaperMeta, SearchQuery, SourceHit
from agentic_scholarly.ratelimit import RateLimiter

BASE_URL: Final = "https://api.openalex.org"
# Only what a record needs: whole works are large and OpenAlex bills by request.
SELECT: Final = ",".join(
    (
        "id",
        "doi",
        "title",
        "display_name",
        "publication_year",
        "type",
        "authorships",
        "primary_location",
        "best_oa_location",
        "locations",
        "abstract_inverted_index",
        "cited_by_count",
        "ids",
        "is_retracted",
    )
)
# Work types that are not papers (front matter, notices, reviews of reviews).
_SKIPPED_TYPES: Final = frozenset(
    {"paratext", "erratum", "retraction", "peer-review", "grant", "supplementary-materials"}
)
# OpenAlex puts no bound on inverted indexes; this bounds memory on a malformed one.
_MAX_ABSTRACT_WORDS: Final = 5_000


class OpenAlexClient(SourceClient):
    """Search OpenAlex works.

    Without a key the lab shares 10 requests/s and a $0.10 daily budget (a search costs
    $0.001, so about 100 searches a day); a free key raises that to 30/s and $1/day.
    """

    def __init__(
        self,
        http: httpx.AsyncClient,
        limiter: RateLimiter,
        *,
        api_key: str | None = None,
        retry: RetryPolicy = DEFAULT_RETRY,
    ) -> None:
        super().__init__(http, limiter, retry=retry)
        # Sent as a bearer token, which OpenAlex accepts like the api_key parameter, so the key
        # never appears in request URLs (httpx logs URLs at INFO level).
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else None

    @property
    def name(self) -> Literal["openalex"]:
        return "openalex"

    async def search(self, query: SearchQuery) -> list[PaperMeta]:
        params: dict[str, str | int] = {
            "search": query.text,
            "per_page": query.limit,
            "select": SELECT,
        }
        years = year_filter(query.year_from, query.year_to)
        if years:
            params["filter"] = years
        response = await self._get(f"{BASE_URL}/works", params=params, headers=self._headers)
        results = as_list(self._json(response).get("results"))
        papers = (
            parse_work(as_dict(work), query.text, position)
            for position, work in enumerate(results, start=1)
        )
        return [paper for paper in papers if paper is not None]

    def _rate_limit_error(self, response: httpx.Response) -> SourceError:
        # A spent daily budget also answers 429. The headers tell it apart from the per-second
        # limit, and X-RateLimit-Reset gives the seconds until the budget resets (midnight UTC).
        remaining = _number(response.headers.get("x-ratelimit-remaining-usd"))
        if remaining is not None and remaining <= 0:
            return SourceError(
                self.name,
                "source.quota_exhausted",
                "the daily OpenAlex budget is spent",
                status=429,
                retry_after=_number(response.headers.get("x-ratelimit-reset")),
            )
        return super()._rate_limit_error(response)


def _number(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def year_filter(year_from: int | None, year_to: int | None) -> str | None:
    """OpenAlex's publication_year filter for an inclusive, possibly open, range."""
    if year_from is not None and year_to is not None:
        return f"publication_year:{year_from}-{year_to}"
    if year_from is not None:
        return f"publication_year:>{year_from - 1}"
    if year_to is not None:
        return f"publication_year:<{year_to + 1}"
    return None


def rebuild_abstract(index: object) -> str | None:
    """The abstract text from OpenAlex's inverted index ({word: [positions]})."""
    if not isinstance(index, dict):
        return None
    words: dict[int, str] = {}
    for word, positions in index.items():
        if not isinstance(word, str):
            continue
        for position in as_list(positions):
            if isinstance(position, int) and 0 <= position < _MAX_ABSTRACT_WORDS:
                words[position] = word
    return " ".join(words[position] for position in sorted(words)) or None


def parse_work(work: dict[str, Any], query: str, position: int) -> PaperMeta | None:
    if work.get("type") in _SKIPPED_TYPES:
        return None
    # Titles keep inline markup from the publisher (<i>, <sub>, &amp;).
    title = strip_markup(work.get("title")) or strip_markup(work.get("display_name"))
    if title is None:
        return None
    doi = normalize_doi(work.get("doi"))
    openalex_id = normalize_openalex_id(work.get("id"))
    primary = as_dict(work.get("primary_location"))
    best = as_dict(work.get("best_oa_location"))
    locations = [as_dict(location) for location in as_list(work.get("locations"))]
    open_locations = [best, *(location for location in locations if location.get("is_oa"))]
    authors = [
        text_or_none(as_dict(as_dict(authorship).get("author")).get("display_name"))
        for authorship in as_list(work.get("authorships"))
    ]
    return build_paper(
        "openalex",
        {
            "title": title,
            "authors": [author for author in authors if author],
            "year": year_or_none(work.get("publication_year")),
            "venue": text_or_none(as_dict(primary.get("source")).get("display_name")),
            "abstract": rebuild_abstract(work.get("abstract_inverted_index")),
            "doi": doi,
            "arxiv_id": arxiv_id_from_doi(doi) or _arxiv_id([primary, best, *locations]),
            "openalex_id": openalex_id,
            "pmcid": normalize_pmcid(as_dict(work.get("ids")).get("pmcid")),
            "citation_count": int_or_none(work.get("cited_by_count")),
            "url": landing_url(
                doi,
                primary.get("landing_page_url"),
                f"https://openalex.org/{openalex_id}" if openalex_id else None,
            ),
            "oa_candidates": unique_candidates(
                pdf_candidate(location.get("pdf_url"), "openalex") for location in open_locations
            ),
            "retracted": work.get("is_retracted") is True,
            "hits": [SourceHit(source="openalex", query=query, position=position)],
        },
    )


def _arxiv_id(locations: list[dict[str, Any]]) -> str | None:
    """The arXiv id of an arXiv-hosted location, if the work has one."""
    for location in locations:
        for key in ("landing_page_url", "pdf_url"):
            url = location.get(key)
            if isinstance(url, str) and "arxiv.org/" in url:
                arxiv_id = normalize_arxiv_id(url)
                if arxiv_id:
                    return arxiv_id
    return None

"""CORE (core.ac.uk): repository copies of a paper, found by title. Needs an API key."""

from typing import Any, Final, Literal

import httpx

from agentic_scholarly.clients.base import (
    SourceClient,
    as_dict,
    as_list,
    pdf_candidate,
    text_or_none,
    unique_candidates,
    year_or_none,
)
from agentic_scholarly.http import DEFAULT_RETRY, RetryPolicy
from agentic_scholarly.ids import normalize_title
from agentic_scholarly.models import OaCandidate
from agentic_scholarly.ratelimit import RateLimiter

SEARCH_URL: Final = "https://api.core.ac.uk/v3/search/works"


class CoreClient(SourceClient):
    """CORE title search, enabled only when the lab configured an API key."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        limiter: RateLimiter,
        *,
        api_key: str | None,
        retry: RetryPolicy = DEFAULT_RETRY,
    ) -> None:
        super().__init__(http, limiter, retry=retry)
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else None

    @property
    def name(self) -> Literal["core"]:
        return "core"

    @property
    def enabled(self) -> bool:
        return self._headers is not None

    async def oa_for_title(
        self, title: str, *, year: int | None = None, limit: int = 5
    ) -> list[OaCandidate]:
        """Download links of CORE works with the same title (and year within one, if known).

        A title search returns other papers too; only exact title matches are kept, since a
        wrong PDF is worse than none.
        """
        if self._headers is None:
            return []
        wanted = normalize_title(title)
        if not wanted:
            return []
        # Quotes and backslashes would end the phrase query early.
        phrase = title.replace("\\", " ").replace('"', " ")
        response = await self._get(
            SEARCH_URL,
            params={"q": f'title:"{" ".join(phrase.split())}"', "limit": limit},
            headers=self._headers,
        )
        results = (as_dict(work) for work in as_list(self._json(response).get("results")))
        return unique_candidates(
            candidate
            for work in results
            if _same_paper(work, wanted, year)
            for candidate in _download_links(work)
        )


def _same_paper(work: dict[str, Any], wanted_title: str, year: int | None) -> bool:
    title = text_or_none(work.get("title"))
    if title is None or normalize_title(title) != wanted_title:
        return False
    found_year = year_or_none(work.get("yearPublished"))
    return year is None or found_year is None or abs(found_year - year) <= 1


def _download_links(work: dict[str, Any]) -> list[OaCandidate | None]:
    links = [
        as_dict(link).get("url")
        for link in as_list(work.get("links"))
        if as_dict(link).get("type") == "download"
    ]
    return [pdf_candidate(url, "core") for url in (work.get("downloadUrl"), *links)]

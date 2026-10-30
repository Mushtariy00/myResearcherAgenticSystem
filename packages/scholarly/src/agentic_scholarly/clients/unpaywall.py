"""Unpaywall: a DOI's open-access PDF locations. The API requires a contact email."""

from typing import Final, Literal
from urllib.parse import quote

import httpx

from agentic_scholarly.clients.base import (
    SourceClient,
    as_dict,
    as_list,
    pdf_candidate,
    unique_candidates,
)
from agentic_scholarly.http import DEFAULT_RETRY, RetryPolicy
from agentic_scholarly.ids import normalize_doi
from agentic_scholarly.models import OaCandidate
from agentic_scholarly.ratelimit import RateLimiter

API_URL: Final = "https://api.unpaywall.org/v2"


class UnpaywallClient(SourceClient):
    """Unpaywall lookups, enabled only when the lab configured a contact email."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        limiter: RateLimiter,
        *,
        email: str | None,
        retry: RetryPolicy = DEFAULT_RETRY,
    ) -> None:
        super().__init__(http, limiter, retry=retry)
        self._email = (email or "").strip() or None

    @property
    def name(self) -> Literal["unpaywall"]:
        return "unpaywall"

    @property
    def enabled(self) -> bool:
        return self._email is not None

    async def oa_for_doi(self, doi: str) -> list[OaCandidate]:
        """PDF links for doi, best location first; empty when disabled or Unpaywall has none."""
        if self._email is None:
            return []
        normalized = normalize_doi(doi)
        if normalized is None:
            raise ValueError(f"not a DOI: {doi!r}")
        response = await self._get(
            f"{API_URL}/{quote(normalized, safe='/')}",
            params={"email": self._email},
            allow=(404,),
        )
        if response.status_code == 404:
            return []
        record = self._json(response)
        locations = [record.get("best_oa_location"), *as_list(record.get("oa_locations"))]
        return unique_candidates(
            pdf_candidate(as_dict(location).get("url_for_pdf"), "unpaywall")
            for location in locations
        )

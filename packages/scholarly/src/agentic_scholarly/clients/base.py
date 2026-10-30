"""What the source clients share: the error type, the search protocol and parsing helpers."""

import html
import logging
import re
from collections.abc import Iterable, Mapping
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol

import httpx

from agentic_scholarly.http import DEFAULT_RETRY, RetryPolicy, request, retry_after_seconds
from agentic_scholarly.models import (
    OaCandidate,
    OaSource,
    PaperMeta,
    SearchQuery,
    SourceName,
    is_https_url,
)
from agentic_scholarly.ratelimit import RateLimiter, throttled

logger = logging.getLogger("agentic_scholarly.clients")

_TAG = re.compile(r"<[^>]+>")
_YEAR = re.compile(r"^\s*(\d{4})")


class SourceError(Exception):
    """A source could not answer: rate limited, an HTTP error, a network failure or a reply in
    an unexpected shape. ``code`` is a short message code such as ``source.rate_limited``."""

    def __init__(
        self,
        source: str,
        code: str,
        detail: str = "",
        *,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(f"{source}: {code}" + (f" ({detail})" if detail else ""))
        self.source = source
        self.code = code
        self.status = status
        self.retry_after = retry_after


class SearchClient(Protocol):
    """A scholarly search source."""

    @property
    def name(self) -> SourceName: ...

    async def search(self, query: SearchQuery) -> list[PaperMeta]: ...


class SourceClient:
    """Base for API clients: injected httpx client and rate limiter, retries, error mapping."""

    @property
    def name(self) -> str:
        """The source's name: its rate-limit bucket and the prefix of its errors."""
        raise NotImplementedError

    def __init__(
        self,
        http: httpx.AsyncClient,
        limiter: RateLimiter,
        *,
        retry: RetryPolicy = DEFAULT_RETRY,
    ) -> None:
        self._http = http
        self._limiter = limiter
        self._retry = retry

    def _gate(self) -> AbstractAsyncContextManager[None]:
        return throttled(self._limiter, self.name)

    async def _get(
        self,
        url: str,
        *,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
        allow: Iterable[int] = (),
    ) -> httpx.Response:
        """GET with retries; raises SourceError unless the status is 2xx or in ``allow``."""
        try:
            response = await request(
                self._http,
                "GET",
                url,
                params=params,
                headers=headers,
                gate=self._gate,
                retry=self._retry,
            )
        except httpx.RequestError as exc:
            raise SourceError(self.name, "source.network", type(exc).__name__) from exc
        if response.status_code == 429:
            raise self._rate_limit_error(response)
        if not response.is_success and response.status_code not in set(allow):
            raise SourceError(
                self.name,
                "source.http_status",
                f"HTTP {response.status_code}",
                status=response.status_code,
            )
        return response

    def _rate_limit_error(self, response: httpx.Response) -> SourceError:
        """The error for a 429 that outlasted the retries."""
        return SourceError(
            self.name,
            "source.rate_limited",
            status=429,
            retry_after=retry_after_seconds(response),
        )

    def _json(self, response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise SourceError(self.name, "source.bad_response", "not JSON") from exc
        if not isinstance(payload, dict):
            raise SourceError(self.name, "source.bad_response", "not a JSON object")
        return payload


def as_dict(value: object) -> dict[str, Any]:
    """value if it is a JSON object, else an empty one: sources omit or null fields freely."""
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def text_or_none(value: object) -> str | None:
    """A string with whitespace collapsed, or None for anything empty or not a string."""
    if not isinstance(value, str):
        return None
    return " ".join(value.split()) or None


def strip_markup(value: object) -> str | None:
    """Plain text from an HTML or JATS fragment (Crossref abstracts are JATS XML)."""
    if not isinstance(value, str):
        return None
    return text_or_none(html.unescape(_TAG.sub(" ", value)))


def int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def year_or_none(value: object) -> int | None:
    """A plausible publication year from an int or a date string ("2023-01-17T...")."""
    if isinstance(value, str):
        match = _YEAR.match(value)
        value = int(match.group(1)) if match else None
    year = int_or_none(value)
    return year if year is not None and 1000 <= year <= 2100 else None


def https_or_none(value: object) -> str | None:
    """value if it is an https URL (landing pages are kept for people only when https)."""
    text = text_or_none(value)
    return text if text is not None and " " not in text and is_https_url(text) else None


def pdf_candidate(value: object, source: OaSource) -> OaCandidate | None:
    """An open-access candidate from a PDF link, upgrading http to https (the fetcher refuses
    plain http; most repositories serve both), or None if the link is unusable."""
    url = text_or_none(value)
    if url is None or " " in url:
        return None
    if url.startswith("http://"):
        url = "https://" + url.removeprefix("http://")
    try:
        return OaCandidate(url=url, source=source)
    except ValueError:
        return None


def unique_candidates(candidates: Iterable[OaCandidate | None]) -> list[OaCandidate]:
    seen: set[str] = set()
    found: list[OaCandidate] = []
    for candidate in candidates:
        if candidate is not None and candidate.url not in seen:
            seen.add(candidate.url)
            found.append(candidate)
    return found


def landing_url(doi: str | None, *pages: object) -> str | None:
    """The page people should open: the DOI resolver when there is a DOI, else the first https
    landing page the source gave."""
    if doi:
        return f"https://doi.org/{doi}"
    for page in pages:
        url = https_or_none(page)
        if url:
            return url
    return None


def build_paper(source: str, fields: dict[str, Any]) -> PaperMeta | None:
    """A validated PaperMeta, or None (logged) when a source record is unusable; one odd record
    should not sink a whole result page."""
    try:
        return PaperMeta.model_validate(fields)
    except ValueError as exc:
        logger.warning("skipped a %s record: %s", source, exc)
        return None

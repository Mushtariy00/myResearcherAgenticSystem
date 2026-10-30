"""The open-access waterfall: which links may serve a paper's PDF, and trying them in order.

Order: arXiv, PMC (the Cloud Service, then Europe PMC), Unpaywall, OpenAlex, Semantic Scholar,
CORE. Within the PMC tier the Cloud Service goes first: it is NLM's route for programmatic
access, while Europe PMC's website answered automated requests with 403 in the October 2026
live check. arXiv and PMC links follow from ids and the others come with the search metadata,
so they cost nothing to list. Unpaywall and CORE need an API call per paper, so ``resolve``
asks them only after every cheaper candidate has failed. Sci-Hub, Google Scholar, ResearchGate
and publisher pages are never used.
"""

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from contextlib import AbstractAsyncContextManager, nullcontext
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlsplit

from agentic_scholarly.clients import arxiv, europepmc, pmc
from agentic_scholarly.clients.base import SourceError
from agentic_scholarly.clients.core import CoreClient
from agentic_scholarly.clients.unpaywall import UnpaywallClient
from agentic_scholarly.fetch import FetchedPdf, FetchError
from agentic_scholarly.ids import normalize_arxiv_id
from agentic_scholarly.models import OA_SOURCES, OaCandidate, PaperMeta
from agentic_scholarly.pdf import InvalidPdf, validate_pdf
from agentic_scholarly.ratelimit import Mutex, RateLimiter, throttled

# Shadow libraries and sites whose terms forbid automated downloads.
_BLOCKED_HOSTS: Final = ("sci-hub", "scihub", "libgen", "researchgate.net", "scholar.google")

PdfFetch = Callable[[str], Awaitable[FetchedPdf]]


@dataclass(frozen=True, slots=True)
class Attempt:
    """One candidate tried: ``error`` is the failure code, or None for the one that worked."""

    candidate: OaCandidate
    error: str | None = None


@dataclass(frozen=True, slots=True)
class Resolution:
    """The waterfall's outcome: the first valid PDF (or none), and everything tried."""

    pdf: FetchedPdf | None
    candidate: OaCandidate | None
    attempts: tuple[Attempt, ...]
    lookup_errors: tuple[str, ...] = ()


def candidates(paper: PaperMeta) -> list[OaCandidate]:
    """The paper's PDF links in waterfall order, without duplicates or blocked hosts."""
    derived: list[OaCandidate] = []
    if paper.arxiv_id:
        derived.append(OaCandidate(url=arxiv.pdf_url(paper.arxiv_id), source="arxiv"))
    if paper.pmcid:
        derived += [pmc.pdf_candidate(paper.pmcid), europepmc.pdf_candidate(paper.pmcid)]
    # sorted() is stable: derived links lead within their source.
    ordered = sorted([*derived, *paper.oa_candidates], key=lambda c: OA_SOURCES.index(c.source))
    return _unique(candidate for candidate in ordered if not _blocked(candidate.url))


async def resolve(
    paper: PaperMeta,
    fetch: PdfFetch,
    *,
    unpaywall: UnpaywallClient | None = None,
    core: CoreClient | None = None,
    limiter: RateLimiter | None = None,
    arxiv_mutex: Mutex | None = None,
) -> Resolution:
    """Try the paper's candidates in order and return the first PDF that PDFium opens.

    ``fetch`` downloads one URL (``functools.partial(fetch_pdf, client=safe_client)``). With a
    limiter, arXiv PDFs take tokens from the arXiv bucket (and hold ``arxiv_mutex``), since
    arXiv's request limit covers its whole site.
    """
    tried: set[str] = set()
    attempts: list[Attempt] = []
    lookup_errors: list[str] = []

    async def first_valid(found: Iterable[OaCandidate]) -> Resolution | None:
        for candidate in found:
            key = _url_key(candidate.url)
            if key in tried or _blocked(candidate.url):
                continue
            tried.add(key)
            pdf, error = await _try(candidate, fetch, limiter, arxiv_mutex)
            attempts.append(Attempt(candidate, error))
            if pdf is not None:
                return Resolution(pdf, candidate, tuple(attempts), tuple(lookup_errors))
        return None

    found = await first_valid(candidates(paper))
    if found is None and unpaywall is not None and unpaywall.enabled and paper.doi:
        found = await first_valid(await _lookup(unpaywall.oa_for_doi(paper.doi), lookup_errors))
    if found is None and core is not None and core.enabled:
        lookup = core.oa_for_title(paper.title, year=paper.year)
        found = await first_valid(await _lookup(lookup, lookup_errors))
    return found or Resolution(None, None, tuple(attempts), tuple(lookup_errors))


async def _lookup(lookup: Awaitable[list[OaCandidate]], errors: list[str]) -> list[OaCandidate]:
    try:
        return await lookup
    except SourceError as exc:
        errors.append(f"{exc.source}:{exc.code}")
        return []


async def _try(
    candidate: OaCandidate,
    fetch: PdfFetch,
    limiter: RateLimiter | None,
    arxiv_mutex: Mutex | None,
) -> tuple[FetchedPdf | None, str | None]:
    gate: AbstractAsyncContextManager[None] = (
        throttled(limiter, "arxiv", arxiv_mutex)
        if limiter is not None and candidate.source == "arxiv"
        else nullcontext()
    )
    try:
        async with gate:
            pdf = await fetch(candidate.url)
    except FetchError as exc:
        return None, exc.code
    try:
        # PDFium is CPU-bound and serialised by a lock; keep it off the event loop.
        await asyncio.to_thread(validate_pdf, pdf.data)
    except InvalidPdf as exc:
        return None, exc.code
    return pdf, None


def _blocked(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(blocked in host for blocked in _BLOCKED_HOSTS)


def _url_key(url: str) -> str:
    """A key under which links to the same file compare equal (arXiv spells PDFs many ways)."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.").removeprefix("export.")
    path = parts.path.rstrip("/")
    if host == "arxiv.org" and path.startswith("/pdf/"):
        arxiv_id = normalize_arxiv_id(path.removeprefix("/pdf/"))
        if arxiv_id:
            return f"arxiv.org/pdf/{arxiv_id}"
    if host == "europepmc.org":
        # Europe PMC article paths ignore case (OpenAlex writes pmc123, we write PMC123).
        path = path.lower()
    return f"{host}{path}?{parts.query}"


def _unique(found: Iterable[OaCandidate]) -> list[OaCandidate]:
    seen: set[str] = set()
    unique: list[OaCandidate] = []
    for candidate in found:
        key = _url_key(candidate.url)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique

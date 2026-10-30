"""The scholarly clients one worker process shares: one HTTP pool for the APIs, rate limits kept
in Valkey for the whole lab (all users share one IP), the SSRF-guarded PDF fetcher and GROBID."""

from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Protocol

import httpx
from redis.asyncio import Redis

from agentic_scholarly.clients import (
    ArxivClient,
    CoreClient,
    CrossrefClient,
    OpenAlexClient,
    SearchClient,
    SemanticScholarClient,
    UnpaywallClient,
)
from agentic_scholarly.fetch import SafeClient, fetch_pdf
from agentic_scholarly.grobid import GrobidClient, TeiDocument
from agentic_scholarly.http import make_client
from agentic_scholarly.ratelimit import (
    Mutex,
    RateLimiter,
    ValkeyMutex,
    ValkeyRateLimiter,
    source_limits,
)
from agentic_scholarly.waterfall import PdfFetch
from agentic_worker.settings import WorkerSettings


class FullTextParser(Protocol):
    """GROBID, or a stand-in for it."""

    async def is_alive(self) -> bool: ...

    async def fulltext(self, pdf: bytes) -> TeiDocument: ...


@dataclass(frozen=True)
class Scholarly:
    search: Mapping[str, SearchClient]  # by RunConfig source name
    unpaywall: UnpaywallClient
    core: CoreClient
    fetch: PdfFetch  # fetch_pdf with the SafeClient
    grobid: FullTextParser
    limiter: RateLimiter
    arxiv_mutex: Mutex
    data_dir: Path  # PDFs live under <data_dir>/papers
    clients: tuple[httpx.AsyncClient, ...] = ()  # closed by aclose

    async def aclose(self) -> None:
        for client in self.clients:
            await client.aclose()


def open_scholarly(settings: WorkerSettings, valkey: Redis) -> Scholarly:
    contact = settings.contact_email or None
    openalex_key = settings.openalex_api_key.get_secret_value() or None
    # make_client hands the contact to user_agent, which takes None for a User-Agent without a
    # mailto; only make_client's annotation insists on a string.
    http = make_client(contact)
    # URLs found in metadata go through the SSRF guard. GROBID gets the plain client: its
    # private address is one the guard refuses.
    safe = SafeClient(contact=contact)
    limiter = ValkeyRateLimiter(valkey, source_limits(openalex_key=openalex_key is not None))
    arxiv_mutex = ValkeyMutex(valkey, "arxiv")
    return Scholarly(
        search={
            "arxiv": ArxivClient(http, limiter, mutex=arxiv_mutex),
            "openalex": OpenAlexClient(http, limiter, api_key=openalex_key),
            "semantic_scholar": SemanticScholarClient(
                http, limiter, api_key=settings.s2_api_key.get_secret_value() or None
            ),
            "crossref": CrossrefClient(http, limiter),
        },
        unpaywall=UnpaywallClient(http, limiter, email=contact),
        core=CoreClient(http, limiter, api_key=settings.core_api_key.get_secret_value() or None),
        fetch=partial(fetch_pdf, client=safe),
        grobid=GrobidClient(settings.grobid_url, http),
        limiter=limiter,
        arxiv_mutex=arxiv_mutex,
        data_dir=settings.data_dir,
        clients=(http, safe),
    )

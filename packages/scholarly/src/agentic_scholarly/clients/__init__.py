"""Clients for scholarly sources.

Search clients (``name`` + ``search(query)``): OpenAlex, Semantic Scholar, arXiv, Crossref.
Open-access lookups: Unpaywall (DOI), CORE (title), Europe PMC and the PMC Cloud Service
(PMCID, no request needed). Every client takes its httpx client and rate limiter by injection.
"""

from agentic_scholarly.clients.arxiv import ArxivClient
from agentic_scholarly.clients.base import SearchClient, SourceError
from agentic_scholarly.clients.core import CoreClient
from agentic_scholarly.clients.crossref import CrossrefClient
from agentic_scholarly.clients.openalex import OpenAlexClient
from agentic_scholarly.clients.semantic_scholar import SemanticScholarClient
from agentic_scholarly.clients.unpaywall import UnpaywallClient

__all__ = [
    "ArxivClient",
    "CoreClient",
    "CrossrefClient",
    "OpenAlexClient",
    "SearchClient",
    "SemanticScholarClient",
    "SourceError",
    "UnpaywallClient",
]

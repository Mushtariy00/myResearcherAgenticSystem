"""The normalised paper record every source client produces, plus the search request."""

from collections.abc import Callable
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agentic_scholarly.ids import (
    arxiv_id_from_doi,
    normalize_arxiv_id,
    normalize_doi,
    normalize_openalex_id,
    normalize_pmcid,
    normalize_s2_id,
)

SourceName = Literal["openalex", "semantic_scholar", "arxiv", "crossref"]
SOURCE_NAMES: tuple[SourceName, ...] = ("openalex", "semantic_scholar", "arxiv", "crossref")

# Where an open-access PDF link came from; the waterfall tries them in OA_SOURCES order.
OaSource = Literal["arxiv", "europepmc", "pmc", "unpaywall", "openalex", "semantic_scholar", "core"]
OA_SOURCES: tuple[OaSource, ...] = (
    "arxiv",
    "pmc",
    "europepmc",
    "unpaywall",
    "openalex",
    "semantic_scholar",
    "core",
)


def is_https_url(value: str) -> bool:
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return parts.scheme == "https" and bool(parts.hostname)


def _one_line(value: str) -> str:
    return " ".join(value.split())


def _normalized(value: object, normalize: Callable[[object], str | None], label: str) -> object:
    if value is None:
        return None
    normalized = normalize(value)
    if normalized is None:
        raise ValueError(f"not a valid {label}: {value!r}")
    return normalized


class SearchQuery(BaseModel):
    """One search request: free text, an optional publication-year range and a result limit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1, max_length=500)
    year_from: int | None = Field(default=None, ge=1800, le=2100)
    year_to: int | None = Field(default=None, ge=1800, le=2100)
    limit: int = Field(default=25, ge=1, le=100)

    @field_validator("text")
    @classmethod
    def _text(cls, value: str) -> str:
        text = _one_line(value)
        if not text:
            raise ValueError("the query text is empty")
        return text

    @model_validator(mode="after")
    def _years_in_order(self) -> Self:
        if (
            self.year_from is not None
            and self.year_to is not None
            and self.year_from > self.year_to
        ):
            raise ValueError("year_from is after year_to")
        return self


class SourceHit(BaseModel):
    """Which query found the paper in which source, and at which position (1 is the top hit)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: SourceName
    query: str
    position: int = Field(ge=1)


class OaCandidate(BaseModel):
    """A link that may serve the paper's open-access PDF, and the service that gave it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    url: str = Field(max_length=2048)
    source: OaSource

    @field_validator("url")
    @classmethod
    def _https(cls, value: str) -> str:
        # The fetcher only speaks https; refusing other schemes here keeps them out of the queue.
        if not is_https_url(value):
            raise ValueError("an open-access candidate must be an https URL")
        return value


class PaperMeta(BaseModel):
    """A paper as one or more sources describe it.

    Identifiers are canonical: ``doi`` lower case without a URL prefix, ``arxiv_id`` without a
    version, ``openalex_id`` a W id, ``pmcid`` with its PMC prefix. ``url`` is an https landing
    page for people, never a PDF link; PDF links live in ``oa_candidates``.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    authors: list[str] = Field(default_factory=list)
    year: int | None = Field(default=None, ge=1000, le=2100)
    venue: str | None = None
    abstract: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    s2_id: str | None = None
    openalex_id: str | None = None
    pmcid: str | None = None
    citation_count: int | None = Field(default=None, ge=0)
    url: str | None = None
    oa_candidates: list[OaCandidate] = Field(default_factory=list)
    retracted: bool = False
    hits: list[SourceHit] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        title = _one_line(value)
        if not title:
            raise ValueError("a paper needs a title")
        return title

    @field_validator("authors")
    @classmethod
    def _authors(cls, value: list[str]) -> list[str]:
        return [name for name in map(_one_line, value) if name]

    @field_validator("venue", "abstract")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _one_line(value) or None

    @field_validator("doi", mode="before")
    @classmethod
    def _doi(cls, value: object) -> object:
        return _normalized(value, normalize_doi, "DOI")

    @field_validator("arxiv_id", mode="before")
    @classmethod
    def _arxiv_id(cls, value: object) -> object:
        return _normalized(value, normalize_arxiv_id, "arXiv id")

    @field_validator("s2_id", mode="before")
    @classmethod
    def _s2_id(cls, value: object) -> object:
        return _normalized(value, normalize_s2_id, "Semantic Scholar id")

    @field_validator("openalex_id", mode="before")
    @classmethod
    def _openalex_id(cls, value: object) -> object:
        return _normalized(value, normalize_openalex_id, "OpenAlex work id")

    @field_validator("pmcid", mode="before")
    @classmethod
    def _pmcid(cls, value: object) -> object:
        return _normalized(value, normalize_pmcid, "PMCID")

    @field_validator("url")
    @classmethod
    def _landing_page(cls, value: str | None) -> str | None:
        if value is not None and not is_https_url(value):
            raise ValueError("the landing page must be an https URL")
        return value

    @model_validator(mode="after")
    def _arxiv_from_doi(self) -> Self:
        # arXiv's own DOIs (10.48550/arXiv.*) carry the arXiv id; keep both keys for merging.
        if self.arxiv_id is None:
            self.arxiv_id = arxiv_id_from_doi(self.doi)
        return self

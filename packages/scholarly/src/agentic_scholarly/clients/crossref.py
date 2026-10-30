"""Crossref works: search, DOI lookup and retraction detection.

Crossref records a retraction twice: the notice carries ``update-to`` pointing at the retracted
DOI, and the retracted work carries ``updated-by`` pointing back. Each entry names its
``source``: the publisher, or Retraction Watch (whose entries add a ``record-id`` into its
database). Requests carry the contact mailto in the User-Agent, which puts them in Crossref's
polite pool.
"""

import re
from typing import Any, Final, Literal
from urllib.parse import quote

from agentic_scholarly.clients.base import (
    SourceClient,
    as_dict,
    as_list,
    build_paper,
    int_or_none,
    landing_url,
    strip_markup,
    text_or_none,
    year_or_none,
)
from agentic_scholarly.ids import arxiv_id_from_doi, normalize_arxiv_id, normalize_doi
from agentic_scholarly.models import PaperMeta, SearchQuery, SourceHit

API_URL: Final = "https://api.crossref.org/works"
SELECT: Final = ",".join(
    (
        "DOI",
        "title",
        "author",
        "issued",
        "container-title",
        "abstract",
        "is-referenced-by-count",
        "type",
        "relation",
        "update-to",
        "updated-by",
    )
)
# Update types that withdraw a paper's findings, in whole or in part.
RETRACTION_TYPES: Final = frozenset({"retraction", "partial_retraction", "withdrawal", "removal"})
# Crossref also indexes components, datasets, peer reviews and front matter; search papers only.
_PAPER_TYPES: Final = (
    "journal-article",
    "proceedings-article",
    "posted-content",
    "book-chapter",
)
_ABSTRACT_HEADING = re.compile(r"^(?:abstract|summary)\b[\s:.\-]*", re.IGNORECASE)


class CrossrefClient(SourceClient):
    """Search Crossref, look up a DOI, and check whether a DOI has been retracted."""

    @property
    def name(self) -> Literal["crossref"]:
        return "crossref"

    async def search(self, query: SearchQuery) -> list[PaperMeta]:
        filters = [f"type:{kind}" for kind in _PAPER_TYPES]
        if query.year_from is not None:
            filters.append(f"from-pub-date:{query.year_from}")
        if query.year_to is not None:
            filters.append(f"until-pub-date:{query.year_to}")
        params: dict[str, str | int] = {
            "query": query.text,
            "rows": query.limit,
            "select": SELECT,
            "filter": ",".join(filters),
        }
        response = await self._get(API_URL, params=params)
        items = as_list(as_dict(self._json(response).get("message")).get("items"))
        papers = (
            parse_work(as_dict(item), query.text, position)
            for position, item in enumerate(items, start=1)
            if not is_retraction_notice(as_dict(item))
        )
        return [paper for paper in papers if paper is not None]

    async def lookup(self, doi: str) -> PaperMeta | None:
        """The Crossref record of a DOI (``retracted`` set from ``updated-by``), or None."""
        response = await self._get(_work_url(doi), allow=(404,))
        if response.status_code == 404:
            return None
        return parse_work(as_dict(self._json(response).get("message")))

    async def is_retracted(self, doi: str) -> bool:
        """Whether any notice updates doi with a retraction (Crossref's ``updates`` filter)."""
        target = _doi(doi)
        params: dict[str, str | int] = {
            "filter": f"updates:{target}",
            "select": "DOI,update-to",
            "rows": 50,
        }
        response = await self._get(API_URL, params=params)
        notices = as_list(as_dict(self._json(response).get("message")).get("items"))
        return any(target in retraction_targets(as_dict(notice)) for notice in notices)


def retraction_targets(item: dict[str, Any]) -> set[str]:
    """DOIs that this record (a notice) retracts, from its ``update-to`` entries."""
    targets: set[str] = set()
    for raw in as_list(item.get("update-to")):
        update = as_dict(raw)
        target = normalize_doi(update.get("DOI"))
        if target and update.get("type") in RETRACTION_TYPES:
            targets.add(target)
    return targets


def is_retraction_notice(item: dict[str, Any]) -> bool:
    """A notice that retracts another work: a search hit worth dropping, it is not a paper."""
    own = normalize_doi(item.get("DOI"))
    return any(target != own for target in retraction_targets(item))


def is_retracted_work(item: dict[str, Any]) -> bool:
    """Whether a work's ``updated-by`` lists a retraction (publisher or Retraction Watch)."""
    return any(
        as_dict(update).get("type") in RETRACTION_TYPES
        for update in as_list(item.get("updated-by"))
    )


def parse_work(
    item: dict[str, Any], query: str | None = None, position: int | None = None
) -> PaperMeta | None:
    # Titles keep JATS inline markup from the publisher (<i>, <scp>, &amp;).
    titles = [strip_markup(title) for title in as_list(item.get("title"))]
    title = next((title for title in titles if title), None)
    doi = normalize_doi(item.get("DOI"))
    if title is None or doi is None:
        return None
    venues = [text_or_none(venue) for venue in as_list(item.get("container-title"))]
    hits = (
        [SourceHit(source="crossref", query=query, position=position)]
        if query is not None and position is not None
        else []
    )
    return build_paper(
        "crossref",
        {
            "title": title,
            "authors": _authors(item),
            "year": _year(item),
            "venue": next((venue for venue in venues if venue), None),
            "abstract": _abstract(item.get("abstract")),
            "doi": doi,
            "arxiv_id": arxiv_id_from_doi(doi) or _preprint_arxiv_id(item),
            "citation_count": int_or_none(item.get("is-referenced-by-count")),
            "url": landing_url(doi),
            "retracted": is_retracted_work(item),
            "hits": hits,
        },
    )


def _doi(doi: str) -> str:
    normalized = normalize_doi(doi)
    if normalized is None:
        raise ValueError(f"not a DOI: {doi!r}")
    return normalized


def _work_url(doi: str) -> str:
    # DOIs may contain characters that are special in a URL path (#, ?, ;); slashes stay.
    return f"{API_URL}/{quote(_doi(doi), safe='/')}"


def _authors(item: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for raw in as_list(item.get("author")):
        author = as_dict(raw)
        parts = [text_or_none(author.get("given")), text_or_none(author.get("family"))]
        name = " ".join(part for part in parts if part) or text_or_none(author.get("name"))
        if name:
            names.append(name)
    return names


def _year(item: dict[str, Any]) -> int | None:
    parts = as_list(as_dict(item.get("issued")).get("date-parts"))
    first = as_list(parts[0]) if parts else []
    return year_or_none(first[0]) if first else None


def _abstract(value: object) -> str | None:
    text = strip_markup(value)
    if text is None:
        return None
    return _ABSTRACT_HEADING.sub("", text, count=1).strip() or None


def _preprint_arxiv_id(item: dict[str, Any]) -> str | None:
    """The arXiv id of the work's preprint, when the publisher linked one."""
    relations = as_dict(item.get("relation"))
    for name in ("has-preprint", "is-preprint-of"):
        for raw in as_list(relations.get(name)):
            relation = as_dict(raw)
            value = relation.get("id")
            if relation.get("id-type") == "arxiv":
                arxiv_id = normalize_arxiv_id(value)
            else:
                arxiv_id = arxiv_id_from_doi(normalize_doi(value))
            if arxiv_id:
                return arxiv_id
    return None

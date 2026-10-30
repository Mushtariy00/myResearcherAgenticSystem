"""One record per paper from the hits of every query and source.

Two records describe the same paper when, in this order of trust, they share a DOI, an arXiv
id or a Semantic Scholar id, or have the same normalised title and first author's surname with
publication years at most one apart. A weaker key never joins records whose stronger ids
disagree (two different DOIs: a conference paper and its journal extension stay apart). arXiv's
own DOIs (10.48550/arXiv.*) count as arXiv ids, so a preprint merges with its published version.

The merged record keeps every id, candidate and hit, the longest abstract and author list, the
highest citation count, and the rest from its most complete member.
"""

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

from agentic_scholarly.ids import arxiv_id_from_doi, normalize_title
from agentic_scholarly.models import PaperMeta

_NAME_SUFFIXES = frozenset({"jr", "sr", "ii", "iii", "iv"})
# Short generic titles ("Introduction", "Editorial") recur by the same author every year.
_MIN_TITLE_CHARS = 12


@dataclass
class _Group:
    members: list[int]
    dois: set[str] = field(default_factory=set)
    arxiv_ids: set[str] = field(default_factory=set)
    s2_ids: set[str] = field(default_factory=set)

    def conflicts_with(self, other: "_Group") -> bool:
        return any(
            mine and theirs and not mine & theirs
            for mine, theirs in (
                (self.dois, other.dois),
                (self.arxiv_ids, other.arxiv_ids),
                (self.s2_ids, other.s2_ids),
            )
        )

    def absorb(self, other: "_Group") -> None:
        self.members.extend(other.members)
        self.dois |= other.dois
        self.arxiv_ids |= other.arxiv_ids
        self.s2_ids |= other.s2_ids


def merge(papers: Iterable[PaperMeta]) -> list[PaperMeta]:
    """De-duplicated papers, in the order each paper was first seen."""
    records = list(papers)
    parent = list(range(len(records)))
    groups = {index: _group(index, paper) for index, paper in enumerate(records)}

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def join(first: int, second: int, *, guarded: bool) -> None:
        a, b = root(first), root(second)
        if a == b or (guarded and groups[a].conflicts_with(groups[b])):
            return
        keep, drop = min(a, b), max(a, b)
        parent[drop] = keep
        groups[keep].absorb(groups.pop(drop))

    # A shared DOI is decisive; the weaker keys check for contradicting ids first.
    for key, guarded in ((_doi_key, False), (_arxiv_key, True), (_s2_key, True)):
        for first, second in _sharing(records, key):
            join(first, second, guarded=guarded)
    buckets: dict[tuple[str, str], list[int]] = {}
    for index, paper in enumerate(records):
        fuzzy = _fuzzy_key(paper)
        if fuzzy is not None:
            buckets.setdefault(fuzzy, []).append(index)
    for indexes in buckets.values():
        for offset, first in enumerate(indexes):
            for second in indexes[offset + 1 :]:
                if _years_close(records[first].year, records[second].year):
                    join(first, second, guarded=True)

    return [
        _combine([records[member] for member in sorted(groups[index].members)])
        for index in sorted(groups)
    ]


def first_author_surname(authors: list[str]) -> str:
    """The first author's surname, normalised ("Vaswani, A." and "Ashish Vaswani" agree)."""
    if not authors:
        return ""
    name = authors[0]
    if "," in name:
        return normalize_title(name.split(",", 1)[0])
    words = normalize_title(name).split()
    while len(words) > 1 and words[-1] in _NAME_SUFFIXES:
        words.pop()
    return words[-1] if words else ""


def _group(index: int, paper: PaperMeta) -> _Group:
    return _Group(
        members=[index],
        dois=set(_doi_key(paper)),
        arxiv_ids=set(_arxiv_key(paper)),
        s2_ids=set(_s2_key(paper)),
    )


def _doi_key(paper: PaperMeta) -> list[str]:
    # arXiv DOIs are matched as arXiv ids instead.
    return [paper.doi] if paper.doi and arxiv_id_from_doi(paper.doi) is None else []


def _arxiv_key(paper: PaperMeta) -> list[str]:
    return [paper.arxiv_id] if paper.arxiv_id else []


def _s2_key(paper: PaperMeta) -> list[str]:
    return [paper.s2_id] if paper.s2_id else []


def _sharing(
    records: list[PaperMeta], key: Callable[[PaperMeta], list[str]]
) -> Iterator[tuple[int, int]]:
    """Pairs (first record with a key value, later record with the same value)."""
    first_seen: dict[str, int] = {}
    for index, paper in enumerate(records):
        for value in key(paper):
            if value in first_seen:
                yield first_seen[value], index
            else:
                first_seen[value] = index


def _fuzzy_key(paper: PaperMeta) -> tuple[str, str] | None:
    title = normalize_title(paper.title)
    if len(title) < _MIN_TITLE_CHARS or " " not in title:
        return None
    return title, first_author_surname(paper.authors)


def _years_close(first: int | None, second: int | None) -> bool:
    return first is None or second is None or abs(first - second) <= 1


def _richness(paper: PaperMeta) -> int:
    filled = [paper.doi, paper.year, paper.venue, paper.abstract, paper.citation_count]
    published = paper.doi is not None and arxiv_id_from_doi(paper.doi) is None
    return sum(value is not None for value in filled) + bool(paper.authors) + published


def _is_preprint_venue(venue: str) -> bool:
    # arXiv, bioRxiv, medRxiv, ChemRxiv...: a published venue says more about the paper.
    return "rxiv" in venue.casefold()


def _combine(group: list[PaperMeta]) -> PaperMeta:
    if len(group) == 1:
        return group[0]
    # Stable: among equally complete records, the first seen leads.
    ranked = sorted(group, key=_richness, reverse=True)

    def first(attribute: str) -> Any:
        return next((value for p in ranked if (value := getattr(p, attribute)) is not None), None)

    published_doi = next(
        (p.doi for p in ranked if p.doi and arxiv_id_from_doi(p.doi) is None), None
    )
    doi = published_doi or first("doi")
    venues = [p.venue for p in ranked if p.venue]
    citations = [p.citation_count for p in group if p.citation_count is not None]
    fields: dict[str, Any] = {
        "title": ranked[0].title,
        "authors": max((p.authors for p in ranked), key=len),
        "year": first("year"),
        "venue": next((v for v in venues if not _is_preprint_venue(v)), first("venue")),
        "abstract": max((p.abstract for p in group if p.abstract), key=len, default=None),
        "doi": doi,
        "arxiv_id": first("arxiv_id"),
        "s2_id": first("s2_id"),
        "openalex_id": first("openalex_id"),
        "pmcid": first("pmcid"),
        "citation_count": max(citations, default=None),
        "url": f"https://doi.org/{doi}" if doi else first("url"),
        "oa_candidates": list(dict.fromkeys(c for p in group for c in p.oa_candidates)),
        "retracted": any(p.retracted for p in group),
        "hits": list(dict.fromkeys(hit for p in group for hit in p.hits)),
    }
    return PaperMeta.model_validate(fields)

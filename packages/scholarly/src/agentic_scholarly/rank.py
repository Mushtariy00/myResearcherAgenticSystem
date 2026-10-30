"""Order merged papers for screening by a transparent score.

    score = 0.30 * position + 0.35 * match + 0.20 * citations + 0.15 * recency

Each component lies in [0, 1]:

- position: 1 / sqrt(p) for the best position p any source gave the paper (1 -> 1.0,
  4 -> 0.5, 25 -> 0.2); 0 without hits.
- match: for the best-matching query, half the share of its terms found in the title plus half
  the share found in the title or abstract (light plural stemming on both sides).
- citations: citations per year since publication, log-scaled so that 100 a year scores 1.0;
  a paper without a year counts as ten years old.
- recency: 1.0 for the newest year of the range, falling linearly to 0 at the oldest (a
  ten-year window when the range has no start); 0 outside the range or without a year.

Retracted papers sort after all others; ties keep the input order.
"""

import math
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Final

from agentic_scholarly.models import PaperMeta, SearchQuery
from agentic_scholarly.terms import stems

WEIGHTS: Final = {"position": 0.30, "match": 0.35, "citations": 0.20, "recency": 0.15}
_FULL_CITATION_RATE: Final = 100.0
_UNDATED_AGE: Final = 10
_OPEN_WINDOW: Final = 10


def rank(
    papers: Iterable[PaperMeta],
    queries: Iterable[str | SearchQuery],
    year_from: int | None = None,
    year_to: int | None = None,
    *,
    now_year: int | None = None,
) -> list[PaperMeta]:
    """Papers best first (see the module docstring for the score)."""
    records = list(papers)
    query_terms = _query_terms(queries)
    current = now_year if now_year is not None else datetime.now(UTC).year
    scored = sorted(
        (paper.retracted, -score(paper, query_terms, year_from, year_to, now_year=current), index)
        for index, paper in enumerate(records)
    )
    return [records[index] for _, _, index in scored]


def score(
    paper: PaperMeta,
    query_terms: list[set[str]],
    year_from: int | None,
    year_to: int | None,
    *,
    now_year: int,
) -> float:
    """The weighted score of one paper; query_terms holds the stemmed terms of each query."""
    return (
        WEIGHTS["position"] * position_score(paper)
        + WEIGHTS["match"] * match_score(paper, query_terms)
        + WEIGHTS["citations"] * citation_score(paper, now_year)
        + WEIGHTS["recency"] * recency_score(paper.year, year_from, year_to, now_year)
    )


def position_score(paper: PaperMeta) -> float:
    best = min((hit.position for hit in paper.hits), default=None)
    return 0.0 if best is None else 1 / math.sqrt(best)


def match_score(paper: PaperMeta, query_terms: list[set[str]]) -> float:
    title = stems(paper.title)
    text = title | stems(paper.abstract or "")
    shares = (
        0.5 * len(wanted & title) / len(wanted) + 0.5 * len(wanted & text) / len(wanted)
        for wanted in query_terms
        if wanted
    )
    return max(shares, default=0.0)


def citation_score(paper: PaperMeta, now_year: int) -> float:
    if not paper.citation_count:
        return 0.0
    age = max(1, now_year - paper.year + 1) if paper.year is not None else _UNDATED_AGE
    per_year = paper.citation_count / age
    return min(1.0, math.log1p(per_year) / math.log1p(_FULL_CITATION_RATE))


def recency_score(
    year: int | None, year_from: int | None, year_to: int | None, now_year: int
) -> float:
    if year is None:
        return 0.0
    newest = year_to if year_to is not None else now_year
    oldest = year_from if year_from is not None else newest - _OPEN_WINDOW
    if year_to is None and year > newest:
        return 1.0
    if not oldest <= year <= newest:
        return 0.0
    if newest == oldest:
        return 1.0
    return (year - oldest) / (newest - oldest)


def _query_terms(queries: Iterable[str | SearchQuery]) -> list[set[str]]:
    return [stems(query.text if isinstance(query, SearchQuery) else query) for query in queries]

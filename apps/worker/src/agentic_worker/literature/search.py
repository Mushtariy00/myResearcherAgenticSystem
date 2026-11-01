"""The search step: every plan query in every chosen source, merged and ranked.

A source that fails (rate limited, out of quota, down) is skipped for the rest of the step and
reported; the papers it returned before failing still count.
"""

import asyncio
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from agentic_core.schemas import ResearchPlan, RunConfig
from agentic_scholarly.clients import SearchClient, SourceError
from agentic_scholarly.merge import merge
from agentic_scholarly.models import PaperMeta, SearchQuery
from agentic_scholarly.rank import rank, score
from agentic_scholarly.terms import stems

log = logging.getLogger(__name__)

RESULTS_PER_QUERY = 25
_MAX_QUERY_CHARS = 500  # SearchQuery's limit
_MIN_YEAR = 1900  # PaperRef's


@dataclass(frozen=True)
class SearchResult:
    papers: list[PaperMeta]  # merged, best first, complete enough for a PaperRef
    scores: list[float]  # agentic_scholarly.rank's score of each paper
    sources: list[str]  # the sources asked
    failed: dict[str, str]  # source -> error code (SourceError.code)
    answered: dict[str, int]  # source -> the queries it answered (all, unless it failed)
    found: int  # papers after merging
    incomplete: int  # of those, left out: no authors, abstract or usable year


def complete(paper: PaperMeta) -> bool:
    """Whether a PaperRef can be built from the record."""
    return bool(
        paper.authors and paper.abstract and paper.year is not None and paper.year >= _MIN_YEAR
    )


async def search(
    clients: Mapping[str, SearchClient], plan: ResearchPlan, config: RunConfig
) -> SearchResult:
    sources = [source for source in config.sources if source in clients]
    queries = [
        SearchQuery(
            text=" ".join(text.split())[:_MAX_QUERY_CHARS],
            year_from=config.year_from,
            year_to=config.year_to,
            limit=RESULTS_PER_QUERY,
        )
        for text in plan.queries
    ]
    # Sources run side by side; each one's queries in turn, under its rate limit.
    results = await asyncio.gather(*(_ask(clients[source], queries) for source in sources))
    failed = {
        source: error for source, (_, error, _) in zip(sources, results, strict=True) if error
    }
    answered = {source: count for source, (_, _, count) in zip(sources, results, strict=True)}
    merged = merge(paper for papers, _, _ in results for paper in papers)
    now_year = datetime.now(UTC).year
    ranked = rank(merged, queries, config.year_from, config.year_to, now_year=now_year)
    kept = [paper for paper in ranked if complete(paper)]
    terms = [stems(query.text) for query in queries]
    return SearchResult(
        papers=kept,
        scores=[
            score(paper, terms, config.year_from, config.year_to, now_year=now_year)
            for paper in kept
        ],
        sources=sources,
        failed=failed,
        answered=answered,
        found=len(merged),
        incomplete=len(merged) - len(kept),
    )


async def _ask(
    client: SearchClient, queries: Sequence[SearchQuery]
) -> tuple[list[PaperMeta], str | None, int]:
    """What the source found, the error it failed with (None if it did not), and the queries it
    answered before that."""
    found: list[PaperMeta] = []
    for answered, query in enumerate(queries):
        try:
            found += await client.search(query)
        except SourceError as exc:
            log.warning("source %s failed on %r: %s", client.name, query.text, exc)
            return found, exc.code, answered
    return found, None, len(queries)

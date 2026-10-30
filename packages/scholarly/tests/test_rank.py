import math
from typing import Any

import pytest

from agentic_scholarly.models import PaperMeta, SearchQuery
from agentic_scholarly.rank import (
    citation_score,
    match_score,
    position_score,
    rank,
    recency_score,
)
from agentic_scholarly.terms import stems


def paper(**fields: Any) -> PaperMeta:
    fields.setdefault("title", "A paper")
    return PaperMeta.model_validate(fields)


def hits(*positions: int) -> list[dict[str, Any]]:
    return [{"source": "openalex", "query": "q", "position": p} for p in positions]


def test_position_uses_the_best_hit() -> None:
    assert position_score(paper(hits=hits(4, 1, 9))) == 1.0
    assert position_score(paper(hits=hits(4))) == 0.5
    assert position_score(paper()) == 0.0


def test_match_counts_title_terms_double() -> None:
    queries = [stems("monocular depth estimation")]
    in_title = paper(title="Monocular Depth Estimation with Transformers")
    in_abstract = paper(title="A new method", abstract="We study monocular depth estimation.")
    partly = paper(title="Depth networks", abstract="Stereo matching.")
    assert match_score(in_title, queries) == 1.0
    assert match_score(in_abstract, queries) == 0.5
    assert match_score(partly, queries) == pytest.approx(1 / 3)
    # The best of several queries counts.
    assert match_score(partly, [*queries, stems("depth networks")]) == 1.0


def test_citations_are_per_year_and_log_scaled() -> None:
    assert citation_score(paper(citation_count=1000, year=2017), now_year=2026) == 1.0
    old = citation_score(paper(citation_count=100, year=2007), now_year=2026)
    assert old == pytest.approx(math.log1p(5) / math.log1p(100))
    assert citation_score(paper(citation_count=0, year=2020), now_year=2026) == 0.0
    assert citation_score(paper(citation_count=50), now_year=2026) == pytest.approx(
        math.log1p(5) / math.log1p(100)
    )


def test_recency_runs_over_the_requested_range() -> None:
    assert recency_score(2024, 2020, 2024, now_year=2026) == 1.0
    assert recency_score(2020, 2020, 2024, now_year=2026) == 0.0
    assert recency_score(2022, 2020, 2024, now_year=2026) == 0.5
    assert recency_score(2019, 2020, 2024, now_year=2026) == 0.0
    assert recency_score(2026, None, None, now_year=2026) == 1.0
    assert recency_score(2021, None, None, now_year=2026) == 0.5
    assert recency_score(None, 2020, 2024, now_year=2026) == 0.0


def test_rank_orders_by_score_and_puts_retractions_last() -> None:
    relevant = paper(
        title="Monocular depth estimation survey",
        year=2024,
        citation_count=300,
        hits=hits(1),
    )
    weaker = paper(title="Depth in photographs", year=2021, citation_count=5, hits=hits(12))
    unrelated = paper(title="Protein folding", year=2015, hits=hits(30))
    retracted = paper(
        title="Monocular depth estimation survey, retracted",
        year=2024,
        citation_count=900,
        hits=hits(1),
        retracted=True,
    )
    ranked = rank(
        [unrelated, retracted, weaker, relevant],
        [SearchQuery(text="monocular depth estimation"), "depth survey"],
        2020,
        2024,
        now_year=2026,
    )
    assert ranked == [relevant, weaker, unrelated, retracted]


def test_ties_keep_the_input_order() -> None:
    first = paper(title="Same")
    second = paper(title="Same")
    assert rank([first, second], ["x"], now_year=2026)[0] is first

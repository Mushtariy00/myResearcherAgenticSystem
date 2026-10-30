import pytest
from pydantic import ValidationError

from agentic_scholarly.models import OaCandidate, PaperMeta, SearchQuery, SourceHit


def test_identifiers_are_stored_canonically() -> None:
    paper = PaperMeta(
        title="  Attention   Is All\nYou Need ",
        authors=["Ashish  Vaswani", " "],
        doi="https://doi.org/10.48550/arXiv.1706.03762",
        openalex_id="https://openalex.org/W2963403868",
        pmcid="6455466",
        s2_id="204E3073870FAE3D05BCBC2F6A8E263D9B72E776",
        abstract="  ",
    )
    assert paper.title == "Attention Is All You Need"
    assert paper.authors == ["Ashish Vaswani"]
    assert paper.doi == "10.48550/arxiv.1706.03762"
    # arXiv's own DOI also gives the arXiv id, so preprint and published versions can merge.
    assert paper.arxiv_id == "1706.03762"
    assert paper.openalex_id == "W2963403868"
    assert paper.pmcid == "PMC6455466"
    assert paper.s2_id == "204e3073870fae3d05bcbc2f6a8e263d9b72e776"
    assert paper.abstract is None
    assert paper.retracted is False


@pytest.mark.parametrize(
    "fields",
    [
        {"title": " "},
        {"title": "T", "doi": "not-a-doi"},
        {"title": "T", "arxiv_id": "v2"},
        {"title": "T", "url": "http://example.org/paper"},
        {"title": "T", "citation_count": -1},
        {"title": "T", "unknown": 1},
    ],
)
def test_invalid_records_are_rejected(fields: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PaperMeta.model_validate(fields)


def test_candidates_must_be_https() -> None:
    assert OaCandidate(url="https://arxiv.org/pdf/1706.03762", source="arxiv").source == "arxiv"
    with pytest.raises(ValidationError):
        OaCandidate(url="http://arxiv.org/pdf/1706.03762", source="arxiv")
    with pytest.raises(ValidationError):
        OaCandidate(url="https://arxiv.org/pdf/1706.03762", source="scihub")  # type: ignore[arg-type]


def test_search_queries_are_bounded() -> None:
    query = SearchQuery(text="  monocular   depth ", year_from=2019, year_to=2024)
    assert query.text == "monocular depth"
    assert query.limit == 25
    with pytest.raises(ValidationError):
        SearchQuery(text="depth", year_from=2024, year_to=2019)
    with pytest.raises(ValidationError):
        SearchQuery(text="   ")
    with pytest.raises(ValidationError):
        SearchQuery(text="depth", limit=500)


def test_hits_record_query_and_position() -> None:
    hit = SourceHit(source="openalex", query="depth", position=1)
    assert hit.position == 1
    with pytest.raises(ValidationError):
        SourceHit(source="openalex", query="depth", position=0)

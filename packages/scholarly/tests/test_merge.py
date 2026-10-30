from typing import Any

from agentic_scholarly.merge import first_author_surname, merge
from agentic_scholarly.models import OaCandidate, PaperMeta, SourceHit


def paper(**fields: Any) -> PaperMeta:
    fields.setdefault("title", "Attention Is All You Need")
    return PaperMeta.model_validate(fields)


def hit(source: str, position: int, query: str = "attention") -> SourceHit:
    return SourceHit.model_validate({"source": source, "query": query, "position": position})


def test_same_doi_merges_and_unions_everything() -> None:
    from_openalex = paper(
        doi="10.1093/bib/bbx044",
        openalex_id="W2612613542",
        pmcid="PMC6455466",
        abstract="Short.",
        citation_count=2210,
        authors=["Riccardo Miotto"],
        oa_candidates=[OaCandidate(url="https://europepmc.org/a.pdf", source="openalex")],
        hits=[hit("openalex", 2)],
    )
    from_s2 = paper(
        doi="https://doi.org/10.1093/BIB/BBX044",
        s2_id="5ea0e3b0dc3b2d6e7a1bf9d16c08c2a1f2b0cf33",
        abstract="A much longer abstract that says more about the paper.",
        citation_count=2501,
        authors=["Riccardo Miotto", "Fei Wang"],
        oa_candidates=[OaCandidate(url="https://oup.example.org/b.pdf", source="semantic_scholar")],
        hits=[hit("semantic_scholar", 5), hit("semantic_scholar", 1, query="health")],
    )
    (merged,) = merge([from_openalex, from_s2])
    assert merged.doi == "10.1093/bib/bbx044"
    assert merged.openalex_id == "W2612613542"
    assert merged.s2_id == "5ea0e3b0dc3b2d6e7a1bf9d16c08c2a1f2b0cf33"
    assert merged.pmcid == "PMC6455466"
    assert merged.abstract == "A much longer abstract that says more about the paper."
    assert merged.citation_count == 2501
    assert merged.authors == ["Riccardo Miotto", "Fei Wang"]
    assert [c.source for c in merged.oa_candidates] == ["openalex", "semantic_scholar"]
    assert len(merged.hits) == 3


def test_a_preprint_merges_with_its_published_version() -> None:
    preprint = paper(
        doi="10.48550/arxiv.1512.03385",
        venue="arXiv (Cornell University)",
        year=2015,
        hits=[hit("openalex", 1)],
    )
    published = paper(
        doi="10.1109/cvpr.2016.90",
        arxiv_id="1512.03385",
        venue="CVPR",
        year=2016,
        citation_count=150000,
        hits=[hit("crossref", 3)],
    )
    (merged,) = merge([preprint, published])
    assert merged.doi == "10.1109/cvpr.2016.90"
    assert merged.arxiv_id == "1512.03385"
    assert merged.venue == "CVPR"
    assert merged.year == 2016
    assert merged.url == "https://doi.org/10.1109/cvpr.2016.90"


def test_semantic_scholar_ids_merge() -> None:
    s2_id = "204e3073870fae3d05bcbc2f6a8e263d9b72e776"
    first = paper(title="Attention is all you need", s2_id=s2_id, year=2017)
    second = paper(title="Attention Is All You Need (v2)", s2_id=s2_id, year=2017)
    assert len(merge([first, second])) == 1


def test_titles_merge_with_the_same_first_author_and_close_years() -> None:
    arxiv_copy = paper(
        title="Attention is all you need.",
        authors=["Vaswani, A.", "Shazeer, N."],
        year=2017,
        arxiv_id="1706.03762",
    )
    repository_copy = paper(
        title="ATTENTION IS ALL YOU NEED", authors=["Ashish Vaswani"], year=2018
    )
    later_work = paper(title="Attention is all you need", authors=["Ashish Vaswani"], year=2020)
    other_author = paper(title="Attention is all you need", authors=["Jane Doe"], year=2017)
    merged = merge([arxiv_copy, repository_copy, later_work, other_author])
    assert len(merged) == 3
    assert merged[0].arxiv_id == "1706.03762"
    assert merged[1].year == 2020
    assert merged[2].authors == ["Jane Doe"]


def test_different_dois_never_merge_on_weaker_keys() -> None:
    conference = paper(title="Deep Residual Learning", authors=["Kaiming He"], doi="10.1109/a.1")
    journal = paper(title="Deep Residual Learning", authors=["Kaiming He"], doi="10.1109/b.2")
    assert len(merge([conference, journal])) == 2


def test_short_generic_titles_need_an_id_to_merge() -> None:
    first = paper(title="Editorial", authors=["Ann Lee"], year=2020)
    second = paper(title="Editorial", authors=["Ann Lee"], year=2021)
    assert len(merge([first, second])) == 2


def test_merge_keeps_first_seen_order_and_flags_retractions() -> None:
    a = paper(title="Paper about apples and pears", doi="10.1000/a")
    b = paper(title="Paper about bananas and kiwis", doi="10.1000/b")
    a_retracted = paper(title="Paper about apples and pears", doi="10.1000/A", retracted=True)
    merged = merge([a, b, a_retracted])
    assert [m.doi for m in merged] == ["10.1000/a", "10.1000/b"]
    assert merged[0].retracted is True
    assert merge([]) == []


def test_surnames() -> None:
    assert first_author_surname(["Vaswani, Ashish"]) == "vaswani"
    assert first_author_surname(["Martin Luther King Jr."]) == "king"
    assert first_author_surname(["José Álvarez"]) == "alvarez"
    assert first_author_surname([]) == ""

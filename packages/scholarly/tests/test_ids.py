import pytest

from agentic_scholarly.ids import (
    arxiv_id_from_doi,
    normalize_arxiv_id,
    normalize_doi,
    normalize_openalex_id,
    normalize_pmcid,
    normalize_s2_id,
    normalize_title,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://doi.org/10.1145/3065386", "10.1145/3065386"),
        ("http://dx.doi.org/10.1109/CVPR.2016.90", "10.1109/cvpr.2016.90"),
        ("doi: 10.1000/XYZ.", "10.1000/xyz"),
        ("10.48550/arXiv.1706.03762", "10.48550/arxiv.1706.03762"),
        ("not a doi", None),
        ("https://example.org/10.1000/x", None),
        (None, None),
        (42, None),
    ],
)
def test_dois_are_lowercase_without_prefixes(raw: object, expected: str | None) -> None:
    assert normalize_doi(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://arxiv.org/abs/1706.03762v7", "1706.03762"),
        ("https://arxiv.org/pdf/2301.07041.pdf", "2301.07041"),
        ("https://export.arxiv.org/abs/2301.07041v2", "2301.07041"),
        ("arXiv:1706.03762v5[cs.CL]", "1706.03762"),
        ("10.48550/arXiv.2010.11929", "2010.11929"),
        ("0704.0001", "0704.0001"),
        ("hep-th/9901001v2", "hep-th/9901001"),
        ("math.GT/0309136", "math.GT/0309136"),
        ("1234", None),
        ("", None),
    ],
)
def test_arxiv_ids_drop_versions_and_prefixes(raw: str, expected: str | None) -> None:
    assert normalize_arxiv_id(raw) == expected


def test_arxiv_ids_come_out_of_arxiv_dois_only() -> None:
    assert arxiv_id_from_doi("10.48550/arxiv.1706.03762") == "1706.03762"
    assert arxiv_id_from_doi("10.1109/cvpr.2016.90") is None
    assert arxiv_id_from_doi(None) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("PMC6455466", "PMC6455466"),
        ("pmc6455466", "PMC6455466"),
        ("6455466", "PMC6455466"),
        ("PMC6455466.2", "PMC6455466"),
        (6455466, "PMC6455466"),
        ("https://www.ncbi.nlm.nih.gov/pmc/articles/6455466", "PMC6455466"),
        ("https://pmc.ncbi.nlm.nih.gov/articles/PMC6455466/", "PMC6455466"),
        ("https://europepmc.org/articles/PMC6455466", "PMC6455466"),
        ("https://example.org/articles/6455466", None),
        ("PMC", None),
        (True, None),
        (0, None),
    ],
)
def test_pmcids_carry_the_prefix(raw: object, expected: str | None) -> None:
    assert normalize_pmcid(raw) == expected


def test_openalex_and_semantic_scholar_ids() -> None:
    assert normalize_openalex_id("https://openalex.org/W2963403868") == "W2963403868"
    assert normalize_openalex_id("w2963403868") == "W2963403868"
    assert normalize_openalex_id("https://openalex.org/A5034823167") is None
    s2 = "204e3073870fae3d05bcbc2f6a8e263d9b72e776"
    assert normalize_s2_id(s2.upper()) == s2
    assert normalize_s2_id("204e30") is None


def test_titles_compare_without_case_accents_or_punctuation() -> None:
    assert normalize_title("Attention Is All You Need!") == "attention is all you need"
    assert normalize_title("Über  Sätze \N{EM DASH} eine Studie") == "uber satze eine studie"
    assert normalize_title("BERT: Pre-training") == "bert pre training"
    # Non-Latin titles keep their letters instead of collapsing to nothing.
    assert normalize_title("심층 학습") != ""

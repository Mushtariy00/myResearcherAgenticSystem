import pytest

from agentic_scholarly.pdf import InvalidPdf, clean_page_text, page_count, page_texts, validate_pdf
from agentic_scholarly.testing import make_pdf


def test_page_texts_come_back_per_page() -> None:
    data = make_pdf(
        [
            ["Monocular depth estimation", "predicts a depth map from one image."],
            "Results\nThe model reaches an abs-rel error of 0.098.",
        ]
    )
    texts = page_texts(data)
    assert len(texts) == 2
    assert texts[0] == "Monocular depth estimation\npredicts a depth map from one image."
    assert "abs-rel error of 0.098." in texts[1]
    assert "\r" not in texts[0] + texts[1]
    assert page_count(data) == 2
    assert validate_pdf(data) == 2


def test_words_hyphenated_across_lines_are_joined() -> None:
    texts = page_texts(make_pdf([["based solely on atten-", "tion mechanisms"]]))
    assert texts == ["based solely on attention mechanisms"]


def test_broken_pdfs_are_invalid() -> None:
    with pytest.raises(InvalidPdf):
        validate_pdf(b"<html>not a pdf</html>")
    with pytest.raises(InvalidPdf):
        validate_pdf(b"%PDF-1.4\n" + b"garbage " * 2000)
    with pytest.raises(InvalidPdf):
        page_texts(b"%PDF-1.7 truncated")
    assert InvalidPdf.code == "pdf.invalid"


def test_control_characters_are_removed() -> None:
    raw = "line one\r\nline two\x00\x0c end" + chr(0xFFFE) + chr(0xFFFF)
    assert clean_page_text(raw) == "line one\nline two end"

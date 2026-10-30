"""The PDF writer and the generated paper preview, without the API."""

import uuid
from datetime import UTC, datetime

from agentic_api.demo.paper_pdf import (
    MAX_PAGES,
    MIN_PAGES,
    evidence_by_page,
    page_count,
    paper_pdf,
)
from agentic_api.pdf import PdfDocument, Style, pdf_text, text_width, wrap_text
from agentic_api.schemas import PaperAnalysisOut, PaperOut
from agentic_core.schemas import EvidenceQuote
from api_testkit import assert_pdf_structure, pdf_page_texts

DELTA = "\N{GREEK SMALL LETTER DELTA}"
AT_LEAST = "\N{GREATER-THAN OR EQUAL TO}"


def _paper(**fields: object) -> PaperOut:
    values: dict[str, object] = {
        "paper_id": "arxiv:2406.09414",
        "title": "Depth Anything V2",
        "authors": ["Lihe Yang", "Bingyi Kang"],
        "year": 2024,
        "venue": "NeurIPS",
        "doi": None,
        "arxiv_id": "2406.09414",
        "url": "https://arxiv.org/abs/2406.09414",
        "abstract": "Synthetic labels plus a large teacher improve fine detail.",
        "citation_count": 120,
        "source": "arxiv",
        "pdf_available": True,
    }
    return PaperOut.model_validate({**values, **fields})


def _analysis(*evidence: tuple[str, int]) -> PaperAnalysisOut:
    return PaperAnalysisOut(
        run_id=uuid.UUID(int=1),
        stage_output_id=uuid.UUID(int=2),
        attempt=1,
        created_at=datetime(2026, 10, 30, tzinfo=UTC),
        contribution="A larger teacher.",
        method="A ViT encoder.",
        results="Sharper boundaries.",
        limitations="Indoor scenes only.",
        evidence=[EvidenceQuote(quote=quote, page=page) for quote, page in evidence],
        demo=True,
    )


def test_text_is_escaped_and_greek_letters_use_the_symbol_font() -> None:
    document = PdfDocument(title="Escapes")
    page = document.add_page()
    page.text(72, 700, r"f(x) = (a \ b)")
    page.text(72, 680, f"{DELTA}1 {AT_LEAST} 0.9", style=Style.BOLD, size=12)
    data = document.render()
    assert rb"(f\(x\) = \(a \\ b\)) Tj" in data
    # The Greek delta and the sign are Symbol glyphs; the rest stays Helvetica-Bold.
    assert b"/F4 12 Tf\n(d) Tj\n/F2 12 Tf\n(1 ) Tj\n/F4 12 Tf\n(\\263) Tj" in data
    assert b"/BaseFont /Symbol >>" in data
    assert b"/BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>" in data
    assert pdf_page_texts(data) == [f"f(x) = (a \\ b)\n{DELTA}1 {AT_LEAST} 0.9"]
    assert assert_pdf_structure(data) == 1


def test_characters_the_fonts_lack_are_approximated() -> None:
    hangul = (  # "monocular depth" in Korean
        "\N{HANGUL SYLLABLE DAN}\N{HANGUL SYLLABLE AN} "
        "\N{HANGUL SYLLABLE GGIP}\N{HANGUL SYLLABLE I}"
    )
    assert pdf_text(hangul) == "danan kkipi"  # romanized syllable by syllable
    assert pdf_text("M\N{LATIN SMALL LETTER U WITH DIAERESIS}ller") == (
        "M\N{LATIN SMALL LETTER U WITH DIAERESIS}ller"  # WinAnsi has it
    )
    assert pdf_text("Nguy\N{LATIN SMALL LETTER E WITH CIRCUMFLEX AND TILDE}n") == "Nguyen"
    assert pdf_text("\N{CJK UNIFIED IDEOGRAPH-6A21}") == "?"
    assert pdf_text("a\tb\n\x07c  d") == "a b c d"  # whitespace collapsed, controls dropped
    assert pdf_text(pdf_text(hangul)) == pdf_text(hangul)


def test_wrapping_keeps_lines_inside_the_width() -> None:
    text = "Monocular depth estimation " * 30 + "x" * 400
    lines = wrap_text(text, 200)
    assert all(text_width(line) <= 200 for line in lines)
    assert "".join(lines).replace(" ", "") == text.replace(" ", "")  # nothing lost
    assert text_width("Depth", Style.BOLD) > text_width("Depth")
    assert wrap_text("   ", 100) == []


def test_a_document_without_pages_still_has_one() -> None:
    data = PdfDocument().render()
    assert data.startswith(b"%PDF-1.4\n")
    assert assert_pdf_structure(data) == 1
    assert b"/Producer <FEFF" in data and b"/Title" not in data


def test_quotes_decide_the_page_count() -> None:
    assert page_count([]) == MIN_PAGES
    assert page_count([_analysis(("Early.", 2))]) == MIN_PAGES
    assert page_count([_analysis(("Late.", 11))]) == 11
    beyond = _analysis(("Shown.", 7), ("Too far to print.", MAX_PAGES + 1))
    assert page_count([beyond]) == 7
    pages = evidence_by_page(
        [_analysis(("Same  quote.", 3), ("Other.", 3)), _analysis(("Same quote.", 3))]
    )
    assert pages == {3: ["Same quote.", "Other."]}


def test_the_preview_is_deterministic_and_prints_every_quote() -> None:
    notes = _analysis(("We train for 30 epochs.", 4), (f"PRISM reaches {DELTA}1 of 0.871.", 6))
    first = paper_pdf(_paper(), [notes])
    assert first == paper_pdf(_paper(), [notes])
    assert first != paper_pdf(_paper(title="Another Title"), [notes])
    assert assert_pdf_structure(first) == 6
    texts = [" ".join(text.split()) for text in pdf_page_texts(first)]
    assert "We train for 30 epochs." in texts[3]
    assert f"PRISM reaches {DELTA}1 of 0.871." in texts[5]
    assert "Reading notes from run 00000000: A larger teacher." in texts[0]
    assert all("Generated preview" in text for text in texts)


def test_long_titles_abstracts_and_quotes_stay_on_their_pages() -> None:
    paper = _paper(title="A Very Long Title " * 20, abstract="Long abstract sentence. " * 400)
    quote = "word " * 900
    data = paper_pdf(paper, [_analysis((quote, 1), ("Short quote.", 1))])
    assert assert_pdf_structure(data) == MIN_PAGES
    first_page = " ".join(pdf_page_texts(data)[0].split())
    assert "Short quote." in first_page  # quotes keep their room; the abstract is shortened
    assert "word word word" in first_page and first_page.count("...") >= 2

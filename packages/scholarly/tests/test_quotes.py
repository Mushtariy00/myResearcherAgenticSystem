import pytest

from agentic_scholarly.pdf import page_texts
from agentic_scholarly.quotes import MIN_QUOTE_CHARS, normalize, verify_quote
from agentic_scholarly.testing import make_pdf

PAGE = (
    "We propose a new simple network architecture, the Transformer, based solely on atten-\n"
    "tion mechanisms, dispensing with recurrence and convolutions entirely. Experiments on\n"
    "two machine translation tasks show these models to be signi\N{LATIN SMALL LIGATURE FI}cantly\n"
    "superior in quality while being more parallelizable. The model achieves a state-of-the-\n"
    "art BLEU score; we call it \N{LEFT DOUBLE QUOTATION MARK}Scaled Dot-Product Attention"
    "\N{RIGHT DOUBLE QUOTATION MARK}."
)


@pytest.mark.parametrize(
    "quote",
    [
        "based solely on attention mechanisms, dispensing with recurrence",
        "dispensing   with recurrence\nand convolutions entirely",
        "EXPERIMENTS ON TWO MACHINE TRANSLATION TASKS",
        "these models to be significantly superior in quality",
        "achieves a state-of-the-art BLEU score",
        'we call it "Scaled Dot-Product Attention"',
        "\N{HORIZONTAL ELLIPSIS}superior in quality while being more\N{HORIZONTAL ELLIPSIS}",
        '"two machine translation tasks show these models"',
    ],
)
def test_quotes_on_the_page_are_verified(quote: str) -> None:
    assert verify_quote(quote, PAGE)


@pytest.mark.parametrize(
    "quote",
    [
        "the Transformer is based on recurrence",
        "superior in quality while being faster to train",
        "simple network",
        "",
    ],
)
def test_paraphrases_and_short_quotes_are_rejected(quote: str) -> None:
    assert not verify_quote(quote, PAGE)


def test_short_means_under_twenty_characters_after_normalising() -> None:
    assert MIN_QUOTE_CHARS == 20
    page = "a b c d e f g h i j k l m n o p"
    assert not verify_quote("  a b c d e f g h i  ", page)
    assert verify_quote("a b c d e f g h i j k", page)


def test_normalize_folds_typography() -> None:
    assert normalize("E\N{LATIN SMALL LIGATURE FFI}cient  \N{LATIN SMALL LIGATURE FL}ow") == (
        "efficient flow"
    )
    assert normalize("\N{LEFT SINGLE QUOTATION MARK}it\N{RIGHT SINGLE QUOTATION MARK}s") == "'it's"
    assert normalize("pre-\n  trained\N{NO-BREAK SPACE}models") == "pretrained models"
    assert normalize("en\N{EN DASH}dash") == "endash"


def test_quotes_verify_against_real_pdf_page_text() -> None:
    page = page_texts(
        make_pdf(
            [
                [
                    "The encoder maps an input sequence of symbol represen-",
                    "tations to a sequence of continuous representations.",
                ]
            ]
        )
    )[0]
    assert verify_quote("maps an input sequence of symbol representations to a sequence", page)

"""Evidence-quote checks: a quote counts only if it appears on the page it cites.

Page text from a PDF differs from the same words typed by a model: line breaks and
hyphenation split words, ligature glyphs stand for letter pairs ("fi", "fl"), quotes are curly
and case varies. ``normalize`` removes those differences from both sides; nothing else is
fuzzy, so a paraphrase or a quote stitched from distant sentences does not match.
"""

import re
import unicodedata
from typing import Final

# Shorter quotes ("we propose", "results show") match almost any paper.
MIN_QUOTE_CHARS: Final = 20

_TRANSLATION: Final = str.maketrans(
    {
        "\N{LEFT SINGLE QUOTATION MARK}": "'",
        "\N{RIGHT SINGLE QUOTATION MARK}": "'",
        "\N{SINGLE LOW-9 QUOTATION MARK}": "'",
        "\N{SINGLE HIGH-REVERSED-9 QUOTATION MARK}": "'",
        "\N{PRIME}": "'",
        "\N{LEFT DOUBLE QUOTATION MARK}": '"',
        "\N{RIGHT DOUBLE QUOTATION MARK}": '"',
        "\N{DOUBLE LOW-9 QUOTATION MARK}": '"',
        "\N{DOUBLE HIGH-REVERSED-9 QUOTATION MARK}": '"',
        "\N{DOUBLE PRIME}": '"',
        "\N{LEFT-POINTING DOUBLE ANGLE QUOTATION MARK}": '"',
        "\N{RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK}": '"',
        "\N{HYPHEN}": "-",
        "\N{NON-BREAKING HYPHEN}": "-",
        "\N{FIGURE DASH}": "-",
        "\N{EN DASH}": "-",
        "\N{EM DASH}": "-",
        "\N{HORIZONTAL BAR}": "-",
        "\N{MINUS SIGN}": "-",
        "\N{SOFT HYPHEN}": None,
        "\N{ZERO WIDTH SPACE}": None,
        "\N{ZERO WIDTH NON-JOINER}": None,
        "\N{ZERO WIDTH JOINER}": None,
        "\N{WORD JOINER}": None,
        "\N{ZERO WIDTH NO-BREAK SPACE}": None,
        # PDFium's mark for a word hyphenated across lines (see agentic_scholarly.pdf).
        chr(0xFFFE): None,
    }
)
# A hyphen between letters, possibly followed by a line break: "atten-\ntion", "state-of-the-art".
_WORD_HYPHEN: Final = re.compile(r"(?<=\w)-\s*(?=\w)")
# Quote marks, spaces and ellipses a model wraps around a quote (NFKC turns an ellipsis
# character into three periods).
_WRAPPING: Final = "\"' ."


def normalize(text: str) -> str:
    """text with compatibility characters folded (NFKC: ligatures, full-width forms), quotes
    and dashes straightened, hyphens inside words removed, whitespace collapsed, case folded."""
    folded = unicodedata.normalize("NFKC", text).translate(_TRANSLATION)
    joined = _WORD_HYPHEN.sub("", folded)
    return " ".join(joined.split()).casefold()


def verify_quote(quote: str, page_text: str) -> bool:
    """Whether quote, at least MIN_QUOTE_CHARS long once normalised, appears in page_text."""
    needle = normalize(quote).strip(_WRAPPING)
    if len(needle) < MIN_QUOTE_CHARS:
        return False
    return needle in normalize(page_text)

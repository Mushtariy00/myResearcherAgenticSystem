"""A small PDF 1.4 writer: pages of positioned text, rules and filled rectangles, nothing more.

No fonts are embedded. Text uses the standard Helvetica fonts with WinAnsiEncoding, and the
standard Symbol font for Greek letters and common math signs, so a metric such as delta1
written with a Greek delta stays searchable in a PDF viewer. Hangul is romanized; any other
character neither font has loses its accents or becomes "?" (see ``pdf_text``). Content
streams are not compressed.
"""

import unicodedata
from enum import StrEnum

PAGE_WIDTH = 595.28  # A4, in points
PAGE_HEIGHT = 841.89


class Style(StrEnum):
    """Text styles. The values are the font resource names every page has."""

    REGULAR = "F1"
    BOLD = "F2"
    OBLIQUE = "F3"


_SYMBOL = "F4"
_BASE_FONTS = {
    Style.REGULAR.value: "Helvetica",
    Style.BOLD.value: "Helvetica-Bold",
    Style.OBLIQUE.value: "Helvetica-Oblique",
    _SYMBOL: "Symbol",
}

# Helvetica (and Helvetica-Oblique) glyph widths for codes 32-126, in 1/1000 em (Adobe AFM).
_HELVETICA_WIDTHS = (
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
)  # fmt: skip
# Helvetica-Bold is up to about 10% wider; measuring it this way only ever wraps a little early.
_BOLD_FACTOR = 1.1
_DEFAULT_WIDTH = 556
# WinAnsi characters beyond ASCII that are not an accented ASCII letter: (code point, width).
_OTHER_WIDTHS = {
    chr(char): width
    for char, width in (
        (0x2013, 556),  # en dash
        (0x2014, 1000),  # em dash
        (0x2018, 222),  # quotation marks
        (0x2019, 222),
        (0x201A, 222),
        (0x201C, 333),
        (0x201D, 333),
        (0x201E, 333),
        (0x2022, 350),  # bullet
        (0x2026, 1000),  # ellipsis
        (0x2122, 1000),  # trade mark
        (0x20AC, 556),  # euro
        (0x00A3, 556),  # pound
        (0x00A7, 556),  # section
        (0x00A9, 737),  # copyright
        (0x00AE, 737),  # registered
        (0x00B0, 400),  # degree
        (0x00B1, 584),  # plus-minus
        (0x00B5, 556),  # micro
        (0x00B7, 278),  # middle dot
        (0x00D7, 584),  # multiplication
        (0x00F7, 584),  # division
        (0x00C6, 1000),  # AE
        (0x00E6, 889),  # ae
        (0x0152, 1000),  # OE
        (0x0153, 944),  # oe
        (0x00DF, 611),  # sharp s
    )
}
# Characters drawn with the Symbol font: (code point, code in its built-in encoding, width).
_SYMBOL_GLYPHS: dict[str, tuple[int, int]] = {
    chr(char): (code, width)
    for char, code, width in (
        (0x0391, 0x41, 722),  # Alpha
        (0x0392, 0x42, 667),  # Beta
        (0x0393, 0x47, 603),  # Gamma
        (0x0394, 0x44, 612),  # Delta
        (0x2206, 0x44, 612),  # increment, drawn as Delta
        (0x0395, 0x45, 611),  # Epsilon
        (0x0396, 0x5A, 611),  # Zeta
        (0x0397, 0x48, 722),  # Eta
        (0x0398, 0x51, 741),  # Theta
        (0x0399, 0x49, 333),  # Iota
        (0x039A, 0x4B, 722),  # Kappa
        (0x039B, 0x4C, 686),  # Lambda
        (0x039C, 0x4D, 889),  # Mu
        (0x039D, 0x4E, 722),  # Nu
        (0x039E, 0x58, 645),  # Xi
        (0x039F, 0x4F, 722),  # Omicron
        (0x03A0, 0x50, 768),  # Pi
        (0x03A1, 0x52, 556),  # Rho
        (0x03A3, 0x53, 592),  # Sigma
        (0x03A4, 0x54, 611),  # Tau
        (0x03A5, 0x55, 690),  # Upsilon
        (0x03A6, 0x46, 763),  # Phi
        (0x03A7, 0x43, 722),  # Chi
        (0x03A8, 0x59, 795),  # Psi
        (0x03A9, 0x57, 768),  # Omega
        (0x2126, 0x57, 768),  # ohm sign, drawn as Omega
        (0x03B1, 0x61, 631),  # alpha
        (0x03B2, 0x62, 549),  # beta
        (0x03B3, 0x67, 411),  # gamma
        (0x03B4, 0x64, 494),  # delta
        (0x03B5, 0x65, 439),  # epsilon
        (0x03B6, 0x7A, 494),  # zeta
        (0x03B7, 0x68, 603),  # eta
        (0x03B8, 0x71, 521),  # theta
        (0x03B9, 0x69, 329),  # iota
        (0x03BA, 0x6B, 549),  # kappa
        (0x03BB, 0x6C, 549),  # lambda
        (0x03BC, 0x6D, 576),  # mu
        (0x03BD, 0x6E, 521),  # nu
        (0x03BE, 0x78, 493),  # xi
        (0x03BF, 0x6F, 549),  # omicron
        (0x03C0, 0x70, 549),  # pi
        (0x03C1, 0x72, 549),  # rho
        (0x03C2, 0x56, 439),  # final sigma
        (0x03C3, 0x73, 603),  # sigma
        (0x03C4, 0x74, 439),  # tau
        (0x03C5, 0x75, 576),  # upsilon
        (0x03C6, 0x66, 521),  # phi
        (0x03C7, 0x63, 549),  # chi
        (0x03C8, 0x79, 686),  # psi
        (0x03C9, 0x77, 686),  # omega
        (0x03D1, 0x4A, 631),  # theta symbol
        (0x03D5, 0x6A, 603),  # phi symbol
        (0x03D6, 0x76, 713),  # pi symbol
        (0x2264, 0xA3, 549),  # less-than or equal to
        (0x2265, 0xB3, 549),  # greater-than or equal to
        (0x2248, 0xBB, 549),  # almost equal to
        (0x2260, 0xB9, 549),  # not equal to
        (0x221E, 0xA5, 713),  # infinity
        (0x2192, 0xAE, 987),  # rightwards arrow
        (0x2190, 0xAC, 987),  # leftwards arrow
        (0x2211, 0xE5, 713),  # summation
        (0x2202, 0xB6, 494),  # partial differential
        (0x2207, 0xD1, 713),  # nabla
        (0x2212, 0x2D, 549),  # minus sign
        (0x221A, 0xD6, 549),  # square root
        (0x2208, 0xCE, 713),  # element of
        (0x2200, 0x22, 713),  # for all
        (0x2203, 0x24, 549),  # there exists
        (0x222B, 0xF2, 274),  # integral
        (0x22C5, 0xD7, 250),  # dot operator
    )
}
# Revised Romanization of Korean, one syllable at a time (without the sound-change rules).
_HANGUL_INITIALS = (
    "g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t",
    "p", "h",
)  # fmt: skip
_HANGUL_VOWELS = (
    "a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo",
    "we", "wi", "yu", "eu", "ui", "i",
)  # fmt: skip
_HANGUL_FINALS = (
    "", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l", "m", "p",
    "p", "t", "t", "ng", "t", "t", "k", "t", "p", "t",
)  # fmt: skip
_HANGUL_FIRST, _HANGUL_LAST = 0xAC00, 0xD7A3


def _drawable(char: str) -> bool:
    if char in _SYMBOL_GLYPHS:
        return True
    if not char.isprintable():
        return False
    try:
        char.encode("cp1252")  # Python's cp1252 matches PDF's WinAnsiEncoding
    except UnicodeEncodeError:
        return False
    return True


def _romanize(char: str) -> str:
    index = ord(char) - _HANGUL_FIRST
    initial, rest = divmod(index, 588)
    vowel, final = divmod(rest, 28)
    return _HANGUL_INITIALS[initial] + _HANGUL_VOWELS[vowel] + _HANGUL_FINALS[final]


def pdf_text(text: str) -> str:
    """``text`` as the fonts can draw it, on one line: whitespace collapsed, Hangul romanized,
    accents dropped where WinAnsi lacks the letter, and anything else replaced with "?"."""
    chars: list[str] = []
    for char in " ".join(text.split()):
        if _drawable(char):
            chars.append(char)
        elif _HANGUL_FIRST <= ord(char) <= _HANGUL_LAST:
            chars.append(_romanize(char))
        elif char.isprintable():
            decomposed = unicodedata.normalize("NFKD", char)
            base = "".join(part for part in decomposed if not unicodedata.combining(part))
            chars.append(base if base and all(_drawable(part) for part in base) else "?")
    return "".join(chars)


def _width(char: str, style: Style) -> float:
    if char in _SYMBOL_GLYPHS:
        return _SYMBOL_GLYPHS[char][1]
    code = ord(char)
    if 32 <= code <= 126:
        width = _HELVETICA_WIDTHS[code - 32]
    elif char in _OTHER_WIDTHS:
        width = _OTHER_WIDTHS[char]
    else:
        base = unicodedata.normalize("NFKD", char)[:1]
        ascii_base = bool(base) and 32 <= ord(base) <= 126
        width = _HELVETICA_WIDTHS[ord(base) - 32] if ascii_base else _DEFAULT_WIDTH
    return width * _BOLD_FACTOR if style == Style.BOLD else width


def _measure(text: str, style: Style, size: float) -> float:
    """Width in points of text that is already in ``pdf_text`` form."""
    return sum(_width(char, style) for char in text) * size / 1000


def text_width(text: str, style: Style = Style.REGULAR, size: float = 10.0) -> float:
    """The width of ``text``, as ``PdfPage.text`` draws it, in points."""
    return _measure(pdf_text(text), style, size)


def wrap_text(
    text: str, width: float, style: Style = Style.REGULAR, size: float = 10.0
) -> list[str]:
    """``text`` (in ``pdf_text`` form) broken into lines at most ``width`` points wide, at spaces;
    a word longer than a whole line is broken where it has to be."""
    lines: list[str] = []
    space = _measure(" ", style, size)
    current, current_width = "", 0.0
    for word in pdf_text(text).split(" "):
        if not word:
            continue
        word_width = _measure(word, style, size)
        if current and current_width + space + word_width <= width:
            current, current_width = f"{current} {word}", current_width + space + word_width
            continue
        if current:
            lines.append(current)
        while word_width > width and len(word) > 1:
            cut = _fitting_prefix(word, width, style, size)
            lines.append(word[:cut])
            word = word[cut:]
            word_width = _measure(word, style, size)
        current, current_width = word, word_width
    if current:
        lines.append(current)
    return lines


def _fitting_prefix(word: str, width: float, style: Style, size: float) -> int:
    total = 0.0
    for index, char in enumerate(word):
        total += _width(char, style) * size / 1000
        if total > width:
            return max(1, index)
    return len(word)


def _number(value: float) -> bytes:
    return (b"%.2f" % value).rstrip(b"0").rstrip(b".")


def _literal(data: bytes) -> bytes:
    """A PDF literal string: parentheses and backslashes escaped, other bytes octal-coded."""
    out = bytearray(b"(")
    for byte in data:
        if byte in b"()\\":
            out += b"\\" + bytes([byte])
        elif 0x20 <= byte <= 0x7E:
            out.append(byte)
        else:
            out += b"\\%03o" % byte
    out += b")"
    return bytes(out)


def _text_string(value: str) -> bytes:
    """A PDF text string for the document information: UTF-16BE with a byte order mark."""
    return b"<FEFF" + value.encode("utf-16-be").hex().upper().encode() + b">"


def _runs(text: str, style: Style) -> list[tuple[str, bytes]]:
    """``text`` (in ``pdf_text`` form) as consecutive (font resource, encoded bytes) runs."""
    runs: list[tuple[str, bytearray]] = []
    for char in text:
        if char in _SYMBOL_GLYPHS:
            font, code = _SYMBOL, bytes([_SYMBOL_GLYPHS[char][0]])
        else:
            font, code = style.value, char.encode("cp1252")
        if runs and runs[-1][0] == font:
            runs[-1][1].extend(code)
        else:
            runs.append((font, bytearray(code)))
    return [(font, bytes(data)) for font, data in runs]


class PdfPage:
    """One A4 page; coordinates are points from the bottom-left corner."""

    def __init__(self) -> None:
        self._operations: list[bytes] = []

    def text(
        self,
        x: float,
        y: float,
        text: str,
        *,
        style: Style = Style.REGULAR,
        size: float = 10.0,
        gray: float = 0.0,
    ) -> None:
        """One line of text with its baseline starting at (x, y); 0 is black, 1 white."""
        runs = _runs(pdf_text(text), style)
        if not runs:
            return
        operations = [b"BT", b"%.3f g" % gray, b"1 0 0 1 %.2f %.2f Tm" % (x, y)]
        for font, data in runs:
            operations.append(b"/%s %s Tf" % (font.encode(), _number(size)))
            operations.append(_literal(data) + b" Tj")
        operations.append(b"ET")
        self._operations.append(b"\n".join(operations))

    def rect(
        self, x: float, y: float, width: float, height: float, *, rgb: tuple[float, float, float]
    ) -> None:
        """A filled rectangle with its lower-left corner at (x, y)."""
        red, green, blue = rgb
        self._operations.append(
            b"q %.3f %.3f %.3f rg %.2f %.2f %.2f %.2f re f Q"
            % (red, green, blue, x, y, width, height)
        )

    def rule(
        self, x1: float, x2: float, y: float, *, gray: float = 0.8, width: float = 0.5
    ) -> None:
        """A horizontal line."""
        self._operations.append(
            b"q %.3f G %.2f w %.2f %.2f m %.2f %.2f l S Q" % (gray, width, x1, y, x2, y)
        )

    def content(self) -> bytes:
        return b"\n".join(self._operations) + b"\n"


class PdfDocument:
    def __init__(self, *, title: str = "", author: str = "", subject: str = "") -> None:
        self._info = {
            "Title": title,
            "Author": author,
            "Subject": subject,
            "Producer": "Agentic Research Platform",
        }
        self._pages: list[PdfPage] = []

    def add_page(self) -> PdfPage:
        page = PdfPage()
        self._pages.append(page)
        return page

    def render(self) -> bytes:
        """The whole file. Objects: 1 catalog, 2 page tree, the fonts, then each page's content
        stream and page dictionary, and last the document information."""
        pages = self._pages or [PdfPage()]  # a PDF needs at least one page
        objects: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>", b""]
        font_refs = []
        for name, base_font in _BASE_FONTS.items():
            encoding = b"" if name == _SYMBOL else b" /Encoding /WinAnsiEncoding"
            objects.append(
                b"<< /Type /Font /Subtype /Type1 /BaseFont /%s%s >>"
                % (base_font.encode(), encoding)
            )
            font_refs.append(b"/%s %d 0 R" % (name.encode(), len(objects)))
        resources = b"<< /Font << " + b" ".join(font_refs) + b" >> >>"
        media_box = b"[0 0 %s %s]" % (_number(PAGE_WIDTH), _number(PAGE_HEIGHT))
        kids = []
        for page in pages:
            stream = page.content()
            objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
            objects.append(
                b"<< /Type /Page /Parent 2 0 R /MediaBox %s /Resources %s /Contents %d 0 R >>"
                % (media_box, resources, len(objects))
            )
            kids.append(b"%d 0 R" % len(objects))
        objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(kids), len(kids))
        info = [
            b"/%s %s" % (key.encode(), _text_string(value))
            for key, value in self._info.items()
            if value
        ]
        objects.append(b"<< " + b" ".join(info) + b" >>")

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")  # the comment marks the file binary
        offsets = []
        for number, body in enumerate(objects, start=1):
            offsets.append(len(out))
            out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
        out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
        out += b"trailer\n<< /Size %d /Root 1 0 R /Info %d 0 R >>\n" % (
            len(objects) + 1,
            len(objects),
        )
        out += b"startxref\n%d\n" % xref
        out += b"%%EOF\n"
        return bytes(out)

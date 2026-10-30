"""PDF checks and per-page text with PDFium (pypdfium2).

PDFium is not thread-safe, so every call holds one process-wide lock. The calls are CPU-bound:
run them in a worker thread (``asyncio.to_thread``) to keep the event loop responsive.
"""

import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Final

import pypdfium2 as pdfium

_LOCK: Final = threading.Lock()
# PDFium replaces a hyphen that splits a word across lines (and the line break) with U+FFFE.
_HYPHENATION_MARK: Final = chr(0xFFFE)
# Control characters other than tab and newline, and the noncharacter U+FFFF; PostgreSQL text
# and JSONB reject NUL.
_CONTROL: Final = re.compile("[\x00-\x08\x0b-\x1f\x7f" + chr(0xFFFF) + "]")


class InvalidPdf(Exception):
    """PDFium cannot open the document, or it has no pages."""

    code: Final = "pdf.invalid"


@contextmanager
def _document(data: bytes) -> Iterator[pdfium.PdfDocument]:
    with _LOCK:
        try:
            document = pdfium.PdfDocument(data)
        except pdfium.PdfiumError as exc:
            raise InvalidPdf(str(exc)) from exc
        try:
            yield document
        finally:
            document.close()


def page_count(data: bytes) -> int:
    with _document(data) as document:
        return len(document)


def validate_pdf(data: bytes) -> int:
    """The page count of a PDF that PDFium opens (an encrypted PDF needs a password and does
    not); raises InvalidPdf otherwise."""
    if not data.startswith(b"%PDF-"):
        raise InvalidPdf("the data does not start with %PDF-")
    pages = page_count(data)
    if pages < 1:
        raise InvalidPdf("the PDF has no pages")
    return pages


def page_texts(data: bytes) -> list[str]:
    """The text of every page, in page order: lines end in newlines, words PDFium found split
    by line-end hyphenation are joined, and control characters are removed."""
    texts: list[str] = []
    with _document(data) as document:
        for index in range(len(document)):
            page = document[index]
            try:
                text_page = page.get_textpage()
                try:
                    texts.append(clean_page_text(text_page.get_text_range()))
                finally:
                    text_page.close()
            finally:
                page.close()
    return texts


def clean_page_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(_HYPHENATION_MARK, "")
    return _CONTROL.sub("", text)

"""A paper's text as the analysis prompt shows it: the abstract, then its sections in order,
each opening with the [page N] it is on, cut to a character budget the sections share fairly.

Page markers matter because evidence quotes must name their page: a quote counts only if it is
found on that page's text. pdfium sections are pages already; GROBID sections get a marker
wherever a paragraph's opening words are found on a new page.
"""

import re
from collections.abc import Sequence
from typing import Any

from agentic_scholarly.quotes import normalize

BUDGET_CHARS = 12_000
_ABSTRACT_CHARS = 3_000
_PROBE_CHARS = 60
_MIN_PROBE_CHARS = 20
CUT_MARK = "[...]"
# A references heading on a line of its own: the bibliography and what follows are not worth
# the budget.
_REFERENCES = re.compile(r"^\s*(?:references|bibliography|literature cited)\s*$", re.I | re.M)

type Section = tuple[str | None, str]  # (title, text)


def page_sections(pages: Sequence[str]) -> list[Section]:
    """One untitled section per page with text, up to the references."""
    sections: list[Section] = []
    for number, text in enumerate(pages, start=1):
        heading = _REFERENCES.search(text) if number > 1 else None
        body = (text[: heading.start()] if heading else text).strip()
        if body:
            sections.append((None, f"[page {number}]\n{body}"))
        if heading:
            break
    return sections


def grobid_sections(sections: Sequence[dict[str, Any]], pages: Sequence[str]) -> list[Section]:
    """GROBID's sections, with a [page N] marker before each paragraph that starts a new page."""
    normalized = [normalize(page) for page in pages]
    current: int | None = None
    located: list[Section] = []
    for section in sections:
        parts: list[str] = []
        for paragraph in str(section.get("text") or "").split("\n\n"):
            page = _page_of(paragraph, normalized, current or 1)
            if page is not None and page != current:
                parts.append(f"[page {page}]")
                current = page
            parts.append(paragraph)
        title = section.get("title")
        located.append((str(title) if title else None, "\n".join(parts)))
    return located


def _page_of(paragraph: str, pages: Sequence[str], start: int) -> int | None:
    """The page whose text holds the paragraph's opening words, looking from ``start`` on."""
    probe = normalize(paragraph)[:_PROBE_CHARS]
    if len(probe) < _MIN_PROBE_CHARS:
        return None
    order = [*range(start - 1, len(pages)), *range(start - 1)]
    return next((index + 1 for index in order if probe in pages[index]), None)


def fair_shares(lengths: Sequence[int], budget: int) -> list[int]:
    """Split budget so that every item gets the same share, or its whole length if that is
    less; what short items leave goes to the long ones."""
    shares = [0] * len(lengths)
    pending = sorted(range(len(lengths)), key=lambda index: lengths[index])
    left = budget
    while pending:
        each = left // len(pending)
        shortest = pending[0]
        if lengths[shortest] > each:
            for index in pending:
                shares[index] = each
            break
        shares[shortest] = lengths[shortest]
        left -= lengths[shortest]
        pending.pop(0)
    return shares


def cut(text: str, limit: int) -> str:
    """text, or its first ``limit`` characters ending at a word and marked as cut."""
    if len(text) <= limit:
        return text
    head = text[:limit]
    space = head.rfind(" ")
    return (head[:space] if space > limit // 2 else head).rstrip() + f" {CUT_MARK}"


def paper_text(abstract: str, sections: Sequence[Section], budget: int = BUDGET_CHARS) -> str:
    """The abstract, then every section's opening within the budget."""
    head = f"Abstract\n{cut(abstract.strip(), _ABSTRACT_CHARS)}"
    blocks = [f"{title}\n{text}" if title else text for title, text in sections]
    shares = fair_shares([len(block) for block in blocks], max(0, budget - len(head)))
    kept = [cut(block, share) for block, share in zip(blocks, shares, strict=True) if share > 0]
    return "\n\n".join([head, *kept])

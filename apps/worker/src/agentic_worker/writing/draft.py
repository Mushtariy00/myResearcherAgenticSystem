"""The draft the code assembles from the outline and the sections, with its citations checked.

Citations are code, not trust: every [n] must name one of the literature output's papers ([1]
is its first), markers outside that list are removed from the text, and the citation list and
the references are built from the markers the draft uses. Markers follow the web's syntax
(apps/web/src/components/shared/markdown-plugins.ts): [3], [1, 4], [2-5]. A group with a 0 in
it is an interval such as [0, 1], not a citation, and code and math are never read for them.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from pydantic import ValidationError

from agentic_core.schemas import Citation, PaperRef, WritingOutput
from agentic_worker.stages import StageFailedError
from agentic_worker.writing.outline import Outline

# Ranges take a hyphen, an en dash or an em dash.
_DASH = r"[\N{EN DASH}\N{EM DASH}-]"
# A citation group, with the space before it, which goes when the group does; "[2](url)" is a
# link, not a citation.
_GROUP = re.compile(
    rf"(?P<space>[ \t]?)\[(?P<inner>\d{{1,4}}(?:\s*(?:,|{_DASH})\s*\d{{1,4}})*)\](?!\()"
)
_RANGE = re.compile(rf"\s*{_DASH}\s*")
# Where the web reads no citations: fenced and inline code, display and inline math.
_UNCITED = re.compile(r"```.*?```|~~~.*?~~~|`[^`\n]*`|\$\$.*?\$\$|\$[^$\n]*\$", re.DOTALL)
_MARKUP = re.compile(r"([\\`*_\[\]$|#])")


@dataclass
class Cited:
    """What a draft cites, as its text is checked against the papers 1..count."""

    count: int
    used: set[int] = field(default_factory=set)
    removed: int = 0  # references to numbers outside 1..count, taken out of the text

    def check(self, text: str) -> str:
        """text without its references outside the list; code and math are left as they are."""
        parts: list[str] = []
        last = 0
        for match in _UNCITED.finditer(text):
            parts += [_GROUP.sub(self._group, text[last : match.start()]), match.group(0)]
            last = match.end()
        parts.append(_GROUP.sub(self._group, text[last:]))
        return "".join(parts)

    def _group(self, match: re.Match[str]) -> str:
        items = [item.strip() for item in match["inner"].split(",")]
        numbers = [[int(n) for n in _RANGE.split(item)] for item in items]
        if any(n < 1 for item in numbers for n in item):
            return match[0]  # an interval, as the web reads it
        kept: list[str] = []
        for item, (first, *rest) in zip(items, numbers, strict=True):
            last = rest[-1] if rest else first
            if len(rest) <= 1 and first <= last <= self.count:
                kept.append(item)
                self.used.update(range(first, last + 1))
            else:
                self.removed += 1
        if len(kept) == len(items):
            return match[0]
        return f"{match['space']}[{', '.join(kept)}]" if kept else ""


def _quoted(text: str) -> str:
    """Text from a scholarly database, quoted into the draft: no markup, no HTML."""
    return _MARKUP.sub(r"\\\1", text).replace("<", "&lt;").replace(">", "&gt;")


def references(papers: Sequence[PaperRef], used: Iterable[int]) -> str:
    """The reference list of the cited papers (1 is the first of ``papers``)."""
    entries: list[str] = []
    for number in sorted(used):
        paper = papers[number - 1]
        authors = ", ".join(paper.authors[:3]) + (" et al" if len(paper.authors) > 3 else "")
        where = paper.venue or "Preprint"
        entry = (
            f"- [{number}] {_quoted(authors.rstrip('.'))}. {_quoted(paper.title.rstrip('.'))}. "
            f"{_quoted(where)}, {paper.year}."
        )
        if paper.doi:
            entry += f" doi:{_quoted(paper.doi)}."
        elif paper.arxiv_id:
            entry += f" arXiv:{_quoted(paper.arxiv_id)}."
        entries.append(entry)
    return "\n".join(entries) or "No paper is cited."


def writing_output(
    outline: Outline, bodies: Sequence[str], papers: Sequence[PaperRef]
) -> tuple[WritingOutput, int]:
    """The draft as the stage's output, and how many references it had to papers outside the
    list (removed)."""
    cited = Cited(len(papers))
    title, abstract = cited.check(outline.title), cited.check(outline.abstract)
    parts = [f"# {title}", "## Abstract", abstract]
    for number, (section, body) in enumerate(zip(outline.sections, bodies, strict=True), 1):
        parts += [f"## {number}. {section.name}", cited.check(body)]
    used = sorted(cited.used)
    parts += ["## References", references(papers, used)]
    try:
        output = WritingOutput(
            title=title,
            abstract=abstract,
            markdown="\n\n".join(parts),
            sections=list(outline.sections),
            citations=[Citation(key=n, paper_id=papers[n - 1].paper_id) for n in used],
            output_format=outline.output_format,
            review_focus=outline.review_focus,
        )
    except ValidationError as exc:  # e.g. an abstract that was nothing but markers
        raise StageFailedError(f"writing.invalid_output: {exc}") from exc
    return output, cited.removed

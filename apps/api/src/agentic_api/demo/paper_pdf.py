"""A generated PDF preview of a paper, until worker-fetch stores the published PDFs.

Every page says it is generated. The text is the paper's metadata and abstract, the reading
notes of the runs that analysed it, and neutral background sentences that claim nothing about
the paper itself. Each evidence quote is printed, highlighted, on the page it cites, so a PDF
viewer finds it there; pages without quotes are kept so that page numbers match the citations.
The same paper and analyses always give the same bytes.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from agentic_api.demo._seed import rng_for
from agentic_api.pdf import (
    PAGE_HEIGHT,
    PAGE_WIDTH,
    PdfDocument,
    PdfPage,
    Style,
    text_width,
    wrap_text,
)
from agentic_api.schemas import PaperAnalysisOut, PaperOut

MIN_PAGES = 4
MAX_PAGES = 60  # quotes that cite later pages are left out of the preview
MAX_QUOTE_LINES = 8
MARGIN = 64.0
WIDTH = PAGE_WIDTH - 2 * MARGIN
TOP = PAGE_HEIGHT - 72.0
BOTTOM = 58.0
_HIGHLIGHT = (1.0, 0.93, 0.6)
_NOTICE_FILL = (0.93, 0.94, 0.97)
_MUTED = 0.45
_NOTICE = (
    "Generated preview, not the published paper. Its text is the paper's metadata and "
    "abstract, the reading notes of the runs that analysed it and neutral background text. "
    "Evidence quotes are printed on the pages they cite."
)
_SECTIONS = (
    ("1 Introduction", "intro"),
    ("2 Background", "background"),
    ("3 Method", "method"),
    ("4 Training", "training"),
    ("5 Evaluation", "evaluation"),
    ("6 Results", "results"),
    ("7 Ablations", "ablation"),
    ("8 Discussion", "discussion"),
    ("9 Limitations", "limitations"),
    ("10 Conclusion", "conclusion"),
)
# Which reading note a section quotes (PaperAnalysisOut field).
_NOTES = {
    "intro": "contribution",
    "method": "method",
    "results": "results",
    "limitations": "limitations",
}
# General statements about the field and the preview; none of them is a claim about the paper.
_SENTENCES: dict[str, tuple[str, ...]] = {
    "intro": (
        "Learning-based approaches to problems like this one differ mainly in their "
        "supervision, their architecture and their training data.",
        "Progress on public benchmarks has been rapid, but results on a single benchmark can "
        "hide sensitivity to the capture setup.",
        "Practical systems also need models that run within a limited compute budget.",
        "Reading notes from the platform's analyses appear wherever a run analysed this paper.",
        "Statements specific to the paper in this preview come from its abstract and from "
        "those reading notes.",
    ),
    "background": (
        "Early methods relied on hand-crafted features and strong priors about scene structure.",
        "Convolutional encoder-decoder networks replaced most of those components.",
        "Transformer backbones and large-scale pretraining are now common starting points.",
        "Self-supervised and synthetic-data methods reduce the need for dense manual labels.",
        "Comparisons are only meaningful when methods share splits, input resolution and "
        "evaluation protocol.",
        "Surveys of the area point to robustness and efficiency as the main open problems.",
    ),
    "method": (
        "Models in this area typically pair a pretrained encoder with a decoder that restores "
        "the full resolution.",
        "Skip connections carry fine detail from early encoder stages to the decoder.",
        "Features from several scales are often fused before the prediction head.",
        "Auxiliary objectives can regularize training when labels are sparse or noisy.",
        "Architectural choices are usually justified by ablations rather than by theory alone.",
    ),
    "training": (
        "Training commonly uses AdamW with a warm-up phase and a decaying learning rate.",
        "Random crops, flips and photometric changes are the standard augmentations.",
        "Mixed precision reduces memory use enough to train on a single consumer GPU.",
        "Checkpoints are usually selected on a held-out validation split.",
        "A fixed random seed makes runs comparable, but several seeds are needed to estimate "
        "the variance.",
    ),
    "evaluation": (
        "Evaluation follows the standard splits and metrics of each benchmark.",
        "Baselines are best re-run with public code rather than copied from papers.",
        "Reporting both accuracy and runtime makes the trade-offs visible.",
        "Metrics computed on cropped or masked regions have to say so explicitly.",
        "Statistical significance is rarely reported, which makes small differences hard to judge.",
    ),
    "results": (
        "A results table should report every metric for every method.",
        "Qualitative examples help to explain where a method succeeds and where it fails.",
        "Errors tend to concentrate in regions where the input is ambiguous.",
        "Gains that hold across several datasets are more convincing than gains on one.",
    ),
    "ablation": (
        "Ablations remove one component at a time and retrain the model.",
        "A component that matters should cost accuracy when it is removed.",
        "Interactions between components can make single removals misleading.",
        "Ablations are only as reliable as the training budget allows.",
    ),
    "discussion": (
        "Results are best read together with the evaluation protocol that produced them.",
        "Differences in data, resolution and compute make cross-paper comparisons approximate.",
        "Open questions remain about robustness to new sensors and environments.",
        "Independent reproduction is the strongest test of reported results.",
    ),
    "limitations": (
        "Evaluations on a few benchmarks may not reflect performance in deployment.",
        "Models inherit the biases of the data they are trained on.",
        "Runtime on embedded hardware often goes unmeasured.",
        "Failure cases deserve as much attention as average metrics.",
    ),
    "conclusion": (
        "The contribution is summarized above, together with the evidence the runs extracted.",
        "Experiments on further datasets would test how well the results generalize.",
        "The published paper remains the reference for every statement in this preview.",
    ),
    "appendix": (
        "This page of the preview carries no text from the paper.",
        "Pages are kept so that page numbers match the evidence cited by the analyses.",
        "The published paper remains the reference for its appendices.",
    ),
}


@dataclass(frozen=True)
class _Block:
    lines: list[str]
    style: Style = Style.REGULAR
    size: float = 10.0
    leading: float = 13.6
    gray: float = 0.0
    fill: tuple[float, float, float] | None = None
    pad: float = 0.0
    space_after: float = 0.0

    @property
    def height(self) -> float:
        return len(self.lines) * self.leading + 2 * self.pad + self.space_after


class _Cursor:
    """Stacks blocks down a page; ``y`` is the top of the space that is still free."""

    def __init__(self, page: PdfPage) -> None:
        self.page = page
        self.y = TOP

    def room(self) -> float:
        return self.y - BOTTOM

    def place(self, block: _Block) -> None:
        box = len(block.lines) * block.leading + 2 * block.pad
        if block.fill is not None:
            self.page.rect(MARGIN, self.y - box, WIDTH, box, rgb=block.fill)
        x = MARGIN + (block.pad + 2 if block.fill is not None else 0)
        # Centre the glyphs in their line: half the extra leading, then the ascent.
        baseline = self.y - block.pad - (block.leading - block.size) / 2 - block.size * 0.78
        for line in block.lines:
            self.page.text(x, baseline, line, style=block.style, size=block.size, gray=block.gray)
            baseline -= block.leading
        self.y -= block.height


def evidence_by_page(analyses: Sequence[PaperAnalysisOut]) -> dict[int, list[str]]:
    """Each distinct evidence quote under the page it cites, in the order the analyses list
    them; pages after MAX_PAGES are left out."""
    pages: dict[int, list[str]] = {}
    seen: set[tuple[int, str]] = set()
    for analysis in analyses:
        for evidence in analysis.evidence:
            quote = " ".join(evidence.quote.split())
            if evidence.page > MAX_PAGES or (evidence.page, quote) in seen:
                continue
            seen.add((evidence.page, quote))
            pages.setdefault(evidence.page, []).append(quote)
    return pages


def page_count(analyses: Sequence[PaperAnalysisOut]) -> int:
    return min(MAX_PAGES, max([MIN_PAGES, *evidence_by_page(analyses)]))


def paper_pdf(paper: PaperOut, analyses: Sequence[PaperAnalysisOut]) -> bytes:
    """The preview of ``paper``; ``analyses`` newest first (their notes and evidence)."""
    quotes = evidence_by_page(analyses)
    count = page_count(analyses)
    document = PdfDocument(
        title=paper.title,
        author=", ".join(paper.authors),
        subject=f"Generated preview of {paper.paper_id}",
    )
    for number in range(1, count + 1):
        page = document.add_page()
        _chrome(page, paper, number, count)
        cursor = _Cursor(page)
        quote_blocks = [_quote(quote) for quote in quotes.get(number, [])]
        reserve = sum(block.height for block in quote_blocks)
        if number == 1:
            _front_matter(cursor, paper, reserve)
        _section(cursor, paper, analyses, number, quote_blocks, reserve)
    return document.render()


def _chrome(page: PdfPage, paper: PaperOut, number: int, count: int) -> None:
    label = "Generated preview"
    label_width = text_width(label, size=8)
    title_lines = wrap_text(paper.title, WIDTH - label_width - 24, size=8) or [""]
    title = title_lines[0] + (" ..." if len(title_lines) > 1 else "")
    page.text(MARGIN, PAGE_HEIGHT - 40, title, size=8, gray=_MUTED)
    page.text(PAGE_WIDTH - MARGIN - label_width, PAGE_HEIGHT - 40, label, size=8, gray=_MUTED)
    page.rule(MARGIN, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 48, gray=0.82)
    footer = f"Page {number} of {count}"
    page.text(MARGIN, 34, paper.paper_id, size=8, gray=_MUTED)
    page.text(PAGE_WIDTH - MARGIN - text_width(footer, size=8), 34, footer, size=8, gray=_MUTED)


def _venue_line(paper: PaperOut) -> str:
    parts = [f"{paper.venue}, {paper.year}" if paper.venue else str(paper.year)]
    if paper.doi:
        parts.append(f"DOI {paper.doi}")
    if paper.arxiv_id:
        parts.append(f"arXiv:{paper.arxiv_id}")
    return " \N{MIDDLE DOT} ".join(parts)


def _front_matter(cursor: _Cursor, paper: PaperOut, reserve: float) -> None:
    """Notice, title, authors, venue and abstract; the abstract is shortened if the page's
    evidence quotes need the room."""
    blocks = [
        _Block(
            wrap_text(_NOTICE, WIDTH - 18, size=8.5),
            size=8.5,
            leading=11.5,
            gray=0.25,
            fill=_NOTICE_FILL,
            pad=6,
            space_after=16,
        ),
        _Block(
            wrap_text(paper.title, WIDTH, Style.BOLD, 17)[:4],
            Style.BOLD,
            17,
            21,
            space_after=6,
        ),
        _Block(
            _clipped(wrap_text(", ".join(paper.authors), WIDTH, size=10.5), 3),
            size=10.5,
            leading=14,
            gray=0.15,
            space_after=4,
        ),
        _Block(
            wrap_text(_venue_line(paper), WIDTH, size=9),
            size=9,
            leading=12,
            gray=0.4,
            space_after=14,
        ),
        _Block(["Abstract"], Style.BOLD, 10.5, 15),
    ]
    for block in blocks:
        cursor.place(block)
    abstract = _Block(wrap_text(paper.abstract, WIDTH), space_after=14)
    fitting = int((cursor.room() - reserve - abstract.space_after) // abstract.leading)
    if fitting >= 1:
        cursor.place(_Block(_clipped(abstract.lines, fitting), space_after=abstract.space_after))


def _clipped(lines: list[str], limit: int) -> list[str]:
    if len(lines) <= limit:
        return lines
    return [*lines[: limit - 1], f"{lines[limit - 1]} ..."] if limit > 0 else []


def _quote(quote: str) -> _Block:
    lines = _clipped(wrap_text(quote, WIDTH - 20, Style.OBLIQUE), MAX_QUOTE_LINES)
    return _Block(lines, Style.OBLIQUE, fill=_HIGHLIGHT, pad=4, space_after=10)


def _heading(number: int) -> tuple[str, str]:
    if number <= len(_SECTIONS):
        return _SECTIONS[number - 1]
    index, letters = number - len(_SECTIONS) - 1, ""
    while True:  # A, B, ..., Z, AA, AB, ...
        index, remainder = divmod(index, 26)
        letters = chr(ord("A") + remainder) + letters
        if index == 0:
            break
        index -= 1
    return f"Appendix {letters}", "appendix"


def _section(
    cursor: _Cursor,
    paper: PaperOut,
    analyses: Sequence[PaperAnalysisOut],
    number: int,
    quote_blocks: list[_Block],
    reserve: float,
) -> None:
    """The page's section: heading and a first paragraph, the page's evidence quotes, then a
    second paragraph. Text that does not fit is left out; the quotes always come first."""
    heading, kind = _heading(number)
    rng = rng_for("paper-pdf", paper.paper_id, number)
    pool = _SENTENCES[kind]
    picked = rng.sample(pool, min(len(pool), 4))
    field = _NOTES.get(kind)
    notes = (
        [
            f"Reading notes from run {str(analysis.run_id)[:8]}: {getattr(analysis, field)}"
            for analysis in analyses[:2]
        ]
        if field
        else []
    )
    first = _Block(wrap_text(" ".join([*notes, *picked[:2]]), WIDTH), space_after=10)
    second = _Block(wrap_text(" ".join(picked[2:]), WIDTH), space_after=10) if picked[2:] else None
    title = _Block([heading], Style.BOLD, 12.5, 18, space_after=4)
    if title.height + first.height + reserve <= cursor.room():
        cursor.place(title)
        cursor.place(first)
    for block in quote_blocks:
        if block.height <= cursor.room():
            cursor.place(block)
    if second is not None and second.height <= cursor.room():
        cursor.place(second)

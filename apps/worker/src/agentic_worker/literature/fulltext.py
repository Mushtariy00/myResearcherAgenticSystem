"""Full text: open-access PDFs through the waterfall, stored by content hash, parsed into page
text (pdfium) and sections (GROBID when it runs, else one per page).

A paper keeps its stored PDF for good. A paper the waterfall found nothing for (abstract_only)
or could not fetch (failed) is looked for again only after RECHECK_AFTER.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from agentic_core.enums import PdfStatus
from agentic_db.models import Paper
from agentic_scholarly import waterfall
from agentic_scholarly.grobid import GrobidError
from agentic_scholarly.ids import (
    normalize_arxiv_id,
    normalize_doi,
    normalize_openalex_id,
    normalize_pmcid,
    normalize_s2_id,
)
from agentic_scholarly.models import PaperMeta
from agentic_scholarly.pdf import InvalidPdf, page_texts
from agentic_scholarly.storage import pdf_path, store_pdf
from agentic_worker.literature import library
from agentic_worker.literature.library import Sessions
from agentic_worker.literature.sources import Scholarly

log = logging.getLogger(__name__)

RECHECK_AFTER = timedelta(days=7)
GROBID_PARSER = "grobid-0.9.1"
PDFIUM_PARSER = "pdfium"


def stored(paper: Paper, data_dir: Path) -> bool:
    """Whether the paper's PDF is on disk."""
    return (
        paper.pdf_status == PdfStatus.AVAILABLE
        and paper.pdf_sha256 is not None
        and pdf_path(data_dir, paper.pdf_sha256).exists()
    )


def needs_fetch(paper: Paper, data_dir: Path, now: datetime) -> bool:
    if stored(paper, data_dir):
        return False
    looked_lately = paper.pdf_checked_at is not None and now - paper.pdf_checked_at < RECHECK_AFTER
    return not (looked_lately and paper.pdf_status in (PdfStatus.ABSTRACT_ONLY, PdfStatus.FAILED))


def waterfall_meta(paper: Paper, found: PaperMeta | None) -> PaperMeta:
    """The library row as the waterfall reads it. PaperMeta refuses invalid ids, so stored ids
    pass the normalisers again. The sources' PDF links come only with this attempt's search."""
    year = paper.year if paper.year is not None and 1000 <= paper.year <= 2100 else None
    return PaperMeta(
        title=paper.title,
        authors=[str(name) for name in paper.authors],
        year=year,
        doi=normalize_doi(paper.doi),
        arxiv_id=normalize_arxiv_id(paper.arxiv_id),
        s2_id=normalize_s2_id(paper.s2_id),
        openalex_id=normalize_openalex_id(paper.openalex_id),
        pmcid=normalize_pmcid(paper.pmcid),
        oa_candidates=list(found.oa_candidates) if found is not None else [],
    )


async def fetch(
    sessions: Sessions, scholarly: Scholarly, paper: Paper, found: PaperMeta | None
) -> None:
    """Look for the paper's PDF and record the outcome."""
    resolution = await waterfall.resolve(
        waterfall_meta(paper, found),
        scholarly.fetch,
        unpaywall=scholarly.unpaywall,
        core=scholarly.core,
        limiter=scholarly.limiter,
        arxiv_mutex=scholarly.arxiv_mutex,
    )
    checked_at = datetime.now(UTC)
    if resolution.pdf is None or resolution.candidate is None:
        tried = [f"{a.candidate.source}:{a.error}" for a in resolution.attempts]
        log.info("paper %s: no PDF (%s)", paper.key, ", ".join(tried) or "no candidates")
        status = PdfStatus.FAILED if resolution.attempts else PdfStatus.ABSTRACT_ONLY
        await library.record_pdf(sessions, paper.id, status=status, checked_at=checked_at)
        return
    # Writing and fsyncing a file blocks; keep it off the event loop.
    sha256, _ = await asyncio.to_thread(store_pdf, scholarly.data_dir, resolution.pdf.data)
    await library.record_pdf(
        sessions,
        paper.id,
        status=PdfStatus.AVAILABLE,
        checked_at=checked_at,
        sha256=sha256,
        source=resolution.candidate.source,
        # The link from the metadata: the final URL after redirects may carry expiring tokens.
        url=resolution.candidate.url,
    )


async def parse(
    sessions: Sessions, scholarly: Scholarly, paper: Paper, *, grobid: asyncio.Lock | None
) -> None:
    """Store the text of the paper's PDF: pages from pdfium, sections from GROBID when a lock
    is given (GROBID parses one document at a time), else from the pages."""
    if paper.pdf_sha256 is None:
        return
    data = await asyncio.to_thread(pdf_path(scholarly.data_dir, paper.pdf_sha256).read_bytes)
    try:
        pages = await asyncio.to_thread(page_texts, data)
    except InvalidPdf as exc:
        log.warning("paper %s: the stored PDF does not open (%s)", paper.key, exc)
        return
    parser = PDFIUM_PARSER
    sections: list[dict[str, Any]] = [
        {"title": None, "text": page} for page in pages if page.strip()
    ]
    references: list[dict[str, Any]] = []
    if grobid is not None:
        try:
            async with grobid:
                document = await scholarly.grobid.fulltext(data)
        except GrobidError as exc:
            log.warning("paper %s: GROBID failed (%s); sections from the pages", paper.key, exc)
        else:
            if document.sections:
                parser = GROBID_PARSER
                sections = [section.model_dump() for section in document.sections]
                references = [reference.model_dump() for reference in document.references]
    await library.add_paper_text(
        sessions, paper.id, parser=parser, pages=pages, sections=sections, references=references
    )

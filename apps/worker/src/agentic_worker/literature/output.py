"""The stage output, built from the library rows: what the reviewer sees and approves."""

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from agentic_core.demo import SOURCE_LABELS
from agentic_core.enums import PdfStatus
from agentic_core.schemas import (
    LiteratureOutput,
    PaperAnalysis,
    PaperFinding,
    PaperRef,
    ResearchPlan,
)
from agentic_db.library import SEARCH_ORDER
from agentic_db.models import PaperText
from agentic_worker.literature.analysis import has_text
from agentic_worker.literature.library import Candidate
from agentic_worker.literature.synthesis import Finding

# Degraded reasons the web shows (stage_outputs.degraded_reason).
PARTIAL_SEARCH_REASON = "literature.partial_search"
NO_FULL_TEXT_REASON = "literature.no_full_text"


def _https(url: str | None) -> str | None:
    return url if url is not None and url.startswith("https://") else None


def best_source(hits: Sequence[Mapping[str, Any]]) -> str:
    """The source of the paper's best hit: the lowest position, ties going to the source searched
    first. The paper library applies the same rule (agentic_db.library)."""

    def order(hit: Mapping[str, Any]) -> tuple[int, int]:
        source = hit["source"]
        searched = SEARCH_ORDER.index(source) if source in SEARCH_ORDER else len(SEARCH_ORDER)
        return int(hit["position"]), searched

    return str(min(hits, key=order)["source"])


def paper_ref(candidate: Candidate) -> PaperRef:
    paper, entry = candidate.paper, candidate.entry
    return PaperRef.model_validate(
        {
            "paper_id": paper.key,
            "title": paper.title,
            "authors": list(paper.authors),
            "year": paper.year,
            "venue": paper.venue,
            "doi": paper.doi,
            "arxiv_id": paper.arxiv_id,
            "url": _https(paper.url),
            "abstract": paper.abstract,
            "citation_count": paper.citation_count,
            "source": best_source(entry.hits),
            "pdf_available": paper.pdf_status == PdfStatus.AVAILABLE,
            "relevance": entry.relevance,
            "decision": entry.decision,
            "decision_reason": entry.decision_reason,
        }
    )


def finding(candidate: Candidate, found: Finding) -> PaperFinding:
    paper = candidate.paper
    return PaperFinding(
        title=paper.title,
        source=SOURCE_LABELS[best_source(candidate.entry.hits)],
        summary=found.summary,
        url=_https(paper.url),
        paper_id=paper.key,
    )


def degraded_reason(
    failed_sources: Sequence[str],
    included: Sequence[Candidate],
    texts: Mapping[uuid.UUID, PaperText],
) -> str | None:
    """partial_search when a source failed, else no_full_text when no included paper has its
    full text (nothing included counts too), else None."""
    if failed_sources:
        return PARTIAL_SEARCH_REASON
    if not any(has_text(texts.get(candidate.paper.id)) for candidate in included):
        return NO_FULL_TEXT_REASON
    return None


def literature_output(
    plan: ResearchPlan,
    selected: Sequence[Candidate],
    reading: Sequence[Candidate],
    findings: Sequence[Finding],
    synthesis: str,
) -> LiteratureOutput:
    """``reading`` is what the synthesis numbered (1 is the first); findings point into it."""
    return LiteratureOutput(
        plan=plan,
        papers=[paper_ref(candidate) for candidate in selected],
        analyses=[
            PaperAnalysis.model_validate(candidate.entry.analysis)
            for candidate in selected
            if candidate.entry.analysis is not None
        ],
        key_findings=[finding(reading[found.paper - 1], found) for found in findings],
        synthesis=synthesis,
    )

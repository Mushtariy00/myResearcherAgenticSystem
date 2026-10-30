"""The paper library: the papers that the literature stages of the caller's runs screened.

Paper ids contain slashes (``doi:10.5555/...``), so they are path parameters of the ``path``
kind; the file route is declared first so that ``.../file`` reaches it.
"""

import logging
import pathlib
import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_api.auth import CurrentUser, current_user
from agentic_api.authz import get_db, load_project, membership_scope
from agentic_api.demo.paper_pdf import paper_pdf
from agentic_api.files import binary_response, file_response, path_response, safe_filename
from agentic_api.schemas import (
    LibraryPaperOut,
    PaperAnalysisOut,
    PaperDetail,
    PaperOut,
    PaperPage,
    PaperRunOut,
)
from agentic_core.enums import PdfStatus
from agentic_core.schemas import PaperAnalysis, PaperSource, ScreeningDecision
from agentic_db.library import LibraryFilter, LibraryPaper, library_page, library_paper
from agentic_scholarly.storage import pdf_path

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/papers", tags=["papers"])
User = Annotated[CurrentUser, Depends(current_user)]
Db = Annotated[AsyncSession, Depends(get_db)]
PaperId = Annotated[str, Path(min_length=1, max_length=300)]
DECISION_ORDER: tuple[ScreeningDecision, ...] = ("include", "maybe", "exclude")
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _stored_sha256(paper: LibraryPaper) -> str | None:
    """The SHA-256 that names the paper's stored PDF, if it has one. Paths to files are built
    only from this checked value, never from anything in the request."""
    sha256 = paper.pdf_sha256
    if paper.pdf_status is PdfStatus.AVAILABLE and sha256 and _SHA256.fullmatch(sha256):
        return sha256
    return None


def _pdf_available(paper: LibraryPaper) -> bool:
    """Whether the viewer can show a PDF: a stored file or, for a seeded demo paper marked
    available (it has no file), the generated preview."""
    return paper.pdf_status is PdfStatus.AVAILABLE and (
        paper.demo or _stored_sha256(paper) is not None
    )


def _paper_out(paper: LibraryPaper) -> PaperOut | None:
    """A stored paper as the API shows it; None (and a warning) if it does not validate."""
    try:
        return PaperOut.model_validate(
            {
                "paper_id": paper.key,
                "title": paper.title,
                "authors": paper.authors,
                "year": paper.year,
                "venue": paper.venue,
                "doi": paper.doi,
                "arxiv_id": paper.arxiv_id,
                "url": paper.url,
                "abstract": paper.abstract or "",
                "citation_count": paper.citation_count,
                # The seed records no hit for a demo paper whose source is not one the search
                # uses (such as CORE).
                "source": paper.source or ("demo" if paper.demo else None),
                "pdf_available": _pdf_available(paper),
            }
        )
    except ValidationError:
        log.warning("a stored paper does not validate: %s", paper.key[:300])
        return None


@router.get("", operation_id="listPapers")
async def list_papers(
    user: User,
    db: Db,
    q: Annotated[str | None, Query(max_length=200)] = None,
    project_id: uuid.UUID | None = None,
    year_from: Annotated[int | None, Query(ge=1900, le=2100)] = None,
    year_to: Annotated[int | None, Query(ge=1900, le=2100)] = None,
    decision: ScreeningDecision | None = None,
    source: PaperSource | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> PaperPage:
    """Papers that the caller's runs screened (every project's for lab admins), best relevance
    first.

    ``q`` searches the title, abstract and parsed full text (web search syntax: quotes, ``or``,
    ``-word``), best matches first; a case-insensitive substring of the title, abstract, an
    author or the venue also matches. Decision and source match when one run's screening has
    both; counts cover all of its runs in scope.
    """
    if year_from is not None and year_to is not None and year_from > year_to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "papers.invalid_year_range")
    if project_id is not None:
        await load_project(db, project_id, user)
    entries, total = await library_page(
        db,
        member_id=membership_scope(user),
        project_id=project_id,
        filters=LibraryFilter(
            q=(q or "").strip() or None,
            year_from=year_from,
            year_to=year_to,
            decision=decision,
            source=source,
        ),
        limit=limit,
        offset=offset,
    )
    items = []
    for entry in entries:
        paper = _paper_out(entry.paper)
        if paper is None:
            continue
        items.append(
            LibraryPaperOut(
                paper=paper,
                run_count=entry.run_count,
                project_count=entry.project_count,
                best_relevance=entry.best_relevance,
                decisions=[d for d in DECISION_ORDER if d in entry.decisions],
                last_seen_at=entry.last_seen_at,
                demo=entry.paper.demo,
            )
        )
    return PaperPage(items=items, total=total, demo=any(item.demo for item in items))


def _not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "paper.not_found")


async def _paper_detail(
    db: AsyncSession, paper_id: str, user: CurrentUser
) -> tuple[LibraryPaper, PaperDetail]:
    found = await library_paper(db, paper_id, member_id=membership_scope(user))
    if found is None:
        raise _not_found()
    paper, appearances = found
    paper_out = _paper_out(paper)
    if paper_out is None:
        raise _not_found()

    runs: dict[uuid.UUID, PaperRunOut] = {}
    analyses: list[PaperAnalysisOut] = []
    for appearance in appearances:  # newest first
        if appearance.run_id not in runs:
            runs[appearance.run_id] = PaperRunOut(
                id=appearance.run_id,
                topic=appearance.run_topic,
                status=appearance.run_status,
                project_id=appearance.project_id,
                project_name=appearance.project_name,
                created_at=appearance.run_created_at,
                relevance=appearance.relevance,
                decision=appearance.decision,
                decision_reason=appearance.decision_reason or "",
                demo=paper.demo,
            )
        published = appearance.analysis
        if published is None:
            continue
        try:
            analysis = PaperAnalysis.model_validate(published.data)
        except ValidationError:
            log.warning("a stored analysis does not validate (output %s)", published.output_id)
            continue
        analyses.append(
            PaperAnalysisOut(
                run_id=appearance.run_id,
                stage_output_id=published.output_id,
                attempt=appearance.attempt,
                created_at=published.output_created_at,
                contribution=analysis.contribution,
                method=analysis.method,
                results=analysis.results,
                limitations=analysis.limitations,
                evidence=analysis.evidence,
                demo=paper.demo,
            )
        )
    detail = PaperDetail(
        paper=paper_out,
        best_relevance=max(appearance.relevance for appearance in appearances),
        runs=list(runs.values()),
        analyses=analyses,
        demo=paper.demo,
    )
    return paper, detail


@router.get(
    "/{paper_id:path}/file",
    operation_id="getPaperFile",
    response_class=StreamingResponse,
    responses=binary_response("application/pdf"),
)
async def get_paper_file(
    paper_id: PaperId, request: Request, user: User, db: Db
) -> StreamingResponse:
    """The paper's PDF as the library stores it. A seeded demo paper without a stored file
    gets a generated preview instead; any other paper without one is not found.

    The preview has the paper's metadata and abstract, and prints every evidence quote of its
    analyses on the page the quote cites, so the viewer can find and highlight it there.
    """
    paper, detail = await _paper_detail(db, paper_id, user)
    # An attachment like every file: the viewer fetches the bytes itself (pdf.js), and a PDF
    # opened directly would meet the API's deny-all CSP, which can blank the browser's viewer.
    filename = f"{safe_filename(paper_id, 'paper')}.pdf"
    sha256 = _stored_sha256(paper)
    if sha256 is not None:
        data_dir: pathlib.Path = request.app.state.settings.data_dir
        try:
            return path_response(
                pdf_path(data_dir, sha256), media_type="application/pdf", filename=filename
            )
        except FileNotFoundError:
            log.warning("the stored PDF of %s is missing", paper.key[:300])
    if not paper.demo:
        raise _not_found()
    return file_response(
        paper_pdf(detail.paper, detail.analyses), media_type="application/pdf", filename=filename
    )


@router.get("/{paper_id:path}", operation_id="getPaper")
async def get_paper(paper_id: PaperId, user: User, db: Db) -> PaperDetail:
    """The paper, every analysis of it and the runs that found it (404 when the caller can open
    none of them)."""
    _, detail = await _paper_detail(db, paper_id, user)
    return detail

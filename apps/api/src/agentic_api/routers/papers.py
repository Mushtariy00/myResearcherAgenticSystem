"""The paper library: papers from the literature outputs of every run the caller can open.

Paper ids contain slashes (``doi:10.5555/...``), so they are path parameters of the ``path``
kind; the file route is declared first so that ``.../file`` reaches it.
"""

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_api.auth import CurrentUser, current_user
from agentic_api.authz import get_db, load_project, membership_scope
from agentic_api.demo import is_demo_reason
from agentic_api.demo.paper_pdf import paper_pdf
from agentic_api.files import binary_response, file_response, safe_filename
from agentic_api.schemas import (
    LibraryPaperOut,
    PaperAnalysisOut,
    PaperDetail,
    PaperOut,
    PaperPage,
    PaperRunOut,
)
from agentic_core.schemas import PaperAnalysis, PaperRef, PaperSource, ScreeningDecision
from agentic_db.library import LibraryFilter, library_page, paper_appearances

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/papers", tags=["papers"])
User = Annotated[CurrentUser, Depends(current_user)]
Db = Annotated[AsyncSession, Depends(get_db)]
PaperId = Annotated[str, Path(min_length=1, max_length=300)]
DECISION_ORDER: tuple[ScreeningDecision, ...] = ("include", "maybe", "exclude")
_PAPER_FIELDS = set(PaperOut.model_fields)


def _paper_ref(data: dict[str, Any]) -> PaperRef | None:
    """A stored paper as the strict schema reads it; None (and a warning) if it no longer does."""
    try:
        return PaperRef.model_validate(data)
    except ValidationError:
        log.warning("a stored paper does not validate: %s", str(data.get("paper_id"))[:300])
        return None


def _paper_out(paper: PaperRef) -> PaperOut:
    return PaperOut.model_validate(paper.model_dump(include=_PAPER_FIELDS))


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
    """Papers of the caller's projects (every project for lab admins), best relevance first.

    ``q`` matches title, abstract, an author or the venue, ignoring case. A paper matches when
    one run's record of it matches every filter; counts cover all of its runs in scope.
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
        paper = _paper_ref(entry.paper)
        if paper is None:
            continue
        items.append(
            LibraryPaperOut(
                paper=_paper_out(paper),
                run_count=entry.run_count,
                project_count=entry.project_count,
                best_relevance=entry.best_relevance,
                decisions=[d for d in DECISION_ORDER if d in entry.decisions],
                last_seen_at=entry.last_seen_at,
                demo=any(is_demo_reason(reason) for reason in entry.degraded_reasons),
            )
        )
    return PaperPage(items=items, total=total, demo=any(item.demo for item in items))


async def _paper_detail(db: AsyncSession, paper_id: str, user: CurrentUser) -> PaperDetail:
    appearances = await paper_appearances(db, paper_id, member_id=membership_scope(user))
    refs = [_paper_ref(appearance.paper) for appearance in appearances]
    newest = next((ref for ref in refs if ref is not None), None)
    if newest is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "paper.not_found")

    runs: dict[uuid.UUID, PaperRunOut] = {}
    analyses: list[PaperAnalysisOut] = []
    for appearance, ref in zip(appearances, refs, strict=True):  # newest first
        demo = is_demo_reason(appearance.degraded_reason)
        if ref is not None and appearance.run_id not in runs:
            runs[appearance.run_id] = PaperRunOut(
                id=appearance.run_id,
                topic=appearance.run_topic,
                status=appearance.run_status,
                project_id=appearance.project_id,
                project_name=appearance.project_name,
                created_at=appearance.run_created_at,
                relevance=ref.relevance,
                decision=ref.decision,
                decision_reason=ref.decision_reason,
                demo=demo,
            )
        if appearance.analysis is None:
            continue
        try:
            analysis = PaperAnalysis.model_validate(appearance.analysis)
        except ValidationError:
            log.warning(
                "a stored analysis does not validate (output %s)", appearance.stage_output_id
            )
            continue
        analyses.append(
            PaperAnalysisOut(
                run_id=appearance.run_id,
                stage_output_id=appearance.stage_output_id,
                attempt=appearance.attempt,
                created_at=appearance.created_at,
                contribution=analysis.contribution,
                method=analysis.method,
                results=analysis.results,
                limitations=analysis.limitations,
                evidence=analysis.evidence,
                demo=demo,
            )
        )
    return PaperDetail(
        paper=_paper_out(newest),
        best_relevance=max(ref.relevance for ref in refs if ref is not None),
        runs=list(runs.values()),
        analyses=analyses,
        demo=any(is_demo_reason(appearance.degraded_reason) for appearance in appearances),
    )


@router.get(
    "/{paper_id:path}/file",
    operation_id="getPaperFile",
    response_class=StreamingResponse,
    responses=binary_response("application/pdf"),
)
async def get_paper_file(paper_id: PaperId, user: User, db: Db) -> StreamingResponse:
    """A generated PDF preview of the paper (always demo content: no PDFs are stored yet).

    It has the paper's metadata and abstract, and prints every evidence quote of its analyses
    on the page the quote cites, so the viewer can find and highlight it there.
    """
    detail = await _paper_detail(db, paper_id, user)
    # An attachment like every file: the viewer fetches the bytes itself (pdf.js), and a PDF
    # opened directly would meet the API's deny-all CSP, which can blank the browser's viewer.
    return file_response(
        paper_pdf(detail.paper, detail.analyses),
        media_type="application/pdf",
        filename=f"{safe_filename(paper_id, 'paper')}.pdf",
    )


@router.get("/{paper_id:path}", operation_id="getPaper")
async def get_paper(paper_id: PaperId, user: User, db: Db) -> PaperDetail:
    """The paper, every analysis of it and the runs that found it (404 when the caller can open
    none of them)."""
    return await _paper_detail(db, paper_id, user)

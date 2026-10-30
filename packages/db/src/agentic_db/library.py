"""The paper library: every paper a literature stage screened, stored once across runs.

``papers`` holds each paper once and ``paper_texts`` its parsed full text. A literature stage
attempt records the papers it ranked in ``run_papers``; a row that also has its screening (a
decision and a relevance) is an *appearance* of the paper, and the library is the papers with
at least one visible appearance. Pass ``member_id`` to see only the runs of projects that user
belongs to, or None for every project (lab admins). Papers without a publication year are left
out, because the API's paper record requires one.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, get_args

from sqlalchemy import (
    CTE,
    Float,
    Subquery,
    Text,
    case,
    column,
    func,
    literal,
    literal_column,
    or_,
    select,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB, aggregate_order_by, array
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import QueryableAttribute
from sqlalchemy.sql.elements import ColumnElement

from agentic_core.enums import PdfStatus, RunStatus
from agentic_core.schemas import ScreeningDecision
from agentic_db.models import (
    Paper,
    PaperText,
    Project,
    ProjectMember,
    Run,
    RunPaper,
    StageOutput,
    StageRun,
)

SCREENING_DECISIONS: tuple[str, ...] = get_args(ScreeningDecision)
# The order the literature stage searches its sources in (agentic_scholarly.models.SOURCE_NAMES).
SEARCH_ORDER = ("openalex", "semantic_scholar", "arxiv", "crossref")
_PAPER_COLUMNS = (
    Paper.key,
    Paper.title,
    Paper.authors,
    Paper.year,
    Paper.venue,
    Paper.doi,
    Paper.arxiv_id,
    Paper.url,
    Paper.abstract,
    Paper.citation_count,
    Paper.demo,
    Paper.pdf_status,
    Paper.pdf_sha256,
)


@dataclass(frozen=True)
class LibraryFilter:
    """A paper matches when its record matches ``q`` and the years, and one of its appearances
    in scope matches both ``decision`` and ``source``."""

    # Full-text search in web search syntax over the title, the abstract and the parsed text;
    # a case-insensitive substring of the title, the abstract, an author or the venue matches too.
    q: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    decision: str | None = None  # screening decision
    source: str | None = None  # where the attempt found the paper (its best hit's source)


@dataclass(frozen=True)
class LibraryPaper:
    """A paper's record in ``papers``, with where its newest appearance found it."""

    key: str
    title: str
    authors: list[Any]
    year: int
    venue: str | None
    doi: str | None
    arxiv_id: str | None
    url: str | None
    abstract: str | None
    citation_count: int | None
    source: str | None  # None when no appearance has a hit
    demo: bool
    pdf_status: PdfStatus
    pdf_sha256: str | None


@dataclass(frozen=True)
class LibraryEntry:
    paper: LibraryPaper
    run_count: int
    project_count: int
    best_relevance: float
    decisions: tuple[str, ...]  # every screening decision it got, unordered
    last_seen_at: datetime  # when the newest attempt that screened it found it


@dataclass(frozen=True)
class PublishedAnalysis:
    """An attempt's analysis of a paper, with the latest output version of the attempt."""

    data: dict[str, Any]  # agentic_core.schemas.PaperAnalysis as JSON
    output_id: uuid.UUID
    output_created_at: datetime


@dataclass(frozen=True)
class PaperAppearance:
    stage_run_id: uuid.UUID
    attempt: int
    relevance: float
    decision: ScreeningDecision
    decision_reason: str | None
    # None while the attempt has no analysis of the paper or no output to publish it in yet.
    analysis: PublishedAnalysis | None
    run_id: uuid.UUID
    run_topic: str
    run_status: RunStatus
    run_created_at: datetime
    project_id: uuid.UUID
    project_name: str


def escape_like(value: str) -> str:
    """``value`` as a literal inside a LIKE pattern (escape character: backslash)."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _array(value: QueryableAttribute[Any]) -> ColumnElement[Any]:
    """``value`` when it is a JSON array, else an empty one, so element functions never fail."""
    return case((func.jsonb_typeof(value) == "array", value), else_=func.jsonb_build_array())


def _best_source() -> ColumnElement[str]:
    """Where a run_papers row's paper was found, as the stage output's PaperRef says: the
    source of its hit at the lowest position, ties going to the source searched first."""
    hit = (
        func.jsonb_array_elements(_array(RunPaper.hits))
        .table_valued(column("value", JSONB))
        .render_derived(name="hit")
    )
    source = hit.c.value["source"].astext
    position = case(
        (
            func.jsonb_typeof(hit.c.value["position"]) == "number",
            hit.c.value["position"].astext.cast(Float),
        )
    )
    return (
        select(source)
        .where(func.jsonb_typeof(hit.c.value["source"]) == "string")
        .order_by(
            position.nulls_last(), func.array_position(array(SEARCH_ORDER), source).nulls_last()
        )
        .limit(1)
        .scalar_subquery()
    )


def _visible(member_id: str | None) -> list[ColumnElement[bool]]:
    """Conditions on run_papers (joined with runs) that keep the appearances ``member_id`` may
    see: screened rows of runs in that member's projects."""
    conditions: list[ColumnElement[bool]] = [
        RunPaper.decision.in_(SCREENING_DECISIONS),
        RunPaper.relevance.is_not(None),
    ]
    if member_id is not None:
        member_of = select(ProjectMember.project_id).where(ProjectMember.user_id == member_id)
        conditions.append(Run.project_id.in_(member_of))
    return conditions


def _library_paper(row: Any, source: str | None) -> LibraryPaper:
    return LibraryPaper(
        key=row.key,
        title=row.title,
        authors=row.authors,
        year=row.year,
        venue=row.venue,
        doi=row.doi,
        arxiv_id=row.arxiv_id,
        url=row.url,
        abstract=row.abstract,
        citation_count=row.citation_count,
        source=source,
        demo=row.demo,
        pdf_status=row.pdf_status,
        pdf_sha256=row.pdf_sha256,
    )


def _appearances(member_id: str | None, project_id: uuid.UUID | None) -> CTE:
    query = (
        select(
            RunPaper.paper_id,
            RunPaper.stage_run_id,
            RunPaper.run_id,
            Run.project_id,
            RunPaper.relevance,
            RunPaper.decision,
            _best_source().label("source"),
            RunPaper.created_at,
        )
        .join(Run, Run.id == RunPaper.run_id)
        .where(*_visible(member_id))
    )
    if project_id is not None:
        query = query.where(Run.project_id == project_id)
    return query.cte("appearance")


def _matching(appearance: CTE, filters: LibraryFilter) -> Subquery:
    """The ids of the matching papers, with how well each matches ``q`` (0 without one)."""
    in_scope = select(appearance.c.paper_id)
    if filters.decision is not None:
        in_scope = in_scope.where(appearance.c.decision == filters.decision)
    if filters.source is not None:
        in_scope = in_scope.where(appearance.c.source == filters.source)
    query = select(Paper.id).where(Paper.year.is_not(None), Paper.id.in_(in_scope))
    if filters.year_from is not None:
        query = query.where(Paper.year >= filters.year_from)
    if filters.year_to is not None:
        query = query.where(Paper.year <= filters.year_to)
    if not filters.q:
        return query.add_columns(literal(0.0).label("text_rank")).subquery("matching")

    terms = func.websearch_to_tsquery("english", filters.q)
    # A subquery of its own, so the parsed text is searched through its index and only the
    # texts of matching papers are read.
    in_text = select(PaperText.paper_id).where(PaperText.tsv.bool_op("@@")(terms))
    pattern = f"%{escape_like(filters.q)}%"
    author = (
        func.jsonb_array_elements_text(_array(Paper.authors))
        .table_valued(column("value", Text))
        .render_derived(name="author")
    )
    query = query.where(
        or_(
            Paper.search.bool_op("@@")(terms),
            Paper.id.in_(in_text),
            Paper.title.ilike(pattern, escape="\\"),
            Paper.abstract.ilike(pattern, escape="\\"),
            Paper.venue.ilike(pattern, escape="\\"),
            select(author.c.value).where(author.c.value.ilike(pattern, escape="\\")).exists(),
        )
    )
    # A match in the title or abstract weighs ten times one in the parsed text (ts_rank's
    # default weights for A and D).
    record_rank = func.ts_rank(func.setweight(Paper.search, literal_column("'A'")), terms)
    body_rank = (
        select(func.ts_rank(PaperText.tsv, terms))
        .where(PaperText.paper_id == Paper.id)
        .scalar_subquery()
    )
    text_rank = record_rank + func.coalesce(body_rank, 0)
    return query.add_columns(text_rank.label("text_rank")).subquery("matching")


async def library_page(
    session: AsyncSession,
    *,
    member_id: str | None,
    project_id: uuid.UUID | None = None,
    filters: LibraryFilter | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[LibraryEntry], int]:
    """One page of matching papers and the number of matching papers.

    With ``q``, the best full-text matches come first; otherwise, and among equal matches, the
    best relevance, then the most recently found. Counts, decisions and relevance cover every
    appearance in scope (``project_id`` narrows the scope to one project), not only the
    appearances that matched the filters.
    """
    appearance = _appearances(member_id, project_id)
    matching = _matching(appearance, filters or LibraryFilter())
    total = await session.scalar(select(func.count()).select_from(matching))

    best = func.max(appearance.c.relevance)
    last_seen = func.max(appearance.c.created_at)
    newest_source = func.array_agg(
        aggregate_order_by(
            appearance.c.source, appearance.c.created_at.desc(), appearance.c.stage_run_id.desc()
        )
    ).filter(appearance.c.source.is_not(None))
    rows = await session.execute(
        select(
            *_PAPER_COLUMNS,
            newest_source[1].label("source"),
            func.count(appearance.c.run_id.distinct()).label("run_count"),
            func.count(appearance.c.project_id.distinct()).label("project_count"),
            best.label("best_relevance"),
            func.array_agg(appearance.c.decision.distinct()).label("decisions"),
            last_seen.label("last_seen_at"),
        )
        .select_from(matching)
        .join(Paper, Paper.id == matching.c.id)
        .join(appearance, appearance.c.paper_id == Paper.id)
        .group_by(Paper.id, matching.c.text_rank)
        .order_by(matching.c.text_rank.desc(), best.desc(), last_seen.desc(), Paper.key)
        .limit(limit)
        .offset(offset)
    )
    entries = [
        LibraryEntry(
            paper=_library_paper(row, row.source),
            run_count=row.run_count,
            project_count=row.project_count,
            best_relevance=row.best_relevance,
            decisions=tuple(row.decisions),
            last_seen_at=row.last_seen_at,
        )
        for row in rows
    ]
    return entries, total or 0


async def library_paper(
    session: AsyncSession, key: str, *, member_id: str | None
) -> tuple[LibraryPaper, list[PaperAppearance]] | None:
    """One paper and every visible appearance of it, newest first; None when there is none."""
    latest_output = (
        select(StageOutput.id, StageOutput.created_at)
        .where(StageOutput.stage_run_id == RunPaper.stage_run_id)
        .order_by(StageOutput.version.desc())
        .limit(1)
        .lateral("latest_output")
    )
    query = (
        select(
            *_PAPER_COLUMNS,
            _best_source().label("source"),
            RunPaper.stage_run_id,
            RunPaper.relevance,
            RunPaper.decision,
            RunPaper.decision_reason,
            RunPaper.analysis,
            StageRun.attempt,
            latest_output.c.id.label("output_id"),
            latest_output.c.created_at.label("output_created_at"),
            Run.id.label("run_id"),
            Run.topic,
            Run.status,
            Run.created_at.label("run_created_at"),
            Project.id.label("project_id"),
            Project.name.label("project_name"),
        )
        .select_from(Paper)
        .join(RunPaper, RunPaper.paper_id == Paper.id)
        .join(StageRun, StageRun.id == RunPaper.stage_run_id)
        .join(Run, Run.id == RunPaper.run_id)
        .join(Project, Project.id == Run.project_id)
        .outerjoin(latest_output, true())
        .where(Paper.key == key, Paper.year.is_not(None), *_visible(member_id))
        .order_by(RunPaper.created_at.desc(), RunPaper.stage_run_id.desc())
    )
    rows = (await session.execute(query)).all()
    if not rows:
        return None
    source = next((row.source for row in rows if row.source is not None), None)
    appearances = [
        PaperAppearance(
            stage_run_id=row.stage_run_id,
            attempt=row.attempt,
            relevance=row.relevance,
            decision=row.decision,
            decision_reason=row.decision_reason,
            analysis=(
                None
                if row.analysis is None or row.output_id is None
                else PublishedAnalysis(row.analysis, row.output_id, row.output_created_at)
            ),
            run_id=row.run_id,
            run_topic=row.topic,
            run_status=RunStatus(row.status),
            run_created_at=row.run_created_at,
            project_id=row.project_id,
            project_name=row.project_name,
        )
        for row in rows
    ]
    return _library_paper(rows[0], source), appearances

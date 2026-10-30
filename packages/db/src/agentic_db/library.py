"""The paper library: the papers of literature stage outputs, de-duplicated across runs.

Every literature stage run contributes the papers of its latest output version
(``data->'papers'``, agentic_core.schemas.PaperRef objects). One (output, paper) pair is an
*appearance*; the library groups appearances by ``paper_id``. Pass ``member_id`` to see only
the projects that user belongs to, or None for every project (lab admins).
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CTE,
    Float,
    Numeric,
    Subquery,
    Text,
    case,
    column,
    func,
    or_,
    select,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB, aggregate_order_by, distinct_on
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from agentic_core.enums import RunStatus
from agentic_core.stages import Stage
from agentic_db.models import Project, ProjectMember, Run, StageOutput, StageRun


@dataclass(frozen=True)
class LibraryFilter:
    """A paper matches when at least one of its appearances matches every given filter."""

    q: str | None = None  # case-insensitive substring of title, abstract, an author or venue
    year_from: int | None = None
    year_to: int | None = None
    decision: str | None = None  # screening decision
    source: str | None = None


@dataclass(frozen=True)
class LibraryEntry:
    paper_id: str
    paper: dict[str, Any]  # the paper as its newest appearance stores it
    run_count: int
    project_count: int
    best_relevance: float | None
    decisions: tuple[str, ...]  # every screening decision it got, unordered
    degraded_reasons: tuple[str, ...]  # of the outputs it appears in (empty: none degraded)
    last_seen_at: datetime  # when its newest appearance was stored


@dataclass(frozen=True)
class PaperAppearance:
    stage_output_id: uuid.UUID
    attempt: int
    created_at: datetime
    degraded_reason: str | None
    paper: dict[str, Any]
    analysis: dict[str, Any] | None  # the output's analysis of the paper, if it has one
    run_id: uuid.UUID
    run_topic: str
    run_status: RunStatus
    run_created_at: datetime
    project_id: uuid.UUID
    project_name: str


def escape_like(value: str) -> str:
    """``value`` as a literal inside a LIKE pattern (escape character: backslash)."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _array(value: ColumnElement[Any]) -> ColumnElement[Any]:
    """``value`` when it is a JSON array, else an empty one, so element functions never fail."""
    return case((func.jsonb_typeof(value) == "array", value), else_=func.jsonb_build_array())


def _latest_literature(member_id: str | None, project_id: uuid.UUID | None) -> Subquery:
    """The latest output version of every visible literature stage run."""
    query = (
        select(
            StageOutput.id.label("output_id"),
            StageOutput.data.label("data"),
            StageOutput.degraded_reason.label("degraded_reason"),
            StageOutput.created_at.label("created_at"),
            StageRun.attempt.label("attempt"),
            StageRun.run_id.label("run_id"),
            Run.project_id.label("project_id"),
        )
        .join(StageRun, StageRun.id == StageOutput.stage_run_id)
        .join(Run, Run.id == StageRun.run_id)
        .where(StageRun.stage == Stage.LITERATURE.value)
        .ext(distinct_on(StageOutput.stage_run_id))
        .order_by(StageOutput.stage_run_id, StageOutput.version.desc())
    )
    if member_id is not None:
        member_of = select(ProjectMember.project_id).where(ProjectMember.user_id == member_id)
        query = query.where(Run.project_id.in_(member_of))
    if project_id is not None:
        query = query.where(Run.project_id == project_id)
    return query.subquery("latest")


def _appearances(member_id: str | None, project_id: uuid.UUID | None) -> CTE:
    latest = _latest_literature(member_id, project_id)
    element = (
        func.jsonb_array_elements(_array(latest.c.data["papers"]))
        .table_valued(column("value", JSONB))
        .render_derived(name="element")
    )
    paper = element.c.value
    return (
        select(
            latest.c.output_id,
            latest.c.run_id,
            latest.c.project_id,
            latest.c.created_at,
            latest.c.degraded_reason,
            paper["paper_id"].astext.label("paper_id"),
            paper.label("paper"),
            case(
                (
                    func.jsonb_typeof(paper["relevance"]) == "number",
                    paper["relevance"].astext.cast(Float),
                )
            ).label("relevance"),
            paper["decision"].astext.label("decision"),
        )
        .select_from(latest)
        .join(element, true())
        .where(
            func.jsonb_typeof(paper) == "object",
            func.jsonb_typeof(paper["paper_id"]) == "string",
            paper["paper_id"].astext != "",
        )
        .cte("appearance")
    )


def _conditions(appearance: CTE, filters: LibraryFilter) -> list[ColumnElement[bool]]:
    paper = appearance.c.paper
    conditions: list[ColumnElement[bool]] = []
    if filters.q:
        pattern = f"%{escape_like(filters.q)}%"
        author = (
            func.jsonb_array_elements_text(_array(paper["authors"]))
            .table_valued(column("value", Text))
            .render_derived(name="author")
        )
        conditions.append(
            or_(
                paper["title"].astext.ilike(pattern, escape="\\"),
                paper["abstract"].astext.ilike(pattern, escape="\\"),
                paper["venue"].astext.ilike(pattern, escape="\\"),
                select(author.c.value).where(author.c.value.ilike(pattern, escape="\\")).exists(),
            )
        )
    year = case((func.jsonb_typeof(paper["year"]) == "number", paper["year"].astext.cast(Numeric)))
    if filters.year_from is not None:
        conditions.append(year >= filters.year_from)
    if filters.year_to is not None:
        conditions.append(year <= filters.year_to)
    if filters.decision is not None:
        conditions.append(paper["decision"].astext == filters.decision)
    if filters.source is not None:
        conditions.append(paper["source"].astext == filters.source)
    return conditions


async def library_page(
    session: AsyncSession,
    *,
    member_id: str | None,
    project_id: uuid.UUID | None = None,
    filters: LibraryFilter | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[LibraryEntry], int]:
    """One page of matching papers, best relevance first, and the number of matching papers.

    Counts, decisions and relevance cover every appearance in scope (``project_id`` narrows the
    scope to one project), not only the appearances that matched the filters.
    """
    appearance = _appearances(member_id, project_id)
    matching = (
        select(appearance.c.paper_id)
        .where(*_conditions(appearance, filters or LibraryFilter()))
        .distinct()
        .subquery("matching")
    )
    total = await session.scalar(select(func.count()).select_from(matching))

    best = func.max(appearance.c.relevance)
    last_seen = func.max(appearance.c.created_at)
    newest = func.array_agg(
        aggregate_order_by(
            appearance.c.paper, appearance.c.created_at.desc(), appearance.c.output_id.desc()
        )
    )
    rows = await session.execute(
        select(
            appearance.c.paper_id,
            newest[1].label("paper"),
            func.count(appearance.c.run_id.distinct()).label("run_count"),
            func.count(appearance.c.project_id.distinct()).label("project_count"),
            best.label("best_relevance"),
            func.array_agg(appearance.c.decision.distinct()).label("decisions"),
            func.array_agg(appearance.c.degraded_reason.distinct()).label("reasons"),
            last_seen.label("last_seen_at"),
        )
        .where(appearance.c.paper_id.in_(select(matching.c.paper_id)))
        .group_by(appearance.c.paper_id)
        .order_by(best.desc().nulls_last(), last_seen.desc(), appearance.c.paper_id)
        .limit(limit)
        .offset(offset)
    )
    entries = [
        LibraryEntry(
            paper_id=row.paper_id,
            paper=row.paper,
            run_count=row.run_count,
            project_count=row.project_count,
            best_relevance=row.best_relevance,
            decisions=tuple(d for d in row.decisions if d is not None),
            degraded_reasons=tuple(r for r in row.reasons if r is not None),
            last_seen_at=row.last_seen_at,
        )
        for row in rows
    ]
    return entries, total or 0


async def paper_appearances(
    session: AsyncSession, paper_id: str, *, member_id: str | None
) -> list[PaperAppearance]:
    """Every visible appearance of one paper, newest first (empty when it has none)."""
    latest = _latest_literature(member_id, None)
    rows = await session.execute(
        select(
            latest.c.output_id,
            latest.c.attempt,
            latest.c.created_at,
            latest.c.degraded_reason,
            latest.c.data["papers"].label("papers"),
            latest.c.data["analyses"].label("analyses"),
            Run.id.label("run_id"),
            Run.topic,
            Run.status,
            Run.created_at.label("run_created_at"),
            Project.id.label("project_id"),
            Project.name.label("project_name"),
        )
        .join(Run, Run.id == latest.c.run_id)
        .join(Project, Project.id == latest.c.project_id)
        .where(_array(latest.c.data["papers"]).contains([{"paper_id": paper_id}]))
        .order_by(latest.c.created_at.desc(), latest.c.output_id.desc())
    )
    appearances: list[PaperAppearance] = []
    for row in rows:
        paper = _with_paper_id(row.papers, paper_id)
        if paper is None:  # the containment check found it; only a concurrent edit could not
            continue
        appearances.append(
            PaperAppearance(
                stage_output_id=row.output_id,
                attempt=row.attempt,
                created_at=row.created_at,
                degraded_reason=row.degraded_reason,
                paper=paper,
                analysis=_with_paper_id(row.analyses, paper_id),
                run_id=row.run_id,
                run_topic=row.topic,
                run_status=RunStatus(row.status),
                run_created_at=row.run_created_at,
                project_id=row.project_id,
                project_name=row.project_name,
            )
        )
    return appearances


def _with_paper_id(items: Any, paper_id: str) -> dict[str, Any] | None:
    if not isinstance(items, list):
        return None
    return next(
        (item for item in items if isinstance(item, dict) and item.get("paper_id") == paper_id),
        None,
    )

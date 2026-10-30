"""The paper library tables as the literature stage reads and writes them.

- ``papers``: one row per paper across runs. A search record merges into the row it shares an
  id with; ``key`` is the first id the paper was found under and never changes. A demo row
  (seeded, with synthetic ids) that a real paper turns out to share an id with becomes that
  paper's row.
- ``run_papers``: one stage attempt's candidates, their screening and their analyses.
- ``paper_texts``: parsed full text.

Every write commits on its own, so a step that stops half way keeps what it finished.
"""

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.enums import PdfStatus
from agentic_core.schemas import LiteratureOutput, PaperRef
from agentic_db.models import Paper, PaperText, RunPaper
from agentic_scholarly.ids import (
    arxiv_id_from_doi,
    normalize_arxiv_id,
    normalize_doi,
    normalize_openalex_id,
    normalize_s2_id,
)
from agentic_scholarly.models import SOURCE_NAMES, PaperMeta

Sessions = async_sessionmaker[AsyncSession]

# External ids in the order that names a paper's key, which is also the order of trust when a
# record shares ids with several rows.
ID_COLUMNS = ("doi", "arxiv_id", "s2_id", "openalex_id")
_KEY_PREFIXES = {"doi": "doi", "arxiv_id": "arxiv", "s2_id": "s2", "openalex_id": "openalex"}
# Ids that keep two papers apart when they disagree (agentic_scholarly.merge's rule).
_GUARDED = ("doi", "arxiv_id", "s2_id")
_UPSERT_TRIES = 3


@dataclass(frozen=True)
class Candidate:
    """A paper as one stage attempt sees it: its library row and its run_papers row."""

    paper: Paper
    entry: RunPaper


def external_ids(meta: PaperMeta) -> dict[str, str]:
    """A record's ids by column, in key order. An arXiv DOI (10.48550/arXiv.*) is the arXiv id it
    carries, so the doi column stays free for the DOI of the published version."""
    doi = meta.doi if meta.doi and arxiv_id_from_doi(meta.doi) is None else None
    ids = {
        "doi": doi,
        "arxiv_id": meta.arxiv_id,
        "s2_id": meta.s2_id,
        "openalex_id": meta.openalex_id,
    }
    return {column: value for column, value in ids.items() if value}


def paper_key(ids: Mapping[str, str]) -> str:
    """The key of a new row: "doi:<doi>", else "arxiv:<id>", "s2:<id>" or "openalex:<W id>"."""
    column = next(column for column in ID_COLUMNS if column in ids)
    return f"{_KEY_PREFIXES[column]}:{ids[column]}"


def _missing(value: object) -> bool:
    return value is None or value == "" or value == []


def _fields(meta: PaperMeta) -> dict[str, Any]:
    return {
        "title": meta.title,
        "authors": list(meta.authors),
        "year": meta.year,
        "venue": meta.venue,
        "abstract": meta.abstract,
        "citation_count": meta.citation_count,
        "url": meta.url,
        "pmcid": meta.pmcid,
    }


def _same_paper(row: Paper, ids: Mapping[str, str]) -> bool:
    """Whether a row that shares an id with the record is the same paper: a shared DOI decides,
    a weaker shared id counts unless a stronger one disagrees. A demo row's other ids are
    synthetic, so they never disagree."""
    if row.demo or ("doi" in ids and row.doi == ids["doi"]):
        return True
    return not any(
        column in ids and getattr(row, column) not in (None, ids[column]) for column in _GUARDED
    )


def _take_over(paper: Paper, meta: PaperMeta) -> None:
    """Make a demo row the real paper's. Its key stays (the demo runs' run_papers rows still
    point at it); the demo metadata gives way to the record's, and the demo said nothing true
    about a PDF: no file is stored for a demo row, whatever its status claimed."""
    paper.demo = False
    for name, value in _fields(meta).items():
        setattr(paper, name, value)
    paper.retracted = meta.retracted
    paper.pdf_status = PdfStatus.UNKNOWN
    paper.pdf_sha256 = paper.pdf_source = paper.pdf_url = paper.pdf_checked_at = None


def _strength(row: Paper, ids: Mapping[str, str]) -> int:
    """The position of the strongest id the row shares with the record."""
    return next(
        (n for n, column in enumerate(ID_COLUMNS) if getattr(row, column) == ids.get(column)),
        len(ID_COLUMNS),
    )


async def _upsert(session: AsyncSession, meta: PaperMeta, ids: Mapping[str, str]) -> Paper:
    rows = list(
        await session.scalars(
            select(Paper).where(or_(*(getattr(Paper, c) == v for c, v in ids.items())))
        )
    )
    matching = [row for row in rows if _same_paper(row, ids)]
    if not matching:
        # Ids held by papers the record disagrees with stay with those papers.
        taken = {(column, getattr(row, column)) for row in rows for column in ID_COLUMNS}
        own = {column: value for column, value in ids.items() if (column, value) not in taken}
        if own:
            paper = Paper(key=paper_key(own), **own, **_fields(meta), retracted=meta.retracted)
            session.add(paper)
            await session.flush()
            return paper
        matching = rows  # the sources contradict each other on every id: join the closest row
    # A real row before a demo row that shares an id by chance.
    paper = min(matching, key=lambda row: (row.demo, _strength(row, ids)))
    taken = {
        (column, getattr(row, column)) for row in rows if row is not paper for column in ID_COLUMNS
    }
    demo = paper.demo
    if demo:
        _take_over(paper, meta)
    for column, value in ids.items():
        # A real row's ids never change; a demo row's synthetic ones give way to the record's.
        if (demo or getattr(paper, column) is None) and (column, value) not in taken:
            setattr(paper, column, value)
    for name, value in _fields(meta).items():
        if _missing(getattr(paper, name)) and not _missing(value):
            setattr(paper, name, value)
    paper.retracted = paper.retracted or meta.retracted
    await session.flush()
    return paper


async def upsert_paper(sessions: Sessions, meta: PaperMeta) -> Paper | None:
    """The library row of a search record: the row it shares an id with, its gaps filled in (a
    real row's ids never change; a demo row is taken over), or a new row. None for a record
    without any id."""
    ids = external_ids(meta)
    if not ids:
        return None
    tries = 1
    while True:
        try:
            async with sessions() as session:
                paper = await _upsert(session, meta, ids)
                await session.commit()
                return paper
        except IntegrityError:
            # Another stage stored this paper, or one of its ids, meanwhile: look again.
            if tries >= _UPSERT_TRIES:
                raise
            tries += 1


async def has_candidates(sessions: Sessions, stage_run_id: uuid.UUID) -> bool:
    async with sessions() as session:
        found = await session.scalar(
            select(RunPaper.paper_id).where(RunPaper.stage_run_id == stage_run_id).limit(1)
        )
    return found is not None


async def add_candidates(sessions: Sessions, rows: Sequence[Mapping[str, Any]]) -> None:
    """All of a search's run_papers rows in one transaction: they exist completely or not at all."""
    if not rows:
        return
    async with sessions() as session:
        await session.execute(pg_insert(RunPaper).values(list(rows)).on_conflict_do_nothing())
        await session.commit()


async def candidates(sessions: Sessions, stage_run_id: uuid.UUID) -> list[Candidate]:
    """The attempt's candidates, best ranked first."""
    async with sessions() as session:
        rows = await session.execute(
            select(RunPaper, Paper)
            .join(Paper, Paper.id == RunPaper.paper_id)
            .where(RunPaper.stage_run_id == stage_run_id)
            .order_by(RunPaper.rank)
        )
        return [Candidate(paper=paper, entry=entry) for entry, paper in rows]


async def record_screening(
    sessions: Sessions, stage_run_id: uuid.UUID, results: Mapping[uuid.UUID, Mapping[str, Any]]
) -> None:
    """One batch's decisions (relevance, decision, decision_reason), together."""
    async with sessions() as session:
        for paper_id, values in results.items():
            await session.execute(
                update(RunPaper)
                .where(RunPaper.stage_run_id == stage_run_id, RunPaper.paper_id == paper_id)
                .values(**values)
            )
        await session.commit()


async def papers(sessions: Sessions, paper_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Paper]:
    async with sessions() as session:
        rows = await session.scalars(select(Paper).where(Paper.id.in_(list(paper_ids))))
        return {row.id: row for row in rows}


async def record_pdf(
    sessions: Sessions,
    paper_id: uuid.UUID,
    *,
    status: PdfStatus,
    checked_at: datetime,
    sha256: str | None = None,
    source: str | None = None,
    url: str | None = None,
) -> None:
    """What the waterfall found; without a PDF the file columns are cleared."""
    async with sessions() as session:
        await session.execute(
            update(Paper)
            .where(Paper.id == paper_id)
            .values(
                pdf_status=status,
                pdf_sha256=sha256,
                pdf_source=source,
                pdf_url=url,
                pdf_checked_at=checked_at,
            )
        )
        await session.commit()


async def paper_texts(
    sessions: Sessions, paper_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, PaperText]:
    async with sessions() as session:
        rows = await session.scalars(
            select(PaperText).where(PaperText.paper_id.in_(list(paper_ids)))
        )
        return {row.paper_id: row for row in rows}


async def add_paper_text(
    sessions: Sessions,
    paper_id: uuid.UUID,
    *,
    parser: str,
    pages: list[str],
    sections: list[dict[str, Any]],
    references: list[dict[str, Any]],
) -> None:
    """A paper's parsed text; a stage that parsed the same paper first keeps its row."""
    async with sessions() as session:
        await session.execute(
            pg_insert(PaperText)
            .values(
                paper_id=paper_id,
                parser=parser,
                page_count=len(pages),
                pages=pages,
                sections=sections,
                references=references,
            )
            .on_conflict_do_nothing()
        )
        await session.commit()


async def record_analysis(
    sessions: Sessions,
    stage_run_id: uuid.UUID,
    paper_id: uuid.UUID,
    analysis: dict[str, Any],
    model: str | None,
) -> None:
    async with sessions() as session:
        await session.execute(
            update(RunPaper)
            .where(RunPaper.stage_run_id == stage_run_id, RunPaper.paper_id == paper_id)
            .values(analysis=analysis, analysis_model=model)
        )
        await session.commit()


# --- demo rows ----------------------------------------------------------------------------------


def _demo_ids(ref: PaperRef) -> dict[str, str]:
    """The ids of a demo paper, from its PaperRef and its key ("semantic_scholar:<id>")."""
    prefix, _, value = ref.paper_id.partition(":")
    ids = {
        "doi": normalize_doi(ref.doi),
        "arxiv_id": normalize_arxiv_id(ref.arxiv_id),
        "s2_id": normalize_s2_id(value) if prefix in ("s2", "semantic_scholar") else None,
        "openalex_id": normalize_openalex_id(value) if prefix == "openalex" else None,
    }
    return {column: found for column, found in ids.items() if found}


async def _demo_paper(session: AsyncSession, ref: PaperRef) -> Paper:
    existing = await session.scalar(select(Paper).where(Paper.key == ref.paper_id))
    if existing is not None:
        return existing
    ids = _demo_ids(ref)
    taken: set[tuple[str, Any]] = set()
    if ids:
        rows = await session.scalars(
            select(Paper).where(or_(*(getattr(Paper, c) == v for c, v in ids.items())))
        )
        taken = {(column, getattr(row, column)) for row in rows for column in ID_COLUMNS}
    paper = Paper(
        key=ref.paper_id,
        # Synthetic ids rarely repeat across demo outputs; a repeat stays with the first paper.
        **{column: value for column, value in ids.items() if (column, value) not in taken},
        title=ref.title,
        authors=list(ref.authors),
        year=ref.year,
        venue=ref.venue,
        abstract=ref.abstract,
        citation_count=ref.citation_count,
        url=ref.url,
        demo=True,
        # Demo papers have no stored file: the API serves its generated preview for them.
        pdf_status=PdfStatus.AVAILABLE if ref.pdf_available else PdfStatus.ABSTRACT_ONLY,
    )
    session.add(paper)
    await session.flush()
    return paper


async def record_demo_papers(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    stage_run_id: uuid.UUID,
    output: LiteratureOutput,
    model: str | None,
    created_at: datetime | None = None,
) -> None:
    """Library rows for a demo literature output, inside the caller's transaction: its papers
    (keyed by their PaperRef ids, flagged demo) and run_papers with its screening and analyses.
    Writing the same output again changes nothing.

    ``created_at`` dates the run_papers rows (the library shows it as when a paper was last
    seen): the seed passes its backdated output's time; None means now.
    """
    analyses = {analysis.paper_id: analysis for analysis in output.analyses}
    queries = output.plan.queries
    dated = {"created_at": created_at} if created_at is not None else {}
    rows: list[dict[str, Any]] = []
    for rank, ref in enumerate(output.papers, start=1):
        paper = await _demo_paper(session, ref)
        analysis = analyses.get(ref.paper_id)
        # A demo paper was not found by a real query; its hit names its source and a plan query.
        hit = {"source": ref.source, "query": queries[(rank - 1) % len(queries)], "position": rank}
        rows.append(
            {
                "stage_run_id": stage_run_id,
                "paper_id": paper.id,
                "run_id": run_id,
                "hits": [hit] if ref.source in SOURCE_NAMES else [],
                "rank": rank,
                "score": ref.relevance,  # no search ranking behind a demo paper
                "relevance": ref.relevance,
                "decision": ref.decision,
                "decision_reason": ref.decision_reason,
                "analysis": analysis.model_dump(mode="json") if analysis is not None else None,
                "analysis_model": model if analysis is not None else None,
                **dated,
            }
        )
    if rows:
        await session.execute(pg_insert(RunPaper).values(rows).on_conflict_do_nothing())

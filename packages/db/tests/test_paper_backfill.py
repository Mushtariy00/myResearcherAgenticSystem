"""The data migration that fills the paper library from literature outputs (0b2bff8fd54a)."""

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.enums import PdfStatus, StageStatus
from agentic_db.library import library_page, library_paper
from agentic_db.models import (
    Paper,
    PaperText,
    Project,
    Run,
    RunPaper,
    StageOutput,
    StageRun,
)
from agentic_db.testing import ALEMBIC_INI

Factory = async_sessionmaker[AsyncSession]
BACKFILL = "0b2bff8fd54a"
BEFORE = "8d4f2b6a1c37"
MARKER = {"backfill": BACKFILL}
T0 = datetime(2026, 10, 30, 6, 0, tzinfo=UTC)


async def _alembic(database_url: str, step: Callable[[Config, str], None], revision: str) -> None:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url)
    # env.py runs an event loop of its own, so Alembic gets a thread of its own.
    await asyncio.to_thread(step, config, revision)


def _ref(paper_id: str, title: str, **fields: Any) -> dict[str, Any]:
    """A paper as literature outputs store it (agentic_core.schemas.PaperRef)."""
    return {
        "paper_id": paper_id,
        "title": title,
        "authors": ["Lihe Yang", "Bingyi Kang"],
        "year": 2024,
        "venue": "NeurIPS",
        "doi": None,
        "arxiv_id": None,
        "url": None,
        "abstract": f"What {title} is about.",
        "citation_count": None,
        "source": "arxiv",
        "pdf_available": True,
        "relevance": 0.8,
        "decision": "include",
        "decision_reason": "Directly on topic.",
        **fields,
    }


def _notes(paper_id: str) -> dict[str, Any]:
    return {
        "paper_id": paper_id,
        "contribution": f"What {paper_id} contributes.",
        "method": "An encoder-decoder network.",
        "results": "Better than the baselines.",
        "limitations": "Indoor scenes only.",
        "evidence": [{"quote": "We train for 30 epochs.", "page": 4}],
    }


def _literature(papers: list[Any], analyses: Any = None) -> dict[str, Any]:
    return {
        "plan": {"topic": "Depth", "queries": ["a", "b", "c"]},
        "papers": papers,
        "analyses": [] if analyses is None else analyses,
        "key_findings": [],
        "synthesis": "What the papers say together.",
    }


class _Seed:
    """Projects, runs, attempts and outputs written the way the worker and the seed write them."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def run(self) -> Run:
        project = Project(name="Depth", created_by="alice")
        self.session.add(project)
        await self.session.flush()
        run = Run(project_id=project.id, owner_id="alice", topic="Monocular depth")
        self.session.add(run)
        await self.session.flush()
        return run

    async def attempt(self, run: Run, stage: str = "literature", attempt: int = 1) -> StageRun:
        stage_run = StageRun(
            run_id=run.id, stage=stage, attempt=attempt, status=StageStatus.APPROVED
        )
        self.session.add(stage_run)
        await self.session.flush()
        return stage_run

    async def output(
        self,
        stage_run: StageRun,
        data: dict[str, Any],
        at: datetime,
        version: int = 1,
        **fields: Any,
    ) -> StageOutput:
        output = StageOutput(
            stage_run_id=stage_run.id,
            version=version,
            data=data,
            sha256="0" * 64,
            created_at=at,
            **fields,
        )
        self.session.add(output)
        await self.session.flush()
        return output


async def _papers(db: Factory) -> dict[str, Paper]:
    async with db() as session:
        return {paper.key: paper for paper in await session.scalars(select(Paper))}


async def _run_papers(db: Factory) -> dict[tuple[uuid.UUID, str], RunPaper]:
    async with db() as session:
        rows = await session.execute(select(RunPaper, Paper.key).join(Paper))
        return {(row.stage_run_id, key): row for row, key in rows}


async def test_the_backfill_adds_nothing_to_an_empty_database(
    db: Factory, database_url: str
) -> None:
    try:
        await _alembic(database_url, command.downgrade, BEFORE)
        await _alembic(database_url, command.upgrade, BACKFILL)
        async with db() as session:
            counts = [
                await session.scalar(select(func.count()).select_from(table))
                for table in (Paper, RunPaper)
            ]
        assert counts == [0, 0]
    finally:
        await _alembic(database_url, command.upgrade, "head")


async def test_the_backfill_fills_the_library_from_literature_outputs(
    db: Factory, database_url: str
) -> None:
    async with db() as session:
        seed = _Seed(session)
        # A generated output that a reviewer then approved with edits (a version without the
        # degraded reason): the edit cut a paper.
        edited = await seed.attempt(await seed.run())
        kept = _ref(
            "arxiv:2401.00001",
            "Kept",
            doi="10.5555/Shared",
            source="semantic_scholar",
            relevance=0.9,
        )
        await seed.output(
            edited,
            _literature([kept, _ref("arxiv:2401.00002", "Cut")], [_notes("arxiv:2401.00001")]),
            T0,
            degraded=True,
            degraded_reason="literature.demo_search",
        )
        edited_version = await seed.output(
            edited,
            _literature([{**kept, "title": "Kept (edited)"}], [_notes("arxiv:2401.00001")]),
            T0 + timedelta(hours=1),
            version=2,
            edited_by="alice",
        )
        # A later real output: a newer record of the same paper, ids to normalise, ids that
        # another paper holds already, a paper without a PDF, and one the worker knows.
        real_run = await seed.run()
        real = await seed.attempt(real_run)
        await seed.output(
            real,
            _literature(
                [
                    _ref(
                        "arxiv:2401.00001",
                        "Kept, newer record",
                        doi="10.5555/SHARED",
                        relevance=0.7,
                        decision="maybe",
                    ),
                    _ref("doi:10.5555/shared", "Same DOI, other key", doi="10.5555/shared"),
                    _ref(
                        "arxiv:2301.07041",
                        "Versioned",
                        arxiv_id="2301.07041v2",
                        source="openalex",
                        pdf_available=False,
                        relevance=0.4,
                        decision="exclude",
                    ),
                    _ref("arxiv:1706.03762", "Known to the worker"),
                    _ref("doi:10.5555/taken", "Taken DOI", doi="10.5555/Taken"),
                ],
                ["not an analysis", _notes("arxiv:2301.07041")],
            ),
            T0 + timedelta(hours=2),
        )
        # Outputs that contribute nothing, or only what is well-formed.
        other = await seed.run()
        await seed.output(await seed.attempt(other), {"topic": "Depth", "queries": ["a"]}, T0)
        method = await seed.attempt(other, "method")
        await seed.output(method, _literature([_ref("arxiv:9", "Wrong stage")]), T0)
        odd = await seed.attempt(other, attempt=2)
        odd_types = {
            "paper_id": "arxiv:9999.00002",
            "title": "Odd types",
            "year": "2024",
            "authors": "Someone",
            "relevance": "high",
            "decision": "accept",
            "citation_count": -1,
            "pdf_available": "no",
        }
        junk = [
            "junk",
            {"paper_id": "", "title": "x"},
            {"paper_id": 7, "title": "x"},
            {"paper_id": "arxiv:9999.00001"},
        ]
        await seed.output(odd, _literature([*junk, odd_types], {}), T0)
        # What the worker wrote for a real-pipeline attempt before the migration ran.
        worker_run = await seed.run()
        worker = await seed.attempt(worker_run)
        known = Paper(
            key="arxiv:1706.03762",
            title="Attention Is All You Need",
            doi="10.5555/taken",
            year=2017,
            authors=["Ashish Vaswani"],
        )
        session.add(known)
        await session.flush()
        session.add(
            PaperText(
                paper_id=known.id,
                parser="pdfium",
                sections=[{"title": "Intro", "text": "Attention."}],
            )
        )
        worker_hits = [{"source": "openalex", "query": "attention", "position": 1}]
        session.add(
            RunPaper(
                stage_run_id=worker.id,
                paper_id=known.id,
                run_id=worker_run.id,
                hits=worker_hits,
                rank=1,
                score=0.93,
                relevance=0.95,
                decision="include",
                decision_reason="Seminal.",
                created_at=T0 + timedelta(hours=3),
            )
        )
        await seed.output(
            worker,
            _literature([_ref("arxiv:1706.03762", "Attention", relevance=0.95)]),
            T0 + timedelta(hours=3),
        )
        await session.commit()
        edited_id, real_id, odd_id, worker_id = edited.id, real.id, odd.id, worker.id
        edited_version_id, real_run_id = edited_version.id, real_run.id

    try:
        await _alembic(database_url, command.downgrade, BEFORE)
        await _alembic(database_url, command.upgrade, BACKFILL)

        papers = await _papers(db)
        assert sorted(papers) == [
            "arxiv:1706.03762",
            "arxiv:2301.07041",
            "arxiv:2401.00001",
            "arxiv:9999.00002",
            "doi:10.5555/shared",
            "doi:10.5555/taken",
        ]
        kept_paper = papers["arxiv:2401.00001"]
        assert (kept_paper.title, kept_paper.doi, kept_paper.demo) == (
            "Kept, newer record",
            "10.5555/shared",
            True,
        )
        # Generated with a PDF: available without a file, as the seed marks demo papers. A
        # real paper's PDF is unknown until the worker looks.
        assert kept_paper.pdf_status is PdfStatus.AVAILABLE
        assert papers["doi:10.5555/shared"].pdf_status is PdfStatus.UNKNOWN
        versioned = papers["arxiv:2301.07041"]
        assert (versioned.arxiv_id, versioned.pdf_status, versioned.demo) == (
            "2301.07041",
            PdfStatus.ABSTRACT_ONLY,
            False,
        )
        assert papers["doi:10.5555/shared"].doi is None  # arxiv:2401.00001 keeps it
        assert papers["doi:10.5555/taken"].doi is None  # the worker's paper holds it
        assert (papers["arxiv:1706.03762"].title, papers["arxiv:1706.03762"].demo) == (
            "Attention Is All You Need",
            False,
        )
        odd_paper = papers["arxiv:9999.00002"]
        assert (odd_paper.year, odd_paper.authors, odd_paper.citation_count) == (None, [], None)

        run_papers = await _run_papers(db)
        assert sorted(
            (row.rank, key)
            for (stage_run_id, key), row in run_papers.items()
            if stage_run_id == real_id
        ) == [
            (1, "arxiv:2401.00001"),
            (2, "doi:10.5555/shared"),
            (3, "arxiv:2301.07041"),
            (4, "arxiv:1706.03762"),
            (5, "doi:10.5555/taken"),
        ]
        from_edit = run_papers[edited_id, "arxiv:2401.00001"]
        assert (from_edit.rank, from_edit.score, from_edit.relevance, from_edit.decision) == (
            1,
            0.9,
            0.9,
            "include",
        )
        assert from_edit.hits == [{"source": "semantic_scholar", "position": 1, **MARKER}]
        assert from_edit.analysis == _notes("arxiv:2401.00001")
        assert from_edit.created_at == T0 + timedelta(hours=1)  # the latest version's
        assert (edited_id, "arxiv:2401.00002") not in run_papers  # cut by the edit
        excluded = run_papers[real_id, "arxiv:2301.07041"]
        assert (excluded.decision, excluded.relevance, excluded.analysis) == (
            "exclude",
            0.4,
            _notes("arxiv:2301.07041"),
        )
        odd_row = run_papers[odd_id, "arxiv:9999.00002"]
        assert (odd_row.relevance, odd_row.score, odd_row.decision, odd_row.analysis) == (
            None,
            0.0,
            None,
            None,
        )
        worker_row = run_papers[worker_id, "arxiv:1706.03762"]
        assert (worker_row.hits, worker_row.score) == (worker_hits, 0.93)  # left as it was
        assert len(run_papers) == 8

        # The library reads the backfilled rows as it read the outputs.
        async with db() as session:
            entries, total = await library_page(session, member_id=None)
            found = await library_paper(session, "arxiv:2401.00001", member_id=None)
        assert total == 5  # "Odd types" has no screening, so it is not in the library
        first = entries[0]
        assert (first.paper.key, first.best_relevance, first.run_count, first.paper.source) == (
            "arxiv:1706.03762",
            0.95,
            2,
            "openalex",
        )
        assert found is not None
        _, appearances = found
        assert [appearance.stage_run_id for appearance in appearances] == [real_id, edited_id]
        published = appearances[1].analysis
        assert published is not None and published.output_id == edited_version_id
        assert appearances[0].run_id == real_run_id and appearances[0].analysis is None

        # The upgrade can run again: nothing changes.
        await _alembic(database_url, command.stamp, BEFORE)
        await _alembic(database_url, command.upgrade, BACKFILL)
        assert {key: paper.id for key, paper in (await _papers(db)).items()} == {
            key: paper.id for key, paper in papers.items()
        }
        assert (await _run_papers(db)).keys() == run_papers.keys()

        # The worker later finds a backfilled paper in a run of its own.
        async with db() as session:
            session.add(
                RunPaper(
                    stage_run_id=worker_id,
                    paper_id=versioned.id,
                    run_id=worker_row.run_id,
                    hits=worker_hits,
                    rank=2,
                    score=0.5,
                )
            )
            await session.commit()
        await _alembic(database_url, command.downgrade, BEFORE)
        assert sorted(await _papers(db)) == ["arxiv:1706.03762", "arxiv:2301.07041"]
        assert sorted(await _run_papers(db)) == sorted(
            [(worker_id, "arxiv:1706.03762"), (worker_id, "arxiv:2301.07041")]
        )
    finally:
        await _alembic(database_url, command.upgrade, "head")

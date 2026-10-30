"""The paper library as the literature stage writes it: one row per paper, merged by external
id under a key that never changes, and the papers of demo outputs."""

import asyncio
import uuid

from sqlalchemy import func, select

from agentic_core import demo
from agentic_core.enums import PdfStatus
from agentic_core.schemas import LiteratureOutput, RunConfig
from agentic_db.models import Paper, RunPaper, StageRun
from agentic_scholarly.models import PaperMeta
from agentic_worker.literature.library import record_demo_papers, upsert_paper
from agentic_worker.stages import PipelineStageRunner, StageContext
from worker_testkit import Factory, FakePlanner, create_run

TOPIC = "Monocular depth estimation"


def meta(**fields: object) -> PaperMeta:
    fields.setdefault("title", "AdaBins: Depth Estimation Using Adaptive Bins")
    fields.setdefault("authors", ["Shariq Farooq Bhat"])
    fields.setdefault("year", 2021)
    fields.setdefault("abstract", "Adaptive bins for depth.")
    return PaperMeta.model_validate(fields)


async def paper_count(db: Factory) -> int:
    async with db() as session:
        return await session.scalar(select(func.count()).select_from(Paper)) or 0


async def test_the_same_doi_found_again_is_one_row_with_a_stable_key(db: Factory) -> None:
    first = await upsert_paper(db, meta(doi="10.1109/CVPR.2021.00400", openalex_id="W3200000002"))
    assert first is not None and first.key == "doi:10.1109/cvpr.2021.00400"
    again = await upsert_paper(
        db,
        meta(
            title="AdaBins: depth estimation using adaptive bins",
            authors=["S. F. Bhat", "I. Alhashim"],
            doi="https://doi.org/10.1109/cvpr.2021.00400",
            arxiv_id="2011.14141v2",
            s2_id="a" * 40,
            openalex_id="W9999999999",
            venue="CVPR",
            citation_count=900,
        ),
    )
    assert again is not None and (again.id, again.key) == (first.id, first.key)
    assert (again.arxiv_id, again.s2_id) == ("2011.14141", "a" * 40)  # new ids are added
    assert again.openalex_id == "W3200000002"  # an id once stored never changes
    assert (again.title, again.authors) == (first.title, first.authors)  # what was there stays
    assert (again.venue, again.citation_count) == ("CVPR", 900)  # gaps are filled
    assert await paper_count(db) == 1


async def test_a_paper_first_found_by_its_arxiv_id_keeps_that_key(db: Factory) -> None:
    preprint = await upsert_paper(db, meta(doi="10.48550/arXiv.2401.10891"))
    assert preprint is not None
    # arXiv's own DOI is the arXiv id: the doi column waits for the published version's DOI.
    assert (preprint.key, preprint.arxiv_id, preprint.doi) == (
        "arxiv:2401.10891",
        "2401.10891",
        None,
    )
    published = await upsert_paper(
        db, meta(doi="10.1109/cvpr52733.2024.00987", arxiv_id="2401.10891")
    )
    assert published is not None and published.id == preprint.id
    assert (published.key, published.doi) == ("arxiv:2401.10891", "10.1109/cvpr52733.2024.00987")


async def test_papers_whose_dois_disagree_stay_apart(db: Factory) -> None:
    conference = await upsert_paper(db, meta(doi="10.1000/conference", arxiv_id="2101.00001"))
    journal = await upsert_paper(
        db, meta(title="AdaBins, extended", doi="10.1000/journal", arxiv_id="2101.00001")
    )
    assert conference is not None and journal is not None and conference.id != journal.id
    # The arXiv id belongs to the first paper; the journal version gets its DOI as its key.
    assert (journal.key, journal.arxiv_id) == ("doi:10.1000/journal", None)


async def test_stages_storing_the_same_paper_at_once_share_its_row(db: Factory) -> None:
    rows = await asyncio.gather(
        *(upsert_paper(db, meta(doi="10.1000/race", openalex_id=f"W10{n}")) for n in range(4))
    )
    assert len({row.id for row in rows if row is not None}) == 1
    assert await paper_count(db) == 1


async def test_a_real_paper_takes_over_a_demo_row_it_shares_an_id_with(db: Factory) -> None:
    run_id = await create_run(db)
    stage_run_id = await add_stage_run(db, run_id)
    async with db() as session:
        seeded = Paper(
            key="arxiv:2301.91234",
            arxiv_id="2301.91234",
            doi="10.5555/bmvc.2023.91234",
            title="A demo title",
            authors=["Demo Author"],
            year=2022,
            venue="BMVC",
            abstract="A demo abstract.",
            citation_count=7,
            url="https://arxiv.org/abs/2301.91234",
            demo=True,
            pdf_status=PdfStatus.AVAILABLE,  # the demo said so; no file is stored
        )
        session.add(seeded)
        await session.flush()
        session.add(
            RunPaper(
                stage_run_id=stage_run_id,
                paper_id=seeded.id,
                run_id=uuid.UUID(run_id),
                hits=[],
                rank=1,
                score=0.5,
            )
        )
        await session.commit()
    real = await upsert_paper(
        db,
        meta(
            title="The real title",
            authors=["Real Author"],
            year=2023,
            abstract="The real abstract.",
            arxiv_id="2301.91234",
            doi="10.1109/real.2023.1",  # disagrees with the synthetic DOI, which gives way
        ),
    )
    assert real is not None and (real.id, real.key) == (seeded.id, "arxiv:2301.91234")
    async with db() as session:
        row = await session.get(Paper, seeded.id)
        entries = (await session.scalars(select(RunPaper.paper_id))).all()
    assert row is not None and not row.demo
    assert (row.title, row.authors, row.year, row.venue, row.abstract) == (
        "The real title",
        ["Real Author"],
        2023,
        None,
        "The real abstract.",
    )
    assert (row.citation_count, row.url, row.doi) == (None, None, "10.1109/real.2023.1")
    assert (row.pdf_status, row.pdf_sha256, row.pdf_source, row.pdf_url) == (
        PdfStatus.UNKNOWN,
        None,
        None,
        None,
    )
    assert entries == [seeded.id]  # the demo run still finds its paper under the same key
    # From now on it is an ordinary row: found again, only its gaps are filled.
    again = await upsert_paper(db, meta(title="Another title", arxiv_id="2301.91234", venue="CVPR"))
    assert again is not None and again.id == seeded.id
    assert (again.title, again.venue) == ("The real title", "CVPR")


async def add_stage_run(db: Factory, run_id: str) -> uuid.UUID:
    async with db() as session:
        stage_run = StageRun(run_id=uuid.UUID(run_id), stage="literature", attempt=1)
        session.add(stage_run)
        await session.commit()
    return stage_run.id


async def library_rows(db: Factory) -> tuple[list[Paper], list[RunPaper]]:
    async with db() as session:
        papers = list(await session.scalars(select(Paper)))
        entries = list(await session.scalars(select(RunPaper).order_by(RunPaper.rank)))
    return papers, entries


def assert_recorded(output: LiteratureOutput, papers: list[Paper], entries: list[RunPaper]) -> None:
    refs = {ref.paper_id: ref for ref in output.papers}
    assert {paper.key for paper in papers} == set(refs)
    assert all(paper.demo and paper.pdf_sha256 is None for paper in papers)
    keys = {paper.id: paper.key for paper in papers}
    assert [keys[entry.paper_id] for entry in entries] == [ref.paper_id for ref in output.papers]
    for entry in entries:
        ref = refs[keys[entry.paper_id]]
        assert (entry.decision, entry.relevance) == (ref.decision, ref.relevance)
    analysed = {keys[entry.paper_id]: entry.analysis for entry in entries if entry.analysis}
    assert analysed == {a.paper_id: a.model_dump(mode="json") for a in output.analyses}


async def test_a_demo_output_is_recorded_once(db: Factory) -> None:
    run_id = await create_run(db)
    stage_run_id = await add_stage_run(db, run_id)
    plan = demo.research_plan(TOPIC, 3)
    output = demo.literature(TOPIC, plan, RunConfig(), 3)
    for _ in range(2):  # a retried activity writes the same output again
        async with db() as session:
            await record_demo_papers(
                session,
                run_id=uuid.UUID(run_id),
                stage_run_id=stage_run_id,
                output=output,
                model="demo/model",
            )
            await session.commit()
    papers, entries = await library_rows(db)
    assert_recorded(output, papers, entries)
    assert {entry.analysis_model for entry in entries if entry.analysis} == {"demo/model"}


async def test_the_demo_search_records_its_papers(db: Factory) -> None:
    run_id = await create_run(db, topic=TOPIC)
    stage_run_id = await add_stage_run(db, run_id)
    ctx = StageContext(
        run_id=run_id,
        stage_run_id=str(stage_run_id),
        stage="literature",
        attempt=1,
        feedback="",
        topic=TOPIC,
        owner_id="bob",
        project_id=str(uuid.uuid4()),
        llm_policy="auto",
        budget_cap_usd=None,
    )
    runner = PipelineStageRunner(FakePlanner(), demo_library=db, demo_stage_seconds=0)
    outcome = await runner.run(ctx)
    assert outcome.degraded_reason == "literature.demo_search"
    papers, entries = await library_rows(db)
    assert_recorded(LiteratureOutput.model_validate(outcome.data), papers, entries)

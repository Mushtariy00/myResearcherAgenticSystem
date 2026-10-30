"""The real literature stage on the test database, with fake sources, PDFs, GROBID and gateway."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from literature_testkit import (
    ADABINS,
    ADABINS_METHOD,
    ADABINS_PDF,
    DEPTH_ANYTHING,
    DEPTH_ANYTHING_PDF,
    DEPTH_ANYTHING_RESULT,
    DPT,
    INCLUDED,
    KEYS,
    TOPIC,
    FakeApis,
    FakeGateway,
    FakeGrobid,
    Harness,
    harness,
    rate_limited,
    screen_answer,
)
from sqlalchemy import select, update
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from agentic_core.enums import PdfStatus
from agentic_core.schemas import LiteratureOutput, RunConfig, validate_stage_output
from agentic_db.models import Paper, PaperText, RunPaper, StageOutput
from agentic_scholarly.grobid import Section
from agentic_scholarly.storage import pdf_path
from agentic_scholarly.testing import FakeNetwork
from agentic_worker.gateway_llm import (
    AttemptEndedError,
    GatewayRateLimitedError,
    LabBalanceExhaustedError,
    RunInactiveError,
)
from agentic_worker.outputs import LITERATURE_PROMPT_VERSION
from agentic_worker.stages import StageContext, StageFailedError
from worker_testkit import Factory, run_events


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


async def run_stage(lit: Harness, config: dict[str, Any] | None = None) -> tuple[str, str]:
    """One literature attempt through execute_stage, to its output: (run id, stage run id)."""
    run_id, stage_run_id = await lit.start(config)
    await ActivityEnvironment().run(lit.activities.execute_stage, lit.execute(run_id, stage_run_id))
    return run_id, stage_run_id


async def stored_output(db: Factory, stage_run_id: str) -> StageOutput:
    async with db() as session:
        return (
            await session.scalars(
                select(StageOutput).where(StageOutput.stage_run_id == uuid.UUID(stage_run_id))
            )
        ).one()


async def library(db: Factory) -> dict[str, Paper]:
    async with db() as session:
        return {paper.key: paper for paper in await session.scalars(select(Paper))}


async def texts(db: Factory) -> dict[uuid.UUID, PaperText]:
    async with db() as session:
        return {text.paper_id: text for text in await session.scalars(select(PaperText))}


async def entries(db: Factory, stage_run_id: str) -> list[RunPaper]:
    async with db() as session:
        rows = await session.scalars(
            select(RunPaper)
            .where(RunPaper.stage_run_id == uuid.UUID(stage_run_id))
            .order_by(RunPaper.rank)
        )
        return list(rows)


async def progress(db: Factory, run_id: str) -> list[tuple[str, dict[str, Any]]]:
    return [(e["code"], e["params"]) for e in await run_events(db, run_id, "log")]


def stored_files(data_dir: Path) -> list[str]:
    return sorted(path.name for path in data_dir.rglob("*.pdf"))


def context(run_id: str, stage_run_id: str, log: Any = None) -> StageContext:
    """The attempt as execute_stage would describe it, for running the stage directly."""

    async def discard(code: str, params: dict[str, Any], message: str) -> None:
        return None

    return StageContext(
        run_id=run_id,
        stage_run_id=stage_run_id,
        stage="literature",
        attempt=1,
        feedback="",
        topic=TOPIC,
        owner_id="bob",
        project_id=str(uuid.uuid4()),
        llm_policy="auto",
        budget_cap_usd=None,
        config=RunConfig(max_papers=5, sources=["arxiv", "openalex"]),
        log=log or discard,
    )


async def test_a_stage_finds_reads_and_synthesises_real_papers(db: Factory, data_dir: Path) -> None:
    lit = harness(db, data_dir)
    run_id, stage_run_id = await run_stage(lit)

    stored = await stored_output(db, stage_run_id)
    assert validate_stage_output("literature", stored.data).model_dump(mode="json") == stored.data
    assert (stored.degraded, stored.degraded_reason) == (False, None)
    assert (stored.model, stored.prompt_version) == (
        "fake/free-model:free",
        LITERATURE_PROMPT_VERSION,
    )
    output = LiteratureOutput.model_validate(stored.data)
    refs = {ref.paper_id: ref for ref in output.papers}
    # Five complete candidates (the paper without an abstract is left out), included first.
    assert set(refs) == set(KEYS.values())
    assert {ref.paper_id for ref in output.papers[:3]} == {KEYS[p] for p in INCLUDED}
    assert [ref.decision for ref in output.papers] == ["include"] * 3 + ["maybe", "exclude"]
    depth = refs[KEYS[DEPTH_ANYTHING]]
    assert (depth.arxiv_id, depth.doi, depth.year) == ("2401.10891", None, 2024)
    assert [refs[KEYS[p]].pdf_available for p in INCLUDED] == [True, True, False]

    # Evidence is kept only where the quote is on the page it names.
    analyses = {analysis.paper_id: analysis for analysis in output.analyses}
    assert set(analyses) == {KEYS[p] for p in INCLUDED}
    assert [(e.quote, e.page) for e in analyses[KEYS[DEPTH_ANYTHING]].evidence] == [
        (DEPTH_ANYTHING_RESULT, 2)
    ]
    assert [(e.quote, e.page) for e in analyses[KEYS[ADABINS]].evidence] == [(ADABINS_METHOD, 1)]
    assert analyses[KEYS[DPT]].evidence == []  # abstract only: nothing to quote
    assert {finding.paper_id for finding in output.key_findings} == {KEYS[p] for p in INCLUDED}
    assert all(finding.source in ("arXiv", "OpenAlex") for finding in output.key_findings)
    assert output.synthesis == "Depth networks improve.\n\nOpen problems remain."

    # The library: papers merged across sources, PDFs stored by hash, text parsed.
    papers = await library(db)
    assert set(papers) == set(KEYS.values())
    depth_row, adabins_row = papers[KEYS[DEPTH_ANYTHING]], papers[KEYS[ADABINS]]
    assert (depth_row.openalex_id, depth_row.doi) == ("W4391000001", None)
    assert (depth_row.pdf_status, depth_row.pdf_source) == (PdfStatus.AVAILABLE, "arxiv")
    assert depth_row.pdf_url == "https://arxiv.org/pdf/2401.10891"
    assert (adabins_row.pdf_status, adabins_row.pdf_source) == (PdfStatus.AVAILABLE, "openalex")
    assert papers[KEYS[DPT]].pdf_status == PdfStatus.ABSTRACT_ONLY
    assert papers[KEYS[DPT]].pdf_checked_at is not None
    for row, pdf in ((depth_row, DEPTH_ANYTHING_PDF), (adabins_row, ADABINS_PDF)):
        assert row.pdf_sha256 is not None
        assert pdf_path(data_dir, row.pdf_sha256).read_bytes() == pdf
    parsed = await texts(db)
    assert set(parsed) == {depth_row.id, adabins_row.id}
    depth_text = parsed[depth_row.id]
    assert (depth_text.parser, depth_text.page_count) == ("pdfium", 3)
    assert DEPTH_ANYTHING_RESULT in depth_text.pages[1]
    assert len(depth_text.sections) == 3 and depth_text.sections[0]["title"] is None

    rows = await entries(db, stage_run_id)
    assert [row.rank for row in rows] == [1, 2, 3, 4, 5]
    assert all(row.hits and row.decision and row.decision_reason for row in rows)
    assert sum(row.analysis is not None for row in rows) == 3

    lines = await progress(db, run_id)
    assert [code for code, _ in lines] == [
        "literature.searched",
        "literature.screened",
        "literature.fetched",
        "literature.parsed",
        "literature.analyzed",
        "literature.synthesized",
    ]
    searched = lines[0][1]
    assert (searched["sources"], searched["found"], searched["incomplete"]) == (
        ["arxiv", "openalex"],
        6,
        1,
    )
    assert [params for _, params in lines[1:]] == [
        {"candidates": 5, "included": 3},
        {"pdfs": 2, "abstract_only": 1},
        {"papers": 2},
        {"papers": 3},
        {"findings": 3},
    ]
    # One screening batch, three analyses and the synthesis, each recorded as an llm.call.
    answered = lit.gateway.answered()
    assert len(answered) == 5 and answered[0] == f"{stage_run_id}:screen:1:call-1"
    keyed = [
        c["idempotency_key"]
        for c in await run_events(db, run_id, "llm.call")
        if c.get("idempotency_key")
    ]
    assert sorted(keyed) == sorted(answered)


async def test_an_attempt_that_runs_again_resumes_where_it_stopped(
    db: Factory, data_dir: Path
) -> None:
    # The first analysis to reach the gateway is told to wait (the free quota ran out).
    gateway = FakeGateway(failures=[(lambda key: ":analyze:" in key, rate_limited(42))])
    lit = harness(db, data_dir, gateway=gateway)
    run_id, stage_run_id = await lit.start()
    request = lit.execute(run_id, stage_run_id)
    with pytest.raises(ApplicationError) as waited:
        await ActivityEnvironment().run(lit.activities.execute_stage, request)
    assert (waited.value.type, waited.value.message) == ("RateLimited", "free_quota.exhausted")
    assert waited.value.next_retry_delay == timedelta(seconds=42)
    paid = set(gateway.answered())
    analysed = {
        row.paper_id: row.analysis for row in await entries(db, stage_run_id) if row.analysis
    }
    searches, dials = len(lit.apis.requests), len(lit.network.connections)
    files = stored_files(data_dir)

    await ActivityEnvironment().run(lit.activities.execute_stage, request)  # the workflow's rerun

    # Nothing finished is done again: no search, no download, no call paid for twice.
    assert (len(lit.apis.requests), len(lit.network.connections)) == (searches, dials)
    assert stored_files(data_dir) == files
    again = gateway.answered()[len(paid) :]
    assert not paid & set(again)
    waited_key = next(call.key for call in gateway.calls if call.status == 429)
    assert waited_key in again and f"{stage_run_id}:synthesize:call-1" in again
    assert len(again) == 1 + 1 + (3 - 1 - len(analysed))  # the waiting one, synthesis, the rest
    rows = await entries(db, stage_run_id)
    assert all(row.analysis is not None for row in rows if row.decision == "include")
    assert {row.paper_id: row.analysis for row in rows if row.paper_id in analysed} == analysed
    stored = await stored_output(db, stage_run_id)
    assert len(LiteratureOutput.model_validate(stored.data).analyses) == 3
    # Each step reported once, the screening and the downloads before the wait.
    codes = [code for code, _ in await progress(db, run_id)]
    assert codes == [
        "literature.searched",
        "literature.screened",
        "literature.fetched",
        "literature.parsed",
        "literature.analyzed",
        "literature.synthesized",
    ]
    keyed = [
        c["idempotency_key"]
        for c in await run_events(db, run_id, "llm.call")
        if c.get("idempotency_key")
    ]
    assert sorted(keyed) == sorted(set(keyed)) == sorted(gateway.answered())


async def test_a_failing_source_flags_a_partial_search(db: Factory, data_dir: Path) -> None:
    lit = harness(db, data_dir, apis=FakeApis(s2_status=429))
    run_id, stage_run_id = await run_stage(
        lit, {"sources": ["arxiv", "semantic_scholar", "openalex"]}
    )
    stored = await stored_output(db, stage_run_id)
    assert (stored.degraded, stored.degraded_reason) == (True, "literature.partial_search")
    lines = await progress(db, run_id)
    assert [params for code, params in lines if code == "literature.source_failed"] == [
        {"source": "semantic_scholar", "error": "source.rate_limited"}
    ]
    # The other sources carried the stage.
    assert len(LiteratureOutput.model_validate(stored.data).papers) == 5


async def test_without_any_full_text_the_output_says_so(db: Factory, data_dir: Path) -> None:
    lit = harness(db, data_dir, network=FakeNetwork({}))  # every download fails to connect
    _, stage_run_id = await run_stage(lit)
    stored = await stored_output(db, stage_run_id)
    assert (stored.degraded, stored.degraded_reason) == (True, "literature.no_full_text")
    output = LiteratureOutput.model_validate(stored.data)
    assert not any(ref.pdf_available for ref in output.papers)
    assert len(output.analyses) == 3 and all(a.evidence == [] for a in output.analyses)
    papers = await library(db)
    assert [papers[KEYS[p]].pdf_status for p in INCLUDED] == [
        PdfStatus.FAILED,  # arXiv had a copy, but it could not be fetched
        PdfStatus.FAILED,
        PdfStatus.ABSTRACT_ONLY,
    ]
    prompts = [
        c.messages[-1]["content"] for c in lit.gateway.calls if c.role == "literature.analyze"
    ]
    assert all("Only the abstract is available" in prompt for prompt in prompts)


async def test_pdfs_are_looked_for_again_only_after_a_week(db: Factory, data_dir: Path) -> None:
    await run_stage(harness(db, data_dir, network=FakeNetwork({})))  # nothing downloads

    # Days later the PDFs are online, but the papers were looked for lately.
    later = harness(db, data_dir)
    _, stage_run_id = await run_stage(later)
    assert later.network.connections == []
    assert (await stored_output(db, stage_run_id)).degraded_reason == "literature.no_full_text"

    async with db() as session:
        await session.execute(
            update(Paper).values(pdf_checked_at=datetime.now(UTC) - timedelta(days=8))
        )
        await session.commit()
    week_later = harness(db, data_dir)
    _, stage_run_id = await run_stage(week_later)
    assert len(week_later.network.connections) == 2  # arXiv and the repository
    assert (await stored_output(db, stage_run_id)).degraded_reason is None
    papers = await library(db)
    assert papers[KEYS[DEPTH_ANYTHING]].pdf_status == PdfStatus.AVAILABLE


async def test_a_second_run_reuses_the_library(db: Factory, data_dir: Path) -> None:
    first = harness(db, data_dir)
    _, first_stage_run = await run_stage(first)
    before = await library(db)

    second = harness(db, data_dir, network=FakeNetwork({}))  # a download would fail now
    _, second_stage_run = await run_stage(second)
    after = await library(db)
    # The same papers, the same rows and keys; stored PDFs and parsed text are reused.
    assert {key: paper.id for key, paper in after.items()} == {
        key: paper.id for key, paper in before.items()
    }
    assert second.network.connections == []
    stored = await stored_output(db, second_stage_run)
    assert stored.degraded_reason is None
    analyses = LiteratureOutput.model_validate(stored.data).analyses
    assert any(analysis.evidence for analysis in analyses)
    first_ids = {row.paper_id for row in await entries(db, first_stage_run)}
    assert {row.paper_id for row in await entries(db, second_stage_run)} == first_ids


async def test_grobid_sections_are_used_when_grobid_runs(db: Factory, data_dir: Path) -> None:
    grobid = FakeGrobid(
        alive=True, sections=[Section(title="Experiments", text=DEPTH_ANYTHING_RESULT)]
    )
    lit = harness(db, data_dir, grobid=grobid)
    await run_stage(lit)
    parsed = await texts(db)
    assert {text.parser for text in parsed.values()} == {"grobid-0.9.1"}
    assert grobid.parsed == 2
    depth_key = KEYS[DEPTH_ANYTHING]
    prompt = next(
        c.messages[-1]["content"]
        for c in lit.gateway.calls
        if c.key.endswith(f"{depth_key}:call-1")
    )
    # The section is placed on the page its text is on, so quotes can name their page.
    assert f"Experiments\n[page 2]\n{DEPTH_ANYTHING_RESULT}" in prompt


async def test_a_cancel_between_steps_makes_no_more_calls(db: Factory, data_dir: Path) -> None:
    lit = harness(db, data_dir)
    run_id, stage_run_id = await lit.start()

    async def cancel_after_screening(code: str, params: dict[str, Any], message: str) -> None:
        if code == "literature.screened":
            ctx.cancelled.set()  # what execute_stage does when the activity is cancelled

    ctx = context(run_id, stage_run_id, cancel_after_screening)
    with pytest.raises(AttemptEndedError):
        await lit.runner.run(ctx)
    assert [call.role for call in lit.gateway.calls] == ["literature.screen"]
    assert lit.network.connections == []


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (rate_limited(42), GatewayRateLimitedError),
        (httpx.Response(402, json={"detail": "lab_balance.exhausted"}), LabBalanceExhaustedError),
        (httpx.Response(409, json={"detail": "run.inactive"}), RunInactiveError),
    ],
)
async def test_gateway_waits_and_pauses_end_the_attempt(
    db: Factory, data_dir: Path, response: httpx.Response, error: type[Exception]
) -> None:
    gateway = FakeGateway(failures=[(lambda key: ":screen:" in key, response)])
    lit = harness(db, data_dir, gateway=gateway)
    run_id, stage_run_id = await lit.start()
    with pytest.raises(error) as raised:
        await lit.runner.run(context(run_id, stage_run_id))
    if isinstance(raised.value, GatewayRateLimitedError):
        assert raised.value.retry_after == 42
    assert [call.role for call in gateway.calls] == ["literature.screen"]
    assert lit.network.connections == []


async def test_an_unusable_answer_gets_one_repair(db: Factory, data_dir: Path) -> None:
    answers = iter(["All of them look relevant to me.", None])

    def screen(prompt: str) -> str:
        return next(answers) or screen_answer(prompt)

    gateway = FakeGateway(answers={"literature.screen": screen})
    lit = harness(db, data_dir, gateway=gateway)
    _, stage_run_id = await run_stage(lit)
    assert gateway.keys("literature.screen") == [
        f"{stage_run_id}:screen:1:call-1",
        f"{stage_run_id}:screen:1:call-2",
    ]
    repair = gateway.calls[1].messages
    assert [m["role"] for m in repair] == ["user", "assistant", "user"]
    assert "--- BEGIN CANDIDATES ---" in repair[0]["content"]
    assert repair[1]["content"] == "All of them look relevant to me."
    assert repair[2]["content"].startswith("Your previous answer could not be used")


async def test_an_answer_cut_off_by_its_budget_is_told_so(db: Factory, data_dir: Path) -> None:
    # A reasoning model thinking aloud until the output budget runs out, before any JSON.
    answers = iter(["The user wants me to screen ten papers. Let me think about each one"])

    def screen(prompt: str) -> str:
        return next(answers, None) or screen_answer(prompt)

    gateway = FakeGateway(
        answers={"literature.screen": screen}, cut_off=lambda key: key.endswith(":screen:1:call-1")
    )
    lit = harness(db, data_dir, gateway=gateway)
    await run_stage(lit)
    repair = gateway.calls[1].messages[-1]["content"]
    assert "ran out of room (4000 tokens) before the JSON" in repair
    assert "Answer with the JSON object alone" in gateway.calls[0].messages[-1]["content"]


async def test_an_answer_still_unusable_after_its_repair_fails_the_stage(
    db: Factory, data_dir: Path
) -> None:
    gateway = FakeGateway(answers={"literature.screen": lambda prompt: json.dumps({"ok": 1})})
    lit = harness(db, data_dir, gateway=gateway)
    run_id, stage_run_id = await lit.start()
    with pytest.raises(StageFailedError, match=r"^literature\.invalid_output: literature\.screen"):
        await lit.runner.run(context(run_id, stage_run_id))
    assert len(gateway.keys("literature.screen")) == 2

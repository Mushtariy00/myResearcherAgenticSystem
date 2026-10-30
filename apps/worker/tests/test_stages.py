"""The pipeline stage runner: demo outputs built on approved inputs, with simulated progress."""

import copy
import dataclasses
import json
import time
from dataclasses import dataclass, field
from typing import Any

import pytest

from agentic_core import demo
from agentic_core.schemas import (
    CodingOutput,
    ExperimentOutput,
    LiteratureOutput,
    MethodOutput,
    RunConfig,
    WritingOutput,
    validate_stage_output,
)
from agentic_worker.outputs import (
    DEMO_PROMPT_VERSION,
    LITERATURE_DEMO_REASON,
    PLAN_PROMPT_VERSION,
    STAGE_DEMO_REASON,
    progress_steps,
)
from agentic_worker.stages import (
    MAX_DEMO_STAGE_SECONDS,
    CrewAIPlanner,
    PipelineStageRunner,
    StageContext,
    StageFailedError,
    StageOutcome,
    plan_prompt,
)
from worker_testkit import FakePlanner

STAGES = ("literature", "method", "coding", "experiment", "writing")


@dataclass
class Recorder:
    lines: list[tuple[str, dict[str, Any], str]] = field(default_factory=list)

    async def __call__(self, code: str, params: dict[str, Any], message: str) -> None:
        self.lines.append((code, params, message))


def context(
    stage: str,
    *,
    inputs: dict[str, dict[str, Any]] | None = None,
    attempt: int = 1,
    feedback: str = "",
    config: RunConfig | None = None,
    log: Recorder | None = None,
    demo_stage_seconds: float | None = None,
) -> StageContext:
    return StageContext(
        run_id="11111111-2222-3333-4444-555555555555",
        stage_run_id=f"stage-run-{stage}-{attempt}",
        stage=stage,
        attempt=attempt,
        feedback=feedback,
        topic="Monocular depth estimation on indoor scenes",
        owner_id="bob",
        project_id="project-1",
        llm_policy="auto",
        budget_cap_usd=None,
        config=config or RunConfig(),
        inputs=inputs or {},
        demo_stage_seconds=demo_stage_seconds,
        log=log or Recorder(),
    )


async def run_pipeline(
    runner: PipelineStageRunner, log: Recorder | None = None
) -> dict[str, StageOutcome]:
    outcomes: dict[str, StageOutcome] = {}
    for stage in STAGES:
        inputs = {done: outcome.data for done, outcome in outcomes.items()}
        outcomes[stage] = await runner.run(context(stage, inputs=inputs, log=log))
    return outcomes


@pytest.fixture
def runner() -> PipelineStageRunner:
    return PipelineStageRunner(FakePlanner(), demo_stage_seconds=0)


async def test_every_stage_returns_a_flagged_schema_valid_output(
    runner: PipelineStageRunner,
) -> None:
    outcomes = await run_pipeline(runner)
    for stage, outcome in outcomes.items():
        assert validate_stage_output(stage, outcome.data).model_dump(mode="json") == outcome.data
        assert outcome.degraded
    literature = outcomes["literature"]
    assert (literature.degraded_reason, literature.prompt_version) == (
        LITERATURE_DEMO_REASON,
        PLAN_PROMPT_VERSION,
    )
    assert literature.model == "fake/free-model:free" and len(literature.llm_calls) == 1
    for stage in STAGES[1:]:
        outcome = outcomes[stage]
        assert (outcome.degraded_reason, outcome.prompt_version) == (
            STAGE_DEMO_REASON,
            DEMO_PROMPT_VERSION,
        )
        assert outcome.model is None and outcome.llm_calls == []


async def test_literature_keeps_the_planners_plan(runner: PipelineStageRunner) -> None:
    planner = FakePlanner()
    outcome = await PipelineStageRunner(planner, demo_stage_seconds=0).run(context("literature"))
    plan = (await planner.plan(context("literature"))).plan
    assert LiteratureOutput.model_validate(outcome.data).plan == plan


async def test_later_stages_build_on_the_approved_inputs(runner: PipelineStageRunner) -> None:
    outcomes = await run_pipeline(runner)
    # A reviewer kept only three included papers (approve with edits).
    edited = copy.deepcopy(outcomes["literature"].data)
    keep = {p["paper_id"] for p in edited["papers"] if p["decision"] == "include"}
    keep = set(sorted(keep)[:3])
    for paper in edited["papers"]:
        if paper["decision"] == "include" and paper["paper_id"] not in keep:
            paper["decision"] = "exclude"
    edited["analyses"] = [a for a in edited["analyses"] if a["paper_id"] in keep]
    method = MethodOutput.model_validate(
        (await runner.run(context("method", inputs={"literature": edited}))).data
    )
    assert all(set(proposal.evidence_paper_ids) <= keep for proposal in method.proposals)

    approved = {stage: outcome.data for stage, outcome in outcomes.items()}
    coding = CodingOutput.model_validate(approved["coding"])
    config_file = next(file.content for file in coding.files if file.role == "config")
    assert f"dataset: {approved['method']['datasets'][0]}" in config_file
    experiment = ExperimentOutput.model_validate(approved["experiment"])
    assert (experiment.provenance.code_sha256, experiment.provenance.config_sha256) == (
        demo.code_hashes(coding)
    )
    writing = WritingOutput.model_validate(approved["writing"])
    included = {
        p["paper_id"] for p in approved["literature"]["papers"] if p["decision"] == "include"
    }
    assert {citation.paper_id for citation in writing.citations} <= included


async def test_coding_attempts_revise_the_previous_attempt(runner: PipelineStageRunner) -> None:
    outcomes = await run_pipeline(runner)
    inputs = {stage: outcomes[stage].data for stage in ("literature", "method")}
    first = CodingOutput.model_validate(outcomes["coding"].data)
    second = CodingOutput.model_validate(
        (
            await runner.run(
                context("coding", inputs=inputs, attempt=2, feedback="Prefer GroupNorm")
            )
        ).data
    )
    old = {file.path: file.content for file in first.files}
    new = {file.path: file.content for file in second.files}
    assert any(old[path] != new[path] for path in ("model.py", "losses.py", "configs/train.yaml"))
    assert "Prefer GroupNorm" in new["README.md"]


async def test_progress_lines_describe_each_stage(runner: PipelineStageRunner) -> None:
    log = Recorder()
    await run_pipeline(runner, log)
    codes = [code for code, _, _ in log.lines]
    for expected in ("demo.search", "demo.screen", "demo.analyse", "demo.synthesise"):
        assert expected in codes
    for expected in ("demo.propose", "demo.code", "demo.smoke_test", "demo.epoch", "demo.draft"):
        assert expected in codes
    assert all(message for _, _, message in log.lines)
    json.dumps([params for _, params, _ in log.lines])  # params travel as JSON event payloads
    epochs = [params for code, params, _ in log.lines if code == "demo.epoch"]
    assert epochs[-1]["epoch"] == epochs[-1]["epochs"]  # the last epoch is always reported


def test_progress_steps_use_the_output_numbers() -> None:
    config = RunConfig(sources=["arxiv", "openalex"])
    plan = demo.research_plan("Monocular depth", 3, config=config)
    literature = demo.literature("Monocular depth", plan, config, 3)
    search, screen, analyse, _ = progress_steps(literature, config)
    assert search.params == {"sources": ["arxiv", "openalex"], "queries": len(plan.queries)}
    assert search.message.startswith("Searching arXiv, OpenAlex")
    assert screen.params["papers"] == len(literature.papers)
    assert analyse.params["papers"] == len(literature.analyses)


def test_stage_seconds_come_from_the_worker_unless_the_run_overrides_them() -> None:
    runner = PipelineStageRunner(FakePlanner(), demo_stage_seconds=6)
    assert runner.stage_seconds(context("method")) == 6
    assert runner.stage_seconds(context("method", demo_stage_seconds=600)) == 600
    assert runner.stage_seconds(context("method", demo_stage_seconds=0)) == 0
    huge = context("method", demo_stage_seconds=10**6)
    assert runner.stage_seconds(huge) == MAX_DEMO_STAGE_SECONDS


async def test_a_simulated_stage_takes_its_time(runner: PipelineStageRunner) -> None:
    literature = (await runner.run(context("literature"))).data
    started = time.monotonic()
    await runner.run(context("method", inputs={"literature": literature}, demo_stage_seconds=0.3))
    assert time.monotonic() - started >= 0.3


async def test_phase1_placeholders_are_rebuilt_instead_of_failing(
    runner: PipelineStageRunner,
) -> None:
    # What Phase 1 approved: the literature plan on its own, and placeholder notes after it.
    plan = demo.research_plan("Monocular depth", 9).model_dump(mode="json")
    inputs: dict[str, dict[str, Any]] = {"literature": plan}
    for stage in ("method", "coding", "experiment"):
        inputs[stage] = {"stage": stage, "note": "placeholder"}
    outcome = await runner.run(context("writing", inputs=inputs))
    WritingOutput.model_validate(outcome.data)


async def test_a_missing_input_fails_the_stage(runner: PipelineStageRunner) -> None:
    with pytest.raises(StageFailedError, match=r"^method\.missing_input"):
        await runner.run(context("method"))
    with pytest.raises(StageFailedError, match=r"^stage\.unknown"):
        await runner.run(context("review"))


def test_a_revision_shows_the_plan_it_revises_and_every_comment() -> None:
    plan = demo.research_plan("Monocular depth", 4)
    previous = demo.literature("Monocular depth", plan, RunConfig(), 4).model_dump(mode="json")
    comments = ("Focus on 2024", "Add a query on self-supervised methods")
    revision = dataclasses.replace(
        context("literature", attempt=3, feedback=comments[-1]),
        previous_output=previous,
        feedback_history=comments,
    )
    prompt = plan_prompt(revision)
    assert json.dumps(previous["plan"], ensure_ascii=False, indent=2) in prompt
    assert previous["papers"][0]["title"] not in prompt  # the plan only, not the demo papers
    assert prompt.index(f"1. {comments[0]}") < prompt.index(f"2. {comments[1]}")
    first = plan_prompt(context("literature"))
    assert "Previous plan" not in first and "Reviewer feedback" not in first


def test_the_planners_gateway_calls_belong_to_the_attempt() -> None:
    ctx = context("literature")
    llm = CrewAIPlanner("http://gw", "secret")._llm(ctx)
    assert llm.cancelled is ctx.cancelled and llm.key_prefix == ctx.stage_run_id
    assert llm.on_call is not None
    llm.on_call({"model": "free/a", "idempotency_key": "k:call-1"})
    assert ctx.llm_calls == [{"model": "free/a", "idempotency_key": "k:call-1"}]

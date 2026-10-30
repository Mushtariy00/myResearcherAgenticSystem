"""The real writing stage on the test database, with a fake gateway."""

import uuid
from datetime import timedelta
from typing import Any

import pytest
from literature_testkit import rate_limited
from llm_stages_testkit import (
    ADABINS,
    DEPTH_ANYTHING,
    DPT,
    SECTION_TEXT,
    approve,
    block,
    context,
    gateway,
    harness,
    progress,
    section_answer,
    stored_output,
    upstream,
)
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from agentic_core.schemas import WritingOutput, validate_stage_output
from agentic_worker.activities import approved_degraded_reasons
from agentic_worker.gateway_llm import AttemptEndedError
from agentic_worker.outputs import WRITING_PROMPT_VERSION
from worker_testkit import Factory, create_run, run_events

DRAFT = """# Compact Depth Transformers for Indoor Scenes

## Abstract

We study compact depth transformers that train on one GPU.

## 1. Introduction

Depth from one image is ill-posed [1]. Bins [2] and transformers [2-3] help.

## 2. Method

We minimize $$L = \\frac{1}{n} \\sum_i |d_i - \\hat d_i|$$ on depths in $[0, 1]$, using `pred[0]` \
as in [2](https://example.org).

## 3. Experiments

### 3.1 Setup
We train on NYU Depth V2 [1, 3].

## References

- [1] Lihe Yang, Bingyi Kang, Zilong Huang et al. Depth Anything: Unleashing the Power of \
Large-Scale Unlabeled Data. CVPR, 2024. arXiv:2401.10891.
- [2] Shariq Farooq Bhat, Ibraheem Alhashim, Peter Wonka. AdaBins: Depth Estimation Using \
Adaptive Bins. CVPR, 2021. doi:10.1109/cvpr46437.2021.00400.
- [3] Rene Ranftl, Alexey Bochkovskiy, Vladlen Koltun. Vision Transformers for Dense Prediction. \
Preprint, 2021. doi:10.1109/iccv48922.2021.01196."""


def prompts(calls: list[Any]) -> list[str]:
    return [call.messages[-1]["content"] for call in calls]


async def test_the_writing_stage_outlines_writes_each_section_and_assembles_the_draft(
    db: Factory,
) -> None:
    mw = harness(db)
    run_id, stage_run_id = await mw.start("writing")
    await ActivityEnvironment().run(
        mw.activities.execute_stage, mw.execute(run_id, stage_run_id, "writing")
    )

    stored = await stored_output(db, stage_run_id)
    assert validate_stage_output("writing", stored.data).model_dump(mode="json") == stored.data
    assert (stored.degraded, stored.degraded_reason) == (False, None)
    assert (stored.model, stored.prompt_version) == ("fake/free-model:free", WRITING_PROMPT_VERSION)
    output = WritingOutput.model_validate(stored.data)
    assert output.markdown == DRAFT
    assert (output.title, output.abstract) == (
        "Compact Depth Transformers for Indoor Scenes",
        "We study compact depth transformers that train on one GPU.",
    )
    # The outline's sections, without the abstract and references the code adds.
    assert [(s.name, s.objective) for s in output.sections] == [
        ("Introduction", "Motivate the problem."),
        ("Method", "Describe the model."),
        ("Experiments", "Report the setup and results."),
    ]
    assert (output.output_format, output.review_focus) == (
        "Markdown draft structured like a conference paper",
        "Check every citation. Check the numbers.",
    )
    # Built from the markers used: [2-3] cites both; math, code and links cite nothing.
    assert [(c.key, c.paper_id) for c in output.citations] == [
        (1, DEPTH_ANYTHING),
        (2, ADABINS),
        (3, DPT),
    ]

    assert await progress(db, run_id) == [
        ("writing.outlined", {"sections": 3}),
        ("writing.drafted", {"section": "Introduction", "index": 1, "sections": 3}),
        ("writing.drafted", {"section": "Method", "index": 2, "sections": 3}),
        ("writing.drafted", {"section": "Experiments", "index": 3, "sections": 3}),
        ("writing.cited", {"citations": 3, "removed": 0}),
    ]
    keys = [f"{stage_run_id}:writing:outline:call-1"]
    keys += [f"{stage_run_id}:writing:section:{n}:call-1" for n in (1, 2, 3)]
    assert mw.gateway.answered() == keys
    assert [call.role for call in mw.gateway.calls] == ["writing.outline"] + ["writing.section"] * 3
    keyed = [call["idempotency_key"] for call in await run_events(db, run_id, "llm.call")]
    assert sorted(keyed) == sorted(keys)

    outline, *sections = prompts(mw.gateway.calls)
    research = block(outline, "RESEARCH")
    assert research.lstrip().startswith("LITERATURE REVIEW\nScope: ")
    assert f"[2] AdaBins: Depth Estimation Using Adaptive Bins (2021; CVPR) | key: {ADABINS}" in (
        research
    )
    assert "\nMETHOD\nResearch gaps:\n" in research and "\nRecommended proposal: " in research
    assert "\nCODE\nSummary: " in research and "\nEXPERIMENT\nStatus: " in research
    assert "to be confirmed" not in outline
    method = sections[1]
    assert 'Write section 2 of 3, "Method", of a research paper draft on this topic' in method
    assert "Its objective: Describe the model." in method
    assert "Sections:\n1. Introduction: Motivate the problem.\n2. Method: Describe" in method
    assert "numbered 2.1, 2.2" in method and block(method, "RESEARCH") == research


async def test_markers_outside_the_paper_list_are_removed_and_flagged(db: Factory) -> None:
    text = {**SECTION_TEXT, "Experiments": "We beat [9] on NYU [1, 3] and [2, 7]; see [5-6]."}
    mw = harness(db, gateway({"writing.section": lambda prompt: section_answer(prompt, text)}))
    run_id, stage_run_id = await mw.start("writing")
    await ActivityEnvironment().run(
        mw.activities.execute_stage, mw.execute(run_id, stage_run_id, "writing")
    )
    stored = await stored_output(db, stage_run_id)
    assert (stored.degraded, stored.degraded_reason) == (True, "writing.citations_removed")
    output = WritingOutput.model_validate(stored.data)
    assert "## 3. Experiments\n\nWe beat on NYU [1, 3] and [2]; see.\n\n## References" in (
        output.markdown
    )
    assert [c.key for c in output.citations] == [1, 2, 3]
    assert (await progress(db, run_id))[-1] == ("writing.cited", {"citations": 3, "removed": 3})


async def test_simulated_code_and_experiment_numbers_are_placeholders_to_be_confirmed(
    db: Factory,
) -> None:
    # A removed citation as well: the simulated results are what the reviewer must see first.
    text = {**SECTION_TEXT, "Experiments": "We train on NYU Depth V2 [1, 9]."}
    mw = harness(db, gateway({"writing.section": lambda prompt: section_answer(prompt, text)}))
    run_id, stage_run_id = await mw.start("writing", simulated=("coding", "experiment"))
    await ActivityEnvironment().run(
        mw.activities.execute_stage, mw.execute(run_id, stage_run_id, "writing")
    )
    stored = await stored_output(db, stage_run_id)
    assert (stored.degraded, stored.degraded_reason) == (True, "writing.simulated_results")
    assert ("writing.cited", {"citations": 3, "removed": 1}) in await progress(db, run_id)
    sent = prompts(mw.gateway.calls)
    assert len(sent) == 4
    for prompt in sent:
        assert (
            "Important: the code and the experiment below are simulated placeholders, generated "
            "for a demonstration and never run, so their numbers are made up. Present every such "
            'number as a placeholder "to be confirmed", never as a result'
        ) in prompt
        research = block(prompt, "RESEARCH")
        assert "\nCODE (SIMULATED PLACEHOLDER: numbers to be confirmed)\nSummary: " in research
        assert "\nEXPERIMENT (SIMULATED PLACEHOLDER: numbers to be confirmed)\n" in research


async def test_only_demo_outputs_count_as_simulated_results(db: Factory) -> None:
    mw = harness(db)
    reasons = {"literature": "literature.partial_search", "experiment": "stage.demo"}
    outcome = await mw.runner.run(context("writing", degraded_inputs=reasons))
    assert outcome.degraded_reason == "writing.simulated_results"
    prompt = prompts(mw.gateway.calls)[0]
    assert "the experiment below is a simulated placeholder, generated for a demonstration" in (
        prompt
    )
    assert "\nCODE\n" in block(prompt, "RESEARCH")


async def test_a_draft_built_on_a_generated_review_says_so_first(db: Factory) -> None:
    """Runs approved while the literature stage was a demo reach the real writing stage: their
    draft cites made-up papers, which matters more than simulated results."""
    mw = harness(db)
    reasons = {"literature": "literature.demo_search", "experiment": "stage.demo"}
    outcome = await mw.runner.run(context("writing", degraded_inputs=reasons))
    assert (outcome.degraded, outcome.degraded_reason) == (True, "writing.demo_literature")


async def test_an_attempt_that_runs_again_replays_the_finished_calls(db: Factory) -> None:
    # The second section is told to wait: the free quota ran out.
    second = ":writing:section:2:call-1"
    fake = gateway(failures=[(lambda key: key.endswith(second), rate_limited(42))])
    mw = harness(db, fake)
    run_id, stage_run_id = await mw.start("writing")
    request = mw.execute(run_id, stage_run_id, "writing")
    with pytest.raises(ApplicationError) as waited:
        await ActivityEnvironment().run(mw.activities.execute_stage, request)
    assert (waited.value.type, waited.value.message) == ("RateLimited", "free_quota.exhausted")
    assert waited.value.next_retry_delay == timedelta(seconds=42)
    paid = fake.answered()
    assert paid == [
        f"{stage_run_id}:writing:outline:call-1",
        f"{stage_run_id}:writing:section:1:call-1",
    ]

    await ActivityEnvironment().run(mw.activities.execute_stage, request)  # the workflow's rerun

    # The finished calls are replays (free); only the rest are paid for.
    assert [call.key for call in fake.calls if call.replayed] == paid
    assert fake.answered()[len(paid) :] == [
        f"{stage_run_id}:writing:section:2:call-1",
        f"{stage_run_id}:writing:section:3:call-1",
    ]
    # Each step reported once, and each call recorded once.
    assert [(code, params.get("index")) for code, params in await progress(db, run_id)] == [
        ("writing.outlined", None),
        ("writing.drafted", 1),
        ("writing.drafted", 2),
        ("writing.drafted", 3),
        ("writing.cited", None),
    ]
    keyed = [call["idempotency_key"] for call in await run_events(db, run_id, "llm.call")]
    assert sorted(keyed) == sorted(set(keyed)) == sorted(fake.answered())
    assert WritingOutput.model_validate((await stored_output(db, stage_run_id)).data).markdown == (
        DRAFT
    )


async def test_a_cancel_between_sections_makes_no_more_calls(db: Factory) -> None:
    mw = harness(db)

    async def cancel_after_the_first_section(
        code: str, params: dict[str, Any], message: str
    ) -> None:
        if code == "writing.drafted" and params["index"] == 1:
            ctx.cancelled.set()  # what execute_stage does when the activity is cancelled

    ctx = context("writing", log=cancel_after_the_first_section)
    with pytest.raises(AttemptEndedError):
        await mw.runner.run(ctx)
    assert [call.key for call in mw.gateway.calls] == [
        f"{ctx.stage_run_id}:writing:outline:call-1",
        f"{ctx.stage_run_id}:writing:section:1:call-1",
    ]


async def test_a_section_without_its_marker_lines_gets_one_repair(db: Factory) -> None:
    answers = iter(["Depth is hard, as everyone knows [1]."])

    def section(prompt: str) -> str:
        return next(answers, None) or section_answer(prompt)

    fake = gateway({"writing.section": section})
    mw = harness(db, fake)
    ctx = context("writing")
    outcome = await mw.runner.run(ctx)
    assert fake.keys("writing.section")[:2] == [
        f"{ctx.stage_run_id}:writing:section:1:call-1",
        f"{ctx.stage_run_id}:writing:section:1:call-2",
    ]
    repair = fake.calls[2].messages[-1]["content"]
    assert repair.startswith(
        "Your previous answer could not be used: the section must be between the lines "
        "--- BEGIN SECTION --- and --- END SECTION ---\nReturn ONLY the corrected section "
        "between the two marker lines, in this form:\n--- BEGIN SECTION ---\n"
    )
    assert WritingOutput.model_validate(outcome.data).markdown == DRAFT


async def test_a_revision_shows_the_previous_draft_and_every_comment(db: Factory) -> None:
    previous = (await harness(db).runner.run(context("writing"))).data
    comments = ("Shorten the introduction", "Cite AdaBins in the method")
    mw = harness(db)
    await mw.runner.run(context("writing", previous_output=previous, feedback_history=comments))
    outline, introduction, *_ = prompts(mw.gateway.calls)
    planned = block(outline, "PREVIOUS OUTLINE")
    assert planned.strip().startswith("Title: Compact Depth Transformers for Indoor Scenes\n")
    assert "\n- Method: Describe the model.\n" in planned
    assert block(introduction, "PREVIOUS SECTION").strip() == SECTION_TEXT["Introduction"]
    for prompt in (outline, introduction):
        assert prompt.index(f"1. {comments[0]}") < prompt.index(f"2. {comments[1]}")


async def test_approved_inputs_keep_the_reason_their_stage_gave_them(db: Factory) -> None:
    run_id = await create_run(db)
    data = upstream()
    await approve(db, run_id, "literature", data["literature"], "literature.partial_search")
    await approve(db, run_id, "method", data["method"])
    await approve(db, run_id, "coding", data["coding"], "stage.demo")
    # A reviewer edited the demo experiment: its numbers are made up all the same.
    edited = data["experiment"] | {"summary": "Edited by the reviewer."}
    await approve(db, run_id, "experiment", data["experiment"], "stage.demo", edited=edited)
    async with db() as session:
        run = uuid.UUID(run_id)
        assert await approved_degraded_reasons(session, run, "writing") == {
            "literature": "literature.partial_search",
            "coding": "stage.demo",
            "experiment": "stage.demo",
        }
        assert await approved_degraded_reasons(session, run, "coding") == {
            "literature": "literature.partial_search"
        }
        assert await approved_degraded_reasons(session, run, "literature") == {}

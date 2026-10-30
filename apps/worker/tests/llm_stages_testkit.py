"""Fakes for the method and writing stages: approved inputs, a fake gateway that answers their
roles, and a harness that runs the real runners through execute_stage on the test database."""

import json
import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx
from literature_testkit import FakeGateway, fake_llms
from sqlalchemy import select

from agentic_core import demo
from agentic_core.enums import Decision, StageStatus
from agentic_core.schemas import LiteratureOutput, RunConfig
from agentic_core.stages import STAGE_ORDER, Stage
from agentic_db.models import Approval, StageOutput, StageRun
from agentic_worker.activities import StageActivities
from agentic_worker.agents import StageAgents
from agentic_worker.method.runner import MethodRunner
from agentic_worker.outputs import STAGE_DEMO_REASON, content_sha256
from agentic_worker.stages import LogEvent, PipelineStageRunner, StageContext
from agentic_worker.types import StageExecIn, StageStartIn
from agentic_worker.writing.runner import WritingRunner
from worker_testkit import Factory, FakePlanner, FakeValkey, create_run, run_events

TOPIC = "Monocular depth estimation"


def _paper(key: str, title: str, authors: list[str], year: int, **fields: Any) -> dict[str, Any]:
    return {
        "paper_id": key,
        "title": title,
        "authors": authors,
        "year": year,
        "abstract": f"The abstract of {title}.",
        "source": "openalex",
        "pdf_available": True,
        "relevance": 0.9,
        "decision": "include",
        "decision_reason": "On topic.",
        **fields,
    }


def _analysis(key: str, contribution: str) -> dict[str, Any]:
    return {
        "paper_id": key,
        "contribution": contribution,
        "method": "A monocular depth network.",
        "results": "Better depth on NYU Depth V2.",
        "limitations": "Indoor scenes only.",
        "evidence": [],
    }


DEPTH_ANYTHING = "arxiv:2401.10891"
ADABINS = "doi:10.1109/cvpr46437.2021.00400"
DPT = "doi:10.1109/iccv48922.2021.01196"
MOLECULES = "doi:10.1000/molecules.2020.5"
KEYS = (DEPTH_ANYTHING, ADABINS, DPT, MOLECULES)  # the papers [1] to [4]

LITERATURE = LiteratureOutput.model_validate(
    {
        "plan": demo.research_plan(TOPIC, 1).model_dump(mode="json"),
        "papers": [
            _paper(
                DEPTH_ANYTHING,
                "Depth Anything: Unleashing the Power of Large-Scale Unlabeled Data",
                ["Lihe Yang", "Bingyi Kang", "Zilong Huang", "Xiaogang Xu"],
                2024,
                venue="CVPR",
                arxiv_id="2401.10891",
                source="arxiv",
            ),
            _paper(
                ADABINS,
                "AdaBins: Depth Estimation Using Adaptive Bins",
                ["Shariq Farooq Bhat", "Ibraheem Alhashim", "Peter Wonka"],
                2021,
                venue="CVPR",
                doi="10.1109/cvpr46437.2021.00400",
            ),
            _paper(
                DPT,
                "Vision Transformers for Dense Prediction",
                ["Rene Ranftl", "Alexey Bochkovskiy", "Vladlen Koltun"],
                2021,
                doi="10.1109/iccv48922.2021.01196",
                pdf_available=False,
                relevance=0.7,
                decision="maybe",
                decision_reason="Dense prediction in general.",
            ),
            _paper(
                MOLECULES,
                "Graph Neural Networks for Molecular Property Prediction",
                ["Chen Wu"],
                2020,
                relevance=0.1,
                decision="exclude",
                decision_reason="Off topic.",
            ),
        ],
        "analyses": [
            _analysis(DEPTH_ANYTHING, "Large-scale pseudo labels for robust depth."),
            _analysis(ADABINS, "Adaptive bins over the depth range."),
        ],
        "key_findings": [
            {
                "title": "Depth Anything",
                "source": "arXiv",
                "summary": "Pseudo labels cut the error by 12.5 percent.",
                "paper_id": DEPTH_ANYTHING,
            },
            {"title": "A survey", "source": "OpenAlex", "summary": "Benchmarks disagree."},
        ],
        "synthesis": "Depth networks improve.\n\nOpen problems remain.",
    }
)


def upstream() -> dict[str, dict[str, Any]]:
    """The approved output of every stage before writing, as stored."""
    method = demo.method(TOPIC, LITERATURE, 2, config=RunConfig())
    coding = demo.coding(TOPIC, method, 3)
    experiment = demo.experiment(TOPIC, coding, 4)
    return {
        "literature": LITERATURE.model_dump(mode="json"),
        "method": method.model_dump(mode="json"),
        "coding": coding.model_dump(mode="json"),
        "experiment": experiment.model_dump(mode="json"),
    }


def inputs_for(stage: str) -> dict[str, dict[str, Any]]:
    """The approved outputs ``stage`` reads: those of the stages before it."""
    before = [s.value for s in STAGE_ORDER[: STAGE_ORDER.index(Stage(stage))]]
    return {name: data for name, data in upstream().items() if name in before}


# --- the gateway's answers -----------------------------------------------------------------------

_KEY = re.compile(r"\| key: (\S+) \|")
_SECTION = re.compile(r'Write section (\d+) of (\d+), "(.+?)"')


def block(prompt: str, label: str) -> str:
    return prompt.split(f"--- BEGIN {label} ---", 1)[1].split(f"--- END {label} ---", 1)[0]


def method_answer(prompt: str, **changes: Any) -> str:
    """Three proposals; evidence by key (one in upper case) and by number."""
    keys = _KEY.findall(block(prompt, "LITERATURE REVIEW"))
    answer: dict[str, Any] = {
        "research_gaps": ["Few methods train on one GPU.", "Results rarely cover two datasets."],
        "proposals": [
            {
                "name": "Distilled depth transformer",
                "rationale": "Pseudo labels transfer to small students.",
                "expected_benefit": "Close to the teacher at a tenth of the cost.",
                "risk": "The student may underfit.",
                "evidence_paper_ids": [keys[0], keys[1].upper(), keys[0]],
            },
            {
                "name": "Adaptive bins head",
                "rationale": ["Bins help.", "They are cheap."],
                "expected_benefit": "Sharper depth edges.",
                "risk": "More hyperparameters.",
                "evidence_paper_ids": ["[2]"],
            },
            {
                "name": "Self-supervised pretraining",
                "rationale": "Unlabeled indoor video is plentiful.",
                "expected_benefit": "Less labelled data.",
                "risk": "Scale ambiguity.",
                "evidence_paper_ids": [],
            },
        ],
        "recommended_option": "distilled depth transformer",
        "implementation_focus": "Train a small ViT student with an L1 loss.",
        "datasets": "nyu2",
        "evaluation_metrics": ["abs_rel", "rmse", "delta1"],
    }
    return json.dumps(answer | changes)


def outline_answer(prompt: str) -> str:
    """Three sections between an abstract and references the outline should leave out."""
    return json.dumps(
        {
            "title": "Compact Depth Transformers\nfor Indoor Scenes",
            "abstract": "We study compact depth transformers that train on one GPU.",
            "sections": [
                {"name": "Abstract", "objective": "Summarize the paper."},
                {"name": "1. Introduction", "objective": "Motivate the problem."},
                {"name": "Method", "objective": "Describe the model."},
                {"name": "III. Experiments", "objective": "Report the setup and results."},
                {"name": "References", "objective": "List the papers."},
            ],
            "output_format": "Markdown draft structured like a conference paper",
            "review_focus": ["Check every citation.", "Check the numbers."],
        }
    )


SECTION_TEXT = {
    "Introduction": "Depth from one image is ill-posed [1]. Bins [2] and transformers [2-3] help.",
    "Method": "We minimize $$L = \\frac{1}{n} \\sum_i |d_i - \\hat d_i|$$ on depths in $[0, 1]$, "
    "using `pred[0]` as in [2](https://example.org).",
    "Experiments": "### 3.1 Setup\nWe train on NYU Depth V2 [1, 3].",
}


def section_answer(prompt: str, text: Mapping[str, str] = SECTION_TEXT) -> str:
    """The section's text between the markers, with reasoning around them and the heading the
    draft adds itself."""
    found = _SECTION.search(prompt)
    if found is None:
        raise AssertionError("not a section request")
    name = found.group(3)
    return (
        f"Let me write the {name} section.\n--- BEGIN SECTION ---\n## {name}\n"
        f"{text.get(name, 'Text.')}\n--- END SECTION ---\nI hope this helps."
    )


ANSWERS: dict[str, Callable[[str], str]] = {
    "method.propose": method_answer,
    "writing.outline": outline_answer,
    "writing.section": section_answer,
}


def gateway(
    answers: Mapping[str, Callable[[str], str]] | None = None,
    failures: list[tuple[Callable[[str], bool], httpx.Response]] | None = None,
) -> FakeGateway:
    """The fake gateway of the literature tests, answering the method and writing roles."""
    return FakeGateway(answers={**ANSWERS, **(answers or {})}, failures=failures or [])


# --- the stages on the test database -------------------------------------------------------------


async def approve(
    db: Factory,
    run_id: str,
    stage: str,
    data: dict[str, Any],
    reason: str | None = None,
    edited: dict[str, Any] | None = None,
) -> None:
    """An approved attempt of ``stage`` whose output says ``reason``; with ``edited``, a reviewer
    approved an edited version of it."""
    async with db() as session:
        stage_run = StageRun(
            run_id=uuid.UUID(run_id), stage=stage, attempt=1, status=StageStatus.APPROVED
        )
        session.add(stage_run)
        await session.flush()
        output = StageOutput(
            stage_run_id=stage_run.id,
            data=data,
            sha256=content_sha256(data),
            degraded=reason is not None,
            degraded_reason=reason,
        )
        session.add(output)
        if edited is not None:
            output = StageOutput(
                stage_run_id=stage_run.id,
                version=2,
                data=edited,
                sha256=content_sha256(edited),
                edited_by="alice",
            )
            session.add(output)
        await session.flush()
        session.add(
            Approval(
                stage_output_id=output.id,
                sha256=output.sha256,
                decision=Decision.APPROVE,
                actor_id="bob",
            )
        )
        await session.commit()


async def stored_output(db: Factory, stage_run_id: str) -> StageOutput:
    async with db() as session:
        return (
            await session.scalars(
                select(StageOutput).where(StageOutput.stage_run_id == uuid.UUID(stage_run_id))
            )
        ).one()


async def progress(db: Factory, run_id: str) -> list[tuple[str, dict[str, Any]]]:
    return [(e["code"], e["params"]) for e in await run_events(db, run_id, "log")]


@dataclass
class Harness:
    """The real method and writing stages behind execute_stage, talking to a fake gateway."""

    db: Factory
    gateway: FakeGateway
    runner: PipelineStageRunner
    activities: StageActivities

    async def start(self, stage: str, simulated: tuple[str, ...] = ()) -> tuple[str, str]:
        """A run with every stage before ``stage`` approved (``simulated`` ones with demo
        outputs) and the first attempt of ``stage`` started: (run id, stage run id)."""
        run_id = await create_run(self.db, topic=TOPIC)
        for earlier, data in inputs_for(stage).items():
            reason = STAGE_DEMO_REASON if earlier in simulated else None
            await approve(self.db, run_id, earlier, data, reason)
        started = await self.activities.start_stage(
            StageStartIn(run_id=run_id, stage=stage, attempt=1)
        )
        return run_id, started.stage_run_id

    def execute(self, run_id: str, stage_run_id: str, stage: str) -> StageExecIn:
        return StageExecIn(run_id=run_id, stage_run_id=stage_run_id, stage=stage, attempt=1)


def harness(db: Factory, fake: FakeGateway | None = None) -> Harness:
    fake = fake or gateway()
    agents = StageAgents(fake_llms(fake))
    runner = PipelineStageRunner(
        FakePlanner(),
        method=MethodRunner(agents, db),
        writing=WritingRunner(agents, db),
        demo_stage_seconds=0,
    )
    return Harness(db, fake, runner, StageActivities(db, FakeValkey(), runner))


async def _discard(code: str, params: dict[str, Any], message: str) -> None:
    return None


def context(
    stage: str,
    *,
    degraded_inputs: Mapping[str, str] | None = None,
    previous_output: dict[str, Any] | None = None,
    feedback_history: tuple[str, ...] = (),
    log: LogEvent = _discard,
) -> StageContext:
    """An attempt of ``stage`` as execute_stage would describe it, for running a stage directly;
    its run has no events yet."""
    return StageContext(
        run_id=str(uuid.uuid4()),
        stage_run_id=str(uuid.uuid4()),
        stage=stage,
        attempt=len(feedback_history) + 1,
        feedback=feedback_history[-1] if feedback_history else "",
        topic=TOPIC,
        owner_id="bob",
        project_id=str(uuid.uuid4()),
        llm_policy="auto",
        budget_cap_usd=None,
        inputs=inputs_for(stage),
        degraded_inputs=degraded_inputs or {},
        log=log,
        previous_output=previous_output,
        feedback_history=feedback_history,
    )

"""Stage-output helpers shared by the activities, the stage runner and the demo seed.

Nothing here talks to an LLM, so the demo seed can import it without loading CrewAI.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from agentic_core import demo
from agentic_core.schemas import (
    CodingOutput,
    ExperimentOutput,
    LiteratureOutput,
    MethodOutput,
    RunConfig,
    StrictModel,
    WritingOutput,
)

PLAN_PROMPT_VERSION = "literature-plan@1"
# The real literature stage: the plan prompt (literature-plan@1) with the screening, analysis
# and synthesis prompts of agentic_worker.literature. Bump it when any of them changes.
LITERATURE_PROMPT_VERSION = "literature@1"
# The real method and writing stages (agentic_worker.method, agentic_worker.writing): bump each
# when any of its prompts changes.
METHOD_PROMPT_VERSION = "method@1"
WRITING_PROMPT_VERSION = "writing@1"
DEMO_PROMPT_VERSION = demo.PROMPT_VERSION
# Degraded reasons the front end shows for demo outputs (the search when the worker runs with
# ARP_LITERATURE_SEARCH=demo; coding and experiment, which are not built yet; method and
# writing with ARP_LLM_STAGES=demo; every stage of a simulated run).
LITERATURE_DEMO_REASON = "literature.demo_search"
STAGE_DEMO_REASON = "stage.demo"
# A literature output with one of these reasons holds generated papers, not found ones (the last
# two are Phase 1 placeholders). A real stage built on it says so: its papers are made up.
GENERATED_LITERATURE_REASONS = frozenset(
    {LITERATURE_DEMO_REASON, STAGE_DEMO_REASON, "literature.search_pending", "stage.placeholder"}
)


def content_sha256(data: dict[str, Any]) -> str:
    """The hash approvals bind to: SHA-256 of the canonical JSON of a stage output."""
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def demo_seed(run_id: str, stage: str, attempt: int | None = None) -> int:
    """A stable seed for a run's demo output. Without ``attempt`` it is shared by all attempts
    (coding uses that, so each attempt revises the previous one)."""
    key = f"{run_id}:{stage}" if attempt is None else f"{run_id}:{stage}:{attempt}"
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big")


@dataclass(frozen=True)
class Progress:
    """One progress log line of a simulated stage.

    ``code`` and ``params`` let the browser translate it; ``message`` is the English fallback.
    """

    code: str
    params: dict[str, Any] = field(default_factory=dict)
    message: str = ""


def progress_steps(output: StrictModel, config: RunConfig) -> list[Progress]:
    """What a real stage would report while producing ``output``, in order."""
    if isinstance(output, LiteratureOutput):
        return _literature_steps(output, config)
    if isinstance(output, MethodOutput):
        return _method_steps(output)
    if isinstance(output, CodingOutput):
        return _coding_steps(output)
    if isinstance(output, ExperimentOutput):
        return _experiment_steps(output)
    if isinstance(output, WritingOutput):
        return _writing_steps(output)
    raise TypeError(f"no progress steps for {type(output).__name__}")


def _literature_steps(output: LiteratureOutput, config: RunConfig) -> list[Progress]:
    sources = list(config.sources)
    labels = ", ".join(demo.SOURCE_LABELS[source] for source in sources)
    queries = len(output.plan.queries)
    papers = len(output.papers)
    candidates = papers * 4 + queries * 3  # what the search returned before de-duplication
    included = sum(paper.decision == "include" for paper in output.papers)
    findings = len(output.key_findings)
    return [
        Progress(
            "demo.search",
            {"sources": sources, "queries": queries},
            f"Searching {labels} with {queries} queries",
        ),
        Progress(
            "demo.screen",
            {"candidates": candidates, "papers": papers},
            f"Screening {candidates} candidates; keeping the {papers} most relevant papers",
        ),
        Progress("demo.analyse", {"papers": included}, f"Analysing {included} included papers"),
        Progress(
            "demo.synthesise",
            {"findings": findings},
            f"Writing the synthesis from {findings} key findings",
        ),
    ]


def _method_steps(output: MethodOutput) -> list[Progress]:
    gaps, proposals = len(output.research_gaps), len(output.proposals)
    return [
        Progress("demo.gaps", {"gaps": gaps}, f"Mapping {gaps} research gaps"),
        Progress("demo.propose", {"proposals": proposals}, f"Drafting {proposals} proposals"),
        Progress(
            "demo.recommend",
            {"option": output.recommended_option},
            f"Recommending: {output.recommended_option}",
        ),
    ]


def _coding_steps(output: CodingOutput) -> list[Progress]:
    tests = sum(file.content.count("\ndef test_") for file in output.files if file.role == "test")
    smoke = output.smoke_test
    verdict = "passed" if smoke.passed else "failed"
    return [
        Progress(
            "demo.code",
            {"files": len(output.files), "entrypoint": output.entrypoint},
            f"Writing {len(output.files)} files (entry point {output.entrypoint})",
        ),
        Progress(
            "demo.test",
            {"tests": tests},
            f"Running {tests} unit tests and a 2-batch dry run",
        ),
        Progress(
            "demo.smoke_test",
            {"passed": smoke.passed, "seconds": round(smoke.duration_seconds, 1)},
            f"Smoke test {verdict} in {smoke.duration_seconds:.0f} s",
        ),
    ]


def _experiment_steps(output: ExperimentOutput) -> list[Progress]:
    provenance = output.provenance
    epochs = max((len(series.points) for series in output.series), default=0)
    steps = [
        Progress(
            "demo.train",
            {"epochs": epochs, "dataset": provenance.dataset, "gpu": provenance.gpu_name},
            f"Training for {epochs} epochs on {provenance.dataset} ({provenance.gpu_name})",
        )
    ]
    metric = next((s for s in output.series if s.name != "loss" and s.split == "val"), None)
    if metric is None or epochs == 0:
        return steps
    # About four evenly spaced checkpoints, always including the last epoch.
    marks = sorted({round(epochs * share) - 1 for share in (0.25, 0.5, 0.75, 1.0)} - {-1})
    for index in marks:
        value = metric.points[index].value if index < len(metric.points) else None
        shown = "not measured" if value is None else f"{value:.3f}"
        steps.append(
            Progress(
                "demo.epoch",
                {
                    "epoch": index + 1,
                    "epochs": epochs,
                    "metric": metric.name,
                    "value": None if value is None else round(value, 4),
                },
                f"Epoch {index + 1}/{epochs}: val {metric.name} {shown}",
            )
        )
    return steps


def _writing_steps(output: WritingOutput) -> list[Progress]:
    names = [section.name for section in output.sections]
    total = len(names)
    steps = [Progress("demo.outline", {"sections": total}, f"Outlining {total} sections")]
    for name in ("Introduction", "Method", "Experiments"):
        if name in names:
            index = names.index(name) + 1
            steps.append(
                Progress(
                    "demo.draft",
                    {"section": name, "index": index, "sections": total},
                    f"Drafting {name} ({index}/{total})",
                )
            )
    citations = len(output.citations)
    steps.append(
        Progress(
            "demo.cite",
            {"citations": citations},
            f"Linking {citations} citations to the included papers",
        )
    )
    return steps

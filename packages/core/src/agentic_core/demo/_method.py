"""Demo method stage: research gaps and three proposals grounded in the screened papers."""

from agentic_core.demo._profiles import dataset_spec, profile_for
from agentic_core.demo._text import counted, join_words, lower_phrase, revision_note, rng_for
from agentic_core.schemas import LiteratureOutput, MethodOutput, MethodProposal, PaperRef, RunConfig


def method(
    topic: str,
    literature: LiteratureOutput,
    seed: int,
    feedback: str = "",
    *,
    config: RunConfig | None = None,
) -> MethodOutput:
    """Three proposals that cite included papers, the gaps behind them, and the dataset
    (``config.dataset`` when set) and metrics to evaluate the recommended one with."""
    config = config or RunConfig()
    profile = profile_for(topic, config.dataset)
    rng = rng_for(seed, "method")
    dataset = dataset_spec(profile, config.dataset)
    metrics = profile.metrics[: rng.choice((2, 3, 3))]
    included = [paper for paper in literature.papers if paper.decision == "include"]
    gaps = rng.sample(profile.gaps, rng.randint(2, 3))
    if included:
        several = rng.randint(1, max(1, len(included) // 3))
        report = counted(several, "reports", "report")
        gaps.append(
            f"Only {several} of the {len(included)} included papers {report} results on more "
            "than one dataset"
        )

    pool = _evidence_pool(literature)
    specs = rng.sample(profile.proposals, 3)
    proposals = []
    for spec in specs:
        cited = sorted(
            rng.sample(pool, min(len(pool), rng.randint(1, 3))),
            key=lambda paper: paper.relevance,
            reverse=True,
        )
        supported = "one screened paper" if len(cited) == 1 else f"{len(cited)} screened papers"
        proposals.append(
            MethodProposal(
                name=spec.name,
                rationale=f"{spec.rationale} Supported by {supported}.",
                expected_benefit=spec.benefit.format(
                    dataset=dataset.label, metric=metrics[0].label
                ),
                risk=spec.risk,
                evidence_paper_ids=[paper.paper_id for paper in cited],
            )
        )
    # The profile lists proposals from most to least feasible on the lab's 6 GB GPU.
    recommended = min(specs, key=profile.proposals.index).name
    focus = (
        f"Implement {lower_phrase(recommended)} as a compact {profile.architecture} that trains on "
        f"the lab's 6 GB GTX 1060 with mixed precision. Keep the harness-owned {dataset.label} "
        "loader, metrics and training loop, generate only the model and loss modules, and "
        f"report {join_words(metric.label for metric in metrics)}."
    )
    note = revision_note(feedback)
    return MethodOutput(
        research_gaps=gaps,
        proposals=proposals,
        recommended_option=recommended,
        implementation_focus=f"{note} {focus}" if note else focus,
        datasets=[config.dataset or dataset.id],
        evaluation_metrics=[metric.name for metric in metrics],
    )


def _evidence_pool(literature: LiteratureOutput) -> list[PaperRef]:
    """Included papers; failing that (a reviewer may have edited them away), maybes, then all."""
    for decision in ("include", "maybe"):
        papers = [paper for paper in literature.papers if paper.decision == decision]
        if papers:
            return papers
    return list(literature.papers)

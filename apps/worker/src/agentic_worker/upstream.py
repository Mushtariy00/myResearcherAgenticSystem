"""The approved outputs of earlier stages, as the method and writing prompts show them.

The literature review becomes one block of text for a data block: its scope, synthesis and key
findings, then every paper of the output, numbered as there ([1] is the first) and with its key,
the notes of its analysis or, for a paper that was not analysed, its abstract (an excluded paper
keeps only its line, for its number). The papers' notes share a character budget fairly, as a
paper's sections do.
"""

from collections.abc import Mapping, Sequence

from pydantic import ValidationError

from agentic_core.schemas import (
    LiteratureOutput,
    PaperAnalysis,
    PaperFinding,
    PaperRef,
    StrictModel,
)
from agentic_core.stages import Stage
from agentic_worker.literature.reading import cut, fair_shares
from agentic_worker.outputs import GENERATED_LITERATURE_REASONS
from agentic_worker.stages import StageContext, StageFailedError

# About 4,000 tokens of paper notes: 800 characters a paper in a 20-paper review.
NOTES_BUDGET_CHARS = 16_000
_SYNTHESIS_CHARS = 4_000
_ABSTRACT_CHARS = 1_000

REVIEWER_FEEDBACK = "Reviewer feedback, oldest first; address every point:\n{comments}"


def approved_input[ModelT: StrictModel](
    ctx: StageContext, stage: Stage, model: type[ModelT]
) -> ModelT:
    """The approved output of ``stage``. Where a demo stage rebuilds an output that predates the
    v1 schemas from generated data, a real stage fails: it would prompt on generated data."""
    data = ctx.inputs.get(stage.value)
    if data is None:
        raise StageFailedError(f"{ctx.stage}.missing_input: no approved {stage.value} output")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise StageFailedError(
            f"{ctx.stage}.missing_input: the approved {stage.value} output predates the v1 schema"
        ) from exc


def generated_literature(ctx: StageContext) -> bool:
    """Whether the approved literature output was generated rather than searched (a demo search,
    or a run approved before the real search): an output built on it rests on made-up papers.
    Runs approved while the literature stage was a demo still reach the real later stages."""
    return ctx.degraded_inputs.get(Stage.LITERATURE.value) in GENERATED_LITERATURE_REASONS


def paper_label(paper: PaperRef) -> str:
    venue = f"; {paper.venue}" if paper.venue else ""
    return f"{paper.title} ({paper.year}{venue})"


def _notes(paper: PaperRef, analysis: PaperAnalysis | None) -> str:
    if analysis is not None:
        return "\n".join(
            [
                f"Contribution: {analysis.contribution}",
                f"Method: {analysis.method}",
                f"Results: {analysis.results}",
                f"Limitations: {analysis.limitations}",
            ]
        )
    if paper.decision == "exclude":
        return ""  # listed only to keep the numbering
    return f"Abstract (not analysed): {cut(paper.abstract, _ABSTRACT_CHARS)}"


def _finding(finding: PaperFinding, numbers: Mapping[str, int]) -> str:
    number = numbers.get(finding.paper_id) if finding.paper_id else None
    return f"- [{number}] {finding.summary}" if number else f"- {finding.title}: {finding.summary}"


def literature_notes(literature: LiteratureOutput, budget: int = NOTES_BUDGET_CHARS) -> str:
    """The literature review as one block of text, for a prompt's data block."""
    numbers = {paper.paper_id: n for n, paper in enumerate(literature.papers, start=1)}
    analyses = {analysis.paper_id: analysis for analysis in literature.analyses}
    heads = [
        f"[{n}] {paper_label(paper)} | key: {paper.paper_id} | screening: {paper.decision}"
        for n, paper in enumerate(literature.papers, start=1)
    ]
    notes = [_notes(paper, analyses.get(paper.paper_id)) for paper in literature.papers]
    shares = fair_shares([len(note) for note in notes], budget)
    papers = [
        f"{head}\n{cut(note, share)}" if note else head
        for head, note, share in zip(heads, notes, shares, strict=True)
    ]
    findings = [_finding(finding, numbers) for finding in literature.key_findings]
    return "\n\n".join(
        [
            f"Scope: {literature.plan.scope}",
            f"Synthesis:\n{cut(literature.synthesis, _SYNTHESIS_CHARS)}",
            "Key findings:\n" + "\n".join(findings),
            "Papers, numbered:\n\n" + "\n\n".join(papers),
        ]
    )


def reviewer_feedback(comments: Sequence[str]) -> str:
    """Every comment that led to a revision, numbered, oldest first."""
    numbered = "\n".join(f"{n}. {comment}" for n, comment in enumerate(comments, start=1))
    return REVIEWER_FEEDBACK.format(comments=numbered)

"""Strict v1 stage-output schemas: the contract between stages, the API and the front end.

Ported from main:src/agentic_ai_system/schemas/models.py and extended to every stage. Fields
are required unless they have a default, and unknown fields are rejected, so an empty or
truncated LLM answer (``{}``) fails validation instead of passing as an all-defaults object.

Until a stage is built for real, the worker fills these models with generated demo data
(``agentic_core.demo``) and flags the output with a ``*.demo*`` degraded reason, so the
front end can be finished against the final shapes.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from agentic_core.stages import STAGE_ORDER, Stage

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


def _https_url(value: str | None) -> str | None:
    # Links end up in href attributes; only plain https URLs are allowed (no javascript:, data:).
    if value is not None and not value.startswith("https://"):
        raise ValueError("url must start with https://")
    return value


HttpsUrl = Annotated[str | None, AfterValidator(_https_url)]


def _relative_posix_path(value: str) -> str:
    parts = value.split("/")
    if value.startswith("/") or "\\" in value or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("path must be a relative POSIX path without '.' or '..' segments")
    return value


RelativePath = Annotated[NonEmptyStr, AfterValidator(_relative_posix_path)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Run options --------------------------------------------------------------------------------

SearchSource = Literal["arxiv", "semantic_scholar", "openalex", "crossref", "core"]


class RunConfig(StrictModel):
    """Options chosen in the new-run wizard, stored in ``runs.config``."""

    year_from: int = Field(default=2018, ge=1990, le=2100)
    year_to: int = Field(default=2026, ge=1990, le=2100)
    sources: list[SearchSource] = Field(
        default_factory=lambda: ["arxiv", "semantic_scholar", "openalex"], min_length=1
    )
    max_papers: int = Field(default=20, ge=5, le=50)
    # The run stops after the last listed stage; always a prefix of STAGE_ORDER.
    stages: list[Stage] = Field(default_factory=lambda: list(STAGE_ORDER), min_length=1)
    dataset: str | None = "nyu2"

    @model_validator(mode="after")
    def _consistent(self) -> "RunConfig":
        if self.year_from > self.year_to:
            raise ValueError("year_from must not be after year_to")
        if len(set(self.sources)) != len(self.sources):
            raise ValueError("sources must be unique")
        if tuple(self.stages) != STAGE_ORDER[: len(self.stages)]:
            raise ValueError("stages must start with literature and follow the pipeline order")
        return self


# --- Literature -------------------------------------------------------------------------------

PaperSource = Literal["arxiv", "semantic_scholar", "openalex", "crossref", "core", "demo"]
ScreeningDecision = Literal["include", "maybe", "exclude"]


class ResearchPlan(StrictModel):
    """The search plan the literature agent writes before searching."""

    topic: NonEmptyStr
    queries: list[NonEmptyStr] = Field(min_length=3, max_length=8)
    scope: NonEmptyStr
    inclusion_criteria: list[NonEmptyStr] = Field(min_length=1)
    subtopics: list[NonEmptyStr] = Field(min_length=1)


class PaperRef(StrictModel):
    """One retrieved paper with its screening result. ``paper_id`` is stable across runs."""

    paper_id: NonEmptyStr
    title: NonEmptyStr
    authors: list[NonEmptyStr] = Field(min_length=1)
    year: int = Field(ge=1900, le=2100)
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    url: HttpsUrl = None
    abstract: NonEmptyStr
    citation_count: int | None = Field(default=None, ge=0)
    source: PaperSource
    pdf_available: bool
    relevance: float = Field(ge=0, le=1)
    decision: ScreeningDecision
    decision_reason: NonEmptyStr


class EvidenceQuote(StrictModel):
    quote: NonEmptyStr
    page: int = Field(ge=1)


class PaperAnalysis(StrictModel):
    """Structured reading notes for one included paper; evidence points into its PDF."""

    paper_id: NonEmptyStr
    contribution: NonEmptyStr
    method: NonEmptyStr
    results: NonEmptyStr
    limitations: NonEmptyStr
    evidence: list[EvidenceQuote] = Field(default_factory=list)


class PaperFinding(StrictModel):
    title: NonEmptyStr
    source: NonEmptyStr
    summary: NonEmptyStr
    url: HttpsUrl = None
    paper_id: str | None = None


class LiteratureOutput(StrictModel):
    plan: ResearchPlan
    papers: list[PaperRef] = Field(min_length=1)
    analyses: list[PaperAnalysis] = Field(default_factory=list)
    key_findings: list[PaperFinding] = Field(min_length=1)
    synthesis: NonEmptyStr

    @model_validator(mode="after")
    def _analyses_reference_papers(self) -> "LiteratureOutput":
        known = {paper.paper_id for paper in self.papers}
        unknown = sorted({a.paper_id for a in self.analyses} - known)
        if unknown:
            raise ValueError(f"analyses reference unknown papers: {', '.join(unknown)}")
        return self


# --- Method -----------------------------------------------------------------------------------


class MethodProposal(StrictModel):
    name: NonEmptyStr
    rationale: NonEmptyStr
    expected_benefit: NonEmptyStr
    risk: NonEmptyStr
    evidence_paper_ids: list[NonEmptyStr] = Field(default_factory=list)


class MethodOutput(StrictModel):
    research_gaps: list[NonEmptyStr] = Field(min_length=1)
    proposals: list[MethodProposal] = Field(min_length=1)
    recommended_option: NonEmptyStr
    implementation_focus: NonEmptyStr
    datasets: list[NonEmptyStr] = Field(min_length=1)
    evaluation_metrics: list[NonEmptyStr] = Field(min_length=1)

    @model_validator(mode="after")
    def _recommendation_is_a_proposal(self) -> "MethodOutput":
        if self.recommended_option not in {proposal.name for proposal in self.proposals}:
            raise ValueError("recommended_option must name one of the proposals")
        return self


# --- Coding -----------------------------------------------------------------------------------

CodeRole = Literal["model", "loss", "config", "test", "docs"]


class CodeFile(StrictModel):
    path: RelativePath
    language: NonEmptyStr  # Shiki language id: python, yaml, markdown, ...
    role: CodeRole
    content: str


class SmokeTest(StrictModel):
    passed: bool
    duration_seconds: float = Field(ge=0)
    log: str


class CodingOutput(StrictModel):
    """Generated model and loss modules. The experiment harness owns data, metrics and the loop."""

    summary: NonEmptyStr
    files: list[CodeFile] = Field(min_length=1)
    entrypoint: NonEmptyStr  # e.g. "model.py:DepthNet"
    smoke_test: SmokeTest

    @model_validator(mode="after")
    def _unique_paths(self) -> "CodingOutput":
        paths = [file.path for file in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("file paths must be unique")
        return self


# --- Experiment -------------------------------------------------------------------------------

ExperimentStatus = Literal["succeeded", "failed", "timeout", "cancelled"]
MetricSplit = Literal["train", "val", "test"]


class MetricPoint(StrictModel):
    epoch: int = Field(ge=0)
    value: float | None  # None means "not measured"; never 0.0 as a stand-in


class MetricSeries(StrictModel):
    name: NonEmptyStr  # loss, abs_rel, rmse, delta1, ...
    split: MetricSplit
    higher_is_better: bool
    points: list[MetricPoint]


class Provenance(StrictModel):
    image_digest: NonEmptyStr  # sha256:... of the sandbox image
    code_sha256: Sha256Hex
    config_sha256: Sha256Hex
    dataset: NonEmptyStr
    dataset_version: NonEmptyStr
    seed: int
    gpu_name: str | None = None
    gpu_seconds: float = Field(ge=0)
    started_at: datetime
    finished_at: datetime | None = None


class ExperimentOutput(StrictModel):
    status: ExperimentStatus
    summary: NonEmptyStr
    config: dict[str, int | float | str | bool]
    series: list[MetricSeries]
    final_metrics: dict[str, float | None]
    logs_tail: str
    provenance: Provenance


# --- Writing ----------------------------------------------------------------------------------


class WritingSection(StrictModel):
    name: NonEmptyStr
    objective: NonEmptyStr


class Citation(StrictModel):
    key: int = Field(ge=1)  # the n of an "[n]" marker in the draft
    paper_id: NonEmptyStr


class WritingOutput(StrictModel):
    title: NonEmptyStr
    abstract: NonEmptyStr
    markdown: NonEmptyStr  # full draft; citations as [n]; rendered sanitized, never as raw HTML
    sections: list[WritingSection] = Field(min_length=1)
    citations: list[Citation] = Field(default_factory=list)
    output_format: NonEmptyStr
    review_focus: NonEmptyStr

    @model_validator(mode="after")
    def _unique_citation_keys(self) -> "WritingOutput":
        keys = [citation.key for citation in self.citations]
        if len(keys) != len(set(keys)):
            raise ValueError("citation keys must be unique")
        return self


STAGE_OUTPUT_MODELS: dict[Stage, type[StrictModel]] = {
    Stage.LITERATURE: LiteratureOutput,
    Stage.METHOD: MethodOutput,
    Stage.CODING: CodingOutput,
    Stage.EXPERIMENT: ExperimentOutput,
    Stage.WRITING: WritingOutput,
}


def validate_stage_output(stage: str, data: Mapping[str, Any]) -> StrictModel:
    """Validate ``data`` against the output model of ``stage``; raises ValidationError."""
    return STAGE_OUTPUT_MODELS[Stage(stage)].model_validate(data)

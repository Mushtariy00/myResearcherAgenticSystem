"""Strict v1 stage-output schemas, ported from legacy/src/agentic_ai_system/schemas/models.py.

Unlike the legacy models, every field is required and unknown fields are rejected, so an empty
or truncated LLM answer (``{}``) fails validation instead of passing as an all-defaults object.
Coding and experiment outputs are redesigned for the harness in Phase 3 and are not defined here.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PaperFinding(StrictModel):
    title: NonEmptyStr
    source: NonEmptyStr
    summary: NonEmptyStr
    url: str | None = None
    paper_id: str | None = None  # id of the row in `papers` once the paper library exists


class LiteratureOutput(StrictModel):
    topic: NonEmptyStr
    key_findings: list[PaperFinding] = Field(min_length=1)
    synthesis: NonEmptyStr


class MethodProposal(StrictModel):
    name: NonEmptyStr
    rationale: NonEmptyStr
    expected_benefit: NonEmptyStr
    risk: NonEmptyStr


class MethodOutput(StrictModel):
    research_gaps: list[NonEmptyStr] = Field(min_length=1)
    proposals: list[MethodProposal] = Field(min_length=1)
    recommended_option: NonEmptyStr
    implementation_focus: NonEmptyStr


class WritingSection(StrictModel):
    name: NonEmptyStr
    objective: NonEmptyStr


class WritingOutput(StrictModel):
    sections: list[WritingSection] = Field(min_length=1)
    output_format: NonEmptyStr
    review_focus: NonEmptyStr

from pydantic import BaseModel, Field


class PaperFinding(BaseModel):
    title: str = ""
    source: str = ""
    summary: str = ""
    url: str = ""


class LiteratureResearchOutput(BaseModel):
    topic: str = ""
    generated_at: str = ""
    key_findings: list[PaperFinding] = Field(default_factory=list)
    synthesis: str = ""


class LiteratureScreenSelection(BaseModel):
    index: int = 0
    title: str = ""
    reason: str = ""


class LiteratureScreenOutput(BaseModel):
    selected_indices: list[int] = Field(default_factory=list)
    rejected_indices: list[int] = Field(default_factory=list)
    selection_rationale: str = ""


class MethodProposal(BaseModel):
    name: str = ""
    rationale: str = ""
    expected_benefit: str = ""
    risk: str = ""


class MethodStageOutput(BaseModel):
    research_gaps: list[str] = Field(default_factory=list)
    proposals: list[MethodProposal] = Field(default_factory=list)
    recommended_option: str = ""
    implementation_focus: str = ""


class CodingStageOutput(BaseModel):
    sandbox_plan: str = ""
    files_to_create: list[str] = Field(default_factory=list)
    validation_steps: list[str] = Field(default_factory=list)


class ExperimentStageOutput(BaseModel):
    experiment_goal: str = ""
    run_config: dict[str, object] = Field(default_factory=dict)
    metrics_to_track: list[str] = Field(default_factory=list)


class WritingSection(BaseModel):
    name: str = ""
    objective: str = ""


class WritingStageOutput(BaseModel):
    sections: list[WritingSection] = Field(default_factory=list)
    output_format: str = ""
    review_focus: str = ""


class CodingExecutionResult(BaseModel):
    sandbox_dir: str = ""
    created_files: list[str] = Field(default_factory=list)
    validated_files: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)


class ExperimentExecutionResult(BaseModel):
    run_dir: str = ""
    metrics: dict[str, float] = Field(default_factory=dict)
    summary_file: str = ""

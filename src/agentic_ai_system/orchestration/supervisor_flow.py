from __future__ import annotations

from datetime import datetime
from typing import Any

from crewai.flow.flow import Flow, listen, start
from pydantic import BaseModel, Field

from agentic_ai_system.execution.experiment_runner import run_experiment_stage
from agentic_ai_system.execution.sandbox_executor import execute_coding_stage
from agentic_ai_system.orchestration.exceptions import CheckpointRejected
from agentic_ai_system.orchestration.flow_utils import approval_gate, kickoff_with_retry, parse_model_output, run_id
from agentic_ai_system.orchestration.literature_pipeline import (
    build_literature_deep_bundle,
    build_literature_queries,
    build_literature_screen_prompt,
    build_literature_synthesis_prompt,
    chunk_text,
    collect_literature_bundle,
    compact_literature_bundle,
    fallback_literature_output,
    fallback_literature_screen_output,
    fetch_literature_papers,
    is_topic_specific_match,
    paper_relevance_score,
    run_literature_stage,
    screen_literature_candidates,
)
from agentic_ai_system.orchestration.research_pipeline import (
    run_coding_stage,
    run_experiment_stage_flow,
    run_method_stage,
    run_writing_stage,
)
from agentic_ai_system.schemas.fetches import LiteratureFetchOutput, PaperAnalysisOutput, PaperFetchResult
from agentic_ai_system.schemas.models import (
    CodingExecutionResult,
    CodingStageOutput,
    ExperimentExecutionResult,
    ExperimentStageOutput,
    LiteratureResearchOutput,
    LiteratureScreenOutput,
    MethodStageOutput,
    WritingStageOutput,
)
from agentic_ai_system.storage.run_persistence import RunPersistence


class SupervisorState(BaseModel):
    topic: str = "AI LLMs"
    current_year: str = ""
    auto_mode: bool = False
    literature_output: LiteratureResearchOutput | None = None
    literature_manifest_path: str = ""
    literature_screen_output: LiteratureScreenOutput | None = None
    literature_screen_path: str = ""
    literature_screen_manifest_path: str = ""
    literature_fetch_output: LiteratureFetchOutput | None = None
    literature_fetch_dir: str = ""
    literature_fetch_manifest_path: str = ""
    literature_analysis_outputs: list[PaperAnalysisOutput] = Field(default_factory=list)
    literature_analysis_manifest_path: str = ""
    method_output: MethodStageOutput | None = None
    method_artifact_path: str = ""
    method_manifest_path: str = ""
    coding_output: CodingStageOutput | None = None
    coding_manifest_path: str = ""
    experiment_output: ExperimentStageOutput | None = None
    experiment_manifest_path: str = ""
    writing_output: WritingStageOutput | None = None
    coding_execution: CodingExecutionResult | None = None
    experiment_execution: ExperimentExecutionResult | None = None
    literature_artifact_path: str = ""
    writing_artifact_dir: str = ""
    writing_artifact_files: list[str] = Field(default_factory=list)
    writing_manifest_path: str = ""
    approvals: dict[str, bool] = Field(default_factory=dict)


class ResearchSupervisorFlow(Flow[SupervisorState]):
    """CLI-first supervisor flow with explicit approval checkpoints."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._persistence = RunPersistence()

    def _run_id(self) -> str:
        return run_id(self)

    def _kickoff_with_retry(self, stage: str, agent: Any, prompt: str, attempts: int = 3) -> Any:
        return kickoff_with_retry(self, stage, agent, prompt, attempts=attempts)

    def _extract_json_candidate(self, raw_output: str) -> str:
        from agentic_ai_system.orchestration.flow_utils import extract_json_candidate

        return extract_json_candidate(raw_output)

    def _parse_model_output(self, raw_output: str, model: type[Any]) -> Any:
        return parse_model_output(raw_output, model)

    def _approval_gate(self, stage: str, preview: str) -> None:
        return approval_gate(self, stage, preview)

    def _is_timeout_error(self, exc: Exception) -> bool:
        return "timed out" in str(exc).lower() or "timeout" in str(exc).lower()

    def _build_literature_queries(self, topic: str) -> list[str]:
        return build_literature_queries(topic)

    def _paper_relevance_score(self, paper: dict[str, Any], topic: str) -> int:
        return paper_relevance_score(paper, topic)

    def _is_topic_specific_match(self, paper: dict[str, Any], topic: str) -> bool:
        return is_topic_specific_match(paper, topic)

    def _collect_literature_bundle(self, topic: str) -> dict[str, Any]:
        return collect_literature_bundle(topic)

    def _compact_literature_bundle(self, source_bundle: dict[str, Any], max_papers: int = 8) -> dict[str, Any]:
        return compact_literature_bundle(source_bundle, max_papers=max_papers)

    def _build_literature_screen_prompt(self, compact_bundle: dict[str, Any]) -> str:
        return build_literature_screen_prompt(self.state.topic, compact_bundle)

    def _fallback_literature_screen_output(self, source_bundle: dict[str, Any]) -> LiteratureScreenOutput:
        return fallback_literature_screen_output(source_bundle)

    def _screen_literature_candidates(
        self,
        source_bundle: dict[str, Any],
        compact_bundle: dict[str, Any],
    ) -> LiteratureScreenOutput:
        return screen_literature_candidates(self, source_bundle, compact_bundle)

    def _build_literature_deep_bundle(
        self,
        source_bundle: dict[str, Any],
        screen_output: LiteratureScreenOutput,
    ) -> dict[str, Any]:
        return build_literature_deep_bundle(source_bundle, screen_output)

    def _chunk_text(self, text: str, chunk_size: int = 4500) -> list[str]:
        return chunk_text(text, chunk_size=chunk_size)

    def _fetch_literature_papers(
        self,
        source_bundle: dict[str, Any],
        screen_output: LiteratureScreenOutput,
        max_papers: int = 4,
    ) -> list[dict[str, object]]:
        return fetch_literature_papers(source_bundle, screen_output, max_papers=max_papers)

    def _build_paper_analysis_prompt(self, paper: PaperFetchResult) -> str:
        from agentic_ai_system.orchestration.literature_pipeline import build_paper_analysis_prompt

        return build_paper_analysis_prompt(self.state.topic, paper)

    def _build_literature_synthesis_prompt(self, analyses: list[PaperAnalysisOutput]) -> str:
        return build_literature_synthesis_prompt(self.state.topic, analyses)

    def _fallback_literature_output(
        self,
        topic: str,
        source_bundle: dict[str, Any],
        reason: str,
    ) -> LiteratureResearchOutput:
        return fallback_literature_output(topic, source_bundle, reason)

    @start()
    def initialize(self) -> str:
        if not self.state.current_year:
            self.state.current_year = str(datetime.now().year)
        if not self.state.topic:
            self.state.topic = "AI LLMs"
        self._persistence.start_run(run_id(self), self.state.topic, self.state.current_year)
        self._persistence.stage_event(run_id(self), "initialize", "completed", "Flow initialized")
        print(f"Starting supervisor flow for topic: {self.state.topic}")
        return self.state.topic

    @listen(initialize)
    def literature_stage(self, _topic: str) -> LiteratureResearchOutput:
        return run_literature_stage(self)

    @listen(literature_stage)
    def method_stage(self, literature_output: LiteratureResearchOutput) -> MethodStageOutput:
        return run_method_stage(self, literature_output)

    @listen(method_stage)
    def coding_stage(self, method_output: MethodStageOutput) -> CodingStageOutput:
        return run_coding_stage(self, method_output)

    @listen(coding_stage)
    def experiment_stage(self, coding_output: CodingStageOutput) -> ExperimentStageOutput:
        return run_experiment_stage_flow(self, coding_output)

    @listen(experiment_stage)
    def writing_stage(self, experiment_output: ExperimentStageOutput) -> WritingStageOutput:
        return run_writing_stage(self, experiment_output)

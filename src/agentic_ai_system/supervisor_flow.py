import ast
import json
import re
from datetime import datetime
from time import sleep
from typing import Any, TypeVar

from crewai.flow.flow import Flow, listen, start
import json5
from pydantic import BaseModel, Field

from agentic_ai_system.crew import AgenticAiSystem
from agentic_ai_system.literature_storage import store_literature_output
from agentic_ai_system.models import (
    CodingStageOutput,
    ExperimentStageOutput,
    LiteratureResearchOutput,
    MethodStageOutput,
    PaperFinding,
    WritingStageOutput,
)
from agentic_ai_system.run_persistence import RunPersistence
from agentic_ai_system.tools import ArxivSearchTool, SemanticScholarSearchTool

ModelT = TypeVar("ModelT", bound=BaseModel)


class CheckpointRejected(RuntimeError):
    """Raised when user rejects a checkpoint and flow should stop gracefully."""


class SupervisorState(BaseModel):
    topic: str = "AI LLMs"
    current_year: str = ""
    literature_output: LiteratureResearchOutput | None = None
    method_output: MethodStageOutput | None = None
    coding_output: CodingStageOutput | None = None
    experiment_output: ExperimentStageOutput | None = None
    writing_output: WritingStageOutput | None = None
    literature_artifact_path: str = ""
    approvals: dict[str, bool] = Field(default_factory=dict)


class ResearchSupervisorFlow(Flow[SupervisorState]):
    """CLI-first supervisor flow with explicit approval checkpoints."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._persistence = RunPersistence()

    def _run_id(self) -> str:
        return str(getattr(self.state, "id", "unknown"))

    def _kickoff_with_retry(
        self,
        stage: str,
        agent: Any,
        prompt: str,
        attempts: int = 3,
    ) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                if attempt > 1:
                    self._persistence.stage_event(
                        self._run_id(),
                        stage,
                        "retry",
                        f"Retry attempt {attempt}/{attempts}",
                    )
                return agent.kickoff(prompt)
            except Exception as exc:  # propagate after bounded retries
                last_error = exc
                self._persistence.stage_event(
                    self._run_id(),
                    stage,
                    "error",
                    f"LLM kickoff failed attempt {attempt}: {exc}",
                )
                if attempt < attempts:
                    sleep(min(2 ** (attempt - 1), 4))
        raise RuntimeError(f"{stage} failed after {attempts} attempts: {last_error}")

    def _build_literature_queries(self, topic: str) -> list[str]:
        base = topic.strip()
        queries = [base]

        lowered = base.lower()
        if "unet" in lowered or "u-net" in lowered:
            queries.extend(
                [
                    "U-Net segmentation model medical imaging",
                    "UNet architecture semantic segmentation",
                    "Attention U-Net nnU-Net TransUNet",
                    "U-Net diffusion model denoising",
                ]
            )
        else:
            queries.extend(
                [
                    f"{base} survey",
                    f"{base} recent advances",
                    f"{base} benchmark",
                ]
            )

        deduped: list[str] = []
        seen: set[str] = set()
        for query in queries:
            key = query.lower()
            if key not in seen:
                deduped.append(query)
                seen.add(key)
        return deduped

    def _paper_relevance_score(self, paper: dict[str, Any], topic: str) -> int:
        text = f"{paper.get('title', '')} {paper.get('summary', '')}".lower()
        topic_tokens = [token for token in re.findall(r"[a-z0-9\-]+", topic.lower()) if len(token) > 2]
        score = sum(1 for token in topic_tokens if token in text)

        boosters = [
            "unet",
            "u-net",
            "segmentation",
            "medical imaging",
            "attention u-net",
            "nnu-net",
            "transunet",
        ]
        score += sum(2 for token in boosters if token in text)
        return score

    def _is_topic_specific_match(self, paper: dict[str, Any], topic: str) -> bool:
        text = f"{paper.get('title', '')} {paper.get('summary', '')}".lower()
        lowered_topic = topic.lower()
        if "unet" in lowered_topic or "u-net" in lowered_topic:
            required_markers = ["unet", "u-net", "nnunet", "transunet", "attention u-net"]
            return any(marker in text for marker in required_markers)
        return True

    def _collect_literature_bundle(self, topic: str) -> dict[str, Any]:
        queries = self._build_literature_queries(topic)
        aggregated: list[dict[str, Any]] = []
        source_errors: list[dict[str, str]] = []

        for query in queries:
            for tool in (ArxivSearchTool(), SemanticScholarSearchTool()):
                raw = tool._run(query, max_results=8)
                payload = json.loads(raw)
                if payload.get("error"):
                    source_errors.append(
                        {
                            "source": payload.get("source", tool.name),
                            "query": query,
                            "error": payload["error"],
                        }
                    )
                    continue

                for paper in payload.get("papers", []):
                    item = dict(paper)
                    item["query"] = query
                    if not self._is_topic_specific_match(item, topic):
                        continue
                    score = self._paper_relevance_score(item, topic)
                    item["relevance_score"] = score
                    aggregated.append(item)

        deduped: dict[str, dict[str, Any]] = {}
        for paper in aggregated:
            key = (paper.get("url") or "").strip().lower() or (paper.get("title") or "").strip().lower()
            if not key:
                continue
            existing = deduped.get(key)
            if not existing or paper.get("relevance_score", 0) > existing.get("relevance_score", 0):
                deduped[key] = paper

        ranked_papers = sorted(
            deduped.values(),
            key=lambda item: (item.get("relevance_score", 0), item.get("citation_count", "0")),
            reverse=True,
        )

        return {
            "topic": topic,
            "queries": queries,
            "errors": source_errors,
            "papers": ranked_papers[:25],
        }

    def _extract_json_candidate(self, raw_output: str) -> str:
        fenced_match = re.search(
            r"```(?:json)?\s*(\{.*?\})\s*```",
            raw_output,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if fenced_match:
            return fenced_match.group(1)

        start_idx = raw_output.find("{")
        if start_idx == -1:
            raise RuntimeError("No JSON object start token found in model output.")

        in_string = False
        escape = False
        depth = 0
        for index in range(start_idx, len(raw_output)):
            char = raw_output[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return raw_output[start_idx : index + 1]

        raise RuntimeError("No complete JSON object found in model output.")

    def _parse_model_output(self, raw_output: str, model: type[ModelT]) -> ModelT:
        payload_text = self._extract_json_candidate(raw_output)
        cleaned_payload = re.sub(r"[\x00-\x1f]", " ", payload_text)

        payload = None
        for candidate in (payload_text, cleaned_payload):
            try:
                payload = json.loads(candidate)
                break
            except json.JSONDecodeError:
                try:
                    payload = json5.loads(candidate)
                    if isinstance(payload, dict):
                        break
                except Exception:
                    payload = None
                try:
                    literal_payload = ast.literal_eval(candidate)
                    if isinstance(literal_payload, dict):
                        payload = literal_payload
                        break
                except (SyntaxError, ValueError):
                    continue

        if payload is None:
            raise RuntimeError(
                f"{model.__name__} stage output was not valid JSON. "
                f"Snippet: {cleaned_payload[:240]}"
            )

        return model.model_validate(payload)

    def _approval_gate(self, stage: str, preview: str) -> None:
        print(f"\n=== {stage.upper()} CHECKPOINT ===")
        print(preview)
        answer = input("\nApprove and continue? [y/N]: ").strip().lower()
        approved = answer in {"y", "yes"}
        self.state.approvals[stage] = approved
        self._persistence.log_approval(self._run_id(), stage, approved)
        if not approved:
            raise CheckpointRejected(f"{stage} checkpoint was rejected by user.")

    @start()
    def initialize(self) -> str:
        if not self.state.current_year:
            self.state.current_year = str(datetime.now().year)
        if not self.state.topic:
            self.state.topic = "AI LLMs"
        self._persistence.start_run(self._run_id(), self.state.topic, self.state.current_year)
        self._persistence.stage_event(self._run_id(), "initialize", "completed", "Flow initialized")
        print(f"Starting supervisor flow for topic: {self.state.topic}")
        return self.state.topic

    @listen(initialize)
    def literature_stage(self, _topic: str) -> LiteratureResearchOutput:
        self._persistence.stage_event(self._run_id(), "literature", "running")
        try:
            crew_system = AgenticAiSystem()
            source_bundle = self._collect_literature_bundle(self.state.topic)
            prompt = (
                f"Research '{self.state.topic}' with emphasis on recent work up to {self.state.current_year}, "
                "but include seminal papers if highly relevant. "
                "Use the provided paper search results and return a structured literature synthesis.\n\n"
                "Return strict JSON only, matching this schema:\n"
                "{\n"
                '  "topic": "string",\n'
                '  "generated_at": "ISO datetime string",\n'
                '  "key_findings": [{"title":"string","source":"string","summary":"string","url":"string"}],\n'
                '  "synthesis": "string"\n'
                "}\n\n"
                f"Search results JSON:\n{json.dumps(source_bundle, ensure_ascii=True)}"
            )
            result = self._kickoff_with_retry(
                "literature",
                crew_system.research_synthesizer(),
                prompt,
            )
            literature_output = self._parse_model_output(result.raw, LiteratureResearchOutput)

            if not literature_output.topic:
                literature_output.topic = self.state.topic
            if not literature_output.generated_at:
                literature_output.generated_at = datetime.now().isoformat()
            if not literature_output.key_findings:
                fallback_findings: list[PaperFinding] = []
                for paper in source_bundle.get("papers", [])[:5]:
                    fallback_findings.append(
                        PaperFinding(
                            title=str(paper.get("title", "")),
                            source=str(paper.get("source", "")),
                            summary=str(paper.get("summary", ""))[:700],
                            url=str(paper.get("url", "")),
                        )
                    )
                literature_output.key_findings = fallback_findings
            if not literature_output.synthesis:
                literature_output.synthesis = (
                    "Synthesis generated from ranked literature results. "
                    "Review key_findings and refine topic keywords if needed."
                )

            self.state.literature_output = literature_output
            artifact = store_literature_output(self.state.topic, literature_output)
            self.state.literature_artifact_path = str(artifact)
            finding_preview = "\n".join(
                [f"- {item.title} ({item.source})" for item in literature_output.key_findings[:5]]
            )
            preview = (
                f"Stored literature artifact: {artifact}\n"
                f"Top findings:\n{finding_preview or '- no findings returned'}\n\n"
                f"Synthesis: {literature_output.synthesis[:350]}"
            )
            self._approval_gate("literature", preview)
            self._persistence.stage_event(
                self._run_id(),
                "literature",
                "completed",
                f"artifact={artifact}",
            )
            return literature_output
        except CheckpointRejected as exc:
            self._persistence.stage_event(self._run_id(), "literature", "stopped", str(exc))
            self._persistence.finish_run(self._run_id(), "stopped")
            raise
        except Exception as exc:
            self._persistence.stage_event(self._run_id(), "literature", "failed", str(exc))
            self._persistence.finish_run(self._run_id(), "failed")
            raise

    @listen(literature_stage)
    def method_stage(self, literature_output: LiteratureResearchOutput) -> MethodStageOutput:
        self._persistence.stage_event(self._run_id(), "method", "running")
        try:
            crew_system = AgenticAiSystem()
            prompt = (
                f"Given this literature synthesis for '{self.state.topic}':\n"
                f"{literature_output.model_dump_json(indent=2)}\n\n"
                "Identify key gaps and propose 2-3 concrete method options with one recommendation.\n"
                "Return strict JSON only with schema:\n"
                "{\n"
                '  "research_gaps": ["string"],\n'
                '  "proposals": [{"name":"string","rationale":"string","expected_benefit":"string","risk":"string"}],\n'
                '  "recommended_option": "string"\n'
                "}"
            )
            result = self._kickoff_with_retry("method", crew_system.method_analyst(), prompt)
            method_output = self._parse_model_output(result.raw, MethodStageOutput)

            self.state.method_output = method_output
            options = "\n".join(
                [f"- {proposal.name}: {proposal.expected_benefit}" for proposal in method_output.proposals]
            )
            preview = (
                f"Recommended option: {method_output.recommended_option}\n"
                f"Research gaps: {', '.join(method_output.research_gaps[:3]) or 'none'}\n"
                f"Proposals:\n{options or '- no proposals returned'}"
            )
            self._approval_gate("method", preview)
            self._persistence.stage_event(self._run_id(), "method", "completed")
            return method_output
        except CheckpointRejected as exc:
            self._persistence.stage_event(self._run_id(), "method", "stopped", str(exc))
            self._persistence.finish_run(self._run_id(), "stopped")
            raise
        except Exception as exc:
            self._persistence.stage_event(self._run_id(), "method", "failed", str(exc))
            self._persistence.finish_run(self._run_id(), "failed")
            raise

    @listen(method_stage)
    def coding_stage(self, method_output: MethodStageOutput) -> CodingStageOutput:
        self._persistence.stage_event(self._run_id(), "coding", "running")
        try:
            crew_system = AgenticAiSystem()
            prompt = (
                f"Create a sandbox-first implementation plan for topic '{self.state.topic}' using "
                f"the selected method output:\n{method_output.model_dump_json(indent=2)}\n\n"
                "Return strict JSON only with schema:\n"
                "{\n"
                '  "sandbox_plan": "string",\n'
                '  "files_to_create": ["string"],\n'
                '  "validation_steps": ["string"]\n'
                "}"
            )
            result = self._kickoff_with_retry("coding", crew_system.coding_architect(), prompt)
            coding_output = self._parse_model_output(result.raw, CodingStageOutput)

            self.state.coding_output = coding_output
            preview = (
                f"Sandbox plan: {coding_output.sandbox_plan}\n"
                f"Files: {', '.join(coding_output.files_to_create) or 'none'}\n"
                f"Validation: {', '.join(coding_output.validation_steps) or 'none'}"
            )
            self._approval_gate("coding", preview)
            self._persistence.stage_event(self._run_id(), "coding", "completed")
            return coding_output
        except CheckpointRejected as exc:
            self._persistence.stage_event(self._run_id(), "coding", "stopped", str(exc))
            self._persistence.finish_run(self._run_id(), "stopped")
            raise
        except Exception as exc:
            self._persistence.stage_event(self._run_id(), "coding", "failed", str(exc))
            self._persistence.finish_run(self._run_id(), "failed")
            raise

    @listen(coding_stage)
    def experiment_stage(self, coding_output: CodingStageOutput) -> ExperimentStageOutput:
        self._persistence.stage_event(self._run_id(), "experiment", "running")
        try:
            crew_system = AgenticAiSystem()
            prompt = (
                f"Design an experiment plan for topic '{self.state.topic}' using this coding plan:\n"
                f"{coding_output.model_dump_json(indent=2)}\n\n"
                "Return strict JSON only with schema:\n"
                "{\n"
                '  "experiment_goal": "string",\n'
                '  "run_config": {"key":"value"},\n'
                '  "metrics_to_track": ["string"]\n'
                "}"
            )
            result = self._kickoff_with_retry("experiment", crew_system.experiment_designer(), prompt)
            experiment_output = self._parse_model_output(result.raw, ExperimentStageOutput)

            self.state.experiment_output = experiment_output
            config_preview = ", ".join(
                [f"{key}={value}" for key, value in experiment_output.run_config.items()]
            )
            preview = (
                f"Experiment goal: {experiment_output.experiment_goal}\n"
                f"Config: {config_preview or 'none'}\n"
                f"Metrics: {', '.join(experiment_output.metrics_to_track) or 'none'}"
            )
            self._approval_gate("experiment", preview)
            self._persistence.stage_event(self._run_id(), "experiment", "completed")
            return experiment_output
        except CheckpointRejected as exc:
            self._persistence.stage_event(self._run_id(), "experiment", "stopped", str(exc))
            self._persistence.finish_run(self._run_id(), "stopped")
            raise
        except Exception as exc:
            self._persistence.stage_event(self._run_id(), "experiment", "failed", str(exc))
            self._persistence.finish_run(self._run_id(), "failed")
            raise

    @listen(experiment_stage)
    def writing_stage(self, experiment_output: ExperimentStageOutput) -> WritingStageOutput:
        self._persistence.stage_event(self._run_id(), "writing", "running")
        try:
            crew_system = AgenticAiSystem()
            prompt = (
                f"Build a writing plan for topic '{self.state.topic}' based on this experiment plan:\n"
                f"{experiment_output.model_dump_json(indent=2)}\n\n"
                "Return strict JSON only with schema:\n"
                "{\n"
                '  "sections": [{"name":"string","objective":"string"}],\n'
                '  "output_format": "string",\n'
                '  "review_focus": "string"\n'
                "}"
            )
            result = self._kickoff_with_retry("writing", crew_system.writing_strategist(), prompt)
            writing_output = self._parse_model_output(result.raw, WritingStageOutput)

            self.state.writing_output = writing_output
            sections_preview = "\n".join(
                [f"- {section.name}: {section.objective}" for section in writing_output.sections]
            )
            preview = (
                f"Output format: {writing_output.output_format}\n"
                f"Review focus: {writing_output.review_focus}\n"
                f"Sections:\n{sections_preview or '- no sections returned'}"
            )
            self._approval_gate("writing", preview)
            self._persistence.stage_event(self._run_id(), "writing", "completed")
            self._persistence.finish_run(self._run_id(), "completed")
            return writing_output
        except CheckpointRejected as exc:
            self._persistence.stage_event(self._run_id(), "writing", "stopped", str(exc))
            self._persistence.finish_run(self._run_id(), "stopped")
            raise
        except Exception as exc:
            self._persistence.stage_event(self._run_id(), "writing", "failed", str(exc))
            self._persistence.finish_run(self._run_id(), "failed")
            raise

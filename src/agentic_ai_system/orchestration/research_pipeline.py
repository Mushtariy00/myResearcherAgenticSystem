from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from agentic_ai_system.crew import AgenticAiSystem
from agentic_ai_system.execution.experiment_runner import run_experiment_stage
from agentic_ai_system.execution.sandbox_executor import execute_coding_stage
from agentic_ai_system.orchestration.flow_utils import kickoff_with_retry, parse_model_output, run_id
from agentic_ai_system.schemas.fetches import LiteratureFetchOutput
from agentic_ai_system.schemas.models import CodingStageOutput, ExperimentStageOutput, LiteratureResearchOutput, MethodStageOutput, WritingStageOutput
from agentic_ai_system.storage.artifact_contract import store_stage_artifact_manifest
from agentic_ai_system.storage.literature_fetch_storage import store_literature_fetch_output
from agentic_ai_system.storage.method_storage import store_method_output
from agentic_ai_system.storage.writing_storage import store_writing_output
from agentic_ai_system.tools.paper_fetch_tools import fetch_pdf_with_waterfall
from agentic_ai_system.ui.bridge import ui_update_queue


def run_pdf_fetch_stage(flow: Any, literature_output: LiteratureResearchOutput) -> LiteratureFetchOutput:
    """
    Fetch PDFs for screened literature papers using waterfall strategy.
    Strategy: arXiv → Unpaywall → OpenAlex → HTML parsing.
    """
    flow._persistence.stage_event(run_id(flow), "pdf_fetch", "running")
    try:
        from agentic_ai_system.schemas.fetches import PaperFetchResult
        
        papers_to_fetch = literature_output.papers[:8] if literature_output.papers else []
        fetch_results = []
        
        for idx, paper in enumerate(papers_to_fetch):
            try:
                result = fetch_pdf_with_waterfall(
                    source_url=paper.source_url,
                    doi=paper.doi if hasattr(paper, 'doi') else None,
                    title=paper.title if hasattr(paper, 'title') else None,
                    max_pages=None,
                )
                
                fetch_result = PaperFetchResult(
                    index=idx,
                    title=paper.title if hasattr(paper, 'title') else result.get("title", ""),
                    source=paper.source if hasattr(paper, 'source') else "unknown",
                    source_url=result.get("source_url", ""),
                    resolved_pdf_url=result.get("resolved_pdf_url", ""),
                    page_count=result.get("page_count", 0),
                    text_length=result.get("text_length", 0),
                    text_chunks=[],
                    text_path="",
                    status=result.get("status", "unknown"),
                    error=result.get("error", ""),
                )
                fetch_results.append(fetch_result)
            except Exception as e:
                fetch_result = PaperFetchResult(
                    index=idx,
                    title=paper.title if hasattr(paper, 'title') else "unknown",
                    source=paper.source if hasattr(paper, 'source') else "unknown",
                    source_url=paper.source_url if hasattr(paper, 'source_url') else "",
                    resolved_pdf_url="",
                    page_count=0,
                    text_length=0,
                    text_chunks=[],
                    text_path="",
                    status="error",
                    error=str(e),
                )
                fetch_results.append(fetch_result)
        
        fetch_output = LiteratureFetchOutput(papers=fetch_results)
        flow.state.literature_fetch_output = fetch_output
        
        fetch_manifest = store_literature_fetch_output(
            flow.state.topic,
            fetch_output,
        )
        flow.state.literature_fetch_dir = str(fetch_manifest.parent)
        flow.state.literature_fetch_manifest_path = str(fetch_manifest)
        
        success_count = sum(1 for r in fetch_results if r.status == "ok")
        preview = (
            f"PDF Fetch Results:\n"
            f"  Total papers attempted: {len(fetch_results)}\n"
            f"  Successfully fetched: {success_count}\n"
            f"  Failed: {len(fetch_results) - success_count}\n"
            f"  Fetch manifest: {fetch_manifest}"
        )
        
        flow._approval_gate("pdf_fetch", preview)
        flow._persistence.stage_event(run_id(flow), "pdf_fetch", "completed")
        ui_update_queue.put({"type": "stage_completed", "stage": "pdf_fetch", "timestamp": datetime.now().isoformat()})
        
        return fetch_output
    except Exception as exc:
        from agentic_ai_system.orchestration.exceptions import CheckpointRejected
        
        if isinstance(exc, CheckpointRejected):
            flow._persistence.stage_event(run_id(flow), "pdf_fetch", "stopped", str(exc))
            flow._persistence.finish_run(run_id(flow), "stopped")
            raise
        flow._persistence.stage_event(run_id(flow), "pdf_fetch", "failed", str(exc))
        flow._persistence.finish_run(run_id(flow), "failed")
        raise



    flow._persistence.stage_event(run_id(flow), "method", "running")
    try:
        crew_system = AgenticAiSystem()
        prompt = (
            f"Given this literature synthesis for '{flow.state.topic}':\n"
            f"{literature_output.model_dump_json(indent=2)}\n\n"
            "Identify key gaps and propose 2-3 concrete method options with one recommendation.\n"
            "Return strict JSON only with schema:\n"
            "{\n"
            '  "research_gaps": ["string"],\n'
            '  "proposals": [{"name":"string","rationale":"string","expected_benefit":"string","risk":"string"}],\n'
            '  "recommended_option": "string"\n'
            "}"
        )
        result = kickoff_with_retry(flow, "method", crew_system.method_analyst(), prompt)
        method_output = parse_model_output(result.raw, MethodStageOutput)
        flow.state.method_output = method_output
        method_artifact = store_method_output(flow.state.topic, method_output)
        flow.state.method_artifact_path = str(method_artifact)
        method_manifest = store_stage_artifact_manifest(
            "method",
            flow.state.topic,
            str(method_artifact),
            "Method output stored",
            auxiliary_paths=[str(method_artifact)],
            metadata={"proposals": len(method_output.proposals)},
        )
        flow.state.method_manifest_path = str(method_manifest)
        options = "\n".join([f"- {proposal.name}: {proposal.expected_benefit}" for proposal in method_output.proposals])
        preview = (
            f"Stored method artifact: {method_artifact}\n"
            f"Recommended option: {method_output.recommended_option}\n"
            f"Research gaps: {', '.join(method_output.research_gaps[:3]) or 'none'}\n"
            f"Proposals:\n{options or '- no proposals returned'}"
        )
        flow._approval_gate("method", preview)
        flow._persistence.stage_event(run_id(flow), "method", "completed")
        ui_update_queue.put({"type": "stage_completed", "stage": "method", "timestamp": datetime.now().isoformat()})
        return method_output
    except Exception as exc:
        from agentic_ai_system.orchestration.exceptions import CheckpointRejected

        if isinstance(exc, CheckpointRejected):
            flow._persistence.stage_event(run_id(flow), "method", "stopped", str(exc))
            flow._persistence.finish_run(run_id(flow), "stopped")
            raise
        flow._persistence.stage_event(run_id(flow), "method", "failed", str(exc))
        flow._persistence.finish_run(run_id(flow), "failed")
        raise


def run_coding_stage(flow: Any, method_output: MethodStageOutput) -> CodingStageOutput:
    flow._persistence.stage_event(run_id(flow), "coding", "running")
    try:
        crew_system = AgenticAiSystem()
        prompt = (
            f"Create a sandbox-first implementation plan for topic '{flow.state.topic}' using "
            f"the selected method output:\n{method_output.model_dump_json(indent=2)}\n\n"
            "Return strict JSON only with schema:\n"
            "{\n"
            '  "sandbox_plan": "string",\n'
            '  "files_to_create": ["string"],\n'
            '  "validation_steps": ["string"]\n'
            "}"
        )
        result = kickoff_with_retry(flow, "coding", crew_system.coding_architect(), prompt)
        coding_output = parse_model_output(result.raw, CodingStageOutput)
        flow.state.coding_output = coding_output
        coding_exec = execute_coding_stage(flow.state.topic, coding_output, method_output)
        flow.state.coding_execution = coding_exec
        coding_manifest = store_stage_artifact_manifest(
            "coding",
            flow.state.topic,
            str(Path(coding_exec.sandbox_dir) / "coding_execution_manifest.json"),
            "Coding sandbox generated",
            auxiliary_paths=[*coding_exec.created_files, *coding_exec.validated_files],
            metadata={
                "created_files": len(coding_exec.created_files),
                "validated_files": len(coding_exec.validated_files),
                "validation_errors": len(coding_exec.validation_errors),
            },
        )
        flow.state.coding_manifest_path = str(coding_manifest)
        preview = (
            f"Sandbox plan: {coding_output.sandbox_plan}\n"
            f"Files: {', '.join(coding_output.files_to_create) or 'none'}\n"
            f"Validation: {', '.join(coding_output.validation_steps) or 'none'}\n"
            f"Sandbox dir: {coding_exec.sandbox_dir}\n"
            f"Created files: {len(coding_exec.created_files)}\n"
            f"Validation errors: {len(coding_exec.validation_errors)}"
        )
        flow._approval_gate("coding", preview)
        flow._persistence.stage_event(run_id(flow), "coding", "completed", f"sandbox_dir={coding_exec.sandbox_dir}")
        ui_update_queue.put({"type": "stage_completed", "stage": "coding", "timestamp": datetime.now().isoformat()})
        return coding_output
    except Exception as exc:
        from agentic_ai_system.orchestration.exceptions import CheckpointRejected

        if isinstance(exc, CheckpointRejected):
            flow._persistence.stage_event(run_id(flow), "coding", "stopped", str(exc))
            flow._persistence.finish_run(run_id(flow), "stopped")
            raise
        flow._persistence.stage_event(run_id(flow), "coding", "failed", str(exc))
        flow._persistence.finish_run(run_id(flow), "failed")
        raise


def run_experiment_stage_flow(flow: Any, coding_output: CodingStageOutput) -> ExperimentStageOutput:
    flow._persistence.stage_event(run_id(flow), "experiment", "running")
    try:
        crew_system = AgenticAiSystem()
        prompt = (
            f"Design an experiment plan for topic '{flow.state.topic}' using this coding plan:\n"
            f"{coding_output.model_dump_json(indent=2)}\n\n"
            "Return strict JSON only with schema:\n"
            "{\n"
            '  "experiment_goal": "string",\n'
            '  "run_config": {"key":"value"},\n'
            '  "metrics_to_track": ["string"]\n'
            "}"
        )
        result = kickoff_with_retry(flow, "experiment", crew_system.experiment_designer(), prompt)
        experiment_output = parse_model_output(result.raw, ExperimentStageOutput)
        flow.state.experiment_output = experiment_output
        coding_exec = flow.state.coding_execution
        if coding_exec is None:
            raise RuntimeError("coding execution artifacts are missing")
        experiment_exec = run_experiment_stage(flow.state.topic, experiment_output, coding_exec)
        flow.state.experiment_execution = experiment_exec
        experiment_manifest = store_stage_artifact_manifest(
            "experiment",
            flow.state.topic,
            experiment_exec.summary_file,
            "Experiment summary stored",
            auxiliary_paths=[experiment_exec.summary_file, experiment_exec.run_dir],
            metadata={"metrics": len(experiment_exec.metrics)},
        )
        flow.state.experiment_manifest_path = str(experiment_manifest)
        config_preview = ", ".join([f"{key}={value}" for key, value in experiment_output.run_config.items()])
        preview = (
            f"Experiment goal: {experiment_output.experiment_goal}\n"
            f"Config: {config_preview or 'none'}\n"
            f"Metrics: {', '.join(experiment_output.metrics_to_track) or 'none'}\n"
            f"Run dir: {experiment_exec.run_dir}\n"
            f"Summary: {experiment_exec.summary_file}"
        )
        flow._approval_gate("experiment", preview)
        flow._persistence.stage_event(run_id(flow), "experiment", "completed", f"run_dir={experiment_exec.run_dir}")
        ui_update_queue.put({"type": "stage_completed", "stage": "experiment", "timestamp": datetime.now().isoformat()})
        return experiment_output
    except Exception as exc:
        from agentic_ai_system.orchestration.exceptions import CheckpointRejected

        if isinstance(exc, CheckpointRejected):
            flow._persistence.stage_event(run_id(flow), "experiment", "stopped", str(exc))
            flow._persistence.finish_run(run_id(flow), "stopped")
            raise
        flow._persistence.stage_event(run_id(flow), "experiment", "failed", str(exc))
        flow._persistence.finish_run(run_id(flow), "failed")
        raise


def run_writing_stage(flow: Any, experiment_output: ExperimentStageOutput) -> WritingStageOutput:
    flow._persistence.stage_event(run_id(flow), "writing", "running")
    try:
        crew_system = AgenticAiSystem()
        prompt = (
            f"Build a writing plan for topic '{flow.state.topic}' based on this experiment plan:\n"
            f"{experiment_output.model_dump_json(indent=2)}\n\n"
            "Return strict JSON only with schema:\n"
            "{\n"
            '  "sections": [{"name":"string","objective":"string"}],\n'
            '  "output_format": "string",\n'
            '  "review_focus": "string"\n'
            "}"
        )
        result = kickoff_with_retry(flow, "writing", crew_system.writing_strategist(), prompt)
        writing_output = parse_model_output(result.raw, WritingStageOutput)
        flow.state.writing_output = writing_output
        out_dir, files = store_writing_output(flow.state.topic, writing_output, experiment_output=flow.state.experiment_output)
        flow.state.writing_artifact_dir = str(out_dir)
        flow.state.writing_artifact_files = [str(path) for path in files]
        writing_manifest = store_stage_artifact_manifest(
            "writing",
            flow.state.topic,
            str(out_dir / "00_summary.md"),
            "Writing plan stored",
            auxiliary_paths=[str(path) for path in files],
            metadata={"sections": len(writing_output.sections)},
        )
        flow.state.writing_manifest_path = str(writing_manifest)
        sections_preview = "\n".join([f"- {section.name}: {section.objective}" for section in writing_output.sections])
        preview = (
            f"Output format: {writing_output.output_format}\n"
            f"Review focus: {writing_output.review_focus}\n"
            f"Sections:\n{sections_preview or '- no sections returned'}\n"
            f"Writing artifact dir: {out_dir}"
        )
        flow._approval_gate("writing", preview)
        flow._persistence.stage_event(run_id(flow), "writing", "completed", f"artifact_dir={out_dir}")
        ui_update_queue.put({"type": "stage_completed", "stage": "writing", "timestamp": datetime.now().isoformat()})
        flow._persistence.finish_run(run_id(flow), "completed")
        return writing_output
    except Exception as exc:
        from agentic_ai_system.orchestration.exceptions import CheckpointRejected

        if isinstance(exc, CheckpointRejected):
            flow._persistence.stage_event(run_id(flow), "writing", "stopped", str(exc))
            flow._persistence.finish_run(run_id(flow), "stopped")
            raise
        flow._persistence.stage_event(run_id(flow), "writing", "failed", str(exc))
        flow._persistence.finish_run(run_id(flow), "failed")
        raise

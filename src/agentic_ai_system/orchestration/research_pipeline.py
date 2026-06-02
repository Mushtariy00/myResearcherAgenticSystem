from __future__ import annotations

from datetime import datetime
import json
import importlib
import platform
import re
import sys
from pathlib import Path
from typing import Any

from agentic_ai_system.crew import AgenticAiSystem
from agentic_ai_system.execution.experiment_runner import run_experiment_stage
from agentic_ai_system.execution.sandbox_executor import execute_coding_stage
from agentic_ai_system.orchestration.flow_utils import kickoff_with_retry, parse_model_output, run_id
from agentic_ai_system.orchestration.exceptions import CheckpointRejected
from agentic_ai_system.orchestration.memory_integration import (
    recall_relevant_research,
    save_literature_findings,
    save_method_decision,
    save_pdf_fetch_results,
)
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
    
    Saves fetch results and strategies to agentmemory for recall in future sessions.
    """
    flow._persistence.stage_event(run_id(flow), "pdf_fetch", "running")
    try:
        from agentic_ai_system.schemas.fetches import PaperFetchResult
        
        papers_to_fetch = literature_output.key_findings[:8] if literature_output.key_findings else []
        fetch_results: list[dict[str, object]] = []
        fetch_strategies = []
        
        for idx, paper in enumerate(papers_to_fetch):
            try:
                source_url = paper.url if hasattr(paper, "url") else ""
                title = paper.title if hasattr(paper, "title") else None
                result = fetch_pdf_with_waterfall(
                    source_url=source_url,
                    doi=None,
                    title=title,
                    max_pages=None,
                )
                result["title"] = title or result.get("title", "")
                result["source"] = paper.source if hasattr(paper, "source") else "unknown"
                result["source_url"] = source_url or result.get("source_url", "")
                fetch_results.append(result)
                
                # Track strategies used
                strategy = result.get("strategy", "unknown")
                if strategy != "unknown":
                    fetch_strategies.append(strategy)
            except Exception as e:
                fetch_results.append(
                    {
                        "source_url": paper.url if hasattr(paper, "url") else "",
                        "resolved_pdf_url": "",
                        "status": "error",
                        "page_count": 0,
                        "text": "",
                        "error": str(e),
                        "title": paper.title if hasattr(paper, "title") else "unknown",
                        "source": paper.source if hasattr(paper, "source") else "unknown",
                    }
                )
        
        fetch_dir, fetch_manifest = store_literature_fetch_output(
            flow.state.topic,
            fetch_results,
        )
        flow.state.literature_fetch_dir = str(fetch_dir)
        flow.state.literature_fetch_manifest_path = str(fetch_manifest)
        fetch_output = LiteratureFetchOutput(
            papers=[
                PaperFetchResult(
                    index=index,
                    title=str(result.get("title", "")),
                    source=str(result.get("source", "")),
                    source_url=str(result.get("source_url", "")),
                    resolved_pdf_url=str(result.get("resolved_pdf_url", "")),
                    page_count=int(result.get("page_count", 0) or 0),
                    text_length=len(str(result.get("text", ""))),
                    text_chunks=[],
                    text_path=str(Path(fetch_dir) / f"paper_{index + 1:02d}.txt"),
                    status=str(result.get("status", "")),
                    error=str(result.get("error", "")),
                )
                for index, result in enumerate(fetch_results)
            ]
        )
        flow.state.literature_fetch_output = fetch_output
        
        success_count = sum(1 for r in fetch_results if r.get("status") == "ok")
        preview = (
            f"PDF Fetch Results:\n"
            f"  Total papers attempted: {len(fetch_results)}\n"
            f"  Successfully fetched: {success_count}\n"
            f"  Failed: {len(fetch_results) - success_count}\n"
            f"  Fetch manifest: {fetch_manifest}"
        )
        
        # Save fetch results to memory for future reference
        save_pdf_fetch_results(
            topic=flow.state.topic,
            run_id=run_id(flow),
            total_attempted=len(fetch_results),
            success_count=success_count,
            fetch_strategies=list(set(fetch_strategies)),
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



def run_method_stage(flow: Any, literature_output: LiteratureResearchOutput) -> MethodStageOutput:
    flow._persistence.stage_event(run_id(flow), "method", "running")
    try:
        # Recall relevant research context from prior sessions before analyzing
        prior_context = recall_relevant_research(
            topic=flow.state.topic,
            stage="method",
            limit=3,
        )
        
        crew_system = AgenticAiSystem()
        
        # Build prompt with optional prior context
        base_prompt = (
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
        
        if prior_context:
            prompt = prior_context + "\n\n" + base_prompt
        else:
            prompt = base_prompt
        
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
        
        # Save method decision to memory for future reference
        save_method_decision(
            topic=flow.state.topic,
            run_id=run_id(flow),
            research_gaps=method_output.research_gaps,
            selected_method=method_output.recommended_option,
            rationale=f"Selected from {len(method_output.proposals)} proposals based on literature analysis",
            artifact_path=str(method_artifact),
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


def _block_stage(flow: Any, stage: str, reason: str) -> None:
    flow._persistence.stage_event(run_id(flow), stage, "blocked", reason)
    flow._persistence.finish_run(run_id(flow), "stopped")
    raise CheckpointRejected(reason)


def _require_method_approved(flow: Any) -> None:
    if not flow.state.approvals.get("method"):
        _block_stage(flow, "coding", "Method stage must be approved before coding.")


def _require_file_exists(flow: Any, stage: str, path: Path, label: str) -> None:
    if not path.exists():
        _block_stage(flow, stage, f"Missing required {label}: {path}")


def _collect_env_manifest() -> tuple[dict[str, object], list[str]]:
    required_packages = ["numpy", "torch"]
    missing: list[str] = []
    package_versions: dict[str, str] = {}
    for package in required_packages:
        try:
            module = importlib.import_module(package)
            package_versions[package] = getattr(module, "__version__", "unknown")
        except ImportError:
            missing.append(package)

    gpu_available = False
    cuda_version = None
    if "torch" in package_versions:
        try:
            torch = importlib.import_module("torch")
            cuda_version = getattr(torch.version, "cuda", None)
            gpu_available = bool(torch.cuda.is_available())
        except Exception:
            gpu_available = False
            cuda_version = None

    manifest = {
        "python_version": sys.version.split()[0],
        "cuda_version": cuda_version,
        "gpu_available": gpu_available,
        "key_packages": package_versions,
        "platform": platform.system().lower(),
        "verified_at": datetime.now().isoformat(),
    }

    return manifest, missing


def check_env_manifest(path: Path) -> tuple[bool, str]:
    manifest, missing = _collect_env_manifest()
    if not path.exists():
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8")
    if missing:
        return False, f"Missing required packages: {', '.join(missing)}"
    return True, "Environment manifest looks good."


def _ensure_env_manifest(flow: Any, path: Path) -> Path:
    ok, reason = check_env_manifest(path)
    if not ok:
        _block_stage(flow, "coding", reason)
    return path


def _data_contract_template() -> dict[str, object]:
    return {
        "dataset_name": "",
        "source": "synthetic_only",
        "input_shape": [1, 1, 1, 1],
        "input_dtype": "float32",
        "label_schema": "",
        "splits": {"train": 0.8, "val": 0.1, "test": 0.1},
        "sample_count": {"train": 0, "val": 0, "test": 0},
        "approved_by": "pending",
        "approved_at": "",
    }


def check_data_contract(path: Path) -> tuple[bool, str]:
    if not path.exists():
        path.write_text(
            json.dumps(_data_contract_template(), indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        return False, f"Created data_contract.json at {path}. Fill in and set approved_by='human' to continue."

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, f"Invalid data_contract.json: {exc}"

    if data.get("approved_by") != "human" or not data.get("approved_at"):
        return False, "data_contract.json must be approved_by='human' with approved_at set."

    return True, "Data contract approved."


def _ensure_data_contract(flow: Any, path: Path) -> Path:
    ok, reason = check_data_contract(path)
    if not ok:
        _block_stage(flow, "coding", reason)
    return path


def check_coding_prereqs(base_path: Path) -> tuple[bool, list[str]]:
    messages: list[str] = []
    env_ok, env_message = check_env_manifest(base_path / "env_manifest.json")
    if not env_ok:
        messages.append(env_message)
    data_ok, data_message = check_data_contract(base_path / "data_contract.json")
    if not data_ok:
        messages.append(data_message)
    return env_ok and data_ok, messages


def _slugify_topic(topic: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "_", topic.strip().lower()).strip("_")
    return base or "task"


def _write_pipeline_manifest(
    sandbox_dir: Path,
    env_manifest: Path,
    data_contract: Path,
    approved_by: str = "human",
) -> Path:
    entry_point = "python train/loop.py --config <path>"
    dry_run_entry = "python train/loop.py --config config/smoke.yaml --dry-run"
    if (sandbox_dir / "train_lct_depth.py").exists():
        entry_point = "python train_lct_depth.py"
        dry_run_entry = "python train_lct_depth.py"
    manifest = {
        "entry_point": entry_point,
        "dry_run_entry": dry_run_entry,
        "expected_inputs": ["config YAML path"],
        "expected_outputs": ["outputs/experiments/<run_id>/"],
        "config_schema": "config/base.yaml",
        "dry_run_max_seconds": 60,
        "env_manifest": str(env_manifest),
        "data_contract": str(data_contract),
        "stage_approved_by": approved_by,
        "stage_approved_at": datetime.now().isoformat(),
    }
    manifest_path = sandbox_dir / "pipeline_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8")
    return manifest_path


def run_coding_stage(flow: Any, method_output: MethodStageOutput) -> CodingStageOutput:
    flow._persistence.stage_event(run_id(flow), "coding", "running")
    try:
        _require_method_approved(flow)
        env_manifest = Path.cwd() / "env_manifest.json"
        data_contract = Path.cwd() / "data_contract.json"
        env_manifest = _ensure_env_manifest(flow, env_manifest)
        data_contract = _ensure_data_contract(flow, data_contract)
        prior_context = recall_relevant_research(
            topic=flow.state.topic,
            stage="coding",
            limit=3,
        )
        crew_system = AgenticAiSystem()
        task_slug = _slugify_topic(flow.state.topic)
        allowed_files = [
            f"src/agentic_ai_system/data/{task_slug}_loader.py",
            f"src/agentic_ai_system/model/{task_slug}_architectures.py",
            f"src/agentic_ai_system/train/{task_slug}_losses.py",
            f"src/agentic_ai_system/train/{task_slug}_metrics.py",
            f"config/{task_slug}.yaml",
        ]
        base_prompt = (
            f"Create a sandbox-first implementation plan for topic '{flow.state.topic}' using "
            f"the selected method output:\n{method_output.model_dump_json(indent=2)}\n\n"
            "Only propose task-specific additions. Do NOT suggest changes to base training pipeline files. "
            "Limit files_to_create to this exact allowlist:\n"
            f"{json.dumps(allowed_files, indent=2)}\n\n"
            "Return strict JSON only with schema:\n"
            "{\n"
            '  "sandbox_plan": "string",\n'
            '  "files_to_create": ["string"],\n'
            '  "validation_steps": ["string"]\n'
            "}"
        )
        prompt = f"{prior_context}\n\n{base_prompt}" if prior_context else base_prompt
        result = kickoff_with_retry(flow, "coding", crew_system.coding_architect(), prompt)
        coding_output = parse_model_output(result.raw, CodingStageOutput)
        flow.state.coding_output = coding_output
        coding_exec = execute_coding_stage(flow.state.topic, coding_output, method_output)
        flow.state.coding_execution = coding_exec
        pipeline_manifest = _write_pipeline_manifest(
            Path(coding_exec.sandbox_dir),
            env_manifest=env_manifest,
            data_contract=data_contract,
        )
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
                "pipeline_manifest": str(pipeline_manifest),
            },
        )
        flow.state.coding_manifest_path = str(coding_manifest)
        preview = (
            f"Sandbox plan: {coding_output.sandbox_plan}\n"
            f"Files: {', '.join(coding_output.files_to_create) or 'none'}\n"
            f"Validation: {', '.join(coding_output.validation_steps) or 'none'}\n"
            f"Sandbox dir: {coding_exec.sandbox_dir}\n"
            f"Created files: {len(coding_exec.created_files)}\n"
            f"Validation errors: {len(coding_exec.validation_errors)}\n"
            f"Pipeline manifest: {pipeline_manifest}"
        )
        flow._approval_gate("coding", preview)
        flow._persistence.stage_event(run_id(flow), "coding", "completed", f"sandbox_dir={coding_exec.sandbox_dir}")
        ui_update_queue.put({"type": "stage_completed", "stage": "coding", "timestamp": datetime.now().isoformat()})
        return coding_output
    except Exception as exc:
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
        prior_context = recall_relevant_research(
            topic=flow.state.topic,
            stage="experiment",
            limit=3,
        )
        crew_system = AgenticAiSystem()
        base_prompt = (
            f"Design an experiment plan for topic '{flow.state.topic}' using this coding plan:\n"
            f"{coding_output.model_dump_json(indent=2)}\n\n"
            "Return strict JSON only with schema:\n"
            "{\n"
            '  "experiment_goal": "string",\n'
            '  "run_config": {"key":"value"},\n'
            '  "metrics_to_track": ["string"]\n'
            "}"
        )
        prompt = f"{prior_context}\n\n{base_prompt}" if prior_context else base_prompt
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
        prior_context = recall_relevant_research(
            topic=flow.state.topic,
            stage="writing",
            limit=3,
        )
        crew_system = AgenticAiSystem()
        base_prompt = (
            f"Build a writing plan for topic '{flow.state.topic}' based on this experiment plan:\n"
            f"{experiment_output.model_dump_json(indent=2)}\n\n"
            "Return strict JSON only with schema:\n"
            "{\n"
            '  "sections": [{"name":"string","objective":"string"}],\n'
            '  "output_format": "string",\n'
            '  "review_focus": "string"\n'
            "}"
        )
        prompt = f"{prior_context}\n\n{base_prompt}" if prior_context else base_prompt
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

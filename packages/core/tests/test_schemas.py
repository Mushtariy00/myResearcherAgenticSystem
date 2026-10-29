from typing import Any

import pytest
from pydantic import ValidationError

from agentic_core.schemas import (
    STAGE_OUTPUT_MODELS,
    CodingOutput,
    ExperimentOutput,
    LiteratureOutput,
    MethodOutput,
    RunConfig,
    WritingOutput,
    validate_stage_output,
)
from agentic_core.stages import Stage

PAPER = {
    "paper_id": "arxiv:2406.09414",
    "title": "Depth Anything V2",
    "authors": ["Lihe Yang", "Bingyi Kang"],
    "year": 2024,
    "venue": "NeurIPS",
    "arxiv_id": "2406.09414",
    "url": "https://arxiv.org/abs/2406.09414",
    "abstract": "Synthetic labels plus a large teacher improve fine detail.",
    "source": "arxiv",
    "pdf_available": True,
    "relevance": 0.92,
    "decision": "include",
    "decision_reason": "Directly studies monocular depth with foundation models.",
}

VALID: dict[Stage, dict[str, Any]] = {
    Stage.LITERATURE: {
        "plan": {
            "topic": "Monocular depth estimation 2023-2025",
            "queries": ["monocular depth", "depth foundation model", "zero-shot depth"],
            "scope": "Recent learning-based monocular depth estimation.",
            "inclusion_criteria": ["Published 2023 or later"],
            "subtopics": ["Foundation models"],
        },
        "papers": [PAPER],
        "analyses": [
            {
                "paper_id": "arxiv:2406.09414",
                "contribution": "Scales pseudo-labels from a synthetic-trained teacher.",
                "method": "DINOv2 encoder with a DPT decoder.",
                "results": "Sharper boundaries than V1 on zero-shot benchmarks.",
                "limitations": "Relative depth only without metric fine-tuning.",
                "evidence": [{"quote": "We replace all labeled real images", "page": 2}],
            }
        ],
        "key_findings": [
            {
                "title": "Depth Anything V2",
                "source": "arXiv",
                "summary": "Synthetic labels plus a large teacher improve fine detail.",
                "url": "https://arxiv.org/abs/2406.09414",
                "paper_id": "arxiv:2406.09414",
            }
        ],
        "synthesis": "Foundation models dominate zero-shot relative depth.",
    },
    Stage.METHOD: {
        "research_gaps": ["Metric scale without per-dataset fine-tuning"],
        "proposals": [
            {
                "name": "Scale-aware distillation",
                "rationale": "Distil metric cues from a stereo teacher.",
                "expected_benefit": "Lower AbsRel on NYU2 without labels.",
                "risk": "Teacher errors transfer to the student.",
                "evidence_paper_ids": ["arxiv:2406.09414"],
            }
        ],
        "recommended_option": "Scale-aware distillation",
        "implementation_focus": "A lightweight student for a 6 GB GPU.",
        "datasets": ["nyu2"],
        "evaluation_metrics": ["abs_rel", "rmse", "delta1"],
    },
    Stage.CODING: {
        "summary": "A ResNet-18 encoder with a scale-invariant loss.",
        "files": [
            {
                "path": "model.py",
                "language": "python",
                "role": "model",
                "content": "class DepthNet: ...",
            },
            {
                "path": "losses/silog.py",
                "language": "python",
                "role": "loss",
                "content": "def silog(): ...",
            },
        ],
        "entrypoint": "model.py:DepthNet",
        "smoke_test": {"passed": True, "duration_seconds": 12.5, "log": "200 steps ok"},
    },
    Stage.EXPERIMENT: {
        "status": "succeeded",
        "summary": "Converged after 10 epochs.",
        "config": {"epochs": 10, "batch_size": 8, "lr": 0.0003, "amp": True},
        "series": [
            {
                "name": "abs_rel",
                "split": "val",
                "higher_is_better": False,
                "points": [{"epoch": 0, "value": 0.31}, {"epoch": 1, "value": None}],
            }
        ],
        "final_metrics": {"abs_rel": 0.142, "delta1": None},
        "logs_tail": "epoch 10 done",
        "provenance": {
            "image_digest": "sha256:" + "a" * 64,
            "code_sha256": "b" * 64,
            "config_sha256": "c" * 64,
            "dataset": "nyu2",
            "dataset_version": "2024-01",
            "seed": 42,
            "gpu_name": "NVIDIA GeForce GTX 1060 6GB",
            "gpu_seconds": 812.4,
            "started_at": "2026-10-30T01:00:00Z",
            "finished_at": "2026-10-30T01:14:00Z",
        },
    },
    Stage.WRITING: {
        "title": "Scale-aware distillation for monocular depth",
        "abstract": "We distil metric cues into a small student.",
        "markdown": "# Introduction\n\nFoundation models [1] dominate.",
        "sections": [{"name": "Introduction", "objective": "Motivate metric depth."}],
        "citations": [{"key": 1, "paper_id": "arxiv:2406.09414"}],
        "output_format": "IEEE conference paper",
        "review_focus": "Check that every claim cites a retrieved paper.",
    },
}


@pytest.mark.parametrize("stage", list(Stage))
def test_every_stage_has_a_model_and_valid_examples_pass(stage: Stage) -> None:
    output = validate_stage_output(stage.value, VALID[stage])
    assert isinstance(output, STAGE_OUTPUT_MODELS[stage])
    # JSON round trip: what the worker stores is what the API and the browser read back.
    assert validate_stage_output(stage.value, output.model_dump(mode="json")) == output


@pytest.mark.parametrize(
    "model", [LiteratureOutput, MethodOutput, CodingOutput, ExperimentOutput, WritingOutput]
)
def test_empty_llm_answer_is_rejected(model: type) -> None:
    # The legacy schemas accepted {} because every field had a default.
    with pytest.raises(ValidationError):
        model.model_validate({})


@pytest.mark.parametrize("stage", list(Stage))
def test_unknown_fields_are_rejected(stage: Stage) -> None:
    with pytest.raises(ValidationError):
        validate_stage_output(stage.value, {**VALID[stage], "confidence": 0.9})


def test_blank_strings_and_empty_lists_are_rejected() -> None:
    literature = VALID[Stage.LITERATURE]
    with pytest.raises(ValidationError):
        LiteratureOutput.model_validate({**literature, "synthesis": "   "})
    with pytest.raises(ValidationError):
        LiteratureOutput.model_validate({**literature, "key_findings": []})
    with pytest.raises(ValidationError):
        LiteratureOutput.model_validate({**literature, "papers": []})


@pytest.mark.parametrize(
    "url", ["javascript:alert(1)", "http://example.org/paper", "data:text/html,x"]
)
def test_only_https_links_are_accepted(url: str) -> None:
    literature = VALID[Stage.LITERATURE]
    with pytest.raises(ValidationError):
        LiteratureOutput.model_validate({**literature, "papers": [{**PAPER, "url": url}]})


def test_analyses_must_reference_retrieved_papers() -> None:
    literature = VALID[Stage.LITERATURE]
    analysis = {**literature["analyses"][0], "paper_id": "arxiv:0000.00000"}
    with pytest.raises(ValidationError, match="unknown papers"):
        LiteratureOutput.model_validate({**literature, "analyses": [analysis]})


def test_recommended_option_must_be_a_proposal() -> None:
    with pytest.raises(ValidationError, match="recommended_option"):
        MethodOutput.model_validate({**VALID[Stage.METHOD], "recommended_option": "Something else"})


@pytest.mark.parametrize("path", ["/etc/passwd", "../model.py", "a/./b.py", "a\\b.py", "a//b.py"])
def test_code_paths_must_stay_inside_the_sandbox(path: str) -> None:
    coding = VALID[Stage.CODING]
    bad = {**coding["files"][0], "path": path}
    with pytest.raises(ValidationError):
        CodingOutput.model_validate({**coding, "files": [bad]})


def test_code_paths_and_citation_keys_are_unique() -> None:
    coding = VALID[Stage.CODING]
    with pytest.raises(ValidationError, match="unique"):
        CodingOutput.model_validate({**coding, "files": [coding["files"][0], coding["files"][0]]})
    writing = VALID[Stage.WRITING]
    with pytest.raises(ValidationError, match="unique"):
        WritingOutput.model_validate({**writing, "citations": writing["citations"] * 2})


def test_run_config_defaults_and_rules() -> None:
    config = RunConfig()
    assert config.stages == list(Stage)
    assert RunConfig.model_validate({"stages": ["literature", "method"]}).stages == [
        Stage.LITERATURE,
        Stage.METHOD,
    ]
    for bad in (
        {"stages": ["method"]},  # must start with literature
        {"stages": ["literature", "coding"]},  # no gaps
        {"stages": []},
        {"year_from": 2025, "year_to": 2020},
        {"sources": ["arxiv", "arxiv"]},
        {"sources": ["demo"]},  # demo is an output label, not a searchable source
        {"max_papers": 500},
        {"demo_stage_seconds": 5},  # internal knobs are not wizard options
    ):
        with pytest.raises(ValidationError):
            RunConfig.model_validate(bad)


def test_missing_metrics_stay_null_instead_of_zero() -> None:
    output = ExperimentOutput.model_validate(VALID[Stage.EXPERIMENT])
    assert output.final_metrics["delta1"] is None
    assert output.series[0].points[1].value is None

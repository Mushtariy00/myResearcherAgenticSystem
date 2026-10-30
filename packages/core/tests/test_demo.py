"""Demo generators: deterministic, schema-valid, consistent across stages, honest about edits."""

import ast
import difflib
import re
from datetime import UTC, datetime
from itertools import pairwise, product

import pytest

from agentic_core import demo
from agentic_core.demo._text import subject_phrase, title_case
from agentic_core.schemas import (
    CodingOutput,
    ExperimentOutput,
    LiteratureOutput,
    MethodOutput,
    RunConfig,
    StrictModel,
    WritingOutput,
    validate_stage_output,
)

TOPICS = [
    "Monocular depth estimation 2023-2025",
    "A survey of transformers for monocular depth estimation (indoor scenes)",
    "Semantic segmentation of urban scenes with limited labels",
    "Long-tailed image classification",
    "LLM reasoning",
    "???",
    "단안 깊이 추정",  # Korean: monocular depth estimation
]
CONFIGS = [
    RunConfig(),
    RunConfig(max_papers=5, sources=["crossref"], year_from=2020, year_to=2020),
    RunConfig(max_papers=50, sources=["core", "openalex"], dataset="cityscapes"),
    RunConfig(max_papers=12, dataset=None, year_from=1995, year_to=2010, sources=["arxiv"]),
    RunConfig(dataset="cifar100", max_papers=8, sources=["semantic_scholar", "arxiv"]),
    RunConfig(dataset="lab_scans_v1"),
]
STAGES = ("literature", "method", "coding", "experiment", "writing")
HTML_TAG = re.compile(r"<[a-zA-Z/!?]")
MARKER = re.compile(r"(?<!\\)\[(\d+)\]")


def pipeline(
    topic: str, config: RunConfig, seed: int, feedback: str = "", attempt: int = 1
) -> tuple[LiteratureOutput, MethodOutput, CodingOutput, ExperimentOutput, WritingOutput]:
    plan = demo.research_plan(topic, seed, config=config)
    literature = demo.literature(topic, plan, config, seed, feedback)
    method = demo.method(topic, literature, seed, feedback, config=config)
    coding = demo.coding(topic, method, seed, attempt, feedback)
    experiment = demo.experiment(topic, coding, seed, feedback=feedback)
    writing = demo.writing(topic, literature, method, experiment, seed, feedback)
    return literature, method, coding, experiment, writing


def dumps(outputs: tuple[StrictModel, ...]) -> list[dict[str, object]]:
    return [output.model_dump(mode="json") for output in outputs]


def test_same_inputs_give_the_same_outputs() -> None:
    first = pipeline(TOPICS[0], RunConfig(), 7, "Focus on 2024")
    assert dumps(first) == dumps(pipeline(TOPICS[0], RunConfig(), 7, "Focus on 2024"))
    other = pipeline(TOPICS[0], RunConfig(), 8, "Focus on 2024")
    for stage, a, b in zip(STAGES, dumps(first), dumps(other), strict=True):
        assert a != b, f"{stage} ignores the seed"


@pytest.mark.parametrize("topic", TOPICS)
def test_outputs_are_schema_valid_for_many_seeds_topics_and_configs(topic: str) -> None:
    for config, seed in product(CONFIGS, range(4)):
        outputs = pipeline(topic, config, seed, "Tighten the scope" if seed % 2 else "")
        for stage, data in zip(STAGES, dumps(outputs), strict=True):
            # A JSON round trip, exactly what the worker stores and the API serves.
            assert validate_stage_output(stage, data).model_dump(mode="json") == data


def test_literature_respects_the_run_config() -> None:
    for config, seed in product(CONFIGS, range(6)):
        literature = pipeline("Monocular depth estimation", config, seed)[0]
        papers = literature.papers
        assert 5 <= len(papers) <= config.max_papers
        assert all(config.year_from <= paper.year <= config.year_to for paper in papers)
        assert {paper.source for paper in papers} <= set(config.sources)
        assert len({paper.paper_id for paper in papers}) == len(papers)
        assert [p.relevance for p in papers] == sorted((p.relevance for p in papers), reverse=True)
        decisions = [paper.decision for paper in papers]
        assert decisions.count("include") >= 3
        assert {"maybe", "exclude"} <= set(decisions)
        included = {paper.paper_id for paper in papers if paper.decision == "include"}
        assert {analysis.paper_id for analysis in literature.analyses} == included
        for analysis in literature.analyses:
            assert 1 <= len(analysis.evidence) <= 3
            assert all(1 <= quote.page <= 12 for quote in analysis.evidence)
        assert 4 <= len(literature.key_findings) <= 6
        assert 2 <= len(literature.synthesis.split("\n\n")) <= 3
        assert all(len(paper.abstract.split(". ")) >= 3 for paper in papers)  # multi-sentence


def test_links_are_https_and_identifiers_clearly_synthetic() -> None:
    for config, seed in product(CONFIGS, range(4)):
        literature = pipeline(TOPICS[seed % len(TOPICS)], config, seed)[0]
        urls = [paper.url for paper in literature.papers]
        urls += [finding.url for finding in literature.key_findings]
        assert all(url and url.startswith("https://") for url in urls)
        for paper in literature.papers:
            if paper.doi:
                assert paper.doi.startswith("10.5555/")  # Crossref's test prefix
            if paper.arxiv_id:
                # Real arXiv sequence numbers stay far below 90000 per month.
                assert re.fullmatch(r"\d{4}\.9\d{3,4}|cs/\d{4}9\d{2}", paper.arxiv_id)


def test_method_builds_on_the_included_papers_and_the_configured_dataset() -> None:
    for config, seed in product(CONFIGS, range(4)):
        literature, method = pipeline(TOPICS[0], config, seed)[:2]
        included = {paper.paper_id for paper in literature.papers if paper.decision == "include"}
        assert len(method.proposals) == 3
        for proposal in method.proposals:
            assert proposal.evidence_paper_ids
            assert set(proposal.evidence_paper_ids) <= included
        assert method.recommended_option in {proposal.name for proposal in method.proposals}
        assert method.datasets == [config.dataset or "nyu2"]
        assert 2 <= len(method.evaluation_metrics) <= 3
        assert method.research_gaps


def test_generated_code_is_valid_python_for_the_recommended_proposal() -> None:
    for config, seed in product(CONFIGS, range(3)):
        method, coding = pipeline(TOPICS[seed], config, seed)[1:3]
        by_path = {file.path: file for file in coding.files}
        assert set(by_path) == {
            "model.py",
            "losses.py",
            "configs/train.yaml",
            "tests/test_model.py",
            "README.md",
        }
        for file in coding.files:
            if file.language == "python":
                ast.parse(file.content, filename=file.path)
        module, _, class_name = coding.entrypoint.partition(":")
        assert f"class {class_name}(nn.Module)" in by_path[module].content
        assert method.recommended_option in by_path["README.md"].content
        assert f"dataset: {method.datasets[0]}" in by_path["configs/train.yaml"].content
        assert coding.smoke_test.passed and coding.smoke_test.log


def test_a_later_coding_attempt_changes_some_lines_and_records_the_feedback() -> None:
    method = pipeline(TOPICS[0], RunConfig(), 11)[1]
    attempts = [
        demo.coding(TOPICS[0], method, 11, attempt, "Use GroupNorm" if attempt > 1 else "")
        for attempt in (1, 2, 3)
    ]
    for before, after in pairwise(attempts):
        old = {file.path: file.content for file in before.files}
        new = {file.path: file.content for file in after.files}
        changed = [path for path in old if old[path] != new[path]]
        code_changed = [path for path in changed if path != "README.md"]
        assert code_changed, "a revision must change the code or the config"
        for path in changed:  # a readable diff: most lines survive
            ratio = difflib.SequenceMatcher(None, old[path], new[path]).ratio()
            assert ratio > 0.7, path
    readme = next(file.content for file in attempts[1].files if file.path == "README.md")
    assert "Reviewer feedback for attempt 2: Use GroupNorm" in readme
    assert "Revised after review: Use GroupNorm." in attempts[1].summary
    assert "Revised after review" not in attempts[0].summary


def test_experiment_follows_the_coding_output() -> None:
    saw_missing_point = False
    for seed in range(12):
        coding = pipeline(TOPICS[seed % 4], CONFIGS[seed % len(CONFIGS)], seed)[2]
        finished = datetime(2026, 10, 30, 6, 0, tzinfo=UTC)
        experiment = demo.experiment(TOPICS[0], coding, seed, finished_at=finished)
        epochs = experiment.config["epochs"]
        assert isinstance(epochs, int) and 12 <= epochs <= 30
        config_file = next(file for file in coding.files if file.role == "config").content
        assert f"epochs: {epochs}" in config_file
        assert all(len(series.points) == epochs for series in experiment.series)
        names = [(series.name, series.split) for series in experiment.series]
        assert names[:2] == [("loss", "train"), ("loss", "val")]
        assert 2 <= len(names) - 2 <= 3
        for series in experiment.series[2:]:
            assert series.points[-1].value == experiment.final_metrics[series.name]
            saw_missing_point |= any(point.value is None for point in series.points)
        assert None not in experiment.final_metrics.values()
        code_sha, config_sha = demo.code_hashes(coding)
        provenance = experiment.provenance
        assert (provenance.code_sha256, provenance.config_sha256) == (code_sha, config_sha)
        assert provenance.gpu_name == "NVIDIA GeForce GTX 1060 6GB"
        assert provenance.finished_at == finished
        assert provenance.started_at < finished and provenance.gpu_seconds > 0
        assert f"epoch {epochs - 1} train" in experiment.logs_tail
    assert saw_missing_point, "now and then a validation point should be missing (None)"


def test_draft_cites_included_papers_and_reports_the_final_metrics() -> None:
    for config, seed in product(CONFIGS, range(4)):
        literature, _, _, experiment, writing = pipeline(TOPICS[seed], config, seed)
        markdown = writing.markdown
        assert 900 <= len(markdown.split()) <= 1500
        for heading in ("## Abstract", "## 1. Introduction", "## 2. Related Work", "## 3. Method"):
            assert heading in markdown
        for heading in ("## 4. Experiments", "## 5. Discussion", "## 6. Conclusion"):
            assert heading in markdown
        assert "## References" in markdown
        keys = {citation.key for citation in writing.citations}
        assert {int(key) for key in MARKER.findall(markdown)} == keys
        included = {paper.paper_id for paper in literature.papers if paper.decision == "include"}
        assert {citation.paper_id for citation in writing.citations} <= included
        assert markdown.count("$$") == 2 and r"\mathcal{L}" in markdown
        assert not HTML_TAG.search(markdown)
        for name, value in experiment.final_metrics.items():
            if name not in ("train_loss", "val_loss") and value is not None:
                assert f"| {value:.3f} |" in markdown
        # The Markdown copy differs only by escapes (e.g. a dataset id such as lab\_scans).
        assert writing.abstract in re.sub(r"\\(.)", r"\1", markdown)


@pytest.mark.parametrize("stage", STAGES)
def test_feedback_is_visibly_reflected(stage: str) -> None:
    feedback = "Focus on papers from 2024 and explain the loss."
    revised = pipeline(TOPICS[0], RunConfig(), 5, feedback)[STAGES.index(stage)]
    original = pipeline(TOPICS[0], RunConfig(), 5)[STAGES.index(stage)]
    note = f"Revised after review: {feedback}"
    assert note in revised.model_dump_json()
    assert "Revised after review" not in original.model_dump_json()


def test_quoted_feedback_cannot_add_markup_to_the_draft() -> None:
    feedback = "<script>alert(1)</script> see [9] and $$x$$ | # heading"
    writing = pipeline(TOPICS[0], RunConfig(), 3, feedback)[4]
    assert not HTML_TAG.search(writing.markdown)
    assert "&lt;script&gt;" in writing.markdown
    assert {int(key) for key in MARKER.findall(writing.markdown)} == {
        citation.key for citation in writing.citations
    }
    assert writing.markdown.count("$$") == 2


def test_topics_become_short_title_phrases() -> None:
    assert subject_phrase("Monocular depth estimation 2023-2025") == "Monocular depth estimation"
    assert subject_phrase("A survey of NYU depth (indoor): methods") == "NYU depth"
    assert subject_phrase("Depth since 2020 \N{EM DASH} a review") == "Depth"
    assert subject_phrase("???") == "representation learning"
    assert title_case("vision transformers for NYU depth") == "Vision Transformers for NYU Depth"

import sqlite3
import tempfile
import unittest
from pathlib import Path
import subprocess
from unittest.mock import patch

import fitz

from agentic_ai_system.execution.experiment_runner import run_experiment_stage
from agentic_ai_system.schemas.models import (
    CodingStageOutput,
    ExperimentStageOutput,
    LiteratureResearchOutput,
    MethodStageOutput,
    WritingSection,
    WritingStageOutput,
)
from agentic_ai_system.orchestration.supervisor_flow import ResearchSupervisorFlow
from agentic_ai_system.storage.run_persistence import RunPersistence
from agentic_ai_system.execution.sandbox_executor import execute_coding_stage
from agentic_ai_system.storage.writing_storage import store_writing_output


class ReliabilityTests(unittest.TestCase):
    def test_parser_handles_non_strict_json(self) -> None:
        flow = ResearchSupervisorFlow()
        raw = (
            "prefix\n"
            "{ 'topic': 'u-net', 'generated_at': '2026-01-01', "
            "'key_findings': [], 'synthesis': 'line1\nline2' }\n"
            "suffix"
        )
        parsed = flow._parse_model_output(raw, LiteratureResearchOutput)
        self.assertEqual(parsed.topic, "u-net")
        self.assertTrue(parsed.synthesis.startswith("line1"))

    def test_run_persistence_writes_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "flow_runs.db"
            persistence = RunPersistence(db_path=db_path)
            persistence.start_run("r1", "topic", "2026")
            persistence.stage_event("r1", "literature", "running")
            persistence.log_approval("r1", "literature", True)
            persistence.finish_run("r1", "completed")

            with sqlite3.connect(db_path) as conn:
                run_status = conn.execute(
                    "SELECT status FROM runs WHERE run_id = 'r1'"
                ).fetchone()
                stage_count = conn.execute(
                    "SELECT COUNT(*) FROM stage_events WHERE run_id = 'r1'"
                ).fetchone()
                approval_count = conn.execute(
                    "SELECT COUNT(*) FROM approvals WHERE run_id = 'r1'"
                ).fetchone()

            self.assertEqual(run_status[0], "completed")
            self.assertEqual(stage_count[0], 1)
            self.assertEqual(approval_count[0], 1)

    def test_coding_experiment_writing_artifacts_are_created(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coding_output = CodingStageOutput(
                sandbox_plan="Create sandbox files",
                files_to_create=["src/main.py", "README.md"],
                validation_steps=["compile python files"],
            )
            method_output = MethodStageOutput(
                research_gaps=["gap-1"],
                recommended_option="Option A",
            )
            coding_result = execute_coding_stage(
                "test topic",
                coding_output,
                method_output,
                base_dir=root,
            )
            self.assertTrue(coding_result.sandbox_dir)
            self.assertGreaterEqual(len(coding_result.created_files), 2)

            experiment_output = ExperimentStageOutput(
                experiment_goal="Check sandbox quality",
                run_config={"device": "cpu"},
                metrics_to_track=["validation_rate"],
            )
            experiment_result = run_experiment_stage(
                "test topic",
                experiment_output,
                coding_result,
                base_dir=root,
            )
            self.assertTrue(Path(experiment_result.summary_file).exists())
            self.assertIn("sandbox_validation_rate", experiment_result.metrics)

            writing_output = WritingStageOutput(
                sections=[WritingSection(name="Intro", objective="Summarize motivation")],
                output_format="markdown",
                review_focus="clarity",
            )
            writing_dir, files = store_writing_output(
                "test topic",
                writing_output,
                experiment_output=experiment_output,
                base_dir=root,
            )
            self.assertTrue(writing_dir.exists())
            self.assertGreaterEqual(len(files), 2)

    def test_auto_mode_skips_approval_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "flow_runs.db"
            flow = ResearchSupervisorFlow()
            flow._persistence = RunPersistence(db_path=db_path)
            flow.state.topic = "demo"
            flow.state.current_year = "2026"
            flow.state.auto_mode = True
            flow.state.id = "auto-1"

            flow._approval_gate("literature", "preview text")

            with sqlite3.connect(db_path) as conn:
                row = conn.execute(
                    "SELECT approved FROM approvals WHERE run_id = 'auto-1' AND stage = 'literature'"
                ).fetchone()

            self.assertEqual(row[0], 1)

    def test_method_output_is_persisted(self) -> None:
        from agentic_ai_system.storage.method_storage import store_method_output

        with tempfile.TemporaryDirectory() as temp_dir:
            path = store_method_output(
                "demo topic",
                MethodStageOutput(
                    research_gaps=["gap-1"],
                    recommended_option="Option A",
                    implementation_focus="Prototype A",
                ),
                base_dir=Path(temp_dir),
            )
            self.assertTrue(path.exists())

    def test_coding_stage_writes_runnable_scaffold(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coding_output = CodingStageOutput(
                sandbox_plan="Create runnable scaffold",
                files_to_create=[
                    "src/lct_depth/conv_encoder.py",
                    "src/lct_depth/token_sparsifier.py",
                    "src/lct_depth/decoder.py",
                    "src/lct_depth/lct_depth_model.py",
                    "train_lct_depth.py",
                    "benchmark.py",
                    "README.md",
                ],
                validation_steps=["compile python files"],
            )
            method_output = MethodStageOutput(
                research_gaps=["gap-1"],
                recommended_option="Option A",
                implementation_focus="Prototype A",
            )
            coding_result = execute_coding_stage(
                "demo topic",
                coding_output,
                method_output,
                base_dir=root,
            )
            model_text = (Path(coding_result.sandbox_dir) / "src" / "lct_depth" / "lct_depth_model.py").read_text(
                encoding="utf-8"
            )
            train_text = (Path(coding_result.sandbox_dir) / "train_lct_depth.py").read_text(encoding="utf-8")
            self.assertIn("class LCTDepthModel", model_text)
            self.assertIn("from lct_depth.lct_depth_model import build_model", train_text)
            self.assertTrue((Path(coding_result.sandbox_dir) / "src" / "lct_depth" / "__init__.py").exists())

            run = subprocess.run(
                ["python3", "train_lct_depth.py"],
                cwd=coding_result.sandbox_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("trainable scaffold ready", run.stdout)

    def test_literature_stage_falls_back_on_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            flow = ResearchSupervisorFlow()
            flow._persistence = RunPersistence(db_path=root / "flow_runs.db")
            flow.state.topic = "demo topic"
            flow.state.current_year = "2026"
            flow.state.auto_mode = True
            flow.state.id = "lit-1"

            source_bundle = {
                "queries": ["demo topic"],
                "papers": [
                    {
                        "title": "Paper One",
                        "source": "arxiv",
                        "summary": "summary text",
                        "url": "https://example.com",
                    }
                ],
                "errors": [],
            }

            artifact = root / "literature.json"

            def write_artifact(topic: str, literature_output: LiteratureResearchOutput) -> Path:
                artifact.write_text(
                    literature_output.model_dump_json(indent=2),
                    encoding="utf-8",
                )
                return artifact

            with patch(
                "agentic_ai_system.orchestration.literature_pipeline.collect_literature_bundle",
                return_value=source_bundle,
            ), patch(
                "agentic_ai_system.orchestration.literature_pipeline.kickoff_with_retry",
                side_effect=TimeoutError("The read operation timed out"),
            ), patch(
                "agentic_ai_system.orchestration.literature_pipeline.store_literature_output",
                side_effect=write_artifact,
            ), patch(
                "agentic_ai_system.orchestration.literature_pipeline.store_literature_screen_output",
                return_value=root / "screen.json",
            ), patch(
                "agentic_ai_system.orchestration.literature_pipeline.store_literature_fetch_output",
                return_value=(root / "fetch", root / "fetch_manifest.json"),
            ), patch(
                "agentic_ai_system.orchestration.literature_pipeline.store_literature_analysis_output",
                return_value=(root / "analysis", root / "analysis_manifest.json"),
            ), patch(
                "agentic_ai_system.orchestration.literature_pipeline.store_stage_artifact_manifest",
                return_value=root / "manifest.json",
            ):
                output = flow.literature_stage("demo topic")

            self.assertTrue(artifact.exists())
            self.assertEqual(output.topic, "demo topic")
            self.assertTrue(output.key_findings)
            self.assertIn("Deterministic literature synthesis", output.synthesis)

    def test_literature_prompt_is_compact(self) -> None:
        flow = ResearchSupervisorFlow()
        source_bundle = {
            "topic": "demo topic",
            "queries": ["q1", "q2", "q3", "q4", "q5"],
            "errors": [{"source": "x"}] * 3,
            "papers": [
                {"title": f"Paper {i}", "source": "arxiv", "summary": "s" * 500, "url": f"https://e/{i}", "relevance_score": i}
                for i in range(12)
            ],
        }

        compact = flow._compact_literature_bundle(source_bundle)

        self.assertLessEqual(len(compact["top_papers"]), 8)
        self.assertLessEqual(len(compact["queries"]), 4)
        self.assertEqual(compact["error_count"], 3)
        self.assertLessEqual(len(compact["top_papers"][0]["summary"]), 280)

    def test_literature_stage_uses_two_llm_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            flow = ResearchSupervisorFlow()
            flow._persistence = RunPersistence(db_path=root / "flow_runs.db")
            flow.state.topic = "demo topic"
            flow.state.current_year = "2026"
            flow.state.auto_mode = True
            flow.state.id = "lit-2"

            source_bundle = {
                "topic": "demo topic",
                "queries": ["q1", "q2"],
                "errors": [],
                "papers": [
                    {"title": "Relevant Paper", "source": "arxiv", "summary": "deep summary", "url": "https://e/1", "relevance_score": 9},
                    {"title": "Other Paper", "source": "arxiv", "summary": "other summary", "url": "https://e/2", "relevance_score": 1},
                ],
            }
            screen_json = '{"selected_indices":[0],"rejected_indices":[1],"selection_rationale":"relevant"}'
            paper_json = (
                '{"index":0,"title":"Relevant Paper","source":"arxiv","relevance_assessment":"relevant","key_findings":["finding"],"limitations":["limitation"],"evidence_snippets":["snippet"],"summary":"paper summary"}'
            )
            deep_json = (
                '{"topic":"demo topic","generated_at":"2026-01-01","key_findings":[{"title":"Relevant Paper","source":"arxiv","summary":"deep summary","url":"https://e/1"}],"synthesis":"analysis"}'
            )
            calls: list[str] = []

            class DummyResult:
                def __init__(self, raw: str) -> None:
                    self.raw = raw

            def fake_kickoff(flow_obj, stage: str, agent, prompt: str, attempts: int = 3):
                calls.append(prompt)
                if len(calls) == 1:
                    return DummyResult(screen_json)
                if len(calls) == 2:
                    return DummyResult(paper_json)
                return DummyResult(deep_json)

            with patch(
                "agentic_ai_system.orchestration.literature_pipeline.collect_literature_bundle",
                return_value=source_bundle,
            ), patch(
                "agentic_ai_system.orchestration.literature_pipeline.kickoff_with_retry",
                side_effect=fake_kickoff,
            ), patch(
                "agentic_ai_system.orchestration.literature_pipeline.store_literature_screen_output",
                return_value=root / "screen.json",
            ), patch(
                "agentic_ai_system.orchestration.literature_pipeline.store_literature_fetch_output",
                return_value=(root / "fetch", root / "fetch_manifest.json"),
            ), patch(
                "agentic_ai_system.orchestration.literature_pipeline.store_literature_analysis_output",
                return_value=(root / "analysis", root / "analysis_manifest.json"),
            ), patch(
                "agentic_ai_system.orchestration.literature_pipeline.store_stage_artifact_manifest",
                return_value=root / "manifest.json",
            ), patch(
                "agentic_ai_system.orchestration.literature_pipeline.store_literature_output",
                return_value=root / "lit.json",
            ):
                flow.literature_stage("demo topic")

            self.assertEqual(len(calls), 3)
            self.assertIn("Screen candidate papers", calls[0])
            self.assertIn("Analyze the full text of paper", calls[1])
            self.assertIn("Write a literature synthesis", calls[2])

    def test_pdf_full_text_fetcher_extracts_text(self) -> None:
        from agentic_ai_system.tools.paper_fetch_tools import fetch_open_access_full_text

        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "sample.pdf"
            doc = fitz.open()
            page = doc.new_page()
            page.insert_text((72, 72), "Hello paper world")
            doc.save(str(pdf_path))
            doc.close()

            result = fetch_open_access_full_text(str(pdf_path))

            self.assertEqual(result["status"], "ok")
            self.assertIn("Hello paper world", result["text"])


if __name__ == "__main__":
    unittest.main()

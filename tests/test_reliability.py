import sqlite3
import tempfile
import unittest
from pathlib import Path

from agentic_ai_system.models import LiteratureResearchOutput
from agentic_ai_system.run_persistence import RunPersistence
from agentic_ai_system.supervisor_flow import ResearchSupervisorFlow


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


if __name__ == "__main__":
    unittest.main()

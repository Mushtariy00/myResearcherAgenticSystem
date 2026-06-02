from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agentic_ai_system.orchestration import research_pipeline
from agentic_ai_system.orchestration.exceptions import CheckpointRejected


class _DummyPersistence:
    def stage_event(self, *args, **kwargs):
        pass

    def finish_run(self, *args, **kwargs):
        pass


class _DummyFlow:
    def __init__(self):
        self._persistence = _DummyPersistence()
        self.state = type("S", (), {"approvals": {}})()


class CodingGatesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.flow = _DummyFlow()
        # ensure working directory is a temp dir for manifest writes
        self.tmpdir = tempfile.TemporaryDirectory()
        self.orig_cwd = Path.cwd()
        Path(self.tmpdir.name).mkdir(parents=True, exist_ok=True)
        self.cwd = Path(self.tmpdir.name)

    def tearDown(self) -> None:
        Path.cwd().chdir(self.orig_cwd) if hasattr(Path.cwd(), "chdir") else None
        self.tmpdir.cleanup()

    def test_env_manifest_written_and_returned(self):
        env_path = self.cwd / "env_manifest.json"
        # call ensure, expecting it to create the file and return path
        p = research_pipeline._ensure_env_manifest(self.flow, env_path)
        self.assertTrue(p.exists())
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertIn("python_version", data)
        self.assertIn("key_packages", data)

    def test_data_contract_missing_raises_checkpoint(self):
        data_path = self.cwd / "data_contract.json"
        with self.assertRaises(CheckpointRejected):
            research_pipeline._ensure_data_contract(self.flow, data_path)
        # after call the template should exist
        self.assertTrue(data_path.exists())
        template = json.loads(data_path.read_text(encoding="utf-8"))
        self.assertIn("approved_by", template)

    def test_data_contract_requires_human_approval(self):
        data_path = self.cwd / "data_contract.json"
        # create file without approval
        template = {
            "dataset_name": "myset",
            "approved_by": "pending",
            "approved_at": "",
        }
        data_path.write_text(json.dumps(template), encoding="utf-8")
        with self.assertRaises(CheckpointRejected):
            research_pipeline._ensure_data_contract(self.flow, data_path)

    def test_data_contract_passes_when_approved(self):
        data_path = self.cwd / "data_contract.json"
        template = {
            "dataset_name": "myset",
            "approved_by": "human",
            "approved_at": "2026-01-01T00:00:00Z",
        }
        data_path.write_text(json.dumps(template), encoding="utf-8")
        p = research_pipeline._ensure_data_contract(self.flow, data_path)
        self.assertEqual(p, data_path)


if __name__ == "__main__":
    unittest.main()

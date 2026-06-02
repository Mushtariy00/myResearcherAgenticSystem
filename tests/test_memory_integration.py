from __future__ import annotations

import json
import os
import unittest
from unittest.mock import MagicMock, patch

from agentic_ai_system.orchestration import memory_integration


class MemoryIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_enabled = os.environ.get("AGENTMEMORY_ENABLED")
        self._orig_url = os.environ.get("AGENTMEMORY_URL")

    def tearDown(self) -> None:
        if self._orig_enabled is None:
            os.environ.pop("AGENTMEMORY_ENABLED", None)
        else:
            os.environ["AGENTMEMORY_ENABLED"] = self._orig_enabled
        if self._orig_url is None:
            os.environ.pop("AGENTMEMORY_URL", None)
        else:
            os.environ["AGENTMEMORY_URL"] = self._orig_url

    def test_memory_recall_disabled(self) -> None:
        os.environ["AGENTMEMORY_ENABLED"] = "false"
        results = memory_integration._memory_recall("demo", limit=2)
        self.assertEqual(results, [])

    @patch("urllib.request.urlopen")
    def test_memory_recall_enabled(self, mock_urlopen: MagicMock) -> None:
        os.environ["AGENTMEMORY_ENABLED"] = "true"
        os.environ["AGENTMEMORY_URL"] = "http://localhost:3111"
        response = MagicMock()
        response.read.return_value = json.dumps(
            {"results": [{"content": "Prior finding A"}, {"content": "Prior finding B"}]}
        ).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = response

        results = memory_integration._memory_recall("demo", limit=2)

        self.assertEqual(results, ["Prior finding A", "Prior finding B"])


if __name__ == "__main__":
    unittest.main()

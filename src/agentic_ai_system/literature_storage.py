from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from agentic_ai_system.models import LiteratureResearchOutput


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "topic"


def store_literature_output(
    topic: str,
    literature_output: LiteratureResearchOutput,
    base_dir: Path | None = None,
) -> Path:
    root = base_dir or Path.cwd()
    directory = root / "outputs" / "literature"
    directory.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = directory / f"{_slugify(topic)}_{timestamp}.json"
    filepath.write_text(
        json.dumps(literature_output.model_dump(), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    return filepath

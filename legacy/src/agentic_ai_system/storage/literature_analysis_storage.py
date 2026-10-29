from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from agentic_ai_system.schemas.fetches import PaperAnalysisOutput


def _slugify(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-") or "topic"


def store_literature_analysis_output(
    topic: str,
    analyses: list[PaperAnalysisOutput],
    base_dir: Path | None = None,
) -> tuple[Path, Path]:
    root = base_dir or Path.cwd()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    directory = root / "outputs" / "literature_analysis" / f"{_slugify(topic)}_{timestamp}"
    directory.mkdir(parents=True, exist_ok=True)

    manifest_path = directory / "literature_analysis_manifest.json"
    manifest_path.write_text(
        json.dumps([analysis.model_dump() for analysis in analyses], indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    return directory, manifest_path

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from agentic_ai_system.schemas.models import LiteratureResearchOutput


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


def load_latest_literature_output(
    topic: str,
    base_dir: Path | None = None,
) -> tuple[LiteratureResearchOutput, Path] | None:
    root = base_dir or Path.cwd()
    directory = root / "outputs" / "literature"
    if not directory.exists():
        return None
    slug = _slugify(topic)
    candidates = sorted(
        directory.glob(f"{slug}_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            output = LiteratureResearchOutput.model_validate(payload)
            return output, path
        except Exception:
            continue
    return None

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from agentic_ai_system.schemas.models import MethodStageOutput


def _slugify(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-") or "topic"


def store_method_output(
    topic: str,
    method_output: MethodStageOutput,
    base_dir: Path | None = None,
) -> Path:
    root = base_dir or Path.cwd()
    directory = root / "outputs" / "method"
    directory.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = directory / f"{_slugify(topic)}_{timestamp}.json"
    filepath.write_text(
        json.dumps(method_output.model_dump(), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    return filepath

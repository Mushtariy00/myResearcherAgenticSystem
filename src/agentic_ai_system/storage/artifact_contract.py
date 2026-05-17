from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from agentic_ai_system.schemas.artifacts import StageArtifactManifest


def _slugify(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-") or "topic"


def store_stage_artifact_manifest(
    stage: str,
    topic: str,
    primary_path: str,
    summary: str,
    auxiliary_paths: list[str] | None = None,
    metadata: dict[str, object] | None = None,
    status: str = "completed",
    base_dir: Path | None = None,
) -> Path:
    root = base_dir or Path.cwd()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    directory = root / "outputs" / "artifacts" / f"{_slugify(topic)}_{timestamp}"
    directory.mkdir(parents=True, exist_ok=True)

    manifest = StageArtifactManifest(
        stage=stage,
        topic=topic,
        generated_at=datetime.now().isoformat(),
        primary_path=primary_path,
        auxiliary_paths=auxiliary_paths or [],
        summary=summary,
        status=status,
        metadata=metadata or {},
    )
    manifest_path = directory / f"{_slugify(stage)}.json"
    manifest_path.write_text(
        json.dumps(manifest.model_dump(), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    return manifest_path

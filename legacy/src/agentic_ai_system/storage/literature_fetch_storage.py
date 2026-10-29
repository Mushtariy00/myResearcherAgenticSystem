from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def _slugify(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-") or "topic"


def store_literature_fetch_output(
    topic: str,
    fetch_results: list[dict[str, object]],
    base_dir: Path | None = None,
) -> tuple[Path, Path]:
    root = base_dir or Path.cwd()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    directory = root / "outputs" / "literature_fetch" / f"{_slugify(topic)}_{timestamp}"
    directory.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, object]] = []
    for index, result in enumerate(fetch_results, start=1):
        text = str(result.get("text", ""))
        text_path = directory / f"paper_{index:02d}.txt"
        text_path.write_text(text, encoding="utf-8")
        manifest.append(
            {
                "index": index,
                "source_url": result.get("source_url", ""),
                "resolved_pdf_url": result.get("resolved_pdf_url", ""),
                "status": result.get("status", ""),
                "page_count": result.get("page_count", 0),
                "text_length": len(text),
                "text_path": str(text_path),
                "error": result.get("error", ""),
            }
        )

    manifest_path = directory / "literature_fetch_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8")
    return directory, manifest_path

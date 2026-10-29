from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from agentic_ai_system.schemas.models import ExperimentStageOutput, WritingStageOutput


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "topic"


def store_writing_output(
    topic: str,
    writing_output: WritingStageOutput,
    experiment_output: ExperimentStageOutput | None = None,
    base_dir: Path | None = None,
) -> tuple[Path, list[Path]]:
    root = base_dir or Path.cwd()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = root / "outputs" / "writing" / f"{_slugify(topic)}_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    files: list[Path] = []
    for index, section in enumerate(writing_output.sections, start=1):
        filename = f"{index:02d}_{_slugify(section.name)}.md"
        path = out_dir / filename
        lines = [
            f"# {section.name}",
            "",
            "## Objective",
            section.objective,
            "",
            "## Draft",
            (
                f"Draft this section by focusing on: {section.objective}. "
                "Use approved stage outputs and keep claims grounded in evidence."
            ),
            "",
            "## Review Focus",
            writing_output.review_focus,
            "",
        ]
        if experiment_output and experiment_output.metrics_to_track:
            lines.extend(
                [
                    "## Metrics to Reference",
                    *[f"- {metric}" for metric in experiment_output.metrics_to_track],
                    "",
                ]
            )
        path.write_text("\n".join(lines), encoding="utf-8")
        files.append(path)

    summary = out_dir / "00_summary.md"
    summary_lines = [
        "# Writing Plan Summary",
        "",
        f"**Topic:** {topic}",
        f"**Output format:** {writing_output.output_format}",
        f"**Review focus:** {writing_output.review_focus}",
        "",
        "## Sections",
        *[f"- {section.name}: {section.objective}" for section in writing_output.sections],
        "",
    ]
    summary.write_text("\n".join(summary_lines), encoding="utf-8")
    files.insert(0, summary)

    return out_dir, files

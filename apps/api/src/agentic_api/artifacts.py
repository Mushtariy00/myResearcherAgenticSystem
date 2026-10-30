"""Downloadable files derived from a run's stage outputs (artifact storage comes later).

Each artifact is computed from one stage output: every file of a coding output and all of them
as a zip, an experiment's log and metrics, and a writing output's draft and references. An
artifact id is ``<stage_output_id>.<item>``. The server derives the item again from that output,
and access follows the run that owns the output, so a made-up id cannot reach another run's
data, and an item the output does not have is simply not found.
"""

import csv
import hashlib
import io
import re
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath

from agentic_api.schemas import ArtifactKind
from agentic_core.schemas import (
    CodingOutput,
    ExperimentOutput,
    LiteratureOutput,
    PaperRef,
    WritingOutput,
)
from agentic_core.stages import Stage

ARTIFACT_STAGES = (Stage.CODING, Stage.EXPERIMENT, Stage.WRITING)
_ID = re.compile(
    r"^(?P<output>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    r"\.(?P<item>code\.(?:0|[1-9][0-9]{0,5}|zip)|log|metrics|draft|bib)$"
)
_TEXT = "; charset=utf-8"
_MEDIA_TYPES = {
    ".py": "text/x-python" + _TEXT,
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".json": "application/json",
    ".toml": "application/toml",
    ".md": "text/markdown" + _TEXT,
    ".csv": "text/csv" + _TEXT,
    ".sh": "text/x-shellscript" + _TEXT,
}
_JOURNAL = re.compile(
    r"\b(?:transactions|journal|letters|review|tpami|ijcv|tip|ra-l|pattern recognition)\b",
    re.IGNORECASE,
)
_TEX_SPECIAL = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "^": r"\^{}",
    "~": r"\~{}",
}
# A CSV cell starting with one of these is a formula to a spreadsheet (CSV injection).
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


@dataclass(frozen=True)
class Artifact:
    id: str
    stage: Stage
    kind: ArtifactKind
    filename: str
    path: str | None
    media_type: str
    content: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


def artifact_id(output_id: uuid.UUID, item: str) -> str:
    return f"{output_id}.{item}"


def parse_artifact_id(value: str) -> tuple[uuid.UUID, str] | None:
    """(stage output id, item) of a well-formed artifact id, else None."""
    match = _ID.match(value)
    return (uuid.UUID(match["output"]), match["item"]) if match else None


def file_prefix(run_id: uuid.UUID) -> str:
    """Download names start with the run, so files of different runs don't collide."""
    return f"run-{str(run_id)[:8]}"


def _media_type(path: str) -> str:
    return _MEDIA_TYPES.get(PurePosixPath(path).suffix.lower(), "text/plain" + _TEXT)


def coding_artifacts(
    output_id: uuid.UUID, coding: CodingOutput, *, prefix: str, created_at: datetime
) -> list[Artifact]:
    files = [
        Artifact(
            id=artifact_id(output_id, f"code.{index}"),
            stage=Stage.CODING,
            kind="code_file",
            filename=PurePosixPath(file.path).name,
            path=file.path,
            media_type=_media_type(file.path),
            content=file.content.encode(),
        )
        for index, file in enumerate(coding.files)
    ]
    archive = Artifact(
        id=artifact_id(output_id, "code.zip"),
        stage=Stage.CODING,
        kind="code_archive",
        filename=f"{prefix}-code.zip",
        path=None,
        media_type="application/zip",
        content=_zip([(file.path, file.content) for file in coding.files], created_at),
    )
    return [*files, archive]


def _zip(files: list[tuple[str, str]], created_at: datetime) -> bytes:
    """A deterministic archive: every entry carries the output's creation time."""
    stamp = created_at.astimezone(UTC)
    date_time = (
        (stamp.year, stamp.month, stamp.day, stamp.hour, stamp.minute, stamp.second)
        if stamp.year >= 1980  # the earliest time a zip entry can hold
        else (1980, 1, 1, 0, 0, 0)
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path, content in files:
            entry = zipfile.ZipInfo(path, date_time=date_time)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16  # rw-r--r--
            archive.writestr(entry, content)
    return buffer.getvalue()


def _text_file(text: str) -> bytes:
    """UTF-8, ending with a newline like any text file (the schemas strip it from outputs)."""
    return (text if not text or text.endswith("\n") else f"{text}\n").encode()


def experiment_artifacts(
    output_id: uuid.UUID, experiment: ExperimentOutput, *, prefix: str
) -> list[Artifact]:
    return [
        Artifact(
            id=artifact_id(output_id, "log"),
            stage=Stage.EXPERIMENT,
            kind="experiment_log",
            filename=f"{prefix}-experiment.log",
            path=None,
            media_type="text/plain" + _TEXT,
            content=_text_file(experiment.logs_tail),
        ),
        Artifact(
            id=artifact_id(output_id, "metrics"),
            stage=Stage.EXPERIMENT,
            kind="metrics",
            filename=f"{prefix}-metrics.csv",
            path=None,
            media_type="text/csv" + _TEXT,
            content=_metrics_csv(experiment),
        ),
    ]


def _cell(text: str) -> str:
    return f"'{text}" if text.startswith(_FORMULA_START) else text


def _metrics_csv(experiment: ExperimentOutput) -> bytes:
    """Every measured point, one per row. A missing measurement is an empty value, never 0."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["metric", "split", "epoch", "value", "higher_is_better"])
    for series in experiment.series:
        for point in series.points:
            writer.writerow(
                [
                    _cell(series.name),
                    series.split,
                    point.epoch,
                    "" if point.value is None else repr(point.value),
                    "true" if series.higher_is_better else "false",
                ]
            )
    return buffer.getvalue().encode()


def writing_artifacts(
    output_id: uuid.UUID,
    writing: WritingOutput,
    literature: LiteratureOutput | None,
    *,
    prefix: str,
) -> list[Artifact]:
    """The draft and its references; ``literature`` is the run's literature output, where the
    cited papers' metadata comes from."""
    return [
        Artifact(
            id=artifact_id(output_id, "draft"),
            stage=Stage.WRITING,
            kind="draft",
            filename=f"{prefix}-draft.md",
            path=None,
            media_type="text/markdown" + _TEXT,
            content=_text_file(writing.markdown),
        ),
        Artifact(
            id=artifact_id(output_id, "bib"),
            stage=Stage.WRITING,
            kind="references",
            filename=f"{prefix}-references.bib",
            path=None,
            media_type="application/x-bibtex" + _TEXT,
            content=bibtex(writing, literature).encode(),
        ),
    ]


def _tex(text: str) -> str:
    """Text for a BibTeX field: LaTeX's special characters escaped, on one line."""
    return "".join(_TEX_SPECIAL.get(char, char) for char in " ".join(text.split()))


def _verbatim(text: str) -> str:
    """A URL, DOI or eprint kept as written, minus what would unbalance the field's braces."""
    return "".join(text.split()).replace("\\", "%5C").replace("{", "%7B").replace("}", "%7D")


def _entry(key: int, paper_id: str, paper: PaperRef | None) -> str:
    if paper is None:
        kind = "misc"
        fields = [("title", _tex(paper_id)), ("note", "Not found in the run's literature output")]
    else:
        preprint = not paper.venue or paper.venue.lower() == "arxiv"
        journal = not preprint and _JOURNAL.search(paper.venue or "") is not None
        kind = "misc" if preprint else "article" if journal else "inproceedings"
        fields = [
            ("title", "{" + _tex(paper.title) + "}"),  # double braces keep the capitalization
            ("author", " and ".join(_tex(author) for author in paper.authors)),
            ("year", str(paper.year)),
        ]
        if not preprint:
            fields.append(("journal" if journal else "booktitle", _tex(paper.venue or "")))
        if paper.doi:
            fields.append(("doi", _verbatim(paper.doi)))
        if paper.arxiv_id:
            fields += [("eprint", _verbatim(paper.arxiv_id)), ("archiveprefix", "arXiv")]
        if paper.url:
            fields.append(("url", _verbatim(paper.url)))
        fields.append(("note", _tex(f"Paper id: {paper_id}")))
    body = ",\n".join(f"  {name} = {{{value}}}" for name, value in fields)
    return f"@{kind}{{ref{key},\n{body}\n}}\n"


def bibtex(writing: WritingOutput, literature: LiteratureOutput | None) -> str:
    """One entry per citation; ``ref<n>`` is the draft's ``[n]`` marker."""
    papers = {paper.paper_id: paper for paper in literature.papers} if literature else {}
    citations = sorted(writing.citations, key=lambda citation: citation.key)
    if not citations:
        return "% The draft cites no papers.\n"
    entries = [_entry(c.key, c.paper_id, papers.get(c.paper_id)) for c in citations]
    return "\n".join(entries)

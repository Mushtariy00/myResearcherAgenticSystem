"""Downloadable files of a run's stage outputs.

Each artifact belongs to one stage output: every file of a coding output and all of them as a
zip, an experiment's log, metrics and best checkpoint, and a writing output's draft and
references. An experiment's files come from its training job's folder on the GPU host
(agentic_core.gpu_jobs) when the API can read it, as on one machine: the job's whole log.txt,
its metrics.jsonl as CSV, and checkpoints/best.pt, streamed from disk. Without the folder (the
API on another host, or the files removed) the log and the metrics are derived from the output
itself, its log tail and its metric series, and there is no checkpoint.

An artifact id is ``<stage_output_id>.<item>``. The server derives the item again from that
output, and access follows the run that owns the output, so a made-up id cannot reach another
run's data, and an item the output does not have is simply not found.
"""

import csv
import hashlib
import io
import json
import logging
import math
import re
import stat
import uuid
import zipfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from agentic_api.schemas import ArtifactKind
from agentic_core.gpu_jobs import CHECKPOINT_FILE, LOG_FILE, METRICS_FILE, job_dir
from agentic_core.schemas import (
    CodingOutput,
    ExperimentOutput,
    LiteratureOutput,
    PaperRef,
    WritingOutput,
)
from agentic_core.stages import Stage

log = logging.getLogger(__name__)

ARTIFACT_STAGES = (Stage.CODING, Stage.EXPERIMENT, Stage.WRITING)
_ID = re.compile(
    r"^(?P<output>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    r"\.(?P<item>code\.(?:0|[1-9][0-9]{0,5}|zip)|log|metrics|checkpoint|draft|bib)$"
)
_SHA256 = re.compile(r"[0-9a-f]{64}")
READ_CHUNK = 1024 * 1024
# metrics.jsonl comes out of the job's container, so it is untrusted: a CSV of it keeps the
# records' kind, epoch and step and at most this many metric columns (the harness writes 9),
# named in at most this many characters, and at most this many rows (50 epochs of 100,000 steps,
# the most a run may plan, log 250,000 step records).
MAX_METRIC_COLUMNS = 32
MAX_METRIC_NAME = 64
MAX_METRIC_ROWS = 300_000
_METRIC_KINDS = frozenset({"train_step", "epoch"})
_RECORD_FIELDS = frozenset({"kind", "epoch", "step", "ts"})
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
class StoredFile:
    """A file on disk, streamed when it is downloaded; its size and sha256 as listed."""

    path: Path
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class Artifact:
    id: str
    stage: Stage
    kind: ArtifactKind
    filename: str
    path: str | None
    media_type: str
    content: bytes | StoredFile  # derived in memory, or a job's file on disk

    @property
    def size_bytes(self) -> int:
        if isinstance(self.content, StoredFile):
            return self.content.size_bytes
        return len(self.content)

    @property
    def sha256(self) -> str:
        if isinstance(self.content, StoredFile):
            return self.content.sha256
        return hashlib.sha256(self.content).hexdigest()


@dataclass(frozen=True)
class JobFiles:
    """What an experiment's training job left in its folder on the GPU host, as artifacts serve
    it; each None when it is not there."""

    log: StoredFile | None  # log.txt: the container's whole output
    metrics_csv: bytes | None  # out/metrics.jsonl as CSV
    checkpoint: StoredFile | None  # out/checkpoints/best.pt


NO_JOB_FILES = JobFiles(log=None, metrics_csv=None, checkpoint=None)


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
    output_id: uuid.UUID,
    experiment: ExperimentOutput,
    *,
    prefix: str,
    files: JobFiles = NO_JOB_FILES,
) -> list[Artifact]:
    """The log and the metrics, from the training job's ``files`` where they are, else derived
    from the output; and the best checkpoint when the job left one."""
    artifacts = [
        Artifact(
            id=artifact_id(output_id, "log"),
            stage=Stage.EXPERIMENT,
            kind="experiment_log",
            filename=f"{prefix}-experiment.log",
            path=None,
            media_type="text/plain" + _TEXT,
            content=files.log if files.log is not None else _text_file(experiment.logs_tail),
        ),
        Artifact(
            id=artifact_id(output_id, "metrics"),
            stage=Stage.EXPERIMENT,
            kind="metrics",
            filename=f"{prefix}-metrics.csv",
            path=None,
            media_type="text/csv" + _TEXT,
            content=files.metrics_csv
            if files.metrics_csv is not None
            else _metrics_csv(experiment),
        ),
    ]
    if files.checkpoint is not None:
        artifacts.append(
            Artifact(
                id=artifact_id(output_id, "checkpoint"),
                stage=Stage.EXPERIMENT,
                kind="checkpoint",
                filename=f"{prefix}-best.pt",
                path=None,
                media_type="application/octet-stream",
                content=files.checkpoint,
            )
        )
    return artifacts


def job_files(data_dir: Path, job_id: uuid.UUID, provenance: object) -> JobFiles:
    """The training job's files under ``data_dir``, as the executor left them (blocking: run it
    in a thread). log.txt (at most 32 MB) is hashed here and metrics.jsonl becomes CSV. The
    checkpoint, up to 200 MB, is never read: it is listed with the sha256 the executor recorded
    as it copied it (the job's provenance), so one without a recorded sha256, or no longer of
    the recorded size, is left out."""
    root = job_dir(data_dir, job_id)
    out = root / "out"  # the outputs copied out of the container
    return JobFiles(
        log=_hashed(root / LOG_FILE),
        metrics_csv=_metrics_jsonl_csv(out / METRICS_FILE),
        checkpoint=_recorded(out / CHECKPOINT_FILE, CHECKPOINT_FILE, provenance),
    )


def _hashed(path: Path) -> StoredFile | None:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as file:
            while chunk := file.read(READ_CHUNK):
                size += len(chunk)
                digest.update(chunk)
    except FileNotFoundError:
        return None
    except OSError as exc:
        log.warning("cannot read %s: %s", path, exc)
        return None
    return StoredFile(path=path, size_bytes=size, sha256=digest.hexdigest())


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _recorded(path: Path, name: str, provenance: object) -> StoredFile | None:
    """The output ``name`` with the size and sha256 its job's provenance recorded for it."""
    record = _mapping(provenance)
    sha256 = _mapping(record.get("outputs_sha256")).get(name)
    size = _mapping(record.get("outputs")).get(name)
    if not isinstance(sha256, str) or not _SHA256.fullmatch(sha256) or not isinstance(size, int):
        return None
    try:
        info = path.stat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        log.warning("cannot read %s: %s", path, exc)
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_size != size:
        log.warning("%s is not the file its job recorded; it is not listed", path)
        return None
    return StoredFile(path=path, size_bytes=size, sha256=sha256)


@dataclass(frozen=True)
class _MetricRecord:
    kind: str  # train_step or epoch
    epoch: int | None
    step: int | None
    metrics: dict[str, object]  # column name to a number or None


def _is_measure(value: object) -> bool:
    """A number, or null for "not measured" (booleans are not numbers here)."""
    return value is None or (isinstance(value, int | float) and not isinstance(value, bool))


def _measure_cell(value: object) -> str:
    """Empty when not measured: null, and NaN or an infinity, which no measurement gives."""
    if not isinstance(value, int | float) or isinstance(value, bool):
        return ""
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    return repr(value)


def _index(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _record_metrics(record: Mapping[str, Any]) -> dict[str, object]:
    """A record's measurements by column: a number at the top under its own name (a step's
    loss), and one in an object under <object>_<name> (an epoch's train and val metrics)."""
    metrics: dict[str, object] = {}
    for key, value in record.items():
        if key in _RECORD_FIELDS:
            continue
        items = value.items() if isinstance(value, Mapping) else [(None, value)]
        for name, item in items:
            column = key if name is None else f"{key}_{name}"
            if _is_measure(item) and len(column) <= MAX_METRIC_NAME:
                metrics[column] = item
    return metrics


def _metric_records(path: Path) -> Iterator[_MetricRecord]:
    """The first MAX_METRIC_ROWS step and epoch records of metrics.jsonl, in order. Other lines
    (not JSON, other kinds, a last line cut short) are skipped."""
    found = 0
    with path.open(encoding="utf-8", errors="replace") as lines:
        for line in lines:
            try:
                record = json.loads(line)
            except (ValueError, RecursionError):
                continue
            kind = record.get("kind") if isinstance(record, dict) else None
            if not isinstance(kind, str) or kind not in _METRIC_KINDS:
                continue
            yield _MetricRecord(
                kind=kind,
                epoch=_index(record.get("epoch")),
                step=_index(record.get("step")),
                metrics=_record_metrics(record),
            )
            found += 1
            if found >= MAX_METRIC_ROWS:
                return


def _metrics_jsonl_csv(path: Path) -> bytes | None:
    """metrics.jsonl as CSV: one row per step and epoch record, in the file's order, with its
    kind, epoch and step, then a column per metric (a step's loss; an epoch's train_* and val_*),
    empty where the record has none or it was not measured. The file is read twice, for the
    columns and then for the rows, so its records never all sit in memory."""
    try:
        columns: dict[str, None] = {}  # in the order they first appear
        for record in _metric_records(path):
            for name in record.metrics:
                if name not in columns and len(columns) < MAX_METRIC_COLUMNS:
                    columns[name] = None
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["kind", "epoch", "step", *(_cell(name) for name in columns)])
        for record in _metric_records(path):
            writer.writerow(
                [
                    record.kind,
                    "" if record.epoch is None else record.epoch,
                    "" if record.step is None else record.step,
                    *(_measure_cell(record.metrics.get(name)) for name in columns),
                ]
            )
    except FileNotFoundError:
        return None
    except OSError as exc:
        log.warning("cannot read %s: %s", path, exc)
        return None
    return buffer.getvalue().encode()


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

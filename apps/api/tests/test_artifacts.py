import copy
import csv
import hashlib
import io
import json
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_api import artifacts as artifacts_module
from agentic_api.artifacts import MAX_METRIC_COLUMNS, job_files
from agentic_api.routers import artifacts as artifacts_router
from agentic_api.settings import Settings
from agentic_core.enums import GpuJobKind, GpuJobStatus, StageStatus
from agentic_core.gpu_jobs import CHECKPOINT_FILE, LOG_FILE, METRICS_FILE, RESULTS_FILE, job_dir
from agentic_core.schemas import validate_stage_output
from api_testkit import (
    CODING_OUTPUT,
    EXPERIMENT_OUTPUT,
    ORIGIN,
    WRITING_OUTPUT,
    add_gpu_job,
    add_output,
    add_stage_output,
    add_stage_run,
    as_user,
    create_project,
    literature,
    paper,
    start_run,
    team_project,
)

Factory = async_sessionmaker[AsyncSession]
CREATED = datetime(2026, 10, 30, 1, 2, 3, tzinfo=UTC)
DEPTH_PAPER = paper(
    "arxiv:2406.09414",
    "Depth & Scale_Aware: 100% Synthetic",
    venue="IEEE TPAMI",
    doi="10.5555/tpami.2024.1",
    arxiv_id="2406.09414",
    url="https://arxiv.org/abs/2406.09414",
)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Each test keeps its jobs' files in a data directory of its own."""
    return Settings(environment="test", public_origin=ORIGIN, data_dir=tmp_path)


def test_the_builders_make_valid_outputs() -> None:
    for stage, data in (
        ("coding", CODING_OUTPUT),
        ("experiment", EXPERIMENT_OUTPUT),
        ("writing", WRITING_OUTPUT),
    ):
        validate_stage_output(stage, data)


async def _finished_run(client: httpx.AsyncClient, db: Factory) -> tuple[str, dict[str, str]]:
    """A run of bob's with every stage's output; returns it and the output id per stage."""
    project = await team_project(client)
    run_id = await start_run(client, project)
    outputs = {
        "literature": await add_stage_output(
            db, run_id, "literature", literature([DEPTH_PAPER]), created_at=CREATED
        ),
        "coding": await add_stage_output(
            db,
            run_id,
            "coding",
            CODING_OUTPUT,
            degraded=True,
            degraded_reason="stage.demo",
            created_at=CREATED,
        ),
        "experiment": await add_stage_output(
            db, run_id, "experiment", EXPERIMENT_OUTPUT, created_at=CREATED
        ),
        "writing": await add_stage_output(
            db, run_id, "writing", WRITING_OUTPUT, created_at=CREATED
        ),
    }
    return run_id, outputs


async def _list(client: httpx.AsyncClient, run_id: str, user: str = "bob") -> dict[str, Any]:
    response = await client.get(f"/api/v1/runs/{run_id}/artifacts", headers=as_user(user))
    assert response.status_code == 200, response.text
    return response.json()


async def _download(
    client: httpx.AsyncClient, artifact_id: str, user: str = "bob"
) -> httpx.Response:
    return await client.get(f"/api/v1/artifacts/{artifact_id}", headers=as_user(user))


async def test_run_artifacts_are_listed_with_sizes_and_hashes(
    client: httpx.AsyncClient, db: Factory
) -> None:
    run_id, outputs = await _finished_run(client, db)
    listing = await _list(client, run_id, user="vera")  # viewers may download too
    prefix = f"run-{run_id[:8]}"
    coding, experiment, writing = outputs["coding"], outputs["experiment"], outputs["writing"]
    assert [
        (item["id"], item["stage"], item["kind"], item["filename"], item["path"], item["demo"])
        for item in listing["items"]
    ] == [
        (f"{coding}.code.0", "coding", "code_file", "model.py", "model.py", True),
        (f"{coding}.code.1", "coding", "code_file", "losses.py", "losses.py", True),
        (f"{coding}.code.2", "coding", "code_file", "train.yaml", "configs/train.yaml", True),
        (f"{coding}.code.zip", "coding", "code_archive", f"{prefix}-code.zip", None, True),
        (
            f"{experiment}.log",
            "experiment",
            "experiment_log",
            f"{prefix}-experiment.log",
            None,
            False,
        ),
        (f"{experiment}.metrics", "experiment", "metrics", f"{prefix}-metrics.csv", None, False),
        (f"{writing}.draft", "writing", "draft", f"{prefix}-draft.md", None, False),
        (f"{writing}.bib", "writing", "references", f"{prefix}-references.bib", None, False),
    ]
    assert (listing["run_id"], listing["demo"]) == (run_id, True)
    assert [item["media_type"] for item in listing["items"]] == [
        "text/x-python; charset=utf-8",
        "text/x-python; charset=utf-8",
        "application/yaml",
        "application/zip",
        "text/plain; charset=utf-8",
        "text/csv; charset=utf-8",
        "text/markdown; charset=utf-8",
        "application/x-bibtex; charset=utf-8",
    ]
    for item in listing["items"]:
        response = await _download(client, item["id"], user="vera")
        assert response.status_code == 200, item["id"]
        assert (item["size_bytes"], item["sha256"]) == (
            len(response.content),
            hashlib.sha256(response.content).hexdigest(),
        )
        assert (item["version"], item["created_at"]) == (1, "2026-10-30T01:02:03Z")
        assert item["stage_output_id"] == item["id"].split(".")[0]


async def test_downloads_are_attachments_with_the_derived_content(
    client: httpx.AsyncClient, db: Factory
) -> None:
    run_id, outputs = await _finished_run(client, db)
    prefix = f"run-{run_id[:8]}"
    model = await _download(client, f"{outputs['coding']}.code.0")
    assert model.text == "class DepthNet:\n    pass\n"
    assert model.headers["content-type"] == "text/x-python; charset=utf-8"
    assert model.headers["content-disposition"] == 'attachment; filename="model.py"'
    assert model.headers["x-content-type-options"] == "nosniff"
    assert model.headers["cache-control"] == "private"
    assert model.headers["content-length"] == str(len(model.content))

    archive = await _download(client, f"{outputs['coding']}.code.zip")
    assert archive.headers["content-disposition"] == f'attachment; filename="{prefix}-code.zip"'
    with zipfile.ZipFile(io.BytesIO(archive.content)) as opened:
        assert opened.namelist() == ["model.py", "losses.py", "configs/train.yaml"]
        for file in CODING_OUTPUT["files"]:
            assert opened.read(file["path"]).decode() == file["content"]
        assert {entry.date_time for entry in opened.infolist()} == {(2026, 10, 30, 1, 2, 2)}
    assert (await _download(client, f"{outputs['coding']}.code.zip")).content == archive.content

    log = await _download(client, f"{outputs['experiment']}.log")
    assert log.text == "epoch 0 loss 1.5\nepoch 1 loss 0.9\n"
    metrics = await _download(client, f"{outputs['experiment']}.metrics")
    assert list(csv.reader(io.StringIO(metrics.text))) == [
        ["metric", "split", "epoch", "value", "higher_is_better"],
        ["loss", "train", "0", "1.5", "false"],
        ["loss", "train", "1", "0.9", "false"],
        ["delta1", "val", "0", "", "true"],  # not measured: empty, never 0
        ["delta1", "val", "1", "0.81", "true"],
    ]

    draft = await _download(client, f"{outputs['writing']}.draft")
    assert (draft.text, draft.headers["content-type"]) == (
        WRITING_OUTPUT["markdown"],
        "text/markdown; charset=utf-8",
    )
    references = await _download(client, f"{outputs['writing']}.bib")
    assert references.text == (
        "@article{ref1,\n"
        "  title = {{Depth \\& Scale\\_Aware: 100\\% Synthetic}},\n"
        "  author = {Lihe Yang and Bingyi Kang},\n"
        "  year = {2024},\n"
        "  journal = {IEEE TPAMI},\n"
        "  doi = {10.5555/tpami.2024.1},\n"
        "  eprint = {2406.09414},\n"
        "  archiveprefix = {arXiv},\n"
        "  url = {https://arxiv.org/abs/2406.09414},\n"
        "  note = {Paper id: arxiv:2406.09414}\n"
        "}\n"
        "\n"
        "@misc{ref2,\n"
        "  title = {doi:10.5555/missing},\n"
        "  note = {Not found in the run's literature output}\n"
        "}\n"
    )


async def test_text_from_outputs_cannot_inject_formulas_or_headers(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project = await team_project(client)
    run_id = await start_run(client, project)
    experiment = copy.deepcopy(EXPERIMENT_OUTPUT)
    experiment["series"][0]["name"] = '=HYPERLINK("https://evil.test")'
    coding = copy.deepcopy(CODING_OUTPUT)
    coding["files"][0]["path"] = 'src/mod\N{LATIN SMALL LETTER E WITH GRAVE}le "x";.py'
    experiment_id = await add_stage_output(db, run_id, "experiment", experiment)
    coding_id = await add_stage_output(db, run_id, "coding", coding)

    metrics = await _download(client, f"{experiment_id}.metrics")
    rows = list(csv.reader(io.StringIO(metrics.text)))
    assert rows[1][0] == '\'=HYPERLINK("https://evil.test")'
    odd = await _download(client, f"{coding_id}.code.0")
    assert odd.headers["content-disposition"] == (
        "attachment; filename=\"mod-le-x-.py\"; filename*=UTF-8''mod%C3%A8le%20%22x%22%3B.py"
    )


async def test_artifact_ids_cannot_be_forged(client: httpx.AsyncClient, db: Factory) -> None:
    run_id, outputs = await _finished_run(client, db)
    other = await create_project(client, "Other", owner="carol")
    carols_run = await start_run(client, other, user="carol")
    carols_code = await add_stage_output(db, carols_run, "coding", CODING_OUTPUT)

    async def not_found(artifact_id: str, user: str = "bob") -> None:
        response = await _download(client, artifact_id, user)
        assert (response.status_code, response.json()) == (
            404,
            {"detail": "artifact.not_found"},
        ), artifact_id

    # Another run's output: the same answer as for an id that doesn't exist.
    await not_found(f"{carols_code}.code.0")
    await not_found(f"{uuid.uuid4()}.code.0")
    await not_found(f"{outputs['coding']}.code.0", user="carol")
    hidden = await client.get(f"/api/v1/runs/{run_id}/artifacts", headers=as_user("carol"))
    assert hidden.status_code == 404
    # Items the output doesn't have, outputs of other stages, and malformed ids.
    for artifact_id in (
        f"{outputs['coding']}.log",
        f"{outputs['coding']}.code.3",
        f"{outputs['coding']}.code.01",
        f"{outputs['coding']}.checkpoint",
        f"{outputs['experiment']}.code.0",
        f"{outputs['experiment']}.checkpoint",  # its attempt has no training job
        f"{outputs['writing']}.metrics",
        f"{outputs['literature']}.draft",
        outputs["coding"].upper() + ".code.0",
        outputs["coding"],
        "abc",
        f"{outputs['coding']}.code.0.",
    ):
        await not_found(artifact_id)
    assert (await _download(client, f"{carols_code}.code.0", "carol")).status_code == 200
    assert (await client.get(f"/api/v1/artifacts/{carols_code}.code.0")).status_code == 401


async def test_only_the_latest_valid_outputs_make_artifacts(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project = await team_project(client)
    run_id = await start_run(client, project)
    assert await _list(client, run_id) == {"run_id": run_id, "items": [], "demo": False}

    first = await add_stage_run(db, run_id, "coding", StageStatus.CHANGES_REQUESTED, 1)
    old_id, _ = await add_output(db, first, CODING_OUTPUT)
    second = await add_stage_run(db, run_id, "coding", StageStatus.APPROVED, 2)
    await add_output(db, second, CODING_OUTPUT)
    edited = copy.deepcopy(CODING_OUTPUT)
    edited["files"] = [edited["files"][0]]
    edited_id, _ = await add_output(db, second, edited, version=2, edited_by="alice")
    # Placeholders of unbuilt stages don't validate; a retry made the old writing stale.
    await add_stage_output(db, run_id, "experiment", {"stage": "experiment", "note": "later"})
    await add_stage_output(db, run_id, "writing", WRITING_OUTPUT, status=StageStatus.INVALIDATED)

    listing = await _list(client, run_id)
    assert [item["id"] for item in listing["items"]] == [
        f"{edited_id}.code.0",
        f"{edited_id}.code.zip",
    ]
    assert listing["items"][0]["version"] == 2
    # Earlier versions stay downloadable by id, for whoever can open the run.
    assert (await _download(client, f"{old_id}.code.2", user="vera")).status_code == 200


async def test_references_from_generated_papers_are_demo(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project = await team_project(client)
    run_id = await start_run(client, project)
    await add_stage_output(
        db,
        run_id,
        "literature",
        literature([DEPTH_PAPER]),
        degraded=True,
        degraded_reason="literature.demo_search",
    )
    await add_stage_output(db, run_id, "writing", WRITING_OUTPUT)
    listing = await _list(client, run_id)
    assert {item["kind"]: item["demo"] for item in listing["items"]} == {
        "draft": False,
        "references": True,
    }
    assert listing["demo"] is True


# --- An experiment's training job files (agentic_core.gpu_jobs) ------------------------------

# The container's whole output: far more than the output's tail.
JOB_LOG = "".join(f"epoch {n // 100} step {n % 100} loss {1 / (n + 1):.4f}\n" for n in range(300))
METRICS_JSONL = "".join(
    json.dumps(record) + "\n"
    for record in (
        {
            "ts": "2026-10-31T01:00:00+00:00",
            "kind": "train_step",
            "epoch": 0,
            "step": 0,
            "loss": 1.25,
        },
        {
            "ts": "2026-10-31T01:00:05+00:00",
            "kind": "train_step",
            "epoch": 0,
            "step": 20,
            "loss": 0.75,
        },
        {
            "ts": "2026-10-31T01:00:09+00:00",
            "kind": "epoch",
            "epoch": 0,
            "train": {"loss": 0.9, "rmse": 1.1, "mae": 0.8, "abs_rel": 0.3},
            "val": {"loss": 0.85, "rmse": None, "mae": 0.7, "abs_rel": 0.25},
        },
    )
).encode()
CHECKPOINT = bytes(range(256)) * 1025  # a little over 4 chunks of the 64 KiB streamed at a time
OUTPUTS = {
    RESULTS_FILE: b'{"status": "ok"}',
    METRICS_FILE: METRICS_JSONL,
    CHECKPOINT_FILE: CHECKPOINT,
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _provenance(outputs: dict[str, bytes]) -> dict[str, Any]:
    """A job's provenance as the executor records it: each output it copied, with its sha256."""
    return {
        "image": "arp-sandbox-pytorch:dev",
        "outputs": {name: len(data) for name, data in outputs.items()},
        "outputs_sha256": {name: _sha256(data) for name, data in outputs.items()},
    }


def _job_folder(outputs: dict[str, bytes]) -> dict[str, bytes]:
    """A finished job's folder: its log, and its outputs as copied out of its container."""
    return {LOG_FILE: JOB_LOG.encode(), **{f"out/{name}": data for name, data in outputs.items()}}


async def _trained(
    client: httpx.AsyncClient,
    db: Factory,
    data_dir: Path,
    *,
    files: dict[str, bytes],
    provenance: dict[str, Any] | None,
) -> tuple[str, str, Path]:
    """bob's run with an experiment output whose training job left ``files`` (paths in its
    folder) in the data directory: the run's id, the output's id and the job's folder."""
    project = await team_project(client)
    run_id = await start_run(client, project)
    stage_run_id = await add_stage_run(db, run_id, "experiment", StageStatus.APPROVED)
    output_id, _ = await add_output(db, stage_run_id, EXPERIMENT_OUTPUT, created_at=CREATED)
    job_id = await add_gpu_job(
        db, run_id, stage_run_id, status=GpuJobStatus.SUCCEEDED, provenance=provenance
    )
    root = job_dir(data_dir, job_id)
    for name, data in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(data)
    return run_id, output_id, root


async def test_an_experiment_serves_its_training_jobs_files(
    client: httpx.AsyncClient, db: Factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id, output_id, root = await _trained(
        client, db, tmp_path, files=_job_folder(OUTPUTS), provenance=_provenance(OUTPUTS)
    )
    streamed: list[Path] = []
    stream = artifacts_router.path_response

    def spy(path: Path, **options: Any) -> StreamingResponse:
        streamed.append(path)
        return stream(path, **options)

    monkeypatch.setattr(artifacts_router, "path_response", spy)
    listing = await _list(client, run_id, user="vera")
    prefix = f"run-{run_id[:8]}"
    assert [
        (item["id"], item["kind"], item["filename"], item["media_type"], item["path"])
        for item in listing["items"]
    ] == [
        (
            f"{output_id}.log",
            "experiment_log",
            f"{prefix}-experiment.log",
            "text/plain; charset=utf-8",
            None,
        ),
        (
            f"{output_id}.metrics",
            "metrics",
            f"{prefix}-metrics.csv",
            "text/csv; charset=utf-8",
            None,
        ),
        (
            f"{output_id}.checkpoint",
            "checkpoint",
            f"{prefix}-best.pt",
            "application/octet-stream",
            None,
        ),
    ]
    assert listing["demo"] is False and not any(item["demo"] for item in listing["items"])
    for item in listing["items"]:
        response = await _download(client, item["id"], user="vera")  # viewers may download too
        assert response.status_code == 200, item["id"]
        assert (item["size_bytes"], item["sha256"]) == (
            len(response.content),
            _sha256(response.content),
        )
        assert response.headers["content-type"] == item["media_type"]
        assert response.headers["content-disposition"] == (
            f'attachment; filename="{item["filename"]}"'
        )
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["cache-control"] == "private"
        assert response.headers["content-length"] == str(len(response.content))
    # The log and the checkpoint stream from the job's folder, never read into memory whole.
    assert streamed == [root / LOG_FILE, root / "out" / CHECKPOINT_FILE]

    assert (await _download(client, f"{output_id}.log")).text == JOB_LOG  # all of it
    assert (await _download(client, f"{output_id}.checkpoint")).content == CHECKPOINT
    metrics = await _download(client, f"{output_id}.metrics")
    empty = [""] * 8
    assert list(csv.reader(io.StringIO(metrics.text))) == [
        [
            "kind",
            "epoch",
            "step",
            "loss",
            "train_loss",
            "train_rmse",
            "train_mae",
            "train_abs_rel",
            "val_loss",
            "val_rmse",
            "val_mae",
            "val_abs_rel",
        ],
        ["train_step", "0", "0", "1.25", *empty],
        ["train_step", "0", "20", "0.75", *empty],
        # Not measured (null): empty, never 0.
        ["epoch", "0", "", "", "0.9", "1.1", "0.8", "0.3", "0.85", "", "0.7", "0.25"],
    ]


async def test_a_checkpoint_is_listed_with_the_sha256_its_job_recorded(
    client: httpx.AsyncClient, db: Factory, tmp_path: Path
) -> None:
    """The listing never reads a checkpoint of up to 200 MB to hash it: the executor hashed it
    as it copied it out of the container."""
    provenance = _provenance(OUTPUTS)
    provenance["outputs_sha256"][CHECKPOINT_FILE] = "f" * 64  # not the file's own
    run_id, _, _ = await _trained(
        client, db, tmp_path, files=_job_folder(OUTPUTS), provenance=provenance
    )
    listing = await _list(client, run_id)
    [checkpoint] = [item for item in listing["items"] if item["kind"] == "checkpoint"]
    assert (checkpoint["size_bytes"], checkpoint["sha256"]) == (len(CHECKPOINT), "f" * 64)


@pytest.mark.parametrize(
    "provenance",
    [
        None,
        {"outputs": {CHECKPOINT_FILE: len(CHECKPOINT)}},
        {
            "outputs": {CHECKPOINT_FILE: len(CHECKPOINT) - 1},
            "outputs_sha256": {CHECKPOINT_FILE: _sha256(CHECKPOINT)},
        },
        {
            "outputs": {CHECKPOINT_FILE: len(CHECKPOINT)},
            "outputs_sha256": {CHECKPOINT_FILE: "F" * 64},
        },
    ],
    ids=["no provenance", "no sha256 recorded", "not the file copied", "malformed sha256"],
)
async def test_a_checkpoint_without_its_record_is_not_served(
    client: httpx.AsyncClient, db: Factory, tmp_path: Path, provenance: dict[str, Any] | None
) -> None:
    run_id, output_id, _ = await _trained(
        client, db, tmp_path, files=_job_folder(OUTPUTS), provenance=provenance
    )
    listing = await _list(client, run_id)
    assert [item["kind"] for item in listing["items"]] == ["experiment_log", "metrics"]
    assert (await _download(client, f"{output_id}.log")).text == JOB_LOG
    assert (await _download(client, f"{output_id}.checkpoint")).status_code == 404


async def test_without_its_jobs_files_an_experiment_keeps_its_derived_artifacts(
    client: httpx.AsyncClient, db: Factory, tmp_path: Path
) -> None:
    """As on an API on another machine than the GPU: the output's log tail and series."""
    run_id, output_id, _ = await _trained(
        client, db, tmp_path, files={}, provenance=_provenance(OUTPUTS)
    )
    listing = await _list(client, run_id)
    assert [item["id"] for item in listing["items"]] == [f"{output_id}.log", f"{output_id}.metrics"]
    log = await _download(client, f"{output_id}.log")
    assert log.text == EXPERIMENT_OUTPUT["logs_tail"] + "\n"
    metrics = await _download(client, f"{output_id}.metrics")
    assert metrics.text.splitlines()[0] == "metric,split,epoch,value,higher_is_better"
    assert (await _download(client, f"{output_id}.checkpoint")).status_code == 404


async def test_each_attempt_serves_its_own_training_jobs_files(
    client: httpx.AsyncClient, db: Factory, tmp_path: Path
) -> None:
    run_id, first, _ = await _trained(
        client, db, tmp_path, files=_job_folder(OUTPUTS), provenance=_provenance(OUTPUTS)
    )
    retry = await add_stage_run(db, run_id, "experiment", StageStatus.OUTPUT_READY, attempt=2)
    second, _ = await add_output(db, retry, EXPERIMENT_OUTPUT)
    # Only training jobs count: not a (made-up) smoke job of the attempt, with files of its own.
    smoke = await add_gpu_job(
        db, run_id, retry, kind=GpuJobKind.SMOKE, provenance=_provenance(OUTPUTS)
    )
    for name, data in _job_folder(OUTPUTS).items():
        (job_dir(tmp_path, smoke) / name).parent.mkdir(parents=True, exist_ok=True)
        (job_dir(tmp_path, smoke) / name).write_bytes(data)

    listing = await _list(client, run_id)
    assert [item["id"] for item in listing["items"]] == [f"{second}.log", f"{second}.metrics"]
    tail = await _download(client, f"{second}.log")
    assert tail.text == EXPERIMENT_OUTPUT["logs_tail"] + "\n"
    # The first attempt's output, by its id, still has its own job's files.
    assert (await _download(client, f"{first}.log")).text == JOB_LOG
    assert (await _download(client, f"{first}.checkpoint")).content == CHECKPOINT


async def test_a_jobs_files_are_for_those_who_can_open_the_run(
    client: httpx.AsyncClient, db: Factory, tmp_path: Path
) -> None:
    run_id, output_id, root = await _trained(
        client, db, tmp_path, files=_job_folder(OUTPUTS), provenance=_provenance(OUTPUTS)
    )
    for item in ("log", "metrics", "checkpoint"):
        artifact_id = f"{output_id}.{item}"
        hidden = await _download(client, artifact_id, user="carol")
        assert (hidden.status_code, hidden.json()) == (404, {"detail": "artifact.not_found"})
        assert (await client.get(f"/api/v1/artifacts/{artifact_id}")).status_code == 401
        assert (await _download(client, artifact_id, user="vera")).status_code == 200
    hidden_list = await client.get(f"/api/v1/runs/{run_id}/artifacts", headers=as_user("carol"))
    assert hidden_list.status_code == 404
    # A file gone from the job's folder is no longer served.
    (root / "out" / CHECKPOINT_FILE).unlink()
    assert (await _download(client, f"{output_id}.checkpoint")).status_code == 404
    assert [item["kind"] for item in (await _list(client, run_id))["items"]] == [
        "experiment_log",
        "metrics",
    ]


def test_a_jobs_metrics_become_csv_rows_of_its_step_and_epoch_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """metrics.jsonl comes out of the job's container: only its step and epoch records count,
    their numbers become cells and anything else is left out."""
    job_id = uuid.uuid4()
    out = job_dir(tmp_path, job_id) / "out"
    out.mkdir(parents=True)
    long_name = "x" * 65
    lines = [
        '{"kind": "train_step", "epoch": 0, "step": 0, "loss": 1.5, "lr": 0.001, "ts": "t"}',
        "not json",
        "[1, 2]",
        '{"kind": ["train_step"], "epoch": 0}',
        '{"kind": "summary", "epoch": 0, "loss": 9}',
        '{"kind": "epoch", "epoch": 0, "train": {"loss": 0.9, "note": "x", "flag": true, '
        '"deep": {"a": 1}}, "val": {"loss": NaN, "rmse": Infinity}, "=cmd": 2, '
        f'"{long_name}": 1}}',
        '{"kind": "train_step", "epoch": -1, "step": "3", "loss": "=HYPERLINK(1)"}',
        '{"kind": "train_step", "epoch": 0, "step": 4, "lo',  # cut short
    ]
    (out / METRICS_FILE).write_text("\n".join(lines))
    files = job_files(tmp_path, job_id, None)
    assert (files.log, files.checkpoint) == (None, None)
    assert files.metrics_csv is not None
    assert list(csv.reader(io.StringIO(files.metrics_csv.decode()))) == [
        ["kind", "epoch", "step", "loss", "lr", "train_loss", "val_loss", "val_rmse", "'=cmd"],
        ["train_step", "0", "0", "1.5", "0.001", "", "", "", ""],
        ["epoch", "0", "", "", "", "0.9", "", "", "2"],
        ["train_step", "", "", "", "", "", "", "", ""],
    ]

    # However many metrics and records it holds, the CSV stays bounded.
    wide = {"kind": "epoch", "epoch": 0, **{f"m{n}": n for n in range(MAX_METRIC_COLUMNS + 5)}}
    (out / METRICS_FILE).write_text(json.dumps(wide) + "\n")
    wide_csv = job_files(tmp_path, job_id, None).metrics_csv
    assert wide_csv is not None
    assert len(next(csv.reader(io.StringIO(wide_csv.decode())))) == 3 + MAX_METRIC_COLUMNS
    monkeypatch.setattr(artifacts_module, "MAX_METRIC_ROWS", 2)
    (out / METRICS_FILE).write_bytes(METRICS_JSONL)
    long_csv = job_files(tmp_path, job_id, None).metrics_csv
    assert long_csv is not None
    assert [row[0] for row in csv.reader(io.StringIO(long_csv.decode()))] == [
        "kind",
        "train_step",
        "train_step",
    ]

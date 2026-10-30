import copy
import csv
import hashlib
import io
import uuid
import zipfile
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.enums import StageStatus
from agentic_core.schemas import validate_stage_output
from api_testkit import (
    CODING_OUTPUT,
    EXPERIMENT_OUTPUT,
    WRITING_OUTPUT,
    add_output,
    add_stage_output,
    add_stage_run,
    as_user,
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
    other = await client.post("/api/v1/projects", json={"name": "Other"}, headers=as_user("carol"))
    carols_run = await start_run(client, other.json()["id"], user="carol")
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
        f"{outputs['experiment']}.code.0",
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

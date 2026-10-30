"""The executor running jobs against a fake Docker API and GPU: no Docker or GPU needed."""

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import pytest

from agentic_core.contracts import events_channel
from agentic_core.enums import GpuJobKind, GpuJobStatus
from agentic_core.gpu_jobs import (
    CHECKPOINT_FILE,
    CODE_MOUNT,
    JOB_BAD_INPUT,
    JOB_LOST,
    JOB_NO_RESULT,
    JOB_OOM_KILLED,
    JOB_START_FAILED,
    OUTPUT_FILES,
    job_dir,
)
from agentic_db.gpu_jobs import request_cancel
from agentic_db.models import Dataset
from agentic_executor import executor as executor_module
from agentic_executor.archive import extract_outputs
from agentic_executor.executor import manifest_checksum
from agentic_executor.ports import DockerError
from agentic_executor.template import JobMounts, container_name, container_spec
from executor_testkit import (
    GPU_NAME,
    IMAGE,
    MODEL_SOURCE,
    SIGKILL_EXIT,
    SIGTERM_EXIT,
    Factory,
    FakeDocker,
    FakeGpu,
    FakeValkey,
    Script,
    create_job,
    epoch_events,
    epoch_line,
    epoch_record,
    eventually,
    executor_settings,
    executor_status,
    get_job,
    gpu_sample,
    image_id,
    make_executor,
    results_failed,
    results_ok,
    running,
    speed_up,
    step_line,
    wait_status,
)


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    speed_up(monkeypatch)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


async def test_a_smoke_job_runs_end_to_end(db: Factory, tmp_path: Path) -> None:
    settings = executor_settings(tmp_path)
    docker, valkey = FakeDocker(), FakeValkey()
    job = await create_job(db)
    outputs = {
        "results.json": results_ok(),
        "metrics.jsonl": b'{"kind": "epoch", "epoch": 0}\n',
        "checkpoints/best.pt": b"weights",
        "checkpoints/last.pt": b"not copied",
    }
    steps: list[Any] = [
        "loading the model",
        step_line(0, 0, 0.9),
        0.02,
        "  " + epoch_line(7),  # the training's own look-alike, indented by harness.job
        epoch_line(0),
        "epoch 0 done",
    ]
    docker.script(job.id, Script(steps=steps, outputs=outputs))
    executor = make_executor(db, settings, docker, gpu=FakeGpu(None), valkey=valkey)

    assert await executor.run_next() == job.id

    root = job_dir(settings.data_dir, job.id)
    mounts = JobMounts(
        dataset_name="nyu2",
        dataset_path=tmp_path / "datasets" / "nyu2",
        code_dir=root / "code",
        config_file=root / "config.json",
    )
    expected_spec = container_spec(
        image=IMAGE,
        job_id=str(job.id),
        run_id=str(job.run_id),
        kind=GpuJobKind.SMOKE,
        mounts=mounts,
        limits=settings.limits(),
    )
    assert docker.created == [(container_name(job.id), expected_spec)]
    # The outputs are copied while the container runs, then it is killed, then removed.
    assert docker.ops("download", "kill", "stop", "remove") == ["download", "kill", "remove"]
    assert [state for _, state in docker.downloads] == ["running"]
    assert docker.containers == {}

    finished = await get_job(db, job.id)
    assert finished.status is GpuJobStatus.SUCCEEDED
    assert (finished.error_code, finished.error) == (None, None)
    assert finished.exit_code == 0
    assert finished.gpu_seconds is not None and finished.gpu_seconds > 0
    assert finished.result == json.loads(results_ok())
    assert finished.finished_at is not None and finished.lease_until is None
    assert finished.progress is not None and finished.progress["step"] == 0
    assert finished.log_tail is not None
    assert finished.log_tail.endswith('epoch 0 done\nARP-DONE {"exit_code": 0}')

    record = epoch_record(0)
    assert await epoch_events(db, job.run_id) == [
        {
            "stage": "coding",
            "job_id": str(job.id),
            "kind": "smoke",
            "ordinal": 1,
            "epoch": 0,
            "train": record["train"],
            "val": record["val"],
        }
    ]
    assert finished.epochs_reported == 1
    assert valkey.published == [events_channel(job.run_id)]

    out = root / "out"
    assert (out / "results.json").read_bytes() == results_ok()
    assert (out / "checkpoints" / "best.pt").read_bytes() == b"weights"
    assert not (out / "checkpoints" / "last.pt").exists()
    assert not (root / "out.tar").exists()
    log = (root / "log.txt").read_text().splitlines()
    assert log[0] == "loading the model" and log[-1] == 'ARP-DONE {"exit_code": 0}'

    config_text = (root / "config.json").read_text()
    config = json.loads(config_text)
    assert config_text == json.dumps(config, indent=2, sort_keys=True)
    assert config["model"]["code_dir"] == CODE_MOUNT
    assert config["data"]["root"] == "/data/nyu2"
    assert config["training"] == {"epochs": 2, "learning_rate": 0.001}
    assert (root / "code" / "model.py").read_text() == MODEL_SOURCE
    assert [p.name for p in (root / "code").iterdir()] == ["model.py"]
    assert {_mode(root), _mode(root / "code")} == {0o755}
    assert {_mode(root / "code" / "model.py"), _mode(root / "config.json")} == {0o644}

    assert finished.provenance == {
        "image": IMAGE,
        "image_id": image_id(IMAGE),
        "code_sha256": {"model.py": _sha256(MODEL_SOURCE.encode())},
        "config_sha256": _sha256(config_text.encode()),
        "dataset": {"name": "nyu2", "version": "2026.05", "checksum": None},
        "seed": 7,
        "gpu": GPU_NAME,
        "harness": json.loads(results_ok())["provenance"],
        "outputs": {
            "results.json": len(results_ok()),
            "metrics.jsonl": len(outputs["metrics.jsonl"]),
            "checkpoints/best.pt": 7,
        },
    }


async def test_a_failure_the_harness_reports_keeps_its_code(db: Factory, tmp_path: Path) -> None:
    docker = FakeDocker()
    job = await create_job(db)
    error = "ShapeMismatch: Model output (2, 1, 240, 320) does not match target (2, 1, 480, 640)"
    failed = results_failed("code.shape_mismatch", error)
    docker.script(job.id, Script(steps=["loading"], exit_code=1, outputs={"results.json": failed}))
    await make_executor(db, executor_settings(tmp_path), docker).run_next()

    finished = await get_job(db, job.id)
    assert finished.status is GpuJobStatus.FAILED
    assert (finished.error_code, finished.error) == ("code.shape_mismatch", error)
    assert finished.exit_code == 1
    assert finished.result == json.loads(failed)
    assert finished.provenance is not None
    assert finished.provenance["gpu"] == GPU_NAME  # the latest nvidia-smi reading's
    assert docker.containers == {}


async def test_refused_code_never_gets_a_container(db: Factory, tmp_path: Path) -> None:
    docker = FakeDocker()
    job = await create_job(db, code={"model.py": "import os\n"})
    await make_executor(db, executor_settings(tmp_path), docker).run_next()

    finished = await get_job(db, job.id)
    error = "model.py refused by the allowlist: check.import line 1: Import of 'os' is not allowed"
    assert finished.status is GpuJobStatus.FAILED
    assert (finished.error_code, finished.error) == ("code.refused", error)
    assert finished.result == {
        "status": "failed",
        "error_code": "code.refused",
        "error": error,
        "findings": [
            {"line": 1, "code": "check.import", "message": "Import of 'os' is not allowed"}
        ],
    }
    assert docker.calls == []
    assert finished.finished_at is not None


@pytest.mark.parametrize(
    "code",
    [
        {"model.py": MODEL_SOURCE, "train.py": "print(1)\n"},
        {"loss.py": "class Loss: ...\n"},
        {"model.py": 42},
        {"model.py": "x = 1\n" * 4000},
    ],
    ids=["unknown file", "no model.py", "not text", "too large"],
)
async def test_code_outside_the_contract_is_bad_input(
    db: Factory, tmp_path: Path, code: dict[str, Any]
) -> None:
    docker = FakeDocker()
    job = await create_job(db, code=code)
    await make_executor(db, executor_settings(tmp_path), docker).run_next()
    finished = await get_job(db, job.id)
    assert (finished.status, finished.error_code) == (GpuJobStatus.FAILED, JOB_BAD_INPUT)
    assert docker.calls == []


@pytest.mark.parametrize("folder", ["missing", None], ids=["no such folder", "not set"])
async def test_a_dataset_without_its_folder_is_bad_input(
    db: Factory, tmp_path: Path, folder: str | None
) -> None:
    docker = FakeDocker()
    settings = executor_settings(
        tmp_path, dataset_nyu2=tmp_path / folder if folder is not None else None
    )
    job = await create_job(db)
    await make_executor(db, settings, docker).run_next()

    finished = await get_job(db, job.id)
    assert (finished.status, finished.error_code) == (GpuJobStatus.FAILED, JOB_BAD_INPUT)
    assert finished.error is not None and "ARP_DATASET_NYU2" in finished.error
    assert docker.calls == []


async def test_a_missing_image_fails_the_start(db: Factory, tmp_path: Path) -> None:
    docker = FakeDocker()
    settings = executor_settings(tmp_path, sandbox_image="arp-sandbox-pytorch:missing")
    job = await create_job(db)
    await make_executor(db, settings, docker).run_next()

    finished = await get_job(db, job.id)
    assert (finished.status, finished.error_code) == (GpuJobStatus.FAILED, JOB_START_FAILED)
    assert finished.error is not None and "arp-sandbox-pytorch:missing" in finished.error
    assert docker.created == [] and docker.containers == {}


@pytest.mark.parametrize("op", ["create", "start"])
async def test_a_job_waits_in_the_queue_while_docker_is_unreachable(
    db: Factory, tmp_path: Path, op: str
) -> None:
    """The socket proxy restarting is no fault of the job's: it is not failed for it."""
    docker = FakeDocker()
    docker.failures[op] = [DockerError(0, "cannot reach the Docker socket proxy")]
    job = await create_job(db)
    docker.script(job.id, Script(outputs={"results.json": results_ok()}))
    executor = make_executor(db, executor_settings(tmp_path), docker)

    assert await executor.run_next() == job.id
    requeued = await get_job(db, job.id)
    assert requeued.status is GpuJobStatus.QUEUED and requeued.container_id is None
    assert await executor.run_next() == job.id
    assert (await get_job(db, job.id)).status is GpuJobStatus.SUCCEEDED
    assert docker.containers == {}


async def test_the_outputs_are_copied_again_after_docker_was_unreachable(
    db: Factory, tmp_path: Path
) -> None:
    docker = FakeDocker()
    docker.failures["download"] = [DockerError(0, "cannot reach the Docker socket proxy")]
    job = await create_job(db)
    docker.script(job.id, Script(outputs={"results.json": results_ok()}))
    await make_executor(db, executor_settings(tmp_path), docker).run_next()

    assert (await get_job(db, job.id)).status is GpuJobStatus.SUCCEEDED
    assert docker.ops("download", "kill") == ["download", "download", "kill"]


async def test_a_leftover_container_of_the_same_name_is_replaced(
    db: Factory, tmp_path: Path
) -> None:
    docker = FakeDocker()
    job = await create_job(db)
    leftover = await docker.run_container(container_name(job.id), {}, start=False)
    docker.script(job.id, Script(outputs={"results.json": results_ok()}))
    await make_executor(db, executor_settings(tmp_path), docker).run_next()

    assert (await get_job(db, job.id)).status is GpuJobStatus.SUCCEEDED
    assert leftover in docker.removed
    assert docker.ops("create") == ["create", "create"] and len(docker.created) == 1


async def test_a_cancel_before_the_start_removes_the_new_container(
    db: Factory, tmp_path: Path
) -> None:
    docker = FakeDocker()
    job = await create_job(db)

    async def cancel(name: str) -> None:
        async with db() as session:
            assert await request_cancel(session, job.id) is GpuJobStatus.STARTING
            await session.commit()

    docker.on_create = cancel
    await make_executor(db, executor_settings(tmp_path), docker).run_next()

    assert (await get_job(db, job.id)).status is GpuJobStatus.CANCELLED
    assert docker.ops("start") == [] and docker.containers == {}


async def test_oom_without_results_is_oom_killed(db: Factory, tmp_path: Path) -> None:
    """The memory limit killed the training process; harness.job reported it and held."""
    docker = FakeDocker()
    job = await create_job(db, kind=GpuJobKind.TRAIN)
    script = Script(
        steps=["epoch 0 step 0"], exit_code=-9, oom_killed=True, outputs={"metrics.jsonl": b"{}\n"}
    )
    docker.script(job.id, script)
    await make_executor(db, executor_settings(tmp_path), docker).run_next()

    finished = await get_job(db, job.id)
    assert (finished.status, finished.error_code) == (GpuJobStatus.FAILED, JOB_OOM_KILLED)
    assert finished.exit_code == -9
    assert finished.result is None
    assert finished.provenance is not None
    assert finished.provenance["outputs"] == {"metrics.jsonl": 3}


async def test_training_that_ends_without_results_has_no_result(
    db: Factory, tmp_path: Path
) -> None:
    docker = FakeDocker()
    job = await create_job(db, kind=GpuJobKind.TRAIN)
    docker.script(job.id, Script(steps=["Segmentation fault"], exit_code=-11))
    await make_executor(db, executor_settings(tmp_path), docker).run_next()

    finished = await get_job(db, job.id)
    assert (finished.status, finished.error_code) == (GpuJobStatus.FAILED, JOB_NO_RESULT)
    assert finished.error is not None and "exit code -11" in finished.error


@pytest.mark.parametrize(
    ("oom", "error_code", "exit_code"),
    [(True, JOB_OOM_KILLED, SIGKILL_EXIT), (False, JOB_LOST, 1)],
    ids=["oom killed", "lost"],
)
async def test_a_container_that_stops_before_arp_done_loses_its_outputs(
    db: Factory, tmp_path: Path, oom: bool, error_code: str, exit_code: int
) -> None:
    docker = FakeDocker()
    job = await create_job(db, kind=GpuJobKind.TRAIN)
    script = Script(
        steps=["epoch 0 step 0", 0.02],
        exit_code=None,
        hold=False,
        end_exit_code=exit_code,
        oom_killed=oom,
        outputs={"results.json": results_ok()},
    )
    docker.script(job.id, script)
    await make_executor(db, executor_settings(tmp_path), docker).run_next()

    finished = await get_job(db, job.id)
    assert (finished.status, finished.error_code) == (GpuJobStatus.FAILED, error_code)
    assert finished.exit_code == exit_code
    assert finished.error is not None and f"exit code {exit_code}" in finished.error
    assert docker.downloads == []  # the tmpfs output went with the container
    assert docker.containers == {}


async def test_a_cancel_stops_a_running_job_within_the_check_interval(
    db: Factory, tmp_path: Path
) -> None:
    docker = FakeDocker()
    settings = executor_settings(tmp_path)
    job = await create_job(db, kind=GpuJobKind.TRAIN)
    docker.script(job.id, Script(steps=[step_line(0, 0, 1.2)], exit_code=None))  # trains on
    task = asyncio.create_task(make_executor(db, settings, docker).run_next())
    await wait_status(db, job.id, GpuJobStatus.RUNNING)

    async with db() as session:
        assert await request_cancel(session, job.id) is GpuJobStatus.RUNNING
        await session.commit()
    requested = time.monotonic()
    assert await asyncio.wait_for(task, 5) == job.id

    finished = await get_job(db, job.id)
    assert finished.status is GpuJobStatus.CANCELLED
    assert finished.error_code is None and finished.exit_code == SIGTERM_EXIT
    [(container_id, grace, stopped_at)] = docker.stops
    assert container_id == finished.container_id
    assert grace == settings.stop_grace_seconds
    assert stopped_at - requested < settings.cancel_check_seconds + 0.5
    assert docker.downloads == [] and docker.containers == {}


async def test_a_job_past_its_time_limit_keeps_its_partial_outputs(
    db: Factory, tmp_path: Path
) -> None:
    docker = FakeDocker()
    settings = executor_settings(tmp_path)
    job = await create_job(db, kind=GpuJobKind.TRAIN, timeout_seconds=1)
    outputs = {"metrics.jsonl": b'{"kind": "epoch"}\n', "checkpoints/best.pt": b"weights"}
    steps: list[Any] = [epoch_line(0)]
    docker.script(job.id, Script(steps=steps, exit_code=None, outputs=outputs))
    started = time.monotonic()
    await make_executor(db, settings, docker).run_next()

    assert 1 <= time.monotonic() - started < 3
    finished = await get_job(db, job.id)
    assert finished.status is GpuJobStatus.TIMEOUT
    assert finished.error is not None and "1 s" in finished.error
    assert finished.result is None
    # Copied while it still ran, then stopped with the grace period.
    assert docker.ops("download", "stop", "kill") == ["download", "stop"]
    assert [grace for _, grace, _ in docker.stops] == [settings.stop_grace_seconds]
    out = job_dir(settings.data_dir, job.id) / "out"
    assert (out / "checkpoints" / "best.pt").read_bytes() == b"weights"
    assert finished.provenance is not None
    assert finished.provenance["outputs"] == {"metrics.jsonl": 18, "checkpoints/best.pt": 7}
    assert len(await epoch_events(db, job.run_id)) == 1


async def test_an_output_over_its_cap_is_noted_in_the_error(
    db: Factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    caps = {**OUTPUT_FILES, CHECKPOINT_FILE: 10}  # 200 MB in production
    monkeypatch.setattr(
        executor_module, "extract_outputs", lambda tar, out: extract_outputs(tar, out, caps)
    )
    docker = FakeDocker()
    job = await create_job(db)
    docker.script(
        job.id, Script(outputs={"results.json": results_ok(), CHECKPOINT_FILE: b"w" * 11})
    )
    await make_executor(db, executor_settings(tmp_path), docker).run_next()

    finished = await get_job(db, job.id)
    assert finished.status is GpuJobStatus.SUCCEEDED
    assert finished.error == "Not copied: checkpoints/best.pt (11 bytes, over the 10-byte cap)"
    assert finished.provenance is not None
    assert finished.provenance["outputs_skipped"] == {
        CHECKPOINT_FILE: "11 bytes, over the 10-byte cap"
    }


async def test_the_vram_preflight_waits_until_memory_frees_up(db: Factory, tmp_path: Path) -> None:
    docker = FakeDocker()
    gpu = FakeGpu(gpu_sample(free_mb=1000))
    settings = executor_settings(tmp_path, min_free_vram_mb=2048)
    job = await create_job(db)
    docker.script(job.id, Script(outputs={"results.json": results_ok()}))
    executor = make_executor(db, settings, docker, gpu=gpu)

    async def waiting() -> bool:
        status = await executor_status(db)
        return status is not None and status["waiting_for_vram"] is not None

    async with running(executor):
        await eventually(waiting, what="the heartbeat to say it waits for VRAM")
        status = await executor_status(db)
        assert status is not None
        assert status["waiting_for_vram"] == {"free_mb": 1000, "needed_mb": 2048}
        assert status["gpu"]["name"] == GPU_NAME and status["gpu"]["memory_used_mb"] == 5144
        assert status["job_id"] is None
        assert (await get_job(db, job.id)).status is GpuJobStatus.QUEUED
        assert docker.ops("create") == []

        gpu.reading = gpu_sample(free_mb=4000)
        await wait_status(db, job.id, GpuJobStatus.SUCCEEDED)


async def test_the_heartbeat_names_the_job_on_the_gpu(db: Factory, tmp_path: Path) -> None:
    docker = FakeDocker()
    job = await create_job(db, kind=GpuJobKind.TRAIN)
    gate = asyncio.Event()
    docker.script(job.id, Script(steps=[gate], outputs={"results.json": results_ok()}))
    executor = make_executor(db, executor_settings(tmp_path), docker)

    async def on_the_gpu() -> bool:
        status = await executor_status(db)
        return status is not None and status["job_id"] == str(job.id)

    async with running(executor):
        await eventually(on_the_gpu, what="the heartbeat to name the job")
        status = await executor_status(db)
        assert status is not None and status["alive_at"] and status["waiting_for_vram"] is None
        gate.set()
        await wait_status(db, job.id, GpuJobStatus.SUCCEEDED)


async def test_progress_is_written_while_the_job_runs(db: Factory, tmp_path: Path) -> None:
    docker = FakeDocker()
    job = await create_job(db, kind=GpuJobKind.TRAIN)
    gate = asyncio.Event()
    steps: list[Any] = [step_line(0, 0, 1.5), step_line(0, 20, 1.1), gate, step_line(0, 40, 0.9)]
    docker.script(job.id, Script(steps=steps, outputs={"results.json": results_ok()}))
    task = asyncio.create_task(make_executor(db, executor_settings(tmp_path), docker).run_next())

    async def progressed() -> bool:
        progress = (await get_job(db, job.id)).progress
        return progress is not None and progress["step"] == 0

    await eventually(progressed, what="the first progress write")
    gate.set()
    await asyncio.wait_for(task, 5)
    finished = await get_job(db, job.id)
    assert finished.progress is not None and finished.progress["step"] == 40  # the latest


async def test_the_executor_records_each_dataset_checksum(db: Factory, tmp_path: Path) -> None:
    settings = executor_settings(tmp_path)
    assert settings.dataset_nyu2 is not None
    (settings.dataset_nyu2 / "train.h5").write_bytes(b"12345")
    async with db() as session:
        session.add(Dataset(name="nyu2", version="2026.05", title="NYU Depth V2"))
        await session.commit()

    async def recorded() -> bool:
        async with db() as session:
            dataset = await session.get(Dataset, "nyu2")
        return dataset is not None and dataset.checksum is not None

    async with running(make_executor(db, settings, FakeDocker())):
        await eventually(recorded, what="the dataset checksum")
    async with db() as session:
        dataset = await session.get(Dataset, "nyu2")
    assert dataset is not None and dataset.checksum_at is not None
    assert dataset.checksum == manifest_checksum(settings.dataset_nyu2)


def test_the_manifest_checksum_covers_regular_files_by_path_and_size(tmp_path: Path) -> None:
    root = tmp_path / "nyu2"
    (root / "train").mkdir(parents=True)
    (root / "train" / "a.h5").write_bytes(b"12345")
    (root / "val.h5").write_bytes(b"1")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "b.h5").write_bytes(b"123")
    (root / "link.h5").symlink_to(root / "val.h5")
    (root / "linked").symlink_to(outside, target_is_directory=True)
    expected = _sha256(b"train/a.h5\x005\x00val.h5\x001\x00")
    assert manifest_checksum(root) == expected
    (root / "val.h5").write_bytes(b"12")
    assert manifest_checksum(root) != expected


async def test_queued_jobs_run_one_after_another(db: Factory, tmp_path: Path) -> None:
    docker = FakeDocker()
    jobs = [await create_job(db) for _ in range(3)]
    for job in jobs:
        docker.script(job.id, Script(outputs={"results.json": results_ok()}))
    executor = make_executor(db, executor_settings(tmp_path), docker)
    assert [await executor.run_next() for _ in jobs] == [job.id for job in jobs]
    assert await executor.run_next() is None
    assert len(docker.created) == 3 and docker.containers == {}

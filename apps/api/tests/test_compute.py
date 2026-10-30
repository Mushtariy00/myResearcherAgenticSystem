"""The datasets page and the GPU queue: the datasets and gpu_jobs tables and the executor's
heartbeat, as the API reads them."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_api.gpu_queue import (
    MIN_REMAINING,
    Plan,
    QueueEntry,
    Step,
    executor_alive,
    job_plan,
    latest_step,
    queue_snapshot,
)
from agentic_api.schemas import GpuJobOut
from agentic_core.enums import GpuJobKind, GpuJobStatus, StageStatus
from agentic_db.lab_settings import EXECUTOR_STATUS_KEY
from agentic_db.models import Dataset, Setting
from api_testkit import (
    NYU2_DATASET,
    SMOKE_CONFIG,
    add_dataset,
    add_gpu_job,
    add_stage_run,
    as_user,
    create_project,
    harness_config,
    start_run,
    team_project,
)

Factory = async_sessionmaker[AsyncSession]
NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
REGISTERED = datetime(2026, 10, 30, 21, 23, 53, tzinfo=UTC)
TRAIN_PLAN = Plan(epochs=3, steps_per_epoch=1000)
SMOKE_PLAN = Plan(epochs=1, steps_per_epoch=2)
SMOKE, TRAIN = GpuJobKind.SMOKE, GpuJobKind.TRAIN
# An nvidia-smi sample as the executor's heartbeat holds it (agentic_executor.ports.GpuSample).
GPU_SAMPLE: dict[str, Any] = {
    "index": 0,
    "name": "NVIDIA GeForce GTX 1060 6GB",
    "memory_total_mb": 6144,
    "memory_used_mb": 4402,
    "utilization_percent": 97,
    "temperature_c": None,  # a reading this GPU or driver does not give
    "power_draw_w": 101.5,
    "power_limit_w": 120.0,
    "fan_percent": None,
    "sampled_at": "2026-10-31T11:59:58+00:00",
}
JOB_FIELDS = {
    "id",
    "kind",
    "status",
    "run_id",
    "topic",
    "project_name",
    "owner_name",
    "is_mine",
    "dataset",
    "progress",
    "epoch",
    "total_epochs",
    "gpu_memory_mb",
    "submitted_at",
    "started_at",
    "estimated_start_at",
    "estimated_finish_at",
    "eta_seconds",
    "estimated",
    "demo",
}


# --- Datasets -------------------------------------------------------------------------------


async def test_datasets_are_the_enabled_registered_ones(
    client: httpx.AsyncClient, db: Factory
) -> None:
    async with db() as session:
        await session.execute(delete(Dataset))  # the migration's nyu2, should this test run first
        await session.commit()
    await add_dataset(db, created_at=REGISTERED)
    await add_dataset(db, name="kitti", title="KITTI depth", enabled=False)
    await add_dataset(
        db,
        name="lab_scans",
        version="1.0",
        title="Lab Indoor Scans",
        checksum="ab" * 32,
        created_at=REGISTERED,
        contract={"inputs": "RGB uint8, 3x480x848", "units": 7},
        # Written by hand: a value of the wrong type reads as missing.
        details={
            "tasks": ["monocular_depth", 3],
            "width": "848",
            "splits": {"test": 322, "extra": 5, "train": 2571, "val": True},
            "homepage": "",
        },
    )

    response = await client.get("/api/v1/datasets", headers=as_user("vera"))
    assert response.status_code == 200, response.text
    listing = response.json()
    assert listing["demo"] is False
    scans, nyu = listing["items"]  # by name; the disabled one is not listed
    details = NYU2_DATASET["details"]
    assert nyu == {
        "id": "nyu2",
        "name": "NYU Depth V2",
        "version": "2026.05",
        "tasks": ["monocular_depth"],
        "modality": "RGB-D (Microsoft Kinect)",
        "scenes": "indoor",
        "description": details["description"],
        "width": 640,
        "height": 480,
        "samples": 50_688 + 654,
        # In reading order, whatever order Postgres keeps the JSON's keys in.
        "splits": [
            {"name": "train", "samples": 50_688},
            {"name": "val", "samples": 654},
            {"name": "test", "samples": 0},
        ],
        "size_bytes": None,  # not measured yet
        "license": details["license"],
        "homepage": details["homepage"],
        "mount_path": "/data/nyu2",  # where the executor mounts it
        "checksum_sha256": None,  # until the executor has computed it
        "registered_at": "2026-10-30T21:23:53Z",
        "contract": NYU2_DATASET["contract"],
        "demo": False,
    }
    assert scans == {
        "id": "lab_scans",
        "name": "Lab Indoor Scans",
        "version": "1.0",
        "tasks": ["monocular_depth"],
        "modality": "",
        "scenes": "",
        "description": "",
        "width": 0,
        "height": 0,
        "samples": 2571 + 322 + 5,
        "splits": [
            {"name": "train", "samples": 2571},
            {"name": "test", "samples": 322},
            {"name": "extra", "samples": 5},
        ],
        "size_bytes": None,
        "license": "",
        "homepage": None,
        "mount_path": "/data/lab_scans",
        "checksum_sha256": "ab" * 32,
        "registered_at": "2026-10-30T21:23:53Z",
        "contract": {
            "inputs": "RGB uint8, 3x480x848",
            "targets": "",
            "units": None,
            "valid_range": None,
            "missing_values": None,
            "evaluation": None,
        },
        "demo": False,
    }
    again = await client.get("/api/v1/datasets", headers=as_user("bob"))
    assert again.json() == listing
    assert (await client.get("/api/v1/datasets")).status_code == 401


# --- The GPU queue, from the database ---------------------------------------------------------


async def _attempt(
    client: httpx.AsyncClient, db: Factory, project_id: str, user: str, stage: str = "experiment"
) -> tuple[str, str]:
    """A run of ``user``'s with an attempt of ``stage`` running: (run id, stage run id)."""
    run_id = await start_run(client, project_id, user=user)
    return run_id, await add_stage_run(db, run_id, stage, StageStatus.RUNNING)


async def _queue(client: httpx.AsyncClient, user: str, role: str = "user") -> dict[str, Any]:
    response = await client.get("/api/v1/gpu/queue", headers=as_user(user, role))
    assert response.status_code == 200, response.text
    return response.json()


def _at(value: str) -> datetime:
    return datetime.fromisoformat(value)


async def _heartbeat(db: Factory, seconds_ago: float, gpu: object = GPU_SAMPLE) -> None:
    """The executor's heartbeat, written ``seconds_ago``."""
    value = {
        "alive_at": (datetime.now(UTC) - timedelta(seconds=seconds_ago)).isoformat(),
        "gpu": gpu,
        "job_id": None,
        "waiting_for_vram": None,
    }
    async with db() as session:
        await session.merge(Setting(key=EXECUTOR_STATUS_KEY, value=value, updated_by="executor"))
        await session.commit()


async def test_the_queue_is_the_executors_jobs_in_the_order_it_runs_them(
    client: httpx.AsyncClient, db: Factory
) -> None:
    depth = await team_project(client)
    other = await create_project(client, "Other", owner="carol")
    now = datetime.now(UTC)
    bobs_run, bobs_attempt = await _attempt(client, db, depth, "bob")
    training = await add_gpu_job(
        db,
        bobs_run,
        bobs_attempt,
        status=GpuJobStatus.RUNNING,
        created_at=now - timedelta(minutes=12),
        started_at=now - timedelta(minutes=10),
        # Epoch 1 (from 0), step 499: half of its 3 epochs of 1000 steps.
        progress={"kind": "train_step", "epoch": 1, "step": 499, "loss": 0.42, "ts": "t"},
    )
    carols_run, carols_attempt = await _attempt(client, db, other, "carol", "coding")
    carols_smoke = await add_gpu_job(
        db,
        carols_run,
        carols_attempt,
        kind=SMOKE,
        user_id="carol",
        created_at=now - timedelta(minutes=5),
    )
    alices_run, alices_attempt = await _attempt(client, db, depth, "alice", "coding")
    alices_smoke = await add_gpu_job(
        db,
        alices_run,
        alices_attempt,
        kind=SMOKE,
        user_id="alice",
        created_at=now - timedelta(minutes=2),
    )
    # Older than both smoke tests and still behind them: a coding stage waits on its smoke test.
    next_run, next_attempt = await _attempt(client, db, depth, "bob")
    bobs_next = await add_gpu_job(
        db, next_run, next_attempt, created_at=now - timedelta(minutes=20)
    )
    # Not on the queue: jobs that ended, and a queued one the executor never claims (cancelled).
    ended_run, ended_attempt = await _attempt(client, db, depth, "bob", "coding")
    ended = (
        GpuJobStatus.SUCCEEDED,
        GpuJobStatus.FAILED,
        GpuJobStatus.TIMEOUT,
        GpuJobStatus.CANCELLED,
    )
    for ordinal, status in enumerate(ended, start=1):
        await add_gpu_job(db, ended_run, ended_attempt, kind=SMOKE, status=status, ordinal=ordinal)
    await add_gpu_job(db, ended_run, ended_attempt, kind=SMOKE, ordinal=5, cancel_requested=True)

    queue = await _queue(client, "bob")
    assert (queue["demo"], queue["concurrency"], queue["per_user_limit"]) == (False, 1, 2)
    assert (queue["gpu"], queue["executor_alive"]) == (None, False)  # no heartbeat yet
    [running] = queue["running"]
    assert set(running) == JOB_FIELDS
    assert (running["id"], running["kind"], running["status"], running["run_id"]) == (
        str(training),
        "train",
        "running",
        bobs_run,
    )
    assert (running["topic"], running["project_name"], running["owner_name"]) == (
        "Monocular depth",
        "Depth",
        "Bob",
    )
    assert (running["is_mine"], running["dataset"], running["demo"]) == (True, "nyu2", False)
    # Half its steps in the 10 minutes (and the moments of this test) it has run: as long to go.
    assert (running["progress"], running["epoch"], running["total_epochs"]) == (0.5, 2, 3)
    assert (running["estimated"], running["gpu_memory_mb"]) == (False, None)
    assert _at(running["submitted_at"]) == now - timedelta(minutes=12)
    started = _at(running["started_at"])
    assert started == _at(running["estimated_start_at"]) == now - timedelta(minutes=10)
    total = (_at(running["estimated_finish_at"]) - started).total_seconds()
    assert abs(running["eta_seconds"] - total / 2) <= 1
    assert 600 <= running["eta_seconds"] <= 660

    assert [job["id"] for job in queue["queued"]] == [
        str(carols_smoke),
        str(alices_smoke),
        str(bobs_next),
    ]
    hidden, alices, mine = queue["queued"]
    assert (hidden["run_id"], hidden["topic"], hidden["project_name"]) == (None, None, None)
    assert (hidden["owner_name"], hidden["is_mine"]) == ("Carol", False)  # not bob's to open
    assert (alices["run_id"], alices["topic"], alices["owner_name"]) == (
        alices_run,
        "Monocular depth",
        "Alice",
    )
    assert (mine["kind"], mine["is_mine"], mine["total_epochs"]) == ("train", True, 3)
    for job in queue["queued"]:
        assert (job["status"], job["progress"], job["epoch"], job["started_at"]) == (
            "queued",
            0.0,
            None,
            None,
        )
        assert job["estimated"] is True
    assert _at(hidden["submitted_at"]) == now - timedelta(minutes=5)
    # Each starts when the one before it should finish: a smoke test takes about 2 minutes, and
    # 3 epochs of 1000 steps at 3 steps a second 1000 seconds.
    before = running
    for job, seconds in zip(queue["queued"], (120, 120, 1000), strict=True):
        start, finish = _at(job["estimated_start_at"]), _at(job["estimated_finish_at"])
        assert start == _at(before["estimated_finish_at"])
        assert finish - start == timedelta(seconds=seconds)
        before = job
    assert (queue["my_position"], queue["my_jobs"]) == (0, 2)

    carols = await _queue(client, "carol")
    assert (carols["my_position"], carols["my_jobs"]) == (1, 1)
    assert (carols["running"][0]["run_id"], carols["running"][0]["topic"]) == (None, None)
    assert carols["running"][0]["owner_name"] == "Bob"
    assert [job["topic"] for job in carols["queued"]] == ["Monocular depth", None, None]
    viewers = await _queue(client, "vera")  # a viewer of Depth, with no jobs of her own
    assert [job["project_name"] for job in [*viewers["running"], *viewers["queued"]]] == [
        "Depth",
        None,
        "Depth",
        "Depth",
    ]
    assert (viewers["my_position"], viewers["my_jobs"]) == (None, 0)
    admins = await _queue(client, "root", "admin")
    assert [job["project_name"] for job in [*admins["running"], *admins["queued"]]] == [
        "Depth",
        "Other",
        "Depth",
        "Depth",
    ]
    assert (await client.get("/api/v1/gpu/queue")).status_code == 401


async def test_the_gpu_readings_come_from_a_recent_heartbeat(
    client: httpx.AsyncClient, db: Factory
) -> None:
    queue = await _queue(client, "vera")
    assert (queue["gpu"], queue["executor_alive"], queue["running"], queue["queued"]) == (
        None,
        False,
        [],
        [],
    )
    await _heartbeat(db, seconds_ago=4)
    queue = await _queue(client, "vera")
    assert queue["executor_alive"] is True
    assert queue["gpu"] == {
        "name": "NVIDIA GeForce GTX 1060 6GB",
        "memory_total_mb": 6144,
        "memory_used_mb": 4402,
        "utilization_percent": 97,
        "temperature_c": None,
        "power_draw_w": 101.5,
        "power_limit_w": 120.0,
        "fan_percent": None,
        "sampled_at": "2026-10-31T11:59:58Z",
        "demo": False,
    }
    # nvidia-smi gave no reading, or one that doesn't read as a GPU's: the executor still runs.
    for gpu in (None, {"name": "GPU 0"}):
        await _heartbeat(db, seconds_ago=4, gpu=gpu)
        queue = await _queue(client, "vera")
        assert (queue["gpu"], queue["executor_alive"]) == (None, True)
    # A heartbeat a minute old: the executor stopped, and its last readings are not shown.
    await _heartbeat(db, seconds_ago=61)
    queue = await _queue(client, "vera")
    assert (queue["gpu"], queue["executor_alive"]) == (None, False)


def test_a_heartbeat_counts_while_it_is_recent() -> None:
    def beat(alive_at: object) -> dict[str, Any]:
        return {"alive_at": alive_at, "gpu": None}

    assert executor_alive(beat((NOW - timedelta(seconds=59)).isoformat()), NOW)
    assert not executor_alive(beat((NOW - timedelta(seconds=60)).isoformat()), NOW)
    assert executor_alive(beat("2026-10-31T11:59:30"), NOW)  # without an offset: UTC
    for alive_at in ("yesterday", None, 1761912000):
        assert not executor_alive(beat(alive_at), NOW)
    assert not executor_alive(None, NOW)


# --- Progress and ETAs ------------------------------------------------------------------------


def _entry(
    kind: GpuJobKind = TRAIN,
    *,
    active: bool = False,
    owner: str = "bob",
    plan: Plan = TRAIN_PLAN,
    step: Step | None = None,
    started: datetime | None = None,
    timeout_seconds: int = 6 * 3600,
) -> QueueEntry:
    return QueueEntry(
        id=uuid.uuid4(),
        kind=kind,
        active=active,
        owner_id=owner,
        owner_name=owner.title(),
        run_id=uuid.uuid4(),
        topic="Monocular depth",
        project_name="Depth",
        dataset="nyu2",
        plan=plan,
        step=step,
        submitted_at=NOW - timedelta(hours=1),
        started_at=started,
        timeout_seconds=timeout_seconds,
    )


def _running(kind: GpuJobKind = TRAIN, **fields: Any) -> GpuJobOut:
    [job] = queue_snapshot(NOW, [_entry(kind, active=True, **fields)], None, "bob").running
    return job


def test_a_running_jobs_eta_extrapolates_the_steps_it_has_done() -> None:
    job = _running(step=Step(epoch=1, step=499), started=NOW - timedelta(minutes=10))
    assert (job.progress, job.epoch, job.total_epochs, job.estimated) == (0.5, 2, 3, False)
    assert job.estimated_start_at == job.started_at == NOW - timedelta(minutes=10)
    assert (job.estimated_finish_at, job.eta_seconds) == (NOW + timedelta(minutes=10), 600)
    # Its last step logged: never shown as done, and a few seconds still to go.
    last = _running(step=Step(epoch=2, step=999), started=NOW - timedelta(minutes=10))
    assert (last.progress, last.epoch, last.eta_seconds) == (0.99, 3, MIN_REMAINING.seconds)
    # 250 of 3000 steps in 10 minutes would take 2 hours: the executor stops it after its hour.
    slow = _running(
        step=Step(epoch=0, step=249), started=NOW - timedelta(minutes=10), timeout_seconds=3600
    )
    assert (slow.progress, slow.estimated) == (0.083, False)
    assert slow.estimated_finish_at == NOW + timedelta(minutes=50)


def test_a_running_jobs_progress_is_guessed_until_it_logs_a_step() -> None:
    # A smoke test takes about 2 minutes.
    smoke = _running(SMOKE, plan=SMOKE_PLAN, started=NOW - timedelta(seconds=30))
    assert (smoke.kind, smoke.progress, smoke.epoch, smoke.total_epochs) == ("smoke", 0.25, None, 1)
    assert (smoke.eta_seconds, smoke.estimated) == (90, True)
    # Its container is still being created: it starts now.
    starting = _running(SMOKE, plan=SMOKE_PLAN)
    assert (starting.started_at, starting.estimated_start_at) == (None, NOW)
    assert (starting.progress, starting.eta_seconds) == (0.0, 120)
    # Training takes its planned steps at 3 a second: 3000 steps in 1000 seconds.
    train = _running(started=NOW - timedelta(seconds=250))
    assert (train.progress, train.eta_seconds, train.estimated) == (0.25, 750, True)
    # Longer than guessed: still a few seconds to go.
    late = _running(SMOKE, plan=SMOKE_PLAN, started=NOW - timedelta(minutes=5))
    assert (late.progress, late.eta_seconds) == (0.95, MIN_REMAINING.seconds)
    # No plan to count its steps against: its epoch shows, and 30 minutes are guessed.
    unplanned = _running(
        plan=Plan(None, None), step=Step(4, 10), started=NOW - timedelta(minutes=3)
    )
    assert (unplanned.epoch, unplanned.total_epochs, unplanned.estimated) == (5, None, True)
    assert unplanned.eta_seconds == 27 * 60


def test_queued_jobs_wait_their_turn_one_after_the_other() -> None:
    entries = [
        _entry(active=True, owner="alice", step=Step(1, 499), started=NOW - timedelta(minutes=10)),
        _entry(SMOKE, owner="carol", plan=SMOKE_PLAN),
        _entry(owner="bob"),
        _entry(owner="bob", plan=Plan(None, None)),
        _entry(owner="dana", timeout_seconds=600),
    ]
    snapshot = queue_snapshot(NOW, entries, None, "bob")
    [running] = snapshot.running
    smoke, train, unplanned, short = snapshot.queued
    assert smoke.estimated_start_at == running.estimated_finish_at == NOW + timedelta(minutes=10)
    assert train.estimated_start_at == smoke.estimated_finish_at == NOW + timedelta(minutes=12)
    assert unplanned.estimated_start_at == train.estimated_finish_at
    assert train.estimated_finish_at - train.estimated_start_at == timedelta(seconds=1000)
    assert unplanned.estimated_finish_at - unplanned.estimated_start_at == timedelta(minutes=30)
    # No job is expected to run past its time limit.
    assert short.estimated_finish_at - short.estimated_start_at == timedelta(seconds=600)
    assert [job.eta_seconds for job in snapshot.queued] == [720, 1720, 3520, 4120]
    for job in snapshot.queued:
        assert (job.status, job.progress, job.epoch, job.estimated) == ("queued", 0.0, None, True)
    assert (snapshot.my_position, snapshot.my_jobs) == (2, 2)  # bob's first job is 2nd in line
    # With nothing on the GPU, the first one starts now.
    idle = queue_snapshot(NOW, entries[1:], None, "carol")
    assert (idle.running, idle.queued[0].estimated_start_at, idle.my_position) == ([], NOW, 1)


def test_a_jobs_plan_comes_from_its_config_and_its_dataset() -> None:
    nyu2 = NYU2_DATASET["details"]
    assert job_plan(harness_config(), nyu2) == TRAIN_PLAN
    assert job_plan(SMOKE_CONFIG, nyu2) == SMOKE_PLAN
    # Without a cap, the whole training split in full batches; an epoch also ends with it.
    assert job_plan(harness_config(max_train_steps=None), nyu2) == Plan(3, 50_688 // 8)
    assert job_plan(harness_config(max_train_steps=10_000), nyu2) == Plan(3, 6336)
    assert job_plan(harness_config(max_train_steps=None), {}) == Plan(3, None)
    small = {"splits": {"train": 4}}  # fewer samples than a batch
    assert job_plan(harness_config(max_train_steps=None), small) == Plan(3, None)
    malformed = {"training": {"epochs": True, "max_train_steps": "5"}, "data": []}
    assert job_plan(malformed, nyu2) == Plan(None, None)
    assert job_plan(None, None) == Plan(None, None)
    record = {"kind": "train_step", "epoch": 1, "step": 20, "loss": 0.3, "ts": "t"}
    assert latest_step(record) == Step(1, 20)
    for malformed_record in (
        None,
        {},
        {"epoch": -1, "step": 0},
        {"epoch": 0, "step": "3"},
        {"epoch": True, "step": 1},
        ["epoch", "step"],
    ):
        assert latest_step(malformed_record) is None

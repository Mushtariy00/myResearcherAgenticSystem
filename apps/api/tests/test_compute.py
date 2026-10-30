import uuid
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_api.demo import gpu
from agentic_api.demo.gpu import RealJob, day_schedule, demo_jobs_at, queue_snapshot, telemetry
from agentic_core.enums import RunStatus, StageStatus
from api_testkit import (
    ADMIN,
    add_stage_run,
    as_user,
    create_project,
    set_run_status,
    start_run,
    team_project,
)

Factory = async_sessionmaker[AsyncSession]
NOON = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


async def test_datasets_list_the_registered_datasets(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/datasets", headers=as_user("vera"))
    assert response.status_code == 200, response.text
    listing = response.json()
    assert listing["demo"] is True
    datasets = {item["id"]: item for item in listing["items"]}
    assert len(datasets) >= 3 and "nyu2" in datasets
    nyu = datasets["nyu2"]
    assert (nyu["name"], nyu["version"], nyu["width"], nyu["height"]) == (
        "NYU Depth V2",
        "2025.03",
        640,
        480,
    )
    assert "1,449 densely labelled" in nyu["description"] and "407k raw" in nyu["description"]
    assert nyu["scenes"] == "indoor" and nyu["contract"]["units"] == "metres"
    assert {split["name"]: split["samples"] for split in nyu["splits"]} == {
        "train": 50_688,
        "val": 654,
        "test": 0,
    }
    for item in listing["items"]:
        assert item["samples"] == sum(split["samples"] for split in item["splits"])
        assert item["mount_path"] == f"/datasets/{item['id']}/{item['version']}"
        assert len(item["checksum_sha256"]) == 64 and item["demo"] is True
        assert item["license"] and item["contract"]["inputs"]
    again = await client.get("/api/v1/datasets", headers=as_user("bob"))
    assert again.json() == listing
    assert (await client.get("/api/v1/datasets")).status_code == 401


def test_demo_jobs_follow_one_schedule_per_day() -> None:
    day = date(2026, 10, 30)
    jobs = day_schedule(day)
    assert day_schedule(day) == jobs  # the date alone decides it
    assert day_schedule(day + timedelta(days=1)) != jobs
    assert len(jobs) > 20
    midnight = datetime(2026, 10, 30, tzinfo=UTC)
    assert jobs[0].starts_at >= midnight and jobs[-1].ends_at <= midnight + timedelta(days=1)
    for job in jobs:
        assert job.submitted_at <= job.starts_at < job.ends_at
        assert timedelta(minutes=5) <= job.ends_at - job.starts_at <= timedelta(minutes=52)
        assert 0 < job.gpu_memory_mb < gpu.MEMORY_TOTAL_MB
    for before, after in pairwise(jobs):
        assert before.ends_at <= after.starts_at  # one job at a time
        assert before.submitted_at <= after.submitted_at  # first come, first served


def test_the_queue_moves_with_time() -> None:
    running, waiting = demo_jobs_at(NOON)
    assert demo_jobs_at(NOON) == (running, waiting)
    for job in waiting:
        assert job.submitted_at <= NOON < job.starts_at
    # Over a day the GPU is mostly busy, and nothing waits while it idles.
    samples = [demo_jobs_at(NOON + timedelta(minutes=minute)) for minute in range(0, 1440, 7)]
    assert all(busy is not None or queued == [] for busy, queued in samples)
    assert sum(busy is not None for busy, _ in samples) > 0.8 * len(samples)
    snapshot = queue_snapshot(NOON, [], "bob")
    assert snapshot == queue_snapshot(NOON, [], "bob")
    if running is not None:
        [shown] = snapshot.running
        later = queue_snapshot(NOON + timedelta(seconds=30), [], "bob")
        if later.running and later.running[0].id == shown.id:
            assert later.running[0].progress >= shown.progress
            assert later.running[0].eta_seconds == shown.eta_seconds - 30
    # Estimated starts chain each job's length after the one before it.
    jobs = [*snapshot.running, *snapshot.queued]
    for before, after in pairwise(jobs):
        assert after.estimated_start_at == before.estimated_finish_at
    assert (snapshot.my_position, snapshot.my_jobs, snapshot.demo) == (None, 0, True)


def test_telemetry_is_live_looking_but_reproducible() -> None:
    busy = telemetry(NOON, busy=True, job_memory_mb=4200)
    assert busy == telemetry(NOON + timedelta(seconds=2), busy=True, job_memory_mb=4200)
    assert busy.sampled_at == NOON
    samples = [telemetry(NOON + timedelta(seconds=5 * n), busy=True) for n in range(24)]
    assert len({sample.utilization_percent for sample in samples}) > 1
    for sample in samples:
        assert 70 <= sample.utilization_percent <= 100
        assert 3500 < sample.memory_used_mb < gpu.MEMORY_TOTAL_MB
        assert 60 <= sample.temperature_c <= 84
        assert 0 < sample.power_draw_w <= sample.power_limit_w == 120
    idle = telemetry(NOON, busy=False)
    assert idle.utilization_percent <= 3 and idle.memory_used_mb < 400
    assert idle.temperature_c < busy.temperature_c
    assert busy.name == "NVIDIA GeForce GTX 1060 6GB" and busy.memory_total_mb == 6144


def _real_job(owner: str, minutes_ago: int, shown: bool = True) -> RealJob:
    return RealJob(
        id=str(uuid.uuid4()),
        run_id=uuid.uuid4() if shown else None,
        topic="Depth" if shown else None,
        project_name="Depth" if shown else None,
        owner_id=owner,
        owner_name=owner.title(),
        dataset="nyu2",
        submitted_at=NOON - timedelta(minutes=minutes_ago),
    )


def test_real_jobs_go_first_and_the_caller_finds_their_place() -> None:
    real = [_real_job("alice", 10), _real_job("bob", 4), _real_job("carol", 2, shown=False)]
    snapshot = queue_snapshot(NOON, real, "bob")
    [running] = snapshot.running
    assert (running.id, running.status, running.demo, running.estimated) == (
        real[0].id,
        "running",
        False,
        True,
    )
    assert running.progress == round(10 / 25, 3)
    assert running.eta_seconds == 15 * 60
    assert [job.id for job in snapshot.queued[:2]] == [real[1].id, real[2].id]
    assert all(job.demo for job in snapshot.queued[2:])  # every demo job waits behind them
    assert (snapshot.my_position, snapshot.my_jobs) == (1, 1)
    hidden = snapshot.queued[1]
    assert (hidden.run_id, hidden.topic, hidden.owner_name) == (None, None, "Carol")
    assert snapshot.gpu.utilization_percent >= 70
    assert queue_snapshot(NOON, real, "alice").my_position == 0
    # A job that ran longer than usual still shows a minute to go.
    overdue = queue_snapshot(NOON, [_real_job("bob", 90)], "bob")
    assert (overdue.running[0].progress, overdue.running[0].eta_seconds) == (0.95, 60)


async def _experiment_running(
    client: httpx.AsyncClient, db: Factory, project_id: str, user: str, minutes_ago: int
) -> tuple[str, str]:
    run_id = await start_run(client, project_id, user=user)
    await set_run_status(db, run_id, RunStatus.RUNNING)
    stage_run_id = await add_stage_run(
        db,
        run_id,
        "experiment",
        StageStatus.RUNNING,
        started_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )
    return run_id, stage_run_id


async def _queue(client: httpx.AsyncClient, user: str, role: str = "user") -> dict[str, Any]:
    response = await client.get("/api/v1/gpu/queue", headers=as_user(user, role))
    assert response.status_code == 200, response.text
    return response.json()


async def test_the_gpu_queue_shows_running_experiments(
    client: httpx.AsyncClient, db: Factory
) -> None:
    depth = await team_project(client)
    other = await create_project(client, "Other", owner="carol")
    bobs_run, bobs_job = await _experiment_running(client, db, depth, "bob", 12)
    _, carols_job = await _experiment_running(client, db, other, "carol", 3)
    # Not GPU work: an approved experiment, and a run that is no longer running.
    finished = await start_run(client, depth)
    await set_run_status(db, finished, RunStatus.RUNNING)
    await add_stage_run(db, finished, "experiment", StageStatus.APPROVED)
    stopped, _ = await _experiment_running(client, db, depth, "alice", 1)
    await set_run_status(db, stopped, RunStatus.CANCELLED)

    queue = await _queue(client, "bob")
    assert (queue["demo"], queue["concurrency"], queue["per_user_limit"]) == (True, 1, 2)
    assert (queue["gpu"]["name"], queue["gpu"]["demo"]) == ("NVIDIA GeForce GTX 1060 6GB", True)
    assert set(queue["gpu"]) == {
        "name",
        "memory_total_mb",
        "memory_used_mb",
        "utilization_percent",
        "temperature_c",
        "power_draw_w",
        "power_limit_w",
        "fan_percent",
        "sampled_at",
        "demo",
    }
    assert set(queue["running"][0]) == {
        "id",
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
    [running] = queue["running"]
    assert (running["id"], running["run_id"], running["topic"], running["is_mine"]) == (
        bobs_job,
        bobs_run,
        "Monocular depth",
        True,
    )
    assert (running["owner_name"], running["project_name"], running["dataset"]) == (
        "Bob",
        "Depth",
        "nyu2",
    )
    real_queued = [job for job in queue["queued"] if not job["demo"]]
    assert [job["id"] for job in real_queued] == [carols_job]
    assert (real_queued[0]["topic"], real_queued[0]["run_id"]) == (None, None)  # not bob's to see
    assert real_queued[0]["owner_name"] == "Carol"
    assert (queue["my_position"], queue["my_jobs"]) == (0, 1)

    carols = await _queue(client, "carol")
    assert carols["my_position"] == 1
    assert [job["topic"] for job in carols["queued"] if not job["demo"]] == ["Monocular depth"]
    assert carols["running"][0]["topic"] is None
    admins = await _queue(client, "root", "admin")
    assert admins["running"][0]["topic"] == admins["queued"][0]["topic"] == "Monocular depth"
    assert admins["my_position"] is None
    assert (await client.get("/api/v1/gpu/queue")).status_code == 401
    assert (await client.get("/api/v1/gpu/queue", headers=ADMIN)).status_code == 200

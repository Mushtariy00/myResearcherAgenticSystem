"""The lab GPU as the queue page shows it, until the executor reports telemetry and jobs.

Telemetry and demo jobs are pure functions of the instant asked about: the same instant always
gives the same numbers and nearby instants give nearby ones, so the page looks live without
storing anything. Demo jobs follow a schedule generated per UTC day from the date alone. Real
experiment stages that are running go ahead of every demo job (``queue_snapshot``).
"""

import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from agentic_api.demo._seed import rng_for
from agentic_api.schemas import GpuJobOut, GpuOut, GpuQueueOut

GPU_NAME = "NVIDIA GeForce GTX 1060 6GB"
MEMORY_TOTAL_MB = 6144
POWER_LIMIT_W = 120.0
CONCURRENCY = 1  # worker-gpu runs one job at a time
PER_USER_LIMIT = 2
SAMPLE_SECONDS = 5  # telemetry changes every few seconds, like an nvidia-smi poll
# Real jobs send no progress yet: their progress and ETA assume a typical run of this length.
TYPICAL_JOB = timedelta(minutes=25)
TYPICAL_JOB_MEMORY_MB = 4300
_IDLE_MEMORY_MB = 312
_MIN_REMAINING = timedelta(minutes=1)
_OWNERS = (
    "Ji-woo Kim",
    "Haruto Sato",
    "Dilnoza Karimova",
    "Priya Iyer",
    "Lukas Novak",
    "Seo-yeon Park",
    "Mateo Vargas",
)
_WORK = (
    ("Scale-aware distillation for indoor depth", "nyu2"),
    ("Edge-aware refinement of monocular depth", "nyu2"),
    ("Surface normals as auxiliary supervision", "nyu2"),
    ("Self-supervised depth from corridor videos", "lab_scans_v1"),
    ("Uncertainty-aware depth across sensors", "sunrgbd"),
    ("A lightweight depth network for a 6 GB GPU", "kitti"),
    ("Depth completion from sparse LiDAR", "kitti"),
)


@dataclass(frozen=True)
class DemoJob:
    id: str
    owner_name: str
    topic: str
    dataset: str
    total_epochs: int
    gpu_memory_mb: int
    submitted_at: datetime
    starts_at: datetime
    ends_at: datetime


@dataclass(frozen=True)
class RealJob:
    """A running experiment stage. ``run_id``, ``topic`` and ``project_name`` are None when the
    caller may not open the run; ``owner_name`` is None once the account no longer exists."""

    id: str
    run_id: uuid.UUID | None
    topic: str | None
    project_name: str | None
    owner_id: str
    owner_name: str | None
    dataset: str | None
    submitted_at: datetime


def day_schedule(day: date) -> list[DemoJob]:
    """The demo jobs of one UTC day: back to back, with a few idle gaps, the last one ending by
    midnight. Jobs were submitted in the order they run, a while before they start; a job after
    an idle gap started the moment it was submitted."""
    rng = rng_for("gpu-schedule", day.isoformat())
    midnight = datetime.combine(day, time(), tzinfo=UTC)
    end_of_day = midnight + timedelta(days=1)
    jobs: list[DemoJob] = []
    cursor = midnight
    submitted = midnight - timedelta(minutes=rng.randint(30, 90))
    while True:
        idle = rng.random() < 0.2
        if idle:
            cursor += timedelta(minutes=rng.randint(2, 12))
        ends = min(cursor + timedelta(seconds=rng.randint(16 * 60, 52 * 60)), end_of_day)
        if ends - cursor < timedelta(minutes=5):
            return jobs
        earliest = submitted + timedelta(seconds=rng.randint(20, 600))
        waited = cursor - timedelta(minutes=rng.randint(6, 95))
        submitted = cursor if idle else min(cursor, max(earliest, waited))
        topic, dataset = rng.choice(_WORK)
        jobs.append(
            DemoJob(
                id=f"demo-{day:%Y%m%d}-{len(jobs) + 1:02d}",
                owner_name=rng.choice(_OWNERS),
                topic=topic,
                dataset=dataset,
                total_epochs=rng.choice((12, 16, 20, 24, 30)),
                gpu_memory_mb=rng.randint(2600, 5600),
                submitted_at=submitted,
                starts_at=cursor,
                ends_at=ends,
            )
        )
        cursor = ends


def demo_jobs_at(now: datetime) -> tuple[DemoJob | None, list[DemoJob]]:
    """The demo job on the GPU at ``now`` and the ones waiting for it; while the GPU idles,
    nothing waits."""
    now = now.astimezone(UTC)
    today = now.date()
    jobs = [*day_schedule(today), *day_schedule(today + timedelta(days=1))]
    running = next((job for job in jobs if job.starts_at <= now < job.ends_at), None)
    if running is None:
        return None, []
    return running, [job for job in jobs if job.submitted_at <= now < job.starts_at]


def telemetry(now: datetime, *, busy: bool, job_memory_mb: int = TYPICAL_JOB_MEMORY_MB) -> GpuOut:
    """GPU readings at ``now``: slow waves plus jitter seeded by the sample, high while a job
    runs and near idle otherwise."""
    sample = math.floor(now.timestamp() / SAMPLE_SECONDS)
    t = sample * SAMPLE_SECONDS
    rng = rng_for("gpu-telemetry", sample)
    if busy:
        utilization = 92 + 4 * math.sin(t / 47) + 2.5 * math.sin(t / 13) + rng.uniform(-2.5, 2.5)
        memory = job_memory_mb + 190 + 70 * math.sin(t / 95) + rng.uniform(-24, 24)
        temperature = 72 + 4 * math.sin(t / 900) + 1.5 * math.sin(t / 61) + rng.uniform(-0.6, 0.6)
        power = 0.86 * POWER_LIMIT_W + 9 * math.sin(t / 29) + rng.uniform(-4, 4)
    else:
        utilization = 1.5 + rng.uniform(-1.5, 1.5)
        memory = _IDLE_MEMORY_MB + rng.uniform(-6, 6)
        temperature = 41 + 2 * math.sin(t / 1200) + rng.uniform(-0.4, 0.4)
        power = 9 + rng.uniform(-1, 2)
    return GpuOut(
        name=GPU_NAME,
        memory_total_mb=MEMORY_TOTAL_MB,
        memory_used_mb=_clamp(round(memory), 0, MEMORY_TOTAL_MB),
        utilization_percent=_clamp(round(utilization), 0, 100),
        temperature_c=_clamp(round(temperature), 30, 90),
        power_draw_w=round(min(max(power, 5.0), POWER_LIMIT_W), 1),
        power_limit_w=POWER_LIMIT_W,
        fan_percent=_clamp(round(30 + (temperature - 40) * 1.6), 0, 100),
        sampled_at=datetime.fromtimestamp(t, UTC),
        demo=True,
    )


def _clamp(value: int, low: int, high: int) -> int:
    return min(max(value, low), high)


def _seconds(span: timedelta) -> int:
    return max(0, round(span.total_seconds()))


def _real_running(job: RealJob, now: datetime, caller_id: str) -> GpuJobOut:
    elapsed = max(timedelta(0), now - job.submitted_at)
    finish = now + max(_MIN_REMAINING, TYPICAL_JOB - elapsed)
    return GpuJobOut(
        id=job.id,
        status="running",
        run_id=job.run_id,
        topic=job.topic,
        project_name=job.project_name,
        owner_name=job.owner_name,
        is_mine=job.owner_id == caller_id,
        dataset=job.dataset,
        progress=round(min(0.95, elapsed / TYPICAL_JOB), 3),
        epoch=None,
        total_epochs=None,
        gpu_memory_mb=None,
        submitted_at=job.submitted_at,
        started_at=job.submitted_at,
        estimated_start_at=job.submitted_at,
        estimated_finish_at=finish,
        eta_seconds=_seconds(finish - now),
        estimated=True,
        demo=False,
    )


def _real_queued(job: RealJob, start: datetime, now: datetime, caller_id: str) -> GpuJobOut:
    finish = start + TYPICAL_JOB
    return GpuJobOut(
        id=job.id,
        status="queued",
        run_id=job.run_id,
        topic=job.topic,
        project_name=job.project_name,
        owner_name=job.owner_name,
        is_mine=job.owner_id == caller_id,
        dataset=job.dataset,
        progress=0.0,
        epoch=None,
        total_epochs=None,
        gpu_memory_mb=None,
        submitted_at=job.submitted_at,
        started_at=None,
        estimated_start_at=start,
        estimated_finish_at=finish,
        eta_seconds=_seconds(finish - now),
        estimated=True,
        demo=False,
    )


def _demo_job(job: DemoJob, now: datetime, start: datetime | None = None) -> GpuJobOut:
    """``job`` running (``start`` None: as its schedule says) or queued to start at ``start``."""
    if start is None:
        progress = (now - job.starts_at) / (job.ends_at - job.starts_at)
        finish = job.ends_at
    else:
        progress = 0.0
        finish = start + (job.ends_at - job.starts_at)
    return GpuJobOut(
        id=job.id,
        status="running" if start is None else "queued",
        run_id=None,
        topic=job.topic,
        project_name=None,
        owner_name=job.owner_name,
        is_mine=False,
        dataset=job.dataset,
        progress=round(progress, 3),
        epoch=min(job.total_epochs, math.floor(progress * job.total_epochs) + 1)
        if start is None
        else None,
        total_epochs=job.total_epochs,
        gpu_memory_mb=job.gpu_memory_mb,
        submitted_at=job.submitted_at,
        started_at=job.starts_at if start is None else None,
        estimated_start_at=job.starts_at if start is None else start,
        estimated_finish_at=finish,
        eta_seconds=_seconds(finish - now),
        estimated=False,
        demo=True,
    )


def queue_snapshot(now: datetime, real_jobs: Sequence[RealJob], caller_id: str) -> GpuQueueOut:
    """The GPU and its queue at ``now``. ``real_jobs`` are the running experiment stages, oldest
    first: the oldest one holds the GPU and the rest wait ahead of the demo jobs. Estimated
    start times chain each job's expected length after the one before it."""
    now = now.astimezone(UTC)
    demo_running, demo_waiting = demo_jobs_at(now)
    running: list[GpuJobOut] = []
    queued: list[GpuJobOut] = []
    if real_jobs:
        running.append(_real_running(real_jobs[0], now, caller_id))
        free_at = running[0].estimated_finish_at
        for job in real_jobs[1:]:
            queued.append(_real_queued(job, free_at, now, caller_id))
            free_at = queued[-1].estimated_finish_at
        # The demo job the schedule has on the GPU now waits behind the real ones.
        waiting = [demo_running, *demo_waiting] if demo_running else demo_waiting
    else:
        if demo_running is not None:
            running.append(_demo_job(demo_running, now))
        free_at = demo_running.ends_at if demo_running is not None else now
        waiting = demo_waiting
    for job in waiting:
        queued.append(_demo_job(job, now, start=free_at))
        free_at = queued[-1].estimated_finish_at

    memory = running[0].gpu_memory_mb if running else None
    mine = [index for index, job in enumerate([*running, *queued]) if job.is_mine]
    return GpuQueueOut(
        gpu=telemetry(now, busy=bool(running), job_memory_mb=memory or TYPICAL_JOB_MEMORY_MB),
        concurrency=CONCURRENCY,
        running=running,
        queued=queued,
        # Index 0 is the running job; queue positions count from 1.
        my_position=(mine[0] - len(running) + 1 if mine[0] >= len(running) else 0)
        if mine
        else None,
        my_jobs=len(mine),
        per_user_limit=PER_USER_LIMIT,
        demo=True,
    )

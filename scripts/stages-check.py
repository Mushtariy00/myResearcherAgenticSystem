"""Phase 3: the real coding and experiment stages run on this machine's GPU (docs/design/
experiments.md, "The stages").

Only the LLM is scripted: the coding stage gets the depth_unet example as its answer, so the check
needs no LLM quota. Everything else is real: the stage runners, the dev database, an executor of
its own (stop any other first), the sandbox and the GPU. It checks:
  1. the coding stage smoke-tests the code on the GPU and outputs it, with the config.json that
     says what the smoke test measured
  2. the experiment stage trains it (2 epochs of 100 steps, full validation) and outputs the real
     curves, metrics and provenance
The project, its run and the job folders are removed at the end. Exits non-zero on any FAIL.
Usage: make stages-check (needs make up, the sandbox image and ARP_DATASET_NYU2)
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select, text

from agentic_core.gpu_jobs import JOB_LABEL, job_dir
from agentic_core.schemas import (
    CodingOutput,
    ExperimentOutput,
    MethodOutput,
    MethodProposal,
    RunConfig,
)
from agentic_db import create_engine, session_factory
from agentic_db.models import GpuJob, Project, Run, StageRun
from agentic_executor.settings import ExecutorSettings
from agentic_worker.agents import Answer, Request, StageAgents
from agentic_worker.coding.config import CONFIG_FILE, CodeConfig
from agentic_worker.coding.runner import CodingRunner
from agentic_worker.experiment.runner import ExperimentRunner
from agentic_worker.gpu import GpuJobs
from agentic_worker.stages import StageContext

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "sandbox" / "pytorch" / "examples" / "depth_unet"
LOG = Path.home() / ".local" / "state" / "arp" / "logs" / "stages-check.log"
OWNER = "stages-check"
TOPIC = "Monocular depth estimation on NYU Depth V2"
STAGE_SECONDS = 1200  # the longest either stage may take here
EPOCHS = 2
STEPS_PER_EPOCH = 100

CHOICES = {
    "summary": (
        "A small two-scale U-Net with GroupNorm and a sigmoid depth head bounded at 10 m, "
        "trained with its own L1 loss over the valid pixels."
    ),
    "model_kwargs": {"base_channels": 16, "max_depth": 10.0},
    "loss": "generated",
    "training": {"learning_rate": 0.001, "optimizer": "adam", "weight_decay": 0.0},
}
ANSWER = (
    f"```python\n# file: model.py\n{(EXAMPLE / 'model.py').read_text()}```\n"
    f"```python\n# file: loss.py\n{(EXAMPLE / 'loss.py').read_text()}```\n"
    f"```json\n{json.dumps(CHOICES)}\n```"
)
METHOD = MethodOutput(
    research_gaps=["Depth networks small enough to train on one 6 GB GPU are rarely compared."],
    proposals=[
        MethodProposal(
            name="Small U-Net",
            rationale="Skip connections keep the edges a monocular depth map needs.",
            expected_benefit="Trains in minutes on one GPU.",
            risk="Too small to match the published results.",
        )
    ],
    recommended_option="Small U-Net",
    implementation_focus="A two-scale U-Net with GroupNorm and a bounded depth head.",
    datasets=["nyu2"],
    evaluation_metrics=["rmse", "abs_rel"],
)

passed = 0
failed = 0


def check(ok: bool, what: str) -> bool:
    global passed, failed
    if ok:
        passed += 1
        print(f"  \033[32mPASS\033[0m {what}", flush=True)
    else:
        failed += 1
        print(f"  \033[31mFAIL\033[0m {what}", flush=True)
    return ok


class ScriptedAgents(StageAgents):
    """StageAgents whose every answer is ANSWER: no LLM and no gateway."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def ask[T](self, ctx: StageContext, request: Request[T]) -> Answer[T]:
        self.prompts.append(request.prompt)
        return Answer(value=request.parse(ANSWER), model="scripted/depth_unet", calls=[])


class ExecutorProcess:
    """`python -m agentic_executor` in a process group of its own, logging to LOG."""

    def __init__(self) -> None:
        self.process: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        self.process = subprocess.Popen(
            ["uv", "run", "--package", "agentic-executor", "python", "-m", "agentic_executor"],
            cwd=ROOT,
            stdout=LOG.open("ab"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    def stop(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        os.killpg(self.process.pid, signal.SIGTERM)
        try:
            self.process.wait(15)
        except subprocess.TimeoutExpired:
            os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait()


async def say(code: str, params: dict[str, Any], message: str) -> None:
    print(f"    {message}", flush=True)


def remove_containers(job_id: uuid.UUID) -> None:
    """Any container of the job, through Docker's own CLI (this check's way, not the
    executor's)."""
    listed = subprocess.run(
        ["docker", "ps", "-aq", "--filter", f"label={JOB_LABEL}={job_id}"],
        capture_output=True,
        text=True,
    )
    for container in listed.stdout.split():
        subprocess.run(["docker", "rm", "-f", "-v", container], capture_output=True)


class Check:
    def __init__(self, sessions: Any) -> None:
        self.sessions = sessions
        self.project_id: uuid.UUID | None = None
        self.run_id: uuid.UUID | None = None

    async def setup(self) -> None:
        async with self.sessions() as session:
            project = Project(name="Stages check (removed when it ends)", created_by=OWNER)
            session.add(project)
            await session.flush()
            run = Run(
                project_id=project.id, owner_id=OWNER, topic=TOPIC, config={"dataset": "nyu2"}
            )
            session.add(run)
            await session.commit()
            self.project_id, self.run_id = project.id, run.id

    async def attempt(self, stage: str, inputs: dict[str, dict[str, Any]]) -> StageContext:
        assert self.run_id is not None and self.project_id is not None
        async with self.sessions() as session:
            stage_run = StageRun(run_id=self.run_id, stage=stage, attempt=1)
            session.add(stage_run)
            await session.commit()
        return StageContext(
            run_id=str(self.run_id),
            stage_run_id=str(stage_run.id),
            stage=stage,
            attempt=1,
            feedback="",
            topic=TOPIC,
            owner_id=OWNER,
            project_id=str(self.project_id),
            llm_policy="auto",
            budget_cap_usd=None,
            config=RunConfig(dataset="nyu2"),
            inputs=inputs,
            log=say,
        )

    async def cleanup(self, data_dir: Path) -> int:
        """Remove the check's containers, job folders and project; the jobs left after."""
        async with self.sessions() as session:
            job_ids = list(await session.scalars(select(GpuJob.id).where(GpuJob.user_id == OWNER)))
        for job_id in job_ids:
            remove_containers(job_id)
            shutil.rmtree(job_dir(data_dir, job_id), ignore_errors=True)
        if self.project_id is not None:
            async with self.sessions() as session:
                await session.execute(
                    text("DELETE FROM projects WHERE id = :id"), {"id": self.project_id}
                )
                await session.commit()
        async with self.sessions() as session:
            return len(
                list(await session.scalars(select(GpuJob.id).where(GpuJob.user_id == OWNER)))
            )


async def coding_stage(check_: Check, gpu: GpuJobs) -> CodingOutput | None:
    print("1/2 The coding stage (scripted answer: the depth_unet example)", flush=True)
    agents = ScriptedAgents()
    ctx = await check_.attempt("coding", {"method": METHOD.model_dump(mode="json")})
    started = time.monotonic()
    outcome = await asyncio.wait_for(
        CodingRunner(agents, check_.sessions, gpu).run(ctx), STAGE_SECONDS
    )
    took = time.monotonic() - started
    output = CodingOutput.model_validate(outcome.data)
    files = {file.path: file for file in output.files}
    check(
        sorted(files) == ["config.json", "loss.py", "model.py"]
        and output.entrypoint == "model.py:Model",
        f"output in {took:.0f} s: {', '.join(sorted(files))}, entrypoint {output.entrypoint}",
    )
    check(
        output.smoke_test.passed and output.smoke_test.duration_seconds > 0,
        f"smoke test passed on the GPU in {output.smoke_test.duration_seconds:.1f} GPU seconds",
    )
    config = CodeConfig.model_validate_json(files[CONFIG_FILE].content)
    smoke = config.smoke
    check(
        smoke.peak_gpu_memory_mb is not None
        and smoke.peak_gpu_memory_mb > 0
        and smoke.param_count is not None
        and smoke.param_count > 0,
        f"config.json: {smoke.param_count:,} parameters, "
        f"{smoke.peak_gpu_memory_mb} MB peak at batch {smoke.batch_size}"
        if smoke.param_count is not None
        else "config.json: no measurement",
    )
    check(
        "Implement" in agents.prompts[0] or "model.py" in agents.prompts[0],
        f"the prompt states the contract ({len(agents.prompts[0]):,} characters)",
    )
    return output


async def experiment_stage(check_: Check, gpu: GpuJobs, coding: CodingOutput) -> None:
    print(f"2/2 The experiment stage ({EPOCHS} epochs of {STEPS_PER_EPOCH} steps)", flush=True)
    ctx = await check_.attempt("experiment", {"coding": coding.model_dump(mode="json")})
    runner = ExperimentRunner(
        check_.sessions, gpu, epochs=EPOCHS, steps_per_epoch=STEPS_PER_EPOCH, max_train_hours=1
    )
    started = time.monotonic()
    outcome = await asyncio.wait_for(runner.run(ctx), STAGE_SECONDS)
    took = time.monotonic() - started
    output = ExperimentOutput.model_validate(outcome.data)
    check(output.status == "succeeded", f"training {output.status} in {took:.0f} s")
    validation = [series for series in output.series if series.split == "val"]
    check(
        bool(validation)
        and all(
            len(series.points) == EPOCHS and all(point.value is not None for point in series.points)
            for series in validation
        ),
        f"real curves: {len(output.series)} series, "
        + ", ".join(
            f"val {s.name} {[round(p.value or 0, 3) for p in s.points]}" for s in validation
        ),
    )
    measured = {name: value for name, value in output.final_metrics.items() if value is not None}
    check(
        bool(measured) and len(measured) == len(output.final_metrics),
        "final metrics: " + ", ".join(f"{name} {value:.3f}" for name, value in measured.items()),
    )
    provenance = output.provenance
    check(
        provenance.image_digest.startswith("sha256:")
        and provenance.dataset_version == "2026.05"
        and provenance.gpu_seconds > 0
        and provenance.seed == 42,
        f"provenance: image {provenance.image_digest[:19]}, {provenance.gpu_name}, "
        f"{provenance.gpu_seconds:.0f} GPU seconds, code {provenance.code_sha256[:12]}",
    )
    check(
        f"batch size {output.config.get('batch_size')}" in output.summary
        or str(output.config.get("batch_size")) in output.summary,
        f"summary: {output.summary[:160]}...",
    )


async def lock_is_free(sessions: Any) -> bool:
    async with sessions() as session:
        free = await session.scalar(text("SELECT pg_try_advisory_lock(hashtext('arp.executor'))"))
        if free:
            await session.execute(text("SELECT pg_advisory_unlock(hashtext('arp.executor'))"))
        await session.commit()
        return bool(free)


async def main() -> int:
    settings = ExecutorSettings()
    if settings.dataset_nyu2 is None:
        print("Set ARP_DATASET_NYU2 in .env (the NYU2 folder on this machine)")
        return 1
    engine = create_engine(settings.database_url)
    sessions = session_factory(engine)
    if not await lock_is_free(sessions):
        print("Another executor is running: stop it first (this check starts its own)")
        await engine.dispose()
        return 1
    check_ = Check(sessions)
    executor = ExecutorProcess()
    gpu = GpuJobs(sessions)
    started = time.monotonic()
    try:
        await check_.setup()
        executor.start()
        print(f"Executor started (log: {LOG}); a throwaway project", flush=True)
        coding = await coding_stage(check_, gpu)
        if coding is not None:
            await experiment_stage(check_, gpu, coding)
    except Exception as exc:
        check(False, f"the stages failed: {exc!r}")
    finally:
        executor.stop()
        try:  # a failure here must not hide the one that brought us here
            left = await check_.cleanup(settings.data_dir)
            print(f"Cleaned up ({left} of the check's jobs left)")
        except Exception as exc:
            print(f"Cleanup failed: {exc!r}")
        await engine.dispose()
    print(f"Summary: {passed} passed, {failed} failed in {time.monotonic() - started:.0f} s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

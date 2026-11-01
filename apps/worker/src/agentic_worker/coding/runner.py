"""The coding stage: up to three tries, each an answer, the checks, then a smoke job on the GPU.

A try's code is checked before any GPU time: by the allowlist checker, which the harness runs
again when it loads the code, and against the contract (the classes the harness builds and the
arguments it builds them with). Then a dry run of two batches, the smoke job, tries it. A failure
goes back to the LLM as the next try, with the findings or the job's error and log tail.

The calls' keys are deterministic (``<stage run id>:coding:write`` for the first try,
``...:coding:repair:<try>`` for the others), and a try's smoke job is found again by its ordinal,
the try. So an attempt that runs again (after a crash, a gateway wait or a timeout) gets its
answers replayed from the gateway journal, for free, finds the jobs it submitted, and goes on
where it stopped.
"""

import logging
import math
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.enums import GpuJobKind, GpuJobStatus
from agentic_core.gpu_jobs import (
    CODE_REFUSED,
    HOST_FAILURES,
    LOSS_FILE,
    MODEL_FILE,
    SMOKE_TIMEOUT_SECONDS,
)
from agentic_core.schemas import CodeFile, CodeRole, CodingOutput, MethodOutput, SmokeTest
from agentic_core.stages import Stage
from agentic_db.models import GpuJob
from agentic_worker.agents import StageAgents
from agentic_worker.coding import code
from agentic_worker.coding.answer import MODEL_CLASS, Written, check_code
from agentic_worker.coding.config import CONFIG_FILE, CodeConfig, SmokeMeasure
from agentic_worker.gpu import GpuJobs, JobSpec, harness_config
from agentic_worker.outputs import CODING_PROMPT_VERSION
from agentic_worker.progress import ProgressLines
from agentic_worker.stages import StageContext, StageFailedError, StageOutcome
from agentic_worker.upstream import approved_input, generated_literature

log = logging.getLogger(__name__)

# Progress lines (codes the web translates; params as below).
WRITTEN = "coding.written"  # {try, files, lines}
REFUSED = "coding.refused"  # {try, findings}: the checks refused the code, which did not run
SMOKE_FAILED = "coding.smoke_failed"  # {try, error_code}
SMOKE_PASSED = "coding.smoke_passed"  # {try, seconds}
# The degraded reason the web shows when the review the method builds on was generated.
DEMO_LITERATURE_REASON = "coding.demo_literature"

_ROLES: dict[str, CodeRole] = {MODEL_FILE: "model", LOSS_FILE: "loss"}


class CodingRunner:
    def __init__(
        self, agents: StageAgents, sessions: async_sessionmaker[AsyncSession], gpu: GpuJobs
    ) -> None:
        self._agents = agents
        self._sessions = sessions
        self._gpu = gpu

    async def run(self, ctx: StageContext) -> StageOutcome:
        method = approved_input(ctx, Stage.METHOD, MethodOutput)
        dataset = await self._gpu.dataset(ctx.config.dataset)
        if dataset is None:
            raise StageFailedError(f"coding.no_dataset: {_no_dataset(ctx.config.dataset)}")
        lines = await ProgressLines.resume(ctx, self._sessions)
        calls: list[dict[str, Any]] = []
        failures: list[code.Failure] = []
        retry: code.Retry | None = None
        for number in range(1, code.MAX_TRIES + 1):
            answer = await self._agents.ask(ctx, code.request(ctx, method, dataset, retry))
            calls.extend(answer.calls)
            written = answer.value
            await lines.say(
                WRITTEN,
                {"try": number, "files": len(written.code), "lines": written.lines},
                f"Try {number}: wrote {' and '.join(written.code)} ({written.lines} lines)",
            )
            tried = await self._try(ctx, number, dataset.name, written, lines)
            if isinstance(tried, GpuJob):
                reason = DEMO_LITERATURE_REASON if generated_literature(ctx) else None
                return StageOutcome(
                    data=_output(dataset.name, written, tried).model_dump(mode="json"),
                    model=answer.model,
                    degraded=reason is not None,
                    degraded_reason=reason,
                    prompt_version=CODING_PROMPT_VERSION,
                    llm_calls=calls,
                )
            log.info("run %s: coding try %d failed (%s)", ctx.run_id, number, tried.error_code)
            failures.append(tried)
            retry = code.Retry(number + 1, written, tried, tuple(enumerate(failures[:-1], start=1)))
        raise StageFailedError(f"coding.smoke_failed: {failures[-1].error_code}")

    async def _try(
        self, ctx: StageContext, number: int, dataset: str, written: Written, lines: ProgressLines
    ) -> GpuJob | code.Failure:
        """The try's smoke job once it passed, or why the try failed."""
        findings = check_code(written)
        if findings:
            count = len(findings)
            await lines.say(
                REFUSED,
                {"try": number, "findings": count},
                f"Try {number}: the checks refused the code "
                f"({count} {'finding' if count == 1 else 'findings'})",
            )
            return code.refused(findings)
        job = await self._gpu.run(ctx, _smoke_job(number, dataset, written), lines)
        if job.code != written.code:  # only if the gateway's journal lost the try's answer
            log.warning(
                "run %s: smoke job %s ran other code than try %d", ctx.run_id, job.id, number
            )
        if job.status is GpuJobStatus.SUCCEEDED:
            seconds = _seconds(job)
            await lines.say(
                SMOKE_PASSED,
                {"try": number, "seconds": round(seconds, 1)},
                f"Try {number}: the smoke test passed in {seconds:.0f} s",
            )
            return job
        if job.status is GpuJobStatus.CANCELLED:
            raise StageFailedError(
                f"coding.job_cancelled: the smoke job of try {number} ({job.id}) was cancelled "
                "outside the run"
            )
        failure = code.smoke_failed(job)
        await lines.say(
            SMOKE_FAILED,
            {"try": number, "error_code": failure.error_code},
            f"Try {number}: the smoke test failed ({failure.error_code})",
        )
        if failure.error_code in HOST_FAILURES:
            # The GPU host failed the job (a missing image or dataset folder, a lost container),
            # not the code: another try would fail the same way.
            raise StageFailedError(f"coding.smoke_failed: {failure.error_code}: {job.error or ''}")
        if failure.error_code == CODE_REFUSED and job.code == written.code:
            # The checks above passed this code, and the GPU host runs the same checker (the
            # executor before the container starts, the harness inside it): its refusal means
            # another version of it there, an executor not restarted or a sandbox image not
            # rebuilt since the checker changed. Another try would be refused the same way, with
            # findings that contradict the prompt.
            raise StageFailedError(
                "coding.checker_mismatch: the GPU host refused code that passes the worker's "
                "checks, so it runs another version of the checker (restart the executor, or "
                f"rebuild the sandbox image): {job.error or ''}"
            )
        return failure


def _no_dataset(name: str | None) -> str:
    if name is None:
        return "the run names no dataset"
    return f'"{name}" is not a registered, enabled dataset the harness can train on'


def _smoke_job(number: int, dataset: str, written: Written) -> JobSpec:
    """The dry run of a try's code: one epoch of a few batches, at the smallest batch size."""
    return JobSpec(
        kind=GpuJobKind.SMOKE,
        ordinal=number,
        dataset=dataset,
        code=dict(written.code),
        config=harness_config(
            dataset,
            model_kwargs=dict(written.model_kwargs),
            loss=written.loss,
            training=written.training.model_dump(),
            batch_size=code.SMOKE_BATCH_SIZE,
            epochs=1,
            max_train_steps=code.SMOKE_STEPS,
            max_val_steps=code.SMOKE_STEPS,
        ),
        timeout_seconds=SMOKE_TIMEOUT_SECONDS,
    )


def _output(dataset: str, written: Written, job: GpuJob) -> CodingOutput:
    """The code that passed its smoke test, with config.json: what it passed with and what the
    smoke test measured, for the experiment stage."""
    results = job.result or {}
    config = CodeConfig(
        dataset=dataset,
        model_kwargs=dict(written.model_kwargs),
        loss=written.loss,
        training=written.training,
        smoke=SmokeMeasure(
            job_id=str(job.id),
            batch_size=code.SMOKE_BATCH_SIZE,
            peak_gpu_memory_mb=_megabytes(results.get("peak_gpu_memory_bytes")),
            steps_per_second=_rate(results.get("steps_per_second")),
            param_count=_count(results.get("param_count")),
        ),
    )
    files = [
        CodeFile(path=name, language="python", role=_ROLES[name], content=source)
        for name, source in written.code.items()
    ]
    files.append(
        CodeFile(
            path=CONFIG_FILE,
            language="json",
            role="config",
            content=config.model_dump_json(indent=2) + "\n",
        )
    )
    return CodingOutput(
        summary=written.summary,
        files=files,
        entrypoint=f"{MODEL_FILE}:{MODEL_CLASS}",
        smoke_test=SmokeTest(
            passed=True, duration_seconds=_seconds(job), log=code.log_tail(job.log_tail or "")
        ),
    )


def _seconds(job: GpuJob) -> float:
    """How long the smoke test took: the job's GPU seconds, else the harness's own count."""
    if job.gpu_seconds is not None:
        return max(job.gpu_seconds, 0.0)
    return _rate((job.result or {}).get("duration_s")) or 0.0


# results.json comes out of the sandbox: each of its numbers is checked before it is kept.


def _count(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _rate(value: object) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else None
    return None


def _megabytes(value: object) -> int | None:
    count = _count(value)
    return None if count is None else math.ceil(count / 1024**2)

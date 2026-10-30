"""The experiment stage: one training job of the approved code on the lab GPU, and its output.

docs/design/experiments.md ("The stages"). The approved coding output carries model.py (and
loss.py) and the config.json it passed its smoke test with; the stage plans a bounded training run
from them (agentic_worker.experiment.plan), runs it as the attempt's one training job and waits for
its end, then reads what it measured from the database (agentic_worker.experiment.output).

A training job that fails, times out or is cancelled outside the run is still an output, for the
reviewer to judge; only inputs the job could not run with fail the stage. A cancel of the run
propagates: GpuJobs cancels the job and waits until the executor has stopped it.
"""

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.contracts import EventType
from agentic_core.enums import GpuJobKind
from agentic_core.schemas import CodingOutput
from agentic_core.stages import Stage
from agentic_db.gpu_jobs import find_job
from agentic_db.models import GpuJob, RunEvent
from agentic_worker.experiment.output import dataset_warnings, experiment_output, finished_line
from agentic_worker.experiment.plan import approved_code, free_memory, plan_training
from agentic_worker.gpu import GpuJobs, JobSpec, executor_status
from agentic_worker.outputs import EXPERIMENT_PROMPT_VERSION, STAGE_DEMO_REASON
from agentic_worker.progress import ProgressLines
from agentic_worker.stages import StageContext, StageFailedError, StageOutcome
from agentic_worker.upstream import approved_input

log = logging.getLogger(__name__)

# Progress lines (codes the web translates; params as below). The job's own queued and running
# lines come from GpuJobs, and the executor's experiment.epoch events carry the live curves.
PLANNED = "experiment.planned"  # {epochs, steps, batch_size}
FINISHED = "experiment.finished"  # {status, epochs}: the epochs the job completed
# The degraded reason the web shows when the harness warned about the dataset (depth units that
# differ between the splits, say): the metrics can't be trusted until the dataset is checked.
DATASET_WARNING_REASON = "experiment.dataset_warning"
# Each attempt is a stage run of its own, with one training job.
TRAIN_ORDINAL = 1


class ExperimentRunner:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        gpu: GpuJobs,
        *,
        epochs: int,
        steps_per_epoch: int,
        max_train_hours: float,
    ) -> None:
        self._sessions = sessions
        self._gpu = gpu
        self._epochs = epochs
        self._steps_per_epoch = steps_per_epoch
        self._timeout_seconds = round(max_train_hours * 3600)

    async def run(self, ctx: StageContext) -> StageOutcome:
        coding = approved_input(ctx, Stage.CODING, CodingOutput)
        if ctx.degraded_inputs.get(Stage.CODING.value) == STAGE_DEMO_REASON:
            raise StageFailedError(
                "experiment.demo_code: the approved code is a demo output that never ran; retry "
                "the run from the coding stage to train real code"
            )
        code = approved_code(coding)
        lines = await ProgressLines.resume(ctx, self._sessions)
        submitted = await self._submitted(ctx)
        dataset = await self._gpu.dataset(code.config.dataset)
        reason: str | None = None
        if submitted is not None:
            # An earlier try of this attempt submitted the job, and said so: it trains as planned
            # then, whatever the GPU's memory (its own training may fill it) or the dataset's
            # registration is now.
            log.info("run %s: waiting again on training job %s", ctx.run_id, submitted.id)
            name, config = submitted.dataset, submitted.config
        elif dataset is None:
            raise StageFailedError(
                f"experiment.no_dataset: {code.config.dataset!r} is not a registered, enabled "
                "dataset the harness trains on"
            )
        else:
            plan = plan_training(
                code.config,
                epochs=self._epochs,
                steps_per_epoch=self._steps_per_epoch,
                memory=free_memory(await self._executor_status()),
            )
            name, config = dataset.name, plan.harness_config(dataset.name)
            reason = plan.batch.reason
            await lines.say(PLANNED, *plan.progress())
        spec = JobSpec(
            kind=GpuJobKind.TRAIN,
            ordinal=TRAIN_ORDINAL,
            dataset=name,
            code=code.files,
            config=config,
            timeout_seconds=self._timeout_seconds,
        )
        job = await self._gpu.run(ctx, spec, lines)
        if job.config != config:  # another try of the attempt submitted it first
            reason = None
        output = experiment_output(
            job, await self._epoch_events(job), dataset=dataset, batch_reason=reason
        )
        await lines.say(FINISHED, *finished_line(output, job.error_code))
        warned = bool(dataset_warnings(job.result if isinstance(job.result, dict) else {}))
        return StageOutcome(
            data=output.model_dump(mode="json"),
            degraded=warned,
            degraded_reason=DATASET_WARNING_REASON if warned else None,
            prompt_version=EXPERIMENT_PROMPT_VERSION,
        )

    async def _submitted(self, ctx: StageContext) -> GpuJob | None:
        """The attempt's training job, if an earlier try of the attempt submitted it."""
        async with self._sessions() as session:
            return await find_job(
                session, uuid.UUID(ctx.stage_run_id), GpuJobKind.TRAIN, TRAIN_ORDINAL
            )

    async def _executor_status(self) -> dict[str, Any] | None:
        async with self._sessions() as session:
            return await executor_status(session)

    async def _epoch_events(self, job: GpuJob) -> list[dict[str, Any]]:
        """The payloads of the job's experiment.epoch events, as the executor wrote them. Once
        the job has ended there are no more: the executor reports an epoch only while it runs."""
        async with self._sessions() as session:
            payloads = await session.scalars(
                select(RunEvent.payload)
                .where(
                    RunEvent.run_id == job.run_id,
                    RunEvent.type == EventType.EXPERIMENT_EPOCH,
                    RunEvent.payload.contains({"job_id": str(job.id)}),
                )
                .order_by(RunEvent.seq)
            )
            return list(payloads)

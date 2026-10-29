"""Run the worker: `python -m agentic_worker` (see `make worker`)."""

import os

# CrewAI must not phone home (docs/PLAN.md); set before anything imports crewai.
for _name, _value in {
    "CREWAI_DISABLE_TELEMETRY": "true",
    "CREWAI_TRACING_ENABLED": "false",
    "OTEL_SDK_DISABLED": "true",
}.items():
    os.environ.setdefault(_name, _value)

import asyncio  # noqa: E402
import logging  # noqa: E402

import redis.asyncio as redis  # noqa: E402
from pydantic import SecretStr  # noqa: E402
from pydantic_settings import BaseSettings, SettingsConfigDict  # noqa: E402
from temporalio.client import Client  # noqa: E402
from temporalio.worker import Worker  # noqa: E402

from agentic_core.contracts import TASK_QUEUE  # noqa: E402
from agentic_db import create_engine, session_factory  # noqa: E402
from agentic_worker.activities import StageActivities  # noqa: E402
from agentic_worker.stages import PipelineStageRunner  # noqa: E402
from agentic_worker.workflows import RunWorkflow  # noqa: E402


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARP_", env_file=".env", extra="ignore")

    database_url: str = ""
    valkey_url: str = "redis://localhost:6379/0"
    temporal_address: str = "localhost:7233"
    gateway_url: str = "http://127.0.0.1:8100"
    gateway_token: SecretStr = SecretStr("")
    max_concurrent_activities: int = 4  # the dev box has 4 cores and 7.7 GiB


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = WorkerSettings()
    engine = create_engine(settings.database_url)
    valkey = redis.from_url(settings.valkey_url)
    activities = StageActivities(
        session_factory(engine),
        valkey,
        PipelineStageRunner(settings.gateway_url, settings.gateway_token.get_secret_value()),
    )
    client = await Client.connect(settings.temporal_address)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[RunWorkflow],
        activities=[
            activities.start_stage,
            activities.execute_stage,
            activities.record_decision,
            activities.finish_run,
        ],
        max_concurrent_activities=settings.max_concurrent_activities,
    )
    logging.getLogger(__name__).info("worker listening on task queue %s", TASK_QUEUE)
    try:
        await worker.run()
    finally:
        await valkey.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

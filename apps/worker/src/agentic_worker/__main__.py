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
from datetime import timedelta  # noqa: E402

import redis.asyncio as redis  # noqa: E402
from temporalio.client import Client  # noqa: E402
from temporalio.worker import Worker  # noqa: E402

from agentic_core.contracts import TASK_QUEUE  # noqa: E402
from agentic_db import create_engine, session_factory  # noqa: E402
from agentic_worker.activities import HEARTBEAT_SECONDS, StageActivities  # noqa: E402
from agentic_worker.agents import StageAgents, gateway_llms  # noqa: E402
from agentic_worker.literature.library import Sessions  # noqa: E402
from agentic_worker.literature.runner import LiteratureRunner  # noqa: E402
from agentic_worker.literature.sources import Scholarly, open_scholarly  # noqa: E402
from agentic_worker.method.runner import MethodRunner  # noqa: E402
from agentic_worker.settings import WorkerSettings  # noqa: E402
from agentic_worker.stages import CrewAIPlanner, PipelineStageRunner  # noqa: E402
from agentic_worker.workflows import RunWorkflow  # noqa: E402
from agentic_worker.writing.runner import WritingRunner  # noqa: E402


def stage_runner(
    settings: WorkerSettings, sessions: Sessions, valkey: redis.Redis
) -> tuple[PipelineStageRunner, Scholarly | None]:
    """The stages the settings ask for, and the scholarly clients a real literature stage opened
    (the caller closes them)."""
    gateway_token = settings.gateway_token.get_secret_value()
    planner = CrewAIPlanner(settings.gateway_url, gateway_token)
    agents = StageAgents(gateway_llms(settings.gateway_url, gateway_token))
    real_llm_stages = settings.llm_stages == "real"
    scholarly: Scholarly | None = None
    literature: LiteratureRunner | None = None
    if settings.literature_search == "real":
        # The source rate limits share this Valkey: they are lab-wide.
        scholarly = open_scholarly(settings, valkey)
        literature = LiteratureRunner(planner, scholarly, sessions, agents)
    runner = PipelineStageRunner(
        planner,
        literature=literature,
        method=MethodRunner(agents, sessions) if real_llm_stages else None,
        writing=WritingRunner(agents, sessions) if real_llm_stages else None,
        # A real search records its papers in the library itself.
        demo_library=sessions if literature is None else None,
        demo_stage_seconds=settings.demo_stage_seconds,
    )
    return runner, scholarly


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = WorkerSettings()
    engine = create_engine(settings.database_url)
    sessions = session_factory(engine)
    # Wake-ups only spare SSE a poll: a Valkey that hangs must not hold up an activity.
    valkey = redis.from_url(settings.valkey_url, socket_connect_timeout=2, socket_timeout=2)
    runner, scholarly = stage_runner(settings, sessions, valkey)
    activities = StageActivities(sessions, valkey, runner)
    client = await Client.connect(settings.temporal_address)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[RunWorkflow],
        activities=activities.all(),
        max_concurrent_activities=settings.max_concurrent_activities,
        # A cancel reaches a running stage in a heartbeat response, and the run closes only
        # once the stage has stopped: send every heartbeat instead of one a minute.
        max_heartbeat_throttle_interval=timedelta(seconds=HEARTBEAT_SECONDS),
    )
    logging.getLogger(__name__).info(
        "worker listening on task queue %s (literature search: %s, LLM stages: %s)",
        TASK_QUEUE,
        settings.literature_search,
        settings.llm_stages,
    )
    try:
        await worker.run()
    finally:
        if scholarly is not None:
            await scholarly.aclose()
        await valkey.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

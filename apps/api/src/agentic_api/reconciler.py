"""Starts the workflows of runs whose start was lost.

create_run commits a run before it starts the run's workflow (the worker must find the row).
If the API dies in between, the run would stay queued forever. Every API instance therefore
runs a pass in the background that starts the workflow of each run still queued without one
once the run is older than a grace period.

Several instances may pass at the same time: a run is claimed with a row lock the others skip,
and starting a workflow that already runs changes nothing (TemporalOrchestrator.start_run).
"""

import asyncio
import logging
import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_api.orchestrator import Orchestrator, OrchestratorUnavailableError
from agentic_core.enums import RunStatus
from agentic_db.models import Run

log = logging.getLogger(__name__)
# Well over the time create_run needs from its commit to storing the workflow id (it gives up
# on Temporal after orchestrator.RPC_TIMEOUT and marks the run failed).
GRACE = timedelta(minutes=1)
INTERVAL_SECONDS = 30.0
BATCH = 50  # starts per pass at most


async def start_unstarted_runs(
    sessions: async_sessionmaker[AsyncSession],
    orchestrator: Orchestrator,
    *,
    grace: timedelta = GRACE,
) -> list[uuid.UUID]:
    """One pass: start the workflow of every run that has been queued without one for longer
    than ``grace``; returns the runs it started.

    Seeded demo runs never qualify: the seed writes them finished or paused, or starts their
    workflow right after their row.
    """
    started: list[uuid.UUID] = []
    failed: list[uuid.UUID] = []
    for _ in range(BATCH):
        async with sessions() as session:
            run = await session.scalar(
                select(Run)
                .where(
                    Run.status == RunStatus.QUEUED,
                    Run.workflow_id.is_(None),
                    Run.created_at < func.now() - grace,  # the database's clock, as created_at
                    Run.id.not_in(failed),
                )
                .order_by(Run.created_at, Run.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if run is None:
                break
            try:
                run.workflow_id = await orchestrator.start_run(run.id)
            except OrchestratorUnavailableError:
                log.warning("Temporal is unavailable; queued runs wait for the next pass")
                break
            except Exception:
                log.exception("could not start the workflow of run %s", run.id)
                failed.append(run.id)
                continue
            await session.commit()
            log.warning("started the workflow of run %s, whose start was lost", run.id)
            started.append(run.id)
    return started


async def reconcile_forever(
    sessions: async_sessionmaker[AsyncSession],
    orchestrator: Orchestrator,
    *,
    interval_seconds: float = INTERVAL_SECONDS,
) -> None:
    """A pass every ``interval_seconds`` until cancelled (a background task of the API)."""
    while True:
        try:
            await start_unstarted_runs(sessions, orchestrator)
        except Exception:  # Postgres unreachable, say: try again at the next pass
            log.warning("could not look for queued runs without a workflow", exc_info=True)
        await asyncio.sleep(interval_seconds)

"""The stages' progress lines, and the ones an attempt that runs again wrote before it stopped.

Each line is a run event (``StageActivities._logger``): a code and params the web translates,
plus an English message. An attempt runs again after a gateway wait, a pause for the lab balance
or a crash; it reads back its earlier lines so that no step is reported twice.
"""

import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.contracts import EventType
from agentic_db.models import RunEvent
from agentic_worker.stages import StageContext


async def attempt_lines(
    sessions: async_sessionmaker[AsyncSession], run_id: uuid.UUID, stage: str, attempt: int
) -> list[dict[str, Any]]:
    """The log payloads of ``stage`` written since this attempt's stage.started event, in order."""
    started = (
        select(func.coalesce(func.max(RunEvent.seq), 0))
        .where(
            RunEvent.run_id == run_id,
            RunEvent.type == EventType.STAGE_STARTED,
            RunEvent.payload.contains({"stage": stage, "attempt": attempt}),
        )
        .scalar_subquery()
    )
    async with sessions() as session:
        return list(
            await session.scalars(
                select(RunEvent.payload)
                .where(
                    RunEvent.run_id == run_id,
                    RunEvent.type == EventType.LOG,
                    RunEvent.seq > started,
                    RunEvent.payload.contains({"stage": stage}),
                )
                .order_by(RunEvent.seq)
            )
        )


def _line(code: str, params: dict[str, Any]) -> str:
    return json.dumps([code, params], sort_keys=True, ensure_ascii=False)


@dataclass(frozen=True)
class ProgressLines:
    """Writes an attempt's progress lines, each line (its code and params) once per attempt."""

    ctx: StageContext
    earlier: frozenset[str] = frozenset()

    @classmethod
    async def resume(
        cls, ctx: StageContext, sessions: async_sessionmaker[AsyncSession]
    ) -> "ProgressLines":
        """The lines of an attempt, knowing those it wrote before it last stopped."""
        payloads = await attempt_lines(sessions, uuid.UUID(ctx.run_id), ctx.stage, ctx.attempt)
        written = (_line(str(p.get("code")), p.get("params", {})) for p in payloads)
        return cls(ctx, frozenset(written))

    async def say(self, code: str, params: dict[str, Any], message: str) -> None:
        if _line(code, params) in self.earlier:
            return  # written before this attempt last stopped
        await self.ctx.log(code, params, message)

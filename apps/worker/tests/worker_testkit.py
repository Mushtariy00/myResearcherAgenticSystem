"""Fakes for worker tests: a stage runner without LLMs and a Valkey that accepts publishes."""

import asyncio
from dataclasses import dataclass, field

from agentic_worker.stages import StageContext, StageFailedError, StageOutcome


@dataclass
class FakeRunner:
    fail_stage: str | None = None
    block_stage: str | None = None  # this stage runs until the activity is cancelled
    blocked: asyncio.Event = field(default_factory=asyncio.Event)
    seen: list[StageContext] = field(default_factory=list)

    async def run(self, ctx: StageContext) -> StageOutcome:
        self.seen.append(ctx)
        if ctx.stage == self.fail_stage:
            raise StageFailedError(f"{ctx.stage}.invalid_output: the model returned prose")
        if ctx.stage == self.block_stage:
            self.blocked.set()
            await asyncio.Event().wait()  # never set: only cancellation ends this
        return StageOutcome(
            data={"stage": ctx.stage, "attempt": ctx.attempt, "feedback": ctx.feedback},
            model="fake/model",
        )


class FakeValkey:
    def __init__(self) -> None:
        self.published: list[str] = []

    async def publish(self, channel: str, message: str) -> int:
        self.published.append(channel)
        return 1

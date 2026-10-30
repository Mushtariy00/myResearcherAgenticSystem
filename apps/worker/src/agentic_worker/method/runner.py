"""The method stage: research gaps and method proposals from the approved literature review."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.schemas import LiteratureOutput
from agentic_core.stages import Stage
from agentic_worker.agents import StageAgents
from agentic_worker.method import proposals
from agentic_worker.outputs import METHOD_PROMPT_VERSION
from agentic_worker.progress import ProgressLines
from agentic_worker.stages import StageContext, StageOutcome
from agentic_worker.upstream import approved_input, generated_literature

log = logging.getLogger(__name__)

PROPOSED = "method.proposed"
# The degraded reason the web shows when the review the methods build on was generated.
DEMO_LITERATURE_REASON = "method.demo_literature"


class MethodRunner:
    def __init__(self, agents: StageAgents, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._agents = agents
        self._sessions = sessions

    async def run(self, ctx: StageContext) -> StageOutcome:
        literature = approved_input(ctx, Stage.LITERATURE, LiteratureOutput)
        lines = await ProgressLines.resume(ctx, self._sessions)
        answer = await self._agents.ask(ctx, proposals.request(ctx, literature))
        output = answer.value.output
        if answer.value.unknown_evidence:
            log.warning(
                "run %s: dropped %d evidence ids that name no paper of the literature review",
                ctx.run_id,
                answer.value.unknown_evidence,
            )
        count, gaps = len(output.proposals), len(output.research_gaps)
        await lines.say(
            PROPOSED,
            {"proposals": count, "gaps": gaps},
            f"Proposed {count} methods for {gaps} research gaps",
        )
        reason = DEMO_LITERATURE_REASON if generated_literature(ctx) else None
        return StageOutcome(
            data=output.model_dump(mode="json"),
            model=answer.model,
            degraded=reason is not None,
            degraded_reason=reason,
            prompt_version=METHOD_PROMPT_VERSION,
            llm_calls=answer.calls,
        )

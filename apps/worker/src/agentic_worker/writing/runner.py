"""The writing stage: an outline, one call per section, then the draft the code assembles.

Sections are written one at a time, each seeing the outline. The calls' keys are deterministic
(``<stage run id>:writing:outline``, ``...:writing:section:<n>``), so an attempt that runs again
gets the finished ones replayed from the gateway journal, for free, and goes on from there.
"""

from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.schemas import WritingOutput
from agentic_worker.agents import StageAgents
from agentic_worker.outputs import WRITING_PROMPT_VERSION
from agentic_worker.progress import ProgressLines
from agentic_worker.stages import StageContext, StageOutcome
from agentic_worker.upstream import generated_literature
from agentic_worker.writing import draft, outline, sections
from agentic_worker.writing.research import research

OUTLINED = "writing.outlined"
DRAFTED = "writing.drafted"
CITED = "writing.cited"
# Degraded reasons the web shows (stage_outputs.degraded_reason); the first one wins. Generated
# literature comes first: then the draft cites made-up papers, whatever else holds.
DEMO_LITERATURE_REASON = "writing.demo_literature"
SIMULATED_RESULTS_REASON = "writing.simulated_results"
CITATIONS_REMOVED_REASON = "writing.citations_removed"


def _previous(ctx: StageContext) -> WritingOutput | None:
    """The draft a request-changes attempt revises, if it is one."""
    if ctx.previous_output is None:
        return None
    try:
        return WritingOutput.model_validate(ctx.previous_output)
    except ValidationError:
        return None  # a Phase 1 placeholder: there is no draft to revise, only the comments


class WritingRunner:
    def __init__(self, agents: StageAgents, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._agents = agents
        self._sessions = sessions

    async def run(self, ctx: StageContext) -> StageOutcome:
        inputs = research(ctx)
        previous = _previous(ctx)
        lines = await ProgressLines.resume(ctx, self._sessions)
        calls: list[dict[str, Any]] = []

        planned = await self._agents.ask(ctx, outline.request(ctx, inputs, previous))
        calls.extend(planned.calls)
        plan, model = planned.value, planned.model
        total = len(plan.sections)
        await lines.say(OUTLINED, {"sections": total}, f"Outlined {total} sections")

        earlier = sections.previous_sections(previous.markdown) if previous else {}
        bodies: list[str] = []
        for index, section in enumerate(plan.sections, start=1):
            known = earlier.get(section.name.casefold())
            written = await self._agents.ask(ctx, sections.request(ctx, inputs, plan, index, known))
            calls.extend(written.calls)
            bodies.append(written.value)
            model = written.model
            await lines.say(
                DRAFTED,
                {"section": section.name, "index": index, "sections": total},
                f"Drafted {section.name} ({index}/{total})",
            )

        output, removed = draft.writing_output(plan, bodies, inputs.literature.papers)
        cited = len(output.citations)
        message = f"Cited {cited} {'paper' if cited == 1 else 'papers'}"
        if removed:
            message += f"; removed {removed} citations of papers that are not in the list"
        await lines.say(CITED, {"citations": cited, "removed": removed}, message)
        reason = None
        if generated_literature(ctx):
            reason = DEMO_LITERATURE_REASON
        elif inputs.simulated:
            reason = SIMULATED_RESULTS_REASON
        elif removed:
            reason = CITATIONS_REMOVED_REASON
        return StageOutcome(
            data=output.model_dump(mode="json"),
            model=model,  # of the last call, as the literature stage reports its synthesis's
            degraded=reason is not None,
            degraded_reason=reason,
            prompt_version=WRITING_PROMPT_VERSION,
            llm_calls=calls,
        )

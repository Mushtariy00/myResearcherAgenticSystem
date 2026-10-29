"""What each stage produces. Phase 1: literature returns a real search plan from a CrewAI agent;
the other stages return clearly flagged placeholders (degraded=True) until Phases 2 and 3.
"""

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import Field

from agentic_core.schemas import NonEmptyStr, StrictModel
from agentic_worker.gateway_llm import GatewayLLM
from agentic_worker.llm_json import InvalidModelOutputError, parse_model_output

PROMPT_VERSION = "literature-plan@1"


class StageFailedError(Exception):
    """The stage cannot produce a valid output; retrying the same input won't help."""


@dataclass(frozen=True)
class StageContext:
    run_id: str
    stage_run_id: str
    stage: str
    attempt: int
    feedback: str
    topic: str
    owner_id: str
    project_id: str
    llm_policy: str
    budget_cap_usd: str | None


@dataclass
class StageOutcome:
    data: dict[str, Any]
    model: str | None = None
    degraded: bool = False
    degraded_reason: str | None = None
    prompt_version: str | None = None
    llm_calls: list[dict[str, Any]] = field(default_factory=list)


class StageRunner(Protocol):
    async def run(self, ctx: StageContext) -> StageOutcome: ...


class ResearchPlan(StrictModel):
    topic: NonEmptyStr
    queries: list[NonEmptyStr] = Field(min_length=3, max_length=8)
    scope: NonEmptyStr
    inclusion_criteria: list[NonEmptyStr] = Field(min_length=1)
    subtopics: list[NonEmptyStr] = Field(min_length=1)


# Ported from legacy/src/agentic_ai_system/config/agents.yaml ("researcher").
RESEARCHER = {
    "role": "{topic} Senior Data Researcher",
    "goal": "Uncover cutting-edge developments in {topic}",
    "backstory": (
        "You're a seasoned researcher with a knack for uncovering the latest developments in "
        "{topic}. Known for your ability to find the most relevant information and present it "
        "in a clear and concise manner."
    ),
}

PLAN_PROMPT = """Plan a literature search on this research topic: {topic}
{feedback}
Return ONLY a JSON object with exactly these keys:
- "topic": the topic restated precisely
- "queries": 3 to 6 search queries suitable for arXiv and Semantic Scholar
- "scope": 2-3 sentences on what is in and out of scope
- "inclusion_criteria": the criteria a paper must meet to be included
- "subtopics": the main subtopics the review should cover"""

REPAIR_PROMPT = """Your previous answer could not be used: {error}
Previous answer:
{answer}
Return ONLY the corrected JSON object with the keys topic, queries, scope, inclusion_criteria,
subtopics."""


class PipelineStageRunner:
    def __init__(self, gateway_url: str, gateway_token: str) -> None:
        self._gateway_url = gateway_url
        self._gateway_token = gateway_token

    async def run(self, ctx: StageContext) -> StageOutcome:
        if ctx.stage == "literature":
            return await asyncio.to_thread(self._literature_plan, ctx)
        return StageOutcome(
            data={
                "stage": ctx.stage,
                "note": f"The {ctx.stage} stage is a placeholder in Phase 1; "
                "it is built in later phases.",
            },
            degraded=True,
            degraded_reason="stage.placeholder",
        )

    def _llm(self, ctx: StageContext) -> GatewayLLM:
        return GatewayLLM(
            model="gateway",  # CrewAI requires a model name; the gateway picks the real one
            gateway_url=self._gateway_url,
            gateway_token=self._gateway_token,
            user_id=ctx.owner_id,
            agent_role="researcher",
            key_prefix=ctx.stage_run_id,
            run_id=ctx.run_id,
            project_id=ctx.project_id,
            policy=ctx.llm_policy,
            budget_cap_usd=ctx.budget_cap_usd,
            max_output_tokens=1500,
        )

    def _literature_plan(self, ctx: StageContext) -> StageOutcome:
        from crewai import Agent  # imported late: heavy, and only needed in agent activities

        llm = self._llm(ctx)
        agent = Agent(
            role=RESEARCHER["role"].format(topic=ctx.topic),
            goal=RESEARCHER["goal"].format(topic=ctx.topic),
            backstory=RESEARCHER["backstory"].format(topic=ctx.topic),
            llm=llm,
            allow_delegation=False,
            max_iter=2,
            verbose=False,
        )
        feedback = (
            f"\nReviewer feedback on the previous version, address it:\n{ctx.feedback}\n"
            if ctx.feedback
            else ""
        )
        result = agent.kickoff(PLAN_PROMPT.format(topic=ctx.topic, feedback=feedback))
        if isinstance(result, Coroutine):  # only when called inside an event loop; we use a thread
            result.close()
            raise StageFailedError("crewai.kickoff_returned_coroutine")
        answer = str(result.raw)
        try:
            plan = parse_model_output(answer, ResearchPlan)
        except InvalidModelOutputError as first_error:
            repaired = llm.call(REPAIR_PROMPT.format(error=first_error, answer=answer[:4000]))
            try:
                plan = parse_model_output(repaired, ResearchPlan)
            except InvalidModelOutputError as exc:
                raise StageFailedError(f"literature.invalid_output: {exc}") from exc
        return StageOutcome(
            data=plan.model_dump(),
            model=llm.calls[-1]["model"] if llm.calls else None,
            # Honest about scope: Phase 2 adds the actual search, screening and analysis.
            degraded=True,
            degraded_reason="literature.search_pending",
            prompt_version=PROMPT_VERSION,
            llm_calls=list(llm.calls),
        )

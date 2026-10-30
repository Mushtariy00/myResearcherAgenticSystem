"""What each stage produces.

Literature runs its real CrewAI research-plan step, then fills in search, screening and
analysis with demo data until Phase 2 builds them. Method, coding, experiment and writing
return demo outputs (``agentic_core.demo``) built on the approved outputs of the stages before
them. Every demo output is flagged degraded, and each simulated stage takes a while and reports
its progress as log events, so the front end sees what a real run looks like.
"""

import asyncio
import json
import logging
import threading
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from pydantic import ValidationError

from agentic_core import demo
from agentic_core.schemas import (
    CodingOutput,
    ExperimentOutput,
    LiteratureOutput,
    MethodOutput,
    ResearchPlan,
    RunConfig,
    StrictModel,
)
from agentic_core.stages import Stage
from agentic_worker.gateway_llm import GatewayLLM
from agentic_worker.llm_json import InvalidModelOutputError, parse_model_output
from agentic_worker.outputs import (
    DEMO_PROMPT_VERSION,
    LITERATURE_DEMO_REASON,
    PLAN_PROMPT_VERSION,
    STAGE_DEMO_REASON,
    demo_seed,
    progress_steps,
)

log = logging.getLogger(__name__)

DEFAULT_DEMO_STAGE_SECONDS = 6.0
MAX_DEMO_STAGE_SECONDS = 20 * 60.0  # well inside execute_stage's 30-minute timeout

# Appends one progress line (code, params, English message) to the run's event log.
type LogEvent = Callable[[str, dict[str, Any], str], Awaitable[None]]


async def _discard_log(code: str, params: dict[str, Any], message: str) -> None:
    """Progress sink for contexts built outside an activity (unit tests, scripts)."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


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
    config: RunConfig = field(default_factory=RunConfig)
    # Approved outputs of the earlier stages of this run, keyed by stage (the latest approval).
    inputs: Mapping[str, dict[str, Any]] = field(default_factory=dict)
    # Per-run override of the simulated stage duration (runs.config "demo_stage_seconds").
    demo_stage_seconds: float | None = None
    log: LogEvent = _discard_log
    # A request-changes attempt: the output the reviewer asked to change, and every comment
    # that led to this attempt, oldest first (``feedback`` is the latest one).
    previous_output: Mapping[str, Any] | None = None
    feedback_history: tuple[str, ...] = ()
    # Set when the attempt ends without an output (a cancel too): work still running in a
    # thread then makes no more gateway calls.
    cancelled: threading.Event = field(default_factory=threading.Event)
    # Each gateway answer as it arrives: an attempt that fails has still paid for them.
    llm_calls: list[dict[str, Any]] = field(default_factory=list)


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


@dataclass(frozen=True)
class PlannedSearch:
    plan: ResearchPlan
    model: str | None = None
    llm_calls: list[dict[str, Any]] = field(default_factory=list)


class ResearchPlanner(Protocol):
    """Writes the literature search plan (the stage's one real LLM step for now)."""

    async def plan(self, ctx: StageContext) -> PlannedSearch: ...


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
{revision}
Return ONLY a JSON object with exactly these keys:
- "topic": the topic restated precisely
- "queries": 3 to 6 search queries suitable for arXiv and Semantic Scholar
- "scope": 2-3 sentences on what is in and out of scope
- "inclusion_criteria": the criteria a paper must meet to be included
- "subtopics": the main subtopics the review should cover"""

REVISED_PLAN = """
The reviewer asked for changes to your previous plan. Revise that plan: keep what the reviewer
did not ask to change.
Previous plan:
{plan}
"""

REVIEWER_FEEDBACK = """
Reviewer feedback, oldest first; address every point:
{comments}
"""

REPAIR_PROMPT = """Your previous answer could not be used: {error}
Previous answer:
{answer}
Return ONLY the corrected JSON object with the keys topic, queries, scope, inclusion_criteria,
subtopics."""


def plan_prompt(ctx: StageContext) -> str:
    """The research-plan request; a request-changes attempt shows the plan it revises."""
    revision = ""
    if ctx.previous_output is not None:
        # The plan inside a literature output; Phase 1 stored the plan on its own.
        plan = ctx.previous_output.get("plan", ctx.previous_output)
        revision += REVISED_PLAN.format(plan=json.dumps(plan, ensure_ascii=False, indent=2))
    if ctx.feedback_history:
        comments = "\n".join(f"{n}. {c}" for n, c in enumerate(ctx.feedback_history, 1))
        revision += REVIEWER_FEEDBACK.format(comments=comments)
    return PLAN_PROMPT.format(topic=ctx.topic, revision=revision)


class CrewAIPlanner:
    """The literature research plan from a CrewAI agent, through the LLM gateway."""

    def __init__(self, gateway_url: str, gateway_token: str) -> None:
        self._gateway_url = gateway_url
        self._gateway_token = gateway_token

    async def plan(self, ctx: StageContext) -> PlannedSearch:
        return await asyncio.to_thread(self._plan, ctx)

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
            cancelled=ctx.cancelled,  # also stops the repair call below
            on_call=ctx.llm_calls.append,
        )

    def _plan(self, ctx: StageContext) -> PlannedSearch:
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
        result = agent.kickoff(plan_prompt(ctx))
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
        return PlannedSearch(
            plan=plan,
            model=llm.calls[-1]["model"] if llm.calls else None,
            llm_calls=list(llm.calls),
        )


class PipelineStageRunner:
    def __init__(
        self,
        planner: ResearchPlanner,
        *,
        demo_stage_seconds: float = DEFAULT_DEMO_STAGE_SECONDS,
        clock: Callable[[], datetime] = _utc_now,  # the demo seed backdates finished runs
    ) -> None:
        self._planner = planner
        self._demo_stage_seconds = demo_stage_seconds
        self._clock = clock

    async def run(self, ctx: StageContext) -> StageOutcome:
        try:
            stage = Stage(ctx.stage)
        except ValueError:
            raise StageFailedError(f"stage.unknown: {ctx.stage}") from None
        if stage is Stage.LITERATURE:
            planned = await self._planner.plan(ctx)
            seed = demo_seed(ctx.run_id, ctx.stage, ctx.attempt)
            output = demo.literature(ctx.topic, planned.plan, ctx.config, seed, ctx.feedback)
            await self._simulate(ctx, output)
            return StageOutcome(
                data=output.model_dump(mode="json"),
                model=planned.model,
                # Honest about scope: the plan is real, the papers are generated (Phase 2).
                degraded=True,
                degraded_reason=LITERATURE_DEMO_REASON,
                prompt_version=PLAN_PROMPT_VERSION,
                llm_calls=planned.llm_calls,
            )
        output = self._demo_output(ctx, stage)
        await self._simulate(ctx, output)
        return StageOutcome(
            data=output.model_dump(mode="json"),
            degraded=True,
            degraded_reason=STAGE_DEMO_REASON,
            prompt_version=DEMO_PROMPT_VERSION,
        )

    def stage_seconds(self, ctx: StageContext) -> float:
        seconds = self._demo_stage_seconds
        if ctx.demo_stage_seconds is not None:
            seconds = ctx.demo_stage_seconds
        return min(MAX_DEMO_STAGE_SECONDS, max(0.0, seconds))

    async def _simulate(self, ctx: StageContext, output: StrictModel) -> None:
        """Spread the stage's duration over its progress lines (the caller heartbeats)."""
        steps = progress_steps(output, ctx.config)
        pause = self.stage_seconds(ctx) / len(steps)
        for step in steps:
            await ctx.log(step.code, step.params, step.message)
            await asyncio.sleep(pause)

    def _demo_output(self, ctx: StageContext, stage: Stage) -> StrictModel:
        seed = demo_seed(ctx.run_id, ctx.stage, ctx.attempt)
        if stage is Stage.METHOD:
            return demo.method(
                ctx.topic, self._literature(ctx), seed, ctx.feedback, config=ctx.config
            )
        if stage is Stage.CODING:
            # One seed for all attempts: attempt n revises attempt n - 1 (a readable diff).
            return demo.coding(
                ctx.topic,
                self._method(ctx),
                demo_seed(ctx.run_id, ctx.stage),
                ctx.attempt,
                ctx.feedback,
            )
        if stage is Stage.EXPERIMENT:
            finished = self._clock() + timedelta(seconds=self.stage_seconds(ctx))
            return demo.experiment(
                ctx.topic, self._coding(ctx), seed, feedback=ctx.feedback, finished_at=finished
            )
        return demo.writing(
            ctx.topic,
            self._literature(ctx),
            self._method(ctx),
            self._experiment(ctx),
            seed,
            ctx.feedback,
        )

    # Approved outputs of earlier stages. Runs started in Phase 1 approved placeholders that
    # predate the v1 schemas; those are rebuilt from the generators instead of failing the run.

    def _approved[ModelT: StrictModel](
        self, ctx: StageContext, stage: Stage, model: type[ModelT], rebuild: Callable[[], ModelT]
    ) -> ModelT:
        data = ctx.inputs.get(stage.value)
        if data is None:
            raise StageFailedError(f"{ctx.stage}.missing_input: no approved {stage.value} output")
        try:
            return model.model_validate(data)
        except ValidationError:
            log.warning("run %s: approved %s output predates the v1 schema", ctx.run_id, stage)
            return rebuild()

    def _literature(self, ctx: StageContext) -> LiteratureOutput:
        def rebuild() -> LiteratureOutput:
            try:  # a Phase 1 literature output is the plan on its own
                plan = ResearchPlan.model_validate(ctx.inputs["literature"])
            except ValidationError:
                plan = demo.research_plan(
                    ctx.topic, demo_seed(ctx.run_id, "plan"), config=ctx.config
                )
            seed = demo_seed(ctx.run_id, Stage.LITERATURE, 1)
            return demo.literature(ctx.topic, plan, ctx.config, seed)

        return self._approved(ctx, Stage.LITERATURE, LiteratureOutput, rebuild)

    def _method(self, ctx: StageContext) -> MethodOutput:
        def rebuild() -> MethodOutput:
            seed = demo_seed(ctx.run_id, Stage.METHOD, 1)
            return demo.method(ctx.topic, self._literature(ctx), seed, config=ctx.config)

        return self._approved(ctx, Stage.METHOD, MethodOutput, rebuild)

    def _coding(self, ctx: StageContext) -> CodingOutput:
        def rebuild() -> CodingOutput:
            seed = demo_seed(ctx.run_id, Stage.CODING)
            return demo.coding(ctx.topic, self._method(ctx), seed)

        return self._approved(ctx, Stage.CODING, CodingOutput, rebuild)

    def _experiment(self, ctx: StageContext) -> ExperimentOutput:
        def rebuild() -> ExperimentOutput:
            seed = demo_seed(ctx.run_id, Stage.EXPERIMENT, 1)
            return demo.experiment(ctx.topic, self._coding(ctx), seed)

        return self._approved(ctx, Stage.EXPERIMENT, ExperimentOutput, rebuild)

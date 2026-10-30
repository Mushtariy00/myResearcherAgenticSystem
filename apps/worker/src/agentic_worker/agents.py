"""The stages' CrewAI agents: no tools, every call through the LLM gateway.

Each step asks a fresh agent with its own GatewayLLM, so its calls get the step's semantic
idempotency keys (``<key prefix>:call-<n>``) and an attempt that runs again replays them. An
answer that is not what the step needs gets one repair request, as the plan step does; a second
unusable answer fails the stage (``<stage>.invalid_output``).
"""

import asyncio
import re
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, replace
from typing import Any, Protocol

from agentic_worker.gateway_llm import AttemptEndedError, GatewayLLM
from agentic_worker.llm_json import InvalidModelOutputError
from agentic_worker.stages import StageContext, StageFailedError

# The gateway refuses longer idempotency keys; ":call-<n>" still has to fit.
MAX_KEY_PREFIX = 160
_ECHOED_ANSWER_CHARS = 4000
# A marker that could end a data block early ("--- END PAPER TEXT ---").
_MARKER = re.compile(r"-{3,}(?=\s*(?:BEGIN|END)\b)", re.IGNORECASE)

REPAIR_PROMPT = """Your previous answer could not be used: {error}
Return ONLY the corrected JSON object, in this form:
{shape}"""
# Free reasoning models write their reasoning into the answer; the live check saw one spend a
# whole screening budget on it and never reach the JSON.
JSON_ONLY = "Answer with the JSON object alone, starting with {: no reasoning or notes around it."
CUT_OFF = (
    "it ran out of room ({tokens} tokens) before the JSON was complete; answer with the JSON "
    "object alone, without reasoning"
)


@dataclass(frozen=True)
class Persona:
    """Role, goal and backstory of a CrewAI agent; ``{topic}`` is filled in per run."""

    role: str
    goal: str
    backstory: str

    def on(self, topic: str) -> "Persona":
        return replace(
            self,
            role=self.role.format(topic=topic),
            goal=self.goal.format(topic=topic),
            backstory=self.backstory.format(topic=topic),
        )


@dataclass(frozen=True)
class Request[T]:
    """One question to an agent, and how to read its answer."""

    role: str  # the gateway role, e.g. literature.screen
    key_prefix: str  # e.g. "<stage run id>:screen:2"
    max_output_tokens: int
    persona: Persona
    prompt: str
    parse: Callable[[str], T]  # raises InvalidModelOutputError
    shape: str  # the form the repair request restates
    # The repair request, and what it says of an answer cut off at its budget; an answer that
    # is not a JSON object (a section of the draft) words them for its own form.
    repair: str = REPAIR_PROMPT
    cut_off: str = CUT_OFF


@dataclass(frozen=True)
class Answer[T]:
    value: T
    model: str | None  # the model of the last call (the repair, if there was one)
    calls: list[dict[str, Any]]


class LlmFactory(Protocol):
    def __call__(
        self, ctx: StageContext, *, role: str, key_prefix: str, max_output_tokens: int
    ) -> GatewayLLM: ...


def gateway_llms(gateway_url: str, gateway_token: str) -> LlmFactory:
    """GatewayLLMs that charge the run's owner and stop calling once the attempt ends."""

    def make(
        ctx: StageContext, *, role: str, key_prefix: str, max_output_tokens: int
    ) -> GatewayLLM:
        return GatewayLLM(
            model="gateway",  # CrewAI requires a model name; the gateway picks the real one
            gateway_url=gateway_url,
            gateway_token=gateway_token,
            user_id=ctx.owner_id,
            agent_role=role,
            key_prefix=key_prefix,
            run_id=ctx.run_id,
            project_id=ctx.project_id,
            policy=ctx.llm_policy,
            budget_cap_usd=ctx.budget_cap_usd,
            max_output_tokens=max_output_tokens,
            cancelled=ctx.cancelled,  # also stops the repair call
            on_call=ctx.llm_calls.append,
        )

    return make


def fenced(label: str, text: str) -> str:
    """text between BEGIN and END markers, for prompts that call it data, never instructions.
    Marker-like dashes inside the text are shortened, so it cannot end the block early."""
    return f"--- BEGIN {label} ---\n{_MARKER.sub('-', text).strip()}\n--- END {label} ---"


class StageAgents:
    def __init__(self, make_llm: LlmFactory) -> None:
        self._make_llm = make_llm

    async def ask[T](self, ctx: StageContext, request: Request[T]) -> Answer[T]:
        if ctx.cancelled.is_set():  # the attempt has ended: it asks nothing more
            raise AttemptEndedError(ctx.stage_run_id)
        if len(request.key_prefix) > MAX_KEY_PREFIX:
            raise ValueError(f"idempotency key prefix too long: {request.key_prefix[:60]}...")
        return await asyncio.to_thread(self._ask, ctx, request)

    def _ask[T](self, ctx: StageContext, request: Request[T]) -> Answer[T]:
        from crewai import Agent  # imported late: heavy, and only needed in agent activities

        llm = self._make_llm(
            ctx,
            role=request.role,
            key_prefix=request.key_prefix,
            max_output_tokens=request.max_output_tokens,
        )
        persona = request.persona
        agent = Agent(
            role=persona.role,
            goal=persona.goal,
            backstory=persona.backstory,
            llm=llm,
            allow_delegation=False,
            max_iter=2,
            verbose=False,
        )
        result = agent.kickoff(request.prompt)
        if isinstance(result, Coroutine):  # only when called inside an event loop; we use a thread
            result.close()
            raise StageFailedError("crewai.kickoff_returned_coroutine")
        answer = str(result.raw)
        try:
            value = request.parse(answer)
        except InvalidModelOutputError as first_error:
            error = str(first_error)
            used = llm.calls[-1].get("completion_tokens") if llm.calls else None
            if isinstance(used, int) and used >= request.max_output_tokens:
                error = request.cut_off.format(tokens=used)
            # The repair sees the request again: a missing decision cannot be fixed without it.
            repaired = llm.call(
                [
                    {"role": "user", "content": request.prompt},
                    {"role": "assistant", "content": answer[:_ECHOED_ANSWER_CHARS]},
                    {
                        "role": "user",
                        "content": request.repair.format(error=error, shape=request.shape),
                    },
                ]
            )
            try:
                value = request.parse(repaired)
            except InvalidModelOutputError as exc:
                raise StageFailedError(
                    f"{ctx.stage}.invalid_output: {request.role}: {exc}"
                ) from exc
        return Answer(
            value=value,
            model=llm.calls[-1]["model"] if llm.calls else None,
            calls=list(llm.calls),
        )

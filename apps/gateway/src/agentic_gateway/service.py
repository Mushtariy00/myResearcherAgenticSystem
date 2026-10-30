"""Routing and the spend journal: paid while the budget allows, free otherwise (ADR 0004).

Every attempt is an `llm_calls` row: reserved → sent → settled | unknown | released.
Budget checks run under a per-user advisory lock, so concurrent runs can't overspend. Each
idempotency key is answered by one request at a time, so a retry never pays for a call twice.
"""

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import and_, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.enums import LlmCallState, LlmPolicy, LlmTier, Privacy
from agentic_db.models import LlmCall, Project, Run, Setting
from agentic_db.spend import month_spend, monthly_budget, run_spend
from agentic_gateway.catalog import Catalog, ModelInfo
from agentic_gateway.openrouter import (
    KNOWN_UPSTREAM_ERRORS,
    AccountBalanceError,
    AuthError,
    ChatResult,
    FreeDailyLimitError,
    KeyLimitError,
    NoAnswerError,
    OpenRouterClient,
    UpstreamError,
    UpstreamInterruptedError,
    UpstreamRateLimitError,
)
from agentic_gateway.quota import FreeQuota

log = logging.getLogger(__name__)

DEFAULT_MAX_OUTPUT_TOKENS = 2048
CHARS_PER_TOKEN = 3.5  # conservative: overestimating tokens only makes the reservation larger
DEFAULT_PAID_MODELS = ("google/gemini-2.5-flash", "openai/gpt-4.1-mini")
# Free models change often; unlisted ones are skipped and the catalog fills in text models.
# Nemotron first: on 2026-10-30 Gemma answered empty or rate-limited on every live call.
DEFAULT_FREE_MODELS = ("nvidia/nemotron-3-ultra-550b-a55b:free", "google/gemma-4-31b-it:free")
PAID_MODELS_SETTING = "paid_models_enabled"
# Passive model health (docs/PLAN.md: from real call outcomes, no probes). A model that answered
# empty, or that its provider rate-limited, moves to the back of its chain for a while: each
# free try spends a unit of the daily quota whether or not an answer comes back.
EMPTY_ANSWER_COOLDOWN_SECONDS = 600.0
# With less time than this left before the call's deadline no attempt starts: it would likely be
# cut off, and a paid one billed all the same.
MIN_ATTEMPT_SECONDS = 5.0
IN_PROGRESS_RETRY_SECONDS = 30.0  # how long a retry waits while its key is still being answered
# Advisory lock class of the per-key locks: the two-key form has a key space of its own, apart
# from the budget locks.
CALL_LOCK_CLASS = 1
# Unknown calls the sweeper can't look up are settled at their reservation, the most they can
# have cost: without a generation id after an hour (nothing will ever report their cost), with
# one once /generation has had a day to report it.
UNRECONCILED_AFTER = timedelta(hours=1)
LOOKUP_FOR = timedelta(days=1)
SWEEP_BATCH = 50  # /generation lookups per sweep
GENERATION_TIMEOUT_SECONDS = 10


class NoModelAvailableError(Exception):
    """Every model in the chain failed or none is listed in the catalog."""


class DeadlineExceededError(Exception):
    """The call's overall deadline ran out before a model answered."""


class FreeModelsDisabledError(Exception):
    """The project forbids free models and paid ones are ruled out: the budget, the run cap, the
    kill switch, a free-only run or a key limit. Retrying doesn't change that."""


class RunInactiveError(Exception):
    """The run has ended (or is gone): nothing would use the answer, so nothing is spent on it."""


class CallInProgressError(Exception):
    """Another request for this idempotency key is still being answered."""

    retry_after = IN_PROGRESS_RETRY_SECONDS


@dataclass(frozen=True)
class CompletionRequest:
    idempotency_key: str  # stable per stage attempt and call index, so crash replays are free
    user_id: str  # the run owner: spend is charged to them
    role: str
    messages: list[dict[str, str]]
    run_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    policy: LlmPolicy = LlmPolicy.AUTO
    budget_cap_usd: Decimal | None = None
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    json_mode: bool = False


@dataclass(frozen=True)
class CompletionResult:
    content: str
    model: str
    tier: LlmTier
    cost_usd: Decimal
    prompt_tokens: int | None
    completion_tokens: int | None
    switched_to_free: bool  # a paid call hit an OpenRouter key limit or budget
    replayed: bool  # answered from the journal after a crash; nothing was spent


@dataclass(frozen=True)
class _Policy:
    deny_data_collection: bool  # a confidential project
    allow_free: bool
    paid_enabled: bool  # the admin kill switch is off


def estimate_tokens(messages: list[dict[str, str]]) -> int:
    return int(sum(len(m.get("content", "")) for m in messages) / CHARS_PER_TOKEN) + 8 * len(
        messages
    )


class Router:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        catalog: Catalog,
        client: OpenRouterClient,
        quota: FreeQuota,
        *,
        paid_models: list[str] | None = None,
        free_models: list[str] | None = None,
        timeout: float = 120.0,
        deadline: float = 150.0,
        lease_seconds: int = 300,
    ) -> None:
        self._sessions = sessions
        self._catalog = catalog
        self._client = client
        self._quota = quota
        self._paid = list(paid_models or DEFAULT_PAID_MODELS)
        self._free = list(free_models or DEFAULT_FREE_MODELS)
        self._timeout = timeout  # one upstream attempt
        self._deadline = deadline  # the whole call, every attempt included
        self._lease = timedelta(seconds=lease_seconds)
        # Model id -> monotonic time until which it goes last in its chain (this process only).
        self._cooling: dict[str, float] = {}

    async def complete(self, req: CompletionRequest) -> CompletionResult:
        deadline = time.monotonic() + self._deadline
        async with self._exclusive(req.idempotency_key):
            policy = await self._policy(req)
            if (replayed := await self._replay(req.idempotency_key)) is not None:
                return replayed
            return await self._route(req, policy, deadline)

    async def _route(
        self, req: CompletionRequest, policy: _Policy, deadline: float
    ) -> CompletionResult:
        deny = policy.deny_data_collection
        prompt_tokens = estimate_tokens(req.messages)
        # Why paid routing stopped decides what a project without free models gets.
        ruled_out = req.policy == LlmPolicy.FREE or not policy.paid_enabled
        limited = False  # a key limit or budget at OpenRouter: the answer "switched to free"
        last_error: Exception | None = None

        if not ruled_out:
            chain = await self._chain(self._paid, prompt_tokens, req.max_output_tokens, free=False)
            for info in chain:
                if (timeout := self._attempt_timeout(deadline)) is None:
                    break
                call_id = await self._reserve_paid(req, info, prompt_tokens)
                if call_id is None:
                    ruled_out = True  # the budget or the run cap can't cover it: use free models
                    break
                try:
                    result = await self._send(call_id, info.id, req, deny, timeout)
                except KeyLimitError:
                    await self._finish(call_id, LlmCallState.RELEASED, "key_limit")
                    limited = True
                    break
                except UpstreamInterruptedError as exc:
                    # Maybe billed (the row stays unknown): don't pay a second model for the call.
                    log.warning("paid call %s kept at its reservation: %s", call_id, exc)
                    last_error = exc
                    break
                except AccountBalanceError as exc:
                    # Free models tell whether the lab balance is gone or this call was too large.
                    await self._finish(call_id, LlmCallState.RELEASED, type(exc).__name__)
                    last_error = exc
                    break
                except NoAnswerError as exc:
                    await self._settle_unanswered(call_id, exc)
                    self._cool(info.id, EMPTY_ANSWER_COOLDOWN_SECONDS)
                    last_error = exc
                    continue
                except (UpstreamError, UpstreamRateLimitError, FreeDailyLimitError) as exc:
                    await self._finish(call_id, LlmCallState.RELEASED, type(exc).__name__)
                    if isinstance(exc, UpstreamRateLimitError):
                        self._cool(info.id, exc.retry_after)
                    last_error = exc
                    continue
                except AuthError as exc:
                    await self._finish(call_id, LlmCallState.RELEASED, type(exc).__name__)
                    raise
                return await self._settle(call_id, result, LlmTier.PAID, result.cost_usd, False)

        if not policy.allow_free:
            # Fail the run only for what retrying can't change; upstream trouble passes.
            if limited or (ruled_out and last_error is None):
                raise FreeModelsDisabledError(req.project_id)
            raise last_error or _gave_up(deadline, "no paid model available")
        return await self._complete_free(req, deny, prompt_tokens, limited, deadline)

    async def _complete_free(
        self,
        req: CompletionRequest,
        deny: bool,
        prompt_tokens: int,
        switched: bool,
        deadline: float,
    ) -> CompletionResult:
        last_error: Exception | None = None
        for info in await self._chain(self._free, prompt_tokens, req.max_output_tokens, free=True):
            if (timeout := self._attempt_timeout(deadline)) is None:
                break
            await self._quota.acquire(req.user_id)  # raises when the caller has to wait
            call_id = await self._record(req, info.id, LlmTier.FREE, Decimal(0))
            try:
                result = await self._send(call_id, info.id, req, deny, timeout)
            except UpstreamInterruptedError as exc:
                last_error = exc  # the row stays unknown; trying another free model costs nothing
                continue
            except NoAnswerError as exc:
                await self._finish(call_id, LlmCallState.RELEASED, exc.reason)
                self._cool(info.id, EMPTY_ANSWER_COOLDOWN_SECONDS)
                last_error = exc
                continue
            except (UpstreamError, UpstreamRateLimitError) as exc:
                await self._finish(call_id, LlmCallState.RELEASED, type(exc).__name__)
                if isinstance(exc, UpstreamRateLimitError):
                    self._cool(info.id, exc.retry_after)
                last_error = exc
                continue
            except (AccountBalanceError, KeyLimitError, AuthError, FreeDailyLimitError) as exc:
                # Account-wide: every other free model would fail the same way.
                await self._finish(call_id, LlmCallState.RELEASED, type(exc).__name__)
                raise
            return await self._settle(call_id, result, LlmTier.FREE, Decimal(0), switched)
        if isinstance(last_error, UpstreamRateLimitError):
            raise last_error
        raise _gave_up(deadline, f"no free model answered (last error: {last_error!r})")

    def _attempt_timeout(self, deadline: float) -> float | None:
        """The next attempt's timeout: its own limit or the time left, whichever is shorter.
        None when too little time is left to start one."""
        left = deadline - time.monotonic()
        return min(self._timeout, left) if left >= MIN_ATTEMPT_SECONDS else None

    # --- journal -------------------------------------------------------------------------

    @asynccontextmanager
    async def _exclusive(self, key: str) -> AsyncIterator[None]:
        """Answer each idempotency key one request at a time. A retry that arrives while the
        first request is still being answered (the worker gave up waiting, or restarted) gets
        CallInProgressError instead of paying for the call again, and comes back when the
        journal can replay the answer."""
        async with self._sessions() as session:
            locked = await session.scalar(
                text("SELECT pg_try_advisory_xact_lock(:lock_class, hashtext(:key))"),
                {"lock_class": CALL_LOCK_CLASS, "key": key},
            )
            if not locked:
                raise CallInProgressError(key)
            yield  # held until the session closes, which ends its transaction

    async def _replay(self, key: str) -> CompletionResult | None:
        async with self._sessions() as session:
            call = await session.scalar(
                select(LlmCall)
                .where(LlmCall.idempotency_key.like(_prefix(key), escape="\\"))
                .where(LlmCall.response.is_not(None))
                .order_by(LlmCall.created_at.desc())
                .limit(1)
            )
        if call is None or call.response is None:
            return None
        return CompletionResult(
            content=str(call.response["content"]),
            model=call.model,
            tier=LlmTier(call.tier),
            cost_usd=call.cost_usd or Decimal(0),
            prompt_tokens=call.prompt_tokens,
            completion_tokens=call.completion_tokens,
            switched_to_free=False,
            replayed=True,
        )

    async def _reserve_paid(
        self, req: CompletionRequest, info: ModelInfo, prompt_tokens: int
    ) -> uuid.UUID | None:
        estimate = info.estimate_usd(prompt_tokens, req.max_output_tokens)
        async with self._sessions() as session, session.begin():
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": f"budget:{req.user_id}"},
            )
            budget = await monthly_budget(session, req.user_id)
            if await month_spend(session, req.user_id) + estimate > budget:
                return None
            if req.budget_cap_usd is not None:
                already = await run_spend(session, req.run_id) if req.run_id else Decimal(0)
                if already + estimate > req.budget_cap_usd:
                    return None
            return await self._insert(session, req, info.id, LlmTier.PAID, estimate)

    async def _record(
        self, req: CompletionRequest, model: str, tier: LlmTier, reserved: Decimal
    ) -> uuid.UUID:
        async with self._sessions() as session, session.begin():
            return await self._insert(session, req, model, tier, reserved)

    async def _insert(
        self,
        session: AsyncSession,
        req: CompletionRequest,
        model: str,
        tier: LlmTier,
        reserved: Decimal,
    ) -> uuid.UUID:
        attempts = len(
            (
                await session.scalars(
                    select(LlmCall.id).where(
                        LlmCall.idempotency_key.like(_prefix(req.idempotency_key), escape="\\")
                    )
                )
            ).all()
        )
        call = LlmCall(
            idempotency_key=f"{req.idempotency_key}#{attempts + 1}",
            run_id=req.run_id,
            user_id=req.user_id,
            role=req.role,
            tier=tier,
            model=model,
            state=LlmCallState.RESERVED,
            reserved_usd=reserved,
            lease_until=datetime.now(UTC) + self._lease,
        )
        session.add(call)
        await session.flush()
        return call.id

    async def _send(
        self,
        call_id: uuid.UUID,
        model: str,
        req: CompletionRequest,
        deny: bool,
        request_timeout: float,
    ) -> ChatResult:
        await self._update(call_id, state=LlmCallState.SENT)
        try:
            return await self._client.chat(
                model=model,
                messages=req.messages,
                max_tokens=req.max_output_tokens,
                json_mode=req.json_mode,
                deny_data_collection=deny,
                request_timeout=request_timeout,
            )
        except KNOWN_UPSTREAM_ERRORS:
            raise  # the caller records these
        except BaseException as exc:
            # Lost after sending, cancelled or crashed mid-call: the provider may still bill it.
            # Keep counting the reservation until the sweeper settles it.
            await self._finish(call_id, LlmCallState.UNKNOWN, type(exc.__cause__ or exc).__name__)
            raise

    async def _settle(
        self,
        call_id: uuid.UUID,
        result: ChatResult,
        tier: LlmTier,
        cost: Decimal | None,
        switched: bool,
    ) -> CompletionResult:
        response = {"content": result.content, "model": result.model}
        await self._update(call_id, **_answered(result, cost), response=response)
        return CompletionResult(
            content=result.content,
            model=result.model,
            tier=tier,
            cost_usd=cost or Decimal(0),
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            switched_to_free=switched,
            replayed=False,
        )

    async def _settle_unanswered(self, call_id: uuid.UUID, exc: NoAnswerError) -> None:
        """A paid call answered without an answer may still be billed: it counts at its reported
        cost, or stays unknown with its generation id for the sweeper. Nothing to replay."""
        await self._update(
            call_id, **_answered(exc.result, exc.result.cost_usd), error_class=exc.reason
        )

    async def _finish(self, call_id: uuid.UUID, state: LlmCallState, error: str) -> None:
        await self._update(call_id, state=state, error_class=error)

    async def _update(self, call_id: uuid.UUID, **values: Any) -> None:
        async with self._sessions() as session, session.begin():
            await session.execute(update(LlmCall).where(LlmCall.id == call_id).values(**values))

    # --- policy --------------------------------------------------------------------------

    async def _policy(self, req: CompletionRequest) -> _Policy:
        async with self._sessions() as session:
            if req.run_id is not None:
                # A cancelled run's stage can still be calling (its CrewAI thread outlives the
                # activity): the answers would be thrown away, the money would not.
                status = await session.scalar(select(Run.status).where(Run.id == req.run_id))
                if status is None or status.is_terminal:
                    raise RunInactiveError(req.run_id)
            project = await session.get(Project, req.project_id) if req.project_id else None
            setting = await session.get(Setting, PAID_MODELS_SETTING)
        return _Policy(
            deny_data_collection=project is not None and project.privacy == Privacy.CONFIDENTIAL,
            allow_free=project.allow_free_models if project is not None else True,
            paid_enabled=bool(setting.value.get("enabled", True)) if setting else True,
        )

    async def _chain(
        self, preferred: list[str], prompt_tokens: int, max_output: int, *, free: bool
    ) -> list[ModelInfo]:
        """Preferred models that the catalog lists and whose context fits the request."""
        models = await self._catalog.models()
        needed = prompt_tokens + max_output

        def fits(info: ModelInfo) -> bool:
            return (
                info.text_io
                and info.is_free == free
                and (info.context_length == 0 or info.context_length >= needed)
            )

        chain = [models[m] for m in preferred if m in models and fits(models[m])]
        if (
            free and not chain
        ):  # nothing preferred is listed: fall back to the catalog's free models
            extra = sorted((i for i in models.values() if fits(i)), key=lambda i: -i.context_length)
            chain = extra[:3]
        return self._by_health(chain)

    def _cool(self, model: str, seconds: float) -> None:
        until = time.monotonic() + seconds
        self._cooling[model] = max(self._cooling.get(model, 0.0), until)

    def _by_health(self, chain: list[ModelInfo]) -> list[ModelInfo]:
        """The chain with the models that failed lately at its back, each part in its order.
        None is dropped: when every model is cooling, they are all still tried."""
        now = time.monotonic()
        cooling = {info.id for info in chain if self._cooling.get(info.id, 0.0) > now}
        return [i for i in chain if i.id not in cooling] + [i for i in chain if i.id in cooling]

    # --- sweeper -------------------------------------------------------------------------

    async def sweep(self, http: httpx.AsyncClient, base_url: str, api_key: str) -> int:
        """Release expired never-sent reservations; settle unknown calls via /generation.

        The state changes commit first, and the lookups run outside any transaction: a slow
        /generation must not keep journal rows locked while live calls wait to settle them."""
        now = datetime.now(UTC)
        async with self._sessions() as session, session.begin():
            await session.execute(
                update(LlmCall)
                .where(LlmCall.state == LlmCallState.RESERVED, LlmCall.lease_until < now)
                .values(state=LlmCallState.RELEASED, error_class="lease_expired")
            )
            await session.execute(
                update(LlmCall)
                .where(LlmCall.state == LlmCallState.SENT, LlmCall.lease_until < now)
                .values(state=LlmCallState.UNKNOWN, error_class="lease_expired")
            )
            await session.execute(
                update(LlmCall)
                .where(
                    LlmCall.state == LlmCallState.UNKNOWN,
                    or_(
                        and_(
                            LlmCall.generation_id.is_(None),
                            LlmCall.created_at < now - UNRECONCILED_AFTER,
                        ),
                        LlmCall.created_at < now - LOOKUP_FOR,
                    ),
                )
                .values(
                    state=LlmCallState.SETTLED,
                    cost_usd=LlmCall.reserved_usd,
                    error_class="unreconciled",
                )
            )
        async with self._sessions() as session:
            pending = (
                await session.execute(
                    select(LlmCall.id, LlmCall.generation_id)
                    .where(
                        LlmCall.state == LlmCallState.UNKNOWN, LlmCall.generation_id.is_not(None)
                    )
                    .order_by(LlmCall.created_at.desc())
                    .limit(SWEEP_BATCH)
                )
            ).all()
        resolved = 0
        for call_id, generation_id in pending:
            try:
                cost = await _generation_cost(http, base_url, api_key, str(generation_id))
            except httpx.HTTPError as exc:
                log.warning("sweep stopped, /generation unreachable: %r", exc)
                break
            if cost is None:
                continue
            async with self._sessions() as session, session.begin():
                settled = await session.scalar(
                    update(LlmCall)
                    .where(LlmCall.id == call_id, LlmCall.state == LlmCallState.UNKNOWN)
                    .values(state=LlmCallState.SETTLED, cost_usd=cost)
                    .returning(LlmCall.id)
                )
            if settled is not None:
                resolved += 1
        return resolved


def _answered(result: ChatResult, cost: Decimal | None) -> dict[str, Any]:
    """Journal columns for a call OpenRouter answered. A paid call without a reported cost
    stays unknown (still counted at its reservation) until the sweeper finds the cost."""
    return {
        "state": LlmCallState.SETTLED if cost is not None else LlmCallState.UNKNOWN,
        "cost_usd": cost,
        "generation_id": result.generation_id,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "latency_ms": result.latency_ms,
        "lease_until": None,
    }


def _gave_up(deadline: float, reason: str) -> Exception:
    """Why a chain ended without an answer: out of time, or out of models."""
    if deadline - time.monotonic() < MIN_ATTEMPT_SECONDS:
        return DeadlineExceededError(reason)
    return NoModelAvailableError(reason)


async def _generation_cost(
    http: httpx.AsyncClient, base_url: str, api_key: str, generation_id: str
) -> Decimal | None:
    """The call's final cost from /generation; None while OpenRouter doesn't report one.
    Transport errors propagate: the sweep stops and the next one tries again."""
    response = await http.get(
        f"{base_url.rstrip('/')}/generation",
        params={"id": generation_id},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=GENERATION_TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        return None
    try:
        data: dict[str, Any] = response.json().get("data") or {}
        cost = data.get("total_cost")
        return Decimal(str(cost)) if cost is not None else None
    except (ValueError, AttributeError, ArithmeticError):
        return None


def _prefix(key: str) -> str:
    escaped = key.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"{escaped}#%"

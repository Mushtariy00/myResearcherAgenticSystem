"""Routing and the spend journal: paid while the budget allows, free otherwise (ADR 0004).

Every attempt is an `llm_calls` row: reserved → sent → settled | unknown | released.
Budget checks run under a per-user advisory lock, so concurrent runs can't overspend.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.enums import LlmCallState, LlmPolicy, LlmTier, Privacy
from agentic_db.models import LlmCall, Project, Setting
from agentic_db.spend import month_spend, monthly_budget, run_spend
from agentic_gateway.catalog import Catalog, ModelInfo
from agentic_gateway.openrouter import (
    KNOWN_UPSTREAM_ERRORS,
    AccountBalanceError,
    AuthError,
    ChatResult,
    FreeDailyLimitError,
    KeyLimitError,
    OpenRouterClient,
    UpstreamError,
    UpstreamRateLimitError,
)
from agentic_gateway.quota import FreeQuota

DEFAULT_MAX_OUTPUT_TOKENS = 2048
CHARS_PER_TOKEN = 3.5  # conservative: overestimating tokens only makes the reservation larger
DEFAULT_PAID_MODELS = ("google/gemini-2.5-flash", "openai/gpt-4.1-mini")
# Free models change often; unlisted ones are skipped and the catalog fills in text models.
DEFAULT_FREE_MODELS = ("google/gemma-4-31b-it:free", "nvidia/nemotron-3-ultra-550b-a55b:free")
PAID_MODELS_SETTING = "paid_models_enabled"


class NoModelAvailableError(Exception):
    """Every model in the chain failed or none is listed in the catalog."""


class FreeModelsDisabledError(Exception):
    """The project forbids free models and the budget can't pay for this call."""


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
    switched_to_free: bool  # a paid call hit the user's OpenRouter key limit
    replayed: bool  # answered from the journal after a crash; nothing was spent


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
        lease_seconds: int = 300,
    ) -> None:
        self._sessions = sessions
        self._catalog = catalog
        self._client = client
        self._quota = quota
        self._paid = list(paid_models or DEFAULT_PAID_MODELS)
        self._free = list(free_models or DEFAULT_FREE_MODELS)
        self._timeout = timeout
        self._lease = timedelta(seconds=lease_seconds)

    async def complete(self, req: CompletionRequest) -> CompletionResult:
        if (replayed := await self._replay(req.idempotency_key)) is not None:
            return replayed
        privacy, allow_free = await self._project_policy(req.project_id)
        deny = privacy == Privacy.CONFIDENTIAL
        prompt_tokens = estimate_tokens(req.messages)
        switched = False

        if req.policy == LlmPolicy.AUTO and await self._paid_enabled():
            for model in await self._chain(
                self._paid, prompt_tokens, req.max_output_tokens, free=False
            ):
                call_id = await self._reserve_paid(req, model, prompt_tokens)
                if call_id is None:
                    break  # the budget can't cover it: use free models
                try:
                    result = await self._send(call_id, model, req, deny)
                except KeyLimitError:
                    await self._finish(call_id, LlmCallState.RELEASED, "key_limit")
                    switched = True
                    break
                except (UpstreamError, UpstreamRateLimitError, FreeDailyLimitError) as exc:
                    await self._finish(call_id, LlmCallState.RELEASED, type(exc).__name__)
                    continue
                except (AccountBalanceError, AuthError) as exc:
                    await self._finish(call_id, LlmCallState.RELEASED, type(exc).__name__)
                    raise
                return await self._settle(call_id, result, LlmTier.PAID, result.cost_usd, False)

        if not allow_free:
            raise FreeModelsDisabledError(req.project_id)
        return await self._complete_free(req, deny, prompt_tokens, switched)

    async def _complete_free(
        self, req: CompletionRequest, deny: bool, prompt_tokens: int, switched: bool
    ) -> CompletionResult:
        last_error: Exception | None = None
        for model in await self._chain(self._free, prompt_tokens, req.max_output_tokens, free=True):
            await self._quota.acquire(req.user_id)  # raises QuotaExhaustedError → caller waits
            call_id = await self._record(req, model, LlmTier.FREE, Decimal(0))
            try:
                result = await self._send(call_id, model, req, deny)
            except (UpstreamError, UpstreamRateLimitError) as exc:
                await self._finish(call_id, LlmCallState.RELEASED, type(exc).__name__)
                last_error = exc
                continue
            except (AccountBalanceError, AuthError, FreeDailyLimitError) as exc:
                # The daily cap is account-wide: other free models would fail the same way.
                await self._finish(call_id, LlmCallState.RELEASED, type(exc).__name__)
                raise
            return await self._settle(call_id, result, LlmTier.FREE, Decimal(0), switched)
        if isinstance(last_error, UpstreamRateLimitError):
            raise last_error
        raise NoModelAvailableError(str(last_error) if last_error else "no free model available")

    # --- journal -------------------------------------------------------------------------

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
        self, req: CompletionRequest, model: str, prompt_tokens: int
    ) -> uuid.UUID | None:
        info = await self._catalog.get(model)
        if info is None:
            return None
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
            return await self._insert(session, req, model, LlmTier.PAID, estimate)

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
        self, call_id: uuid.UUID, model: str, req: CompletionRequest, deny: bool
    ) -> ChatResult:
        async with self._sessions() as session, session.begin():
            await session.execute(
                update(LlmCall).where(LlmCall.id == call_id).values(state=LlmCallState.SENT)
            )
        try:
            return await self._client.chat(
                model=model,
                messages=req.messages,
                max_tokens=req.max_output_tokens,
                json_mode=req.json_mode,
                deny_data_collection=deny,
                request_timeout=self._timeout,
            )
        except KNOWN_UPSTREAM_ERRORS:
            raise  # the caller releases the reservation: these responses cost nothing
        except BaseException:
            # Cancelled or crashed mid-call: the provider may still bill it. Keep counting the
            # reservation until the sweeper settles it.
            await self._finish(call_id, LlmCallState.UNKNOWN, "interrupted")
            raise

    async def _settle(
        self,
        call_id: uuid.UUID,
        result: ChatResult,
        tier: LlmTier,
        cost: Decimal | None,
        switched: bool,
    ) -> CompletionResult:
        # A paid call without a reported cost stays "unknown" (still counted) for the sweeper.
        state = LlmCallState.SETTLED if cost is not None else LlmCallState.UNKNOWN
        async with self._sessions() as session, session.begin():
            await session.execute(
                update(LlmCall)
                .where(LlmCall.id == call_id)
                .values(
                    state=state,
                    cost_usd=cost,
                    generation_id=result.generation_id,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                    latency_ms=result.latency_ms,
                    response={"content": result.content, "model": result.model},
                    lease_until=None,
                )
            )
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

    async def _finish(self, call_id: uuid.UUID, state: LlmCallState, error: str) -> None:
        async with self._sessions() as session, session.begin():
            await session.execute(
                update(LlmCall).where(LlmCall.id == call_id).values(state=state, error_class=error)
            )

    # --- policy --------------------------------------------------------------------------

    async def _project_policy(self, project_id: uuid.UUID | None) -> tuple[Privacy, bool]:
        if project_id is None:
            return Privacy.STANDARD, True
        async with self._sessions() as session:
            project = await session.get(Project, project_id)
        if project is None:
            return Privacy.STANDARD, True
        return Privacy(project.privacy), project.allow_free_models

    async def _paid_enabled(self) -> bool:
        async with self._sessions() as session:
            setting = await session.get(Setting, PAID_MODELS_SETTING)
        return bool(setting.value.get("enabled", True)) if setting else True

    async def _chain(
        self, preferred: list[str], prompt_tokens: int, max_output: int, *, free: bool
    ) -> list[str]:
        """Preferred models that the catalog lists and whose context fits the request."""
        models = await self._catalog.models()
        needed = prompt_tokens + max_output

        def fits(info: ModelInfo) -> bool:
            return (
                info.text_io
                and info.is_free == free
                and (info.context_length == 0 or info.context_length >= needed)
            )

        chain = [m for m in preferred if m in models and fits(models[m])]
        if (
            free and not chain
        ):  # nothing preferred is listed: fall back to the catalog's free models
            extra = sorted((i for i in models.values() if fits(i)), key=lambda i: -i.context_length)
            chain = [i.id for i in extra[:3]]
        return chain

    # --- sweeper -------------------------------------------------------------------------

    async def sweep(self, http: httpx.AsyncClient, base_url: str, api_key: str) -> int:
        """Release expired never-sent reservations; settle unknown calls via /generation."""
        now = datetime.now(UTC)
        resolved = 0
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
            unknown = (
                await session.scalars(
                    select(LlmCall).where(
                        LlmCall.state == LlmCallState.UNKNOWN, LlmCall.generation_id.is_not(None)
                    )
                )
            ).all()
            for call in unknown:
                cost = await _generation_cost(http, base_url, api_key, str(call.generation_id))
                if cost is not None:
                    call.cost_usd = cost
                    call.state = LlmCallState.SETTLED
                    resolved += 1
        return resolved


async def _generation_cost(
    http: httpx.AsyncClient, base_url: str, api_key: str, generation_id: str
) -> Decimal | None:
    try:
        response = await http.get(
            f"{base_url.rstrip('/')}/generation",
            params={"id": generation_id},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        if response.status_code != 200:
            return None
        data: dict[str, Any] = response.json().get("data") or {}
        cost = data.get("total_cost")
        return Decimal(str(cost)) if cost is not None else None
    except (httpx.HTTPError, ValueError):
        return None


def _prefix(key: str) -> str:
    escaped = key.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"{escaped}#%"

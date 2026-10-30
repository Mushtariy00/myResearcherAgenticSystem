"""Money rules: paid only while the budget covers it, never overspend, fall back to free."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import redis.exceptions
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.enums import LlmCallState, LlmPolicy, LlmTier, Privacy, RunStatus
from agentic_db.models import Budget, LlmCall, Project, Run, Setting
from agentic_db.spend import month_spend
from agentic_gateway.openrouter import (
    AccountBalanceError,
    AuthError,
    FreeDailyLimitError,
    KeyLimitError,
    UpstreamError,
    UpstreamRateLimitError,
)
from agentic_gateway.quota import FreeQuota, QuotaExhaustedError, QuotaUnavailableError
from agentic_gateway.service import (
    MIN_ATTEMPT_SECONDS,
    CallInProgressError,
    CompletionRequest,
    DeadlineExceededError,
    FreeModelsDisabledError,
    NoModelAvailableError,
    Router,
    RunInactiveError,
)
from gateway_testkit import (
    AUDIO,
    BASE_URL,
    FORBIDDEN,
    FREE_A,
    FREE_B,
    KEY_LIMIT,
    NO_CREDITS,
    OVERLOADED,
    PAID,
    PAID_BACKUP,
    UNAUTHORIZED,
    FakeCounter,
    FakeOpenRouter,
    budget_limit,
    daily_limit,
)

Factory = async_sessionmaker[AsyncSession]
MESSAGES = [{"role": "user", "content": "x" * 350}]  # ~100 tokens


def request(key: str = "stage-1:call-1", **kwargs: object) -> CompletionRequest:
    defaults: dict[str, object] = {
        "user_id": "bob",
        "role": "researcher",
        "messages": MESSAGES,
        "max_output_tokens": 1000,
    }
    return CompletionRequest(idempotency_key=key, **(defaults | kwargs))  # type: ignore[arg-type]


def variant(router: Router, **kwargs: object) -> Router:
    """The fixture's router with other settings, on the same fake OpenRouter and database."""
    options: dict[str, object] = {
        "quota": router._quota,
        "paid_models": [PAID, PAID_BACKUP],
        "free_models": [FREE_A, FREE_B],
        "timeout": 5,
    }
    return Router(
        router._sessions,
        router._catalog,
        router._client,
        **(options | kwargs),  # type: ignore[arg-type]
    )


async def set_budget(db: Factory, usd: str) -> None:
    async with db() as session:
        session.add(Budget(user_id="bob", monthly_usd=Decimal(usd), updated_by="root"))
        await session.commit()


async def calls(db: Factory) -> list[LlmCall]:
    async with db() as session:
        return list((await session.scalars(select(LlmCall).order_by(LlmCall.created_at))).all())


async def spent(db: Factory) -> Decimal:
    async with db() as session:
        return await month_spend(session, "bob")


async def add_project(db: Factory, **kwargs: object) -> Project:
    async with db() as session:
        project = Project(name="Lab", created_by="bob", **kwargs)
        session.add(project)
        await session.commit()
    return project


async def add_run(db: Factory, status: RunStatus) -> Run:
    project = await add_project(db)
    async with db() as session:
        run = Run(project_id=project.id, owner_id="bob", topic="Depth", status=status)
        session.add(run)
        await session.commit()
    return run


async def test_no_budget_means_free_models(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    result = await router.complete(request())
    assert (result.tier, result.model, result.cost_usd) == (LlmTier.FREE, FREE_A, Decimal(0))
    assert upstream.calls == [FREE_A]


async def test_paid_while_the_budget_allows_and_spend_is_the_real_cost(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    await set_budget(db, "1.00")
    result = await router.complete(request())
    assert (result.tier, result.model) == (LlmTier.PAID, PAID)
    assert result.cost_usd == Decimal("0.0021")
    [call] = await calls(db)
    assert call.state == LlmCallState.SETTLED
    assert await spent(db) == Decimal("0.0021")


async def test_free_policy_never_spends(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    await set_budget(db, "1.00")
    result = await router.complete(request(policy=LlmPolicy.FREE))
    assert result.tier == LlmTier.FREE
    assert upstream.calls == [FREE_A]


async def test_budget_too_small_for_the_estimate_uses_free(router: Router, db: Factory) -> None:
    await set_budget(db, "0.0001")  # the estimate for 1,000 output tokens is about $0.0021
    assert (await router.complete(request())).tier == LlmTier.FREE


async def test_concurrent_runs_cannot_overspend(router: Router, db: Factory) -> None:
    await set_budget(db, "0.003")  # covers one reservation (~$0.0021), not two
    results = await asyncio.gather(router.complete(request("a:1")), router.complete(request("b:1")))
    assert sorted(r.tier for r in results) == [LlmTier.FREE, LlmTier.PAID]
    assert await spent(db) <= Decimal("0.003")


async def test_run_cap_limits_paid_spend(router: Router, db: Factory) -> None:
    await set_budget(db, "1.00")
    result = await router.complete(request(budget_cap_usd=Decimal("0.0001")))
    assert result.tier == LlmTier.FREE


async def test_key_limit_switches_the_call_to_free(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    await set_budget(db, "1.00")
    upstream.plan[PAID].append(KEY_LIMIT)
    result = await router.complete(request())
    assert (result.tier, result.switched_to_free) == (LlmTier.FREE, True)
    assert [c.state for c in await calls(db)] == [LlmCallState.RELEASED, LlmCallState.SETTLED]


@pytest.mark.parametrize(
    "limit_source",
    ["openrouter_key_limit", "openrouter_guardrail_budget", "openrouter_workspace_budget"],
)
async def test_budget_limits_in_the_documented_403_form_switch_to_free(
    router: Router, upstream: FakeOpenRouter, db: Factory, limit_source: str
) -> None:
    await set_budget(db, "1.00")
    upstream.plan[PAID].append(budget_limit(403, limit_source))
    result = await router.complete(request())
    assert (result.tier, result.switched_to_free) == (LlmTier.FREE, True)
    assert upstream.calls == [PAID, FREE_A]  # a key-wide limit: no second paid model


async def test_a_key_limit_on_a_free_call_is_released_and_reported(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    upstream.plan[FREE_A].append(KEY_LIMIT)
    with pytest.raises(KeyLimitError):
        await router.complete(request())
    assert [c.state for c in await calls(db)] == [LlmCallState.RELEASED]
    assert upstream.calls == [FREE_A]


async def test_overloaded_paid_model_tries_the_next_paid_model(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    await set_budget(db, "1.00")
    upstream.plan[PAID].append(OVERLOADED)
    result = await router.complete(request())
    assert (result.tier, result.model) == (LlmTier.PAID, PAID_BACKUP)


async def test_a_call_that_never_left_costs_nothing(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    await set_budget(db, "1.00")
    upstream.plan[PAID].append(httpx.ConnectError("connection refused"))
    result = await router.complete(request())
    assert (result.tier, result.model) == (LlmTier.PAID, PAID_BACKUP)
    first, _ = await calls(db)
    assert first.state == LlmCallState.RELEASED
    assert await spent(db) == Decimal("0.0021")


@pytest.mark.parametrize(
    "lost",
    [httpx.ReadTimeout("no answer in time"), httpx.RemoteProtocolError("server disconnected")],
)
async def test_a_paid_call_lost_after_sending_keeps_its_reservation_and_no_other_is_paid(
    router: Router, upstream: FakeOpenRouter, db: Factory, lost: Exception
) -> None:
    await set_budget(db, "1.00")
    upstream.plan[PAID].append(lost)
    result = await router.complete(request())
    assert result.tier == LlmTier.FREE
    assert upstream.calls == [PAID, FREE_A]  # OpenRouter bills the lost call: no second paid one
    lost_call, _ = await calls(db)
    assert (lost_call.state, lost_call.error_class) == (LlmCallState.UNKNOWN, type(lost).__name__)
    assert await spent(db) == lost_call.reserved_usd > 0


async def test_a_paid_402_that_is_no_key_limit_falls_back_to_free(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    await set_budget(db, "1.00")
    upstream.plan[PAID].append(NO_CREDITS)
    result = await router.complete(request())
    assert result.tier == LlmTier.FREE
    assert upstream.calls == [PAID, FREE_A]
    assert [c.state for c in await calls(db)] == [LlmCallState.RELEASED, LlmCallState.SETTLED]


async def test_the_lab_balance_is_exhausted_only_when_free_models_fail_too(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    await set_budget(db, "1.00")
    upstream.plan[PAID].append(NO_CREDITS)
    upstream.plan[FREE_A].append(NO_CREDITS)
    with pytest.raises(AccountBalanceError):
        await router.complete(request())
    assert upstream.calls == [PAID, FREE_A]


async def test_credit_held_by_calls_in_flight_means_wait_and_retry(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    await set_budget(db, "1.00")
    project = await add_project(db, allow_free_models=False)
    in_flight = {"code": 402, "metadata": {"limit_source": "openrouter_in_flight_budget"}}
    for model in (PAID, PAID_BACKUP):
        upstream.plan[model].append(
            httpx.Response(402, headers={"Retry-After": "7"}, json={"error": in_flight})
        )
    with pytest.raises(UpstreamRateLimitError) as exc:
        await router.complete(request(project_id=project.id))
    assert exc.value.retry_after == 7


async def test_an_answer_without_content_counts_at_its_reported_cost(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    await set_budget(db, "1.00")
    thought_only = {  # a thinking model that spent max_tokens on reasoning
        "id": "gen-thought",
        "model": PAID,
        "choices": [{"message": {"content": ""}, "finish_reason": "length"}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 1000, "cost": 0.002},
    }
    upstream.plan[PAID].append((200, thought_only))
    result = await router.complete(request())
    assert result.model == PAID_BACKUP
    unanswered, _ = await calls(db)
    assert (unanswered.state, unanswered.cost_usd) == (LlmCallState.SETTLED, Decimal("0.002"))
    assert (unanswered.error_class, unanswered.response) == ("empty_answer", None)
    assert await spent(db) == Decimal("0.002") + Decimal("0.0021")


async def test_an_error_answer_without_a_cost_is_settled_by_the_sweeper(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    await set_budget(db, "1.00")
    upstream.plan[PAID].append((200, {"id": "gen-broken", "error": {"code": 502, "message": "x"}}))
    assert (await router.complete(request())).model == PAID_BACKUP
    broken, _ = await calls(db)
    assert (broken.state, broken.generation_id) == (LlmCallState.UNKNOWN, "gen-broken")

    upstream.costs["gen-broken"] = 0.0007
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream.handler)) as http:
        assert await router.sweep(http, BASE_URL, "test-key") == 1
    broken, _ = await calls(db)
    assert (broken.state, broken.cost_usd) == (LlmCallState.SETTLED, Decimal("0.0007"))


async def test_a_project_without_free_models_retries_upstream_trouble(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    await set_budget(db, "1.00")
    project = await add_project(db, allow_free_models=False)
    upstream.plan[PAID].append(OVERLOADED)
    upstream.plan[PAID_BACKUP].append(httpx.ConnectError("network blip"))
    with pytest.raises(UpstreamError):  # 502: the worker retries; not 403, which fails the run
        await router.complete(request(project_id=project.id))

    listed_nowhere = variant(router, paid_models=["gone/model"])
    with pytest.raises(NoModelAvailableError):
        await listed_nowhere.complete(request("stage-1:call-2", project_id=project.id))


async def test_projects_can_forbid_free_models(router: Router, db: Factory) -> None:
    project = await add_project(db, allow_free_models=False)
    with pytest.raises(FreeModelsDisabledError):
        await router.complete(request(project_id=project.id))


async def test_a_key_limit_is_final_for_a_project_without_free_models(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    await set_budget(db, "1.00")
    project = await add_project(db, allow_free_models=False)
    upstream.plan[PAID].append(OVERLOADED)
    upstream.plan[PAID_BACKUP].append(KEY_LIMIT)
    with pytest.raises(FreeModelsDisabledError):
        await router.complete(request(project_id=project.id))


async def test_a_retry_while_the_call_is_in_flight_does_not_pay_again(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    await set_budget(db, "1.00")
    upstream.hold = asyncio.Event()
    first = asyncio.create_task(router.complete(request("stage-5:call-1")))
    async with asyncio.timeout(5):
        await upstream.sent.wait()  # the first request is waiting for OpenRouter's answer
        with pytest.raises(CallInProgressError):  # not a second request to OpenRouter
            await router.complete(request("stage-5:call-1"))
    upstream.hold.set()
    answer = await first
    again = await router.complete(request("stage-5:call-1"))
    assert (again.replayed, again.content) == (True, answer.content)
    assert upstream.calls == [PAID]


async def test_each_attempt_gets_at_most_the_time_left(
    router: Router, upstream: FakeOpenRouter
) -> None:
    await variant(router, timeout=120, deadline=8).complete(request())
    [timeout] = upstream.timeouts
    assert MIN_ATTEMPT_SECONDS <= timeout <= 8


async def test_no_attempt_starts_when_the_deadline_is_near(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    upstream.plan[FREE_A].append(OVERLOADED)
    upstream.delays[FREE_A] = 1.2
    tight = variant(router, deadline=MIN_ATTEMPT_SECONDS + 1)
    with pytest.raises(DeadlineExceededError):
        await tight.complete(request())
    assert upstream.calls == [FREE_A]  # FREE_B would have had less than MIN_ATTEMPT_SECONDS


async def test_a_finished_run_gets_no_more_calls(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    await set_budget(db, "1.00")
    cancelled = await add_run(db, RunStatus.CANCELLED)
    with pytest.raises(RunInactiveError):
        await router.complete(request(run_id=cancelled.id))
    with pytest.raises(RunInactiveError):  # deleted, or never existed
        await router.complete(request(run_id=uuid.uuid4()))
    assert upstream.calls == []
    assert await calls(db) == []


async def test_a_run_paused_for_the_lab_balance_still_calls(router: Router, db: Factory) -> None:
    paused = await add_run(db, RunStatus.PAUSED_BUDGET)  # its retries probe for a top-up
    assert (await router.complete(request(run_id=paused.id))).tier == LlmTier.FREE


async def test_free_chain_falls_over(router: Router, upstream: FakeOpenRouter) -> None:
    upstream.plan[FREE_A].append(OVERLOADED)
    result = await router.complete(request())
    assert result.model == FREE_B
    assert upstream.calls == [FREE_A, FREE_B]


async def test_empty_lab_balance_stops_even_free_calls(
    router: Router, upstream: FakeOpenRouter
) -> None:
    upstream.plan[FREE_A].append(NO_CREDITS)
    with pytest.raises(AccountBalanceError):
        await router.complete(request())


async def test_free_quota_is_enforced(
    db: Factory, upstream: FakeOpenRouter, router: Router
) -> None:
    limited = variant(
        router,
        quota=FreeQuota(FakeCounter(), per_minute=1, per_day=1000, per_user_per_day=300),
        free_models=[FREE_A],
    )
    await limited.complete(request("q:1"))
    with pytest.raises(QuotaExhaustedError) as exc:
        await limited.complete(request("q:2"))
    assert exc.value.scope == "minute"
    assert 0 < exc.value.retry_after <= 60


async def test_free_calls_wait_while_valkey_is_down(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    class Down(FakeCounter):
        async def incr(self, name: str) -> int:
            raise redis.exceptions.ConnectionError("Error 111 connecting to 127.0.0.1:6379.")

    down = variant(router, quota=FreeQuota(Down(), per_minute=20, per_day=50, per_user_per_day=20))
    with pytest.raises(QuotaUnavailableError):
        await down.complete(request())
    assert upstream.calls == []
    assert await calls(db) == []


async def test_crash_replay_returns_the_paid_answer_without_paying_again(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    await set_budget(db, "1.00")
    first = await router.complete(request("stage-9:call-1"))
    again = await router.complete(request("stage-9:call-1"))
    assert (again.content, again.replayed, again.tier) == (first.content, True, LlmTier.PAID)
    assert upstream.calls == [PAID]  # only one upstream call
    assert await spent(db) == Decimal("0.0021")


async def test_keys_with_like_wildcards_only_replay_their_own_answers(
    router: Router, upstream: FakeOpenRouter
) -> None:
    await router.complete(request("stage91:call-1"))
    other = await router.complete(request("stage_1:call-1"))  # "_" would match the "9"
    assert other.replayed is False
    assert upstream.calls == [FREE_A, FREE_A]


async def test_kill_switch_forces_free(router: Router, db: Factory) -> None:
    await set_budget(db, "1.00")
    async with db() as session:
        session.add(Setting(key="paid_models_enabled", value={"enabled": False}, updated_by="root"))
        await session.commit()
    assert (await router.complete(request())).tier == LlmTier.FREE


async def test_confidential_projects_ask_providers_not_to_keep_data(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    project = await add_project(db, privacy=Privacy.CONFIDENTIAL)
    await router.complete(request(project_id=project.id))
    assert upstream.bodies[0]["provider"] == {"data_collection": "deny"}


async def test_model_restricted_to_other_apps_is_skipped(
    router: Router, upstream: FakeOpenRouter
) -> None:
    upstream.plan[FREE_A].append(FORBIDDEN)  # seen live: 403 "only available on agentic harnesses"
    assert (await router.complete(request())).model == FREE_B


async def test_daily_free_limit_waits_for_the_reset_without_trying_other_models(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    upstream.plan[FREE_A].append(daily_limit(3600))
    with pytest.raises(FreeDailyLimitError) as exc:
        await router.complete(request())
    assert 3500 < exc.value.retry_after <= 3600  # from X-RateLimit-Reset, not a guess
    assert upstream.calls == [FREE_A]  # the cap is account-wide: other free models would burn too
    assert [c.state for c in await calls(db)] == [LlmCallState.RELEASED]


async def test_free_fallback_never_picks_non_text_models(router: Router) -> None:
    # Not in the catalog: fall back to the catalog's own free models.
    fallback = variant(router, free_models=["gone/model:free"])
    chain = [info.id for info in await fallback._chain(["gone/model:free"], 100, 1000, free=True)]
    assert AUDIO not in chain
    assert set(chain) == {FREE_A, FREE_B}


async def test_bad_key_is_a_configuration_error(router: Router, upstream: FakeOpenRouter) -> None:
    upstream.plan[FREE_A].append(UNAUTHORIZED)
    with pytest.raises(AuthError):
        await router.complete(request())
    assert upstream.calls == [FREE_A]


# --- sweeper ---------------------------------------------------------------------------


async def add_call(db: Factory, state: LlmCallState, **kwargs: object) -> LlmCall:
    async with db() as session:
        call = LlmCall(
            idempotency_key=f"{uuid.uuid4()}:call-1#1",
            user_id="bob",
            role="researcher",
            tier=LlmTier.PAID,
            model=PAID,
            state=state,
            reserved_usd=Decimal("0.004"),
            **kwargs,
        )
        session.add(call)
        await session.commit()
    return call


async def state_of(db: Factory, call: LlmCall) -> tuple[LlmCallState, Decimal | None, str | None]:
    async with db() as session:
        row = await session.get(LlmCall, call.id)
        assert row is not None
        return row.state, row.cost_usd, row.error_class


async def test_unknown_calls_nothing_can_settle_count_at_their_reservation_in_the_end(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    now = datetime.now(UTC)
    no_id = await add_call(db, LlmCallState.UNKNOWN, created_at=now - timedelta(hours=2))
    recent = await add_call(db, LlmCallState.UNKNOWN, created_at=now - timedelta(minutes=10))
    never_reported = await add_call(
        db, LlmCallState.UNKNOWN, generation_id="gen-lost", created_at=now - timedelta(days=2)
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream.handler)) as http:
        await router.sweep(http, BASE_URL, "test-key")
    unreconciled = (LlmCallState.SETTLED, Decimal("0.004"), "unreconciled")
    assert await state_of(db, no_id) == unreconciled
    assert await state_of(db, never_reported) == unreconciled
    assert (await state_of(db, recent))[0] == LlmCallState.UNKNOWN
    assert upstream.lookups == []  # the day of lookups is over


async def test_the_sweeper_commits_expired_leases_before_looking_costs_up(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    expired = datetime.now(UTC) - timedelta(minutes=1)
    stale = await add_call(db, LlmCallState.RESERVED, lease_until=expired)
    lost = await add_call(db, LlmCallState.SENT, lease_until=expired)
    unknown = await add_call(db, LlmCallState.UNKNOWN, generation_id="gen-late")
    upstream.costs["gen-late"] = 0.003
    seen: list[LlmCallState] = []

    async def look_from_elsewhere() -> None:  # what a live call settling a row would wait on
        seen.extend([(await state_of(db, stale))[0], (await state_of(db, lost))[0]])

    upstream.during_lookup = look_from_elsewhere
    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream.handler)) as http:
        assert await router.sweep(http, BASE_URL, "test-key") == 1
    assert seen == [LlmCallState.RELEASED, LlmCallState.UNKNOWN]
    assert await state_of(db, unknown) == (LlmCallState.SETTLED, Decimal("0.003"), None)

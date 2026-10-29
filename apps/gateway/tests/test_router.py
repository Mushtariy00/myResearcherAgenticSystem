"""Money rules: paid only while the budget covers it, never overspend, fall back to free."""

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.enums import LlmCallState, LlmPolicy, LlmTier, Privacy
from agentic_db.models import Budget, LlmCall, Project, Setting
from agentic_db.spend import month_spend
from agentic_gateway.openrouter import AccountBalanceError
from agentic_gateway.quota import FreeQuota, QuotaExhaustedError
from agentic_gateway.service import CompletionRequest, FreeModelsDisabledError, Router
from gateway_testkit import (
    FREE_A,
    FREE_B,
    KEY_LIMIT,
    NO_CREDITS,
    OVERLOADED,
    PAID,
    PAID_BACKUP,
    FakeCounter,
    FakeOpenRouter,
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


async def set_budget(db: Factory, usd: str) -> None:
    async with db() as session:
        session.add(Budget(user_id="bob", monthly_usd=Decimal(usd), updated_by="root"))
        await session.commit()


async def calls(db: Factory) -> list[LlmCall]:
    async with db() as session:
        return list((await session.scalars(select(LlmCall).order_by(LlmCall.created_at))).all())


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
    async with db() as session:
        assert await month_spend(session, "bob") == Decimal("0.0021")


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
    async with db() as session:
        assert await month_spend(session, "bob") <= Decimal("0.003")


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


async def test_overloaded_paid_model_tries_the_next_paid_model(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    await set_budget(db, "1.00")
    upstream.plan[PAID].append(OVERLOADED)
    result = await router.complete(request())
    assert (result.tier, result.model) == (LlmTier.PAID, PAID_BACKUP)


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
    limited = Router(
        db,
        router._catalog,
        router._client,
        FreeQuota(FakeCounter(), per_minute=1, per_day=1000, per_user_per_day=300),
        free_models=[FREE_A],
    )
    await limited.complete(request("q:1"))
    with pytest.raises(QuotaExhaustedError) as exc:
        await limited.complete(request("q:2"))
    assert exc.value.scope == "minute"
    assert 0 < exc.value.retry_after <= 60


async def test_crash_replay_returns_the_paid_answer_without_paying_again(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    await set_budget(db, "1.00")
    first = await router.complete(request("stage-9:call-1"))
    again = await router.complete(request("stage-9:call-1"))
    assert (again.content, again.replayed, again.tier) == (first.content, True, LlmTier.PAID)
    assert upstream.calls == [PAID]  # only one upstream call
    async with db() as session:
        assert await month_spend(session, "bob") == Decimal("0.0021")


async def test_kill_switch_forces_free(router: Router, db: Factory) -> None:
    await set_budget(db, "1.00")
    async with db() as session:
        session.add(Setting(key="paid_models_enabled", value={"enabled": False}, updated_by="root"))
        await session.commit()
    assert (await router.complete(request())).tier == LlmTier.FREE


async def test_confidential_projects_ask_providers_not_to_keep_data(
    router: Router, upstream: FakeOpenRouter, db: Factory
) -> None:
    async with db() as session:
        project = Project(name="Secret", created_by="bob", privacy=Privacy.CONFIDENTIAL)
        session.add(project)
        await session.commit()
    await router.complete(request(project_id=project.id))
    assert upstream.bodies[0]["provider"] == {"data_collection": "deny"}


async def test_projects_can_forbid_free_models(router: Router, db: Factory) -> None:
    async with db() as session:
        project = Project(name="No free", created_by="bob", allow_free_models=False)
        session.add(project)
        await session.commit()
    with pytest.raises(FreeModelsDisabledError):
        await router.complete(request(project_id=project.id))

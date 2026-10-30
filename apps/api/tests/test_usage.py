import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_api.estimates import estimate_run
from agentic_core.enums import LlmCallState, LlmPolicy, LlmTier
from agentic_core.schemas import RunConfig
from agentic_core.stages import Stage
from agentic_db.models import LlmCall
from api_testkit import ADMIN, as_user, start_run, team_project

Factory = async_sessionmaker[AsyncSession]
GEMINI = "google/gemini-2.5-flash"
MINI = "openai/gpt-4.1-mini"
GEMMA = "google/gemma-4-31b-it:free"
NEMOTRON = "nvidia/nemotron-3-ultra-550b-a55b:free"


def _today() -> date:
    return datetime.now(UTC).date()


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time(), tzinfo=UTC)


async def _call(
    db: Factory,
    user: str,
    at: datetime,
    *,
    tier: LlmTier = LlmTier.PAID,
    state: LlmCallState = LlmCallState.SETTLED,
    cost: str | None = None,
    reserved: str = "0",
    run_id: str | None = None,
    model: str = GEMINI,
    tokens: tuple[int, int] | None = None,
) -> None:
    async with db() as session:
        session.add(
            LlmCall(
                idempotency_key=str(uuid.uuid4()),
                run_id=uuid.UUID(run_id) if run_id else None,
                user_id=user,
                role="researcher",
                tier=tier,
                model=model,
                state=state,
                reserved_usd=Decimal(reserved),
                cost_usd=Decimal(cost) if cost is not None else None,
                prompt_tokens=tokens[0] if tokens else None,
                completion_tokens=tokens[1] if tokens else None,
                created_at=at,
            )
        )
        await session.commit()


async def _usage(
    client: httpx.AsyncClient, user: str = "bob", role: str = "user", **params: Any
) -> dict[str, Any]:
    response = await client.get("/api/v1/usage", params=params, headers=as_user(user, role))
    assert response.status_code == 200, response.text
    return response.json()


def _money(totals: dict[str, Any]) -> tuple[Decimal, int, int]:
    return Decimal(totals["paid_usd"]), totals["paid_calls"], totals["free_calls"]


async def _journal(client: httpx.AsyncClient, db: Factory) -> dict[str, str]:
    """Bob's and Alice's calls over the last weeks; returns their runs by name."""
    project = await team_project(client)
    runs = {
        "bob_a": await start_run(client, project, user="bob"),
        "bob_b": await start_run(client, project, user="bob"),
        "alice": await start_run(client, project, user="alice"),
    }
    today = _midnight(_today()) + timedelta(minutes=1)
    await _call(db, "bob", today, cost="0.5", run_id=runs["bob_a"], tokens=(1000, 200))
    await _call(
        db, "bob", today, state=LlmCallState.SENT, reserved="0.25", run_id=runs["bob_a"], model=MINI
    )
    await _call(db, "bob", today, state=LlmCallState.RELEASED, reserved="9", run_id=runs["bob_a"])
    await _call(
        db,
        "bob",
        today - timedelta(days=2),
        tier=LlmTier.FREE,
        cost="0",
        run_id=runs["bob_b"],
        model=GEMMA,
        tokens=(300, 100),
    )
    await _call(db, "bob", today - timedelta(days=8), cost="1")  # before a 7-day window
    await _call(db, "alice", today, cost="2", run_id=runs["alice"])
    await _call(
        db, "alice", today, tier=LlmTier.FREE, cost="0", run_id=runs["alice"], model=NEMOTRON
    )
    return runs


async def test_my_usage_counts_only_my_calls(client: httpx.AsyncClient, db: Factory) -> None:
    runs = await _journal(client, db)
    await client.put("/api/v1/admin/budgets/bob", json={"monthly_usd": "10"}, headers=ADMIN)
    usage = await _usage(client, days=7)
    assert (usage["scope"], usage["days"], usage["demo"], usage["by_user"]) == ("me", 7, False, [])
    assert _money(usage["totals"]) == (Decimal("0.75"), 2, 1)  # released calls never count
    assert (usage["totals"]["prompt_tokens"], usage["totals"]["completion_tokens"]) == (1300, 300)

    days = [date.fromisoformat(day["day"]) for day in usage["by_day"]]
    assert days == [_today() - timedelta(days=6 - offset) for offset in range(7)]
    by_day = {date.fromisoformat(day["day"]): _money(day) for day in usage["by_day"]}
    assert by_day[_today()] == (Decimal("0.75"), 2, 0)
    assert by_day[_today() - timedelta(days=2)] == (Decimal(0), 0, 1)
    assert sum(1 for value in by_day.values() if value == (0, 0, 0)) == 5  # quiet days are zeros
    assert datetime.fromisoformat(usage["since"]) == _midnight(_today() - timedelta(days=6))
    assert datetime.fromisoformat(usage["until"]) == _midnight(_today() + timedelta(days=1))

    assert [(m["model"], m["tier"], *_money(m)) for m in usage["by_model"]] == [
        (GEMINI, "paid", Decimal("0.5"), 1, 0),
        (MINI, "paid", Decimal("0.25"), 1, 0),
        (GEMMA, "free", Decimal(0), 0, 1),
    ]
    assert [(r["run_id"], *_money(r)) for r in usage["top_runs"]] == [
        (runs["bob_a"], Decimal("0.75"), 2, 0),
        (runs["bob_b"], Decimal(0), 0, 1),
    ]
    assert (usage["top_runs"][0]["topic"], usage["top_runs"][0]["project_name"]) == (
        "Monocular depth",
        "Depth",
    )

    budget = usage["budget"]
    me = (await client.get("/api/v1/me", headers=as_user("bob"))).json()
    assert budget["month"] == datetime.now(UTC).strftime("%Y-%m")
    assert (Decimal(budget["monthly_usd"]), Decimal(budget["spent_usd"])) == (
        Decimal(10),
        Decimal(me["spent_usd"]),
    )
    assert Decimal(budget["remaining_usd"]) == 10 - Decimal(me["spent_usd"])

    month = await _usage(client, days=30)
    assert _money(month["totals"]) == (Decimal("1.75"), 3, 1)
    assert len(month["by_day"]) == 30


async def test_lab_usage_is_for_admins(client: httpx.AsyncClient, db: Factory) -> None:
    runs = await _journal(client, db)
    denied = await client.get("/api/v1/usage", params={"scope": "lab"}, headers=as_user("alice"))
    assert (denied.status_code, denied.json()) == (403, {"detail": "permission.denied"})

    lab = await _usage(client, "root", "admin", scope="lab", days=7)
    assert lab["scope"] == "lab"
    assert _money(lab["totals"]) == (Decimal("2.75"), 3, 2)
    assert [(u["user_id"], u["name"], u["email"], *_money(u)) for u in lab["by_user"]] == [
        ("alice", "Alice", "alice@lab.test", Decimal(2), 1, 1),
        ("bob", "Bob", "bob@lab.test", Decimal("0.75"), 2, 1),
    ]
    assert [r["run_id"] for r in lab["top_runs"]] == [runs["alice"], runs["bob_a"], runs["bob_b"]]
    assert [m["model"] for m in lab["by_model"]] == [GEMINI, MINI, GEMMA, NEMOTRON]
    assert _money(lab["by_model"][0]) == (Decimal("2.5"), 2, 0)
    assert lab["budget"]["monthly_usd"] == "0"  # the caller's own budget: root has none


async def test_usage_with_no_calls_is_all_zeros(client: httpx.AsyncClient) -> None:
    usage = await _usage(client, "carol")
    assert usage["totals"] == {
        "paid_usd": "0",
        "paid_calls": 0,
        "free_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }
    assert len(usage["by_day"]) == 30
    assert all(_money(day) == (0, 0, 0) for day in usage["by_day"])
    assert (usage["by_model"], usage["top_runs"]) == ([], [])
    assert usage["budget"] == {
        "month": datetime.now(UTC).strftime("%Y-%m"),
        "monthly_usd": "0",
        "spent_usd": "0",
        "remaining_usd": "0",
    }
    for query in ("days=6", "days=91", "scope=everyone"):
        response = await client.get(f"/api/v1/usage?{query}", headers=as_user("carol"))
        assert response.status_code == 422, query
    assert (await client.get("/api/v1/usage")).status_code == 401


async def _estimate(client: httpx.AsyncClient, user: str = "bob", **body: Any) -> dict[str, Any]:
    response = await client.post("/api/v1/runs/estimate", json=body, headers=as_user(user))
    assert response.status_code == 200, response.text
    return response.json()


def _range(estimate: dict[str, Any]) -> tuple[str, str, str]:
    return estimate["low_usd"], estimate["expected_usd"], estimate["high_usd"]


async def test_an_estimate_shows_its_assumptions(client: httpx.AsyncClient) -> None:
    await client.put("/api/v1/admin/budgets/bob", json={"monthly_usd": "10"}, headers=ADMIN)
    estimate = await _estimate(client)
    assert _range(estimate) == ("0.0752", "0.1478", "0.2843")
    assert (estimate["calls_low"], estimate["expected_calls"], estimate["calls_high"]) == (
        15,
        24,
        47,
    )
    assert (estimate["paid_possible"], estimate["paid_blocked_by"], estimate["capped_by"]) == (
        True,
        None,
        None,
    )
    assert (estimate["llm_policy"], estimate["paid_models_enabled"], estimate["demo"]) == (
        "auto",
        True,
        True,
    )
    assert Decimal(estimate["budget_remaining_usd"]) == 10
    assumptions = estimate["assumptions"]
    assert assumptions["paid_chain"] == [
        {
            "id": GEMINI,
            "prompt_usd_per_mtok": "0.30",
            "completion_usd_per_mtok": "2.50",
            "known": True,
        },
        {
            "id": MINI,
            "prompt_usd_per_mtok": "0.40",
            "completion_usd_per_mtok": "1.60",
            "known": True,
        },
    ]
    steps = assumptions["steps"]
    assert [(s["stage"], s["role"]) for s in steps] == [
        ("literature", "researcher"),
        ("literature", "screener"),
        ("literature", "analyst"),
        ("method", "methodologist"),
        ("coding", "coder"),
        ("experiment", "analyst"),
        ("writing", "writer"),
    ]
    assert steps[0] == {
        "stage": "literature",
        "role": "researcher",
        "calls_low": 2,
        "calls_expected": 2,
        "calls_high": 4,
        "prompt_tokens_per_call": 1800,
        "completion_tokens_per_call": 900,
        "low_usd": "0.0043",  # two calls priced as gpt-4.1-mini, the cheaper model for them
        "expected_usd": "0.0056",  # two at gemini-2.5-flash's prices, the first in the chain
        "high_usd": "0.0112",  # four at the dearest
    }
    for key in ("low_usd", "expected_usd", "high_usd"):
        assert sum(Decimal(step[key]) for step in steps) == Decimal(estimate[key])

    # More papers mean more screening and reading; fewer stages, fewer steps.
    short = await _estimate(client, config={"max_papers": 50, "stages": ["literature"]})
    assert [
        (s["role"], s["calls_low"], s["calls_expected"], s["calls_high"])
        for s in short["assumptions"]["steps"]
    ] == [("researcher", 2, 2, 4), ("screener", 5, 10, 15), ("analyst", 15, 23, 50)]


async def test_estimates_are_zero_when_paid_models_cannot_be_used(
    client: httpx.AsyncClient,
) -> None:
    no_budget = await _estimate(client)
    assert (no_budget["paid_possible"], no_budget["paid_blocked_by"]) == (False, "budget")
    assert _range(no_budget) == ("0.0000", "0.0000", "0.0000")
    assert no_budget["expected_calls"] == 24  # the calls still happen, on free models

    await client.put("/api/v1/admin/budgets/bob", json={"monthly_usd": "10"}, headers=ADMIN)
    free = await _estimate(client, llm_policy="free")
    assert (free["llm_policy"], free["paid_blocked_by"], _range(free)) == (
        "free",
        "policy",
        ("0.0000", "0.0000", "0.0000"),
    )
    zero_cap = await _estimate(client, budget_cap_usd="0")
    assert zero_cap["paid_blocked_by"] == "run_cap"
    await client.put("/api/v1/admin/settings/paid-models", json={"enabled": False}, headers=ADMIN)
    switched_off = await _estimate(client)
    assert (switched_off["paid_blocked_by"], switched_off["paid_models_enabled"]) == (
        "kill_switch",
        False,
    )


async def test_estimates_stop_at_the_run_cap_and_the_budget(client: httpx.AsyncClient) -> None:
    await client.put("/api/v1/admin/budgets/bob", json={"monthly_usd": "10"}, headers=ADMIN)
    capped = await _estimate(client, budget_cap_usd="0.10")
    assert (_range(capped), capped["capped_by"]) == (("0.0752", "0.1000", "0.1000"), "run_cap")
    roomy = await _estimate(client, budget_cap_usd="5")
    assert (_range(roomy), roomy["capped_by"]) == (("0.0752", "0.1478", "0.2843"), None)

    await client.put("/api/v1/admin/budgets/bob", json={"monthly_usd": "0.05"}, headers=ADMIN)
    for cap in (None, "1"):
        tight = await _estimate(client, budget_cap_usd=cap)
        assert (_range(tight), tight["capped_by"]) == (("0.0500", "0.0500", "0.0500"), "budget")


async def test_estimate_requests_are_validated(client: httpx.AsyncClient) -> None:
    url = "/api/v1/runs/estimate"
    for body in (
        {"config": {"stages": ["method"]}},
        {"config": {"max_papers": 500}},
        {"budget_cap_usd": "-1"},
        {"llm_policy": "cheap"},
        {"unknown": True},
    ):
        response = await client.post(url, json=body, headers=as_user("bob"))
        assert response.status_code == 422, body
    assert (await client.post(url, json={})).status_code == 401
    cross_site = await client.post(
        url, json={}, headers={**as_user("bob"), "origin": "https://evil.test"}
    )
    assert (cross_site.status_code, cross_site.json()) == (403, {"detail": "csrf.origin_mismatch"})


def test_models_missing_from_the_catalog_get_a_conservative_price() -> None:
    estimate = estimate_run(
        RunConfig(stages=[Stage.LITERATURE, Stage.METHOD]),
        LlmPolicy.AUTO,
        paid_chain=["unknown/model", GEMINI],
        paid_models_enabled=True,
        budget_remaining_usd=Decimal(100),
    )
    unknown, known = estimate.assumptions.paid_chain
    assert (unknown.known, unknown.prompt_usd_per_mtok, unknown.completion_usd_per_mtok) == (
        False,
        Decimal("3.00"),
        Decimal("15.00"),
    )
    assert known.known is True
    # The first model in the chain prices the expected value; here it is the unknown one.
    researcher = estimate.assumptions.steps[0]
    assert researcher.expected_usd == Decimal("0.0378")  # 2 * (1800 * 3 + 900 * 15) / 1e6
    assert estimate.high_usd > estimate.expected_usd > estimate.low_usd > 0

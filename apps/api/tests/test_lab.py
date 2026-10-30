import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_api.demo import balance as lab_balance
from agentic_api.demo import catalog
from agentic_api.main import AppState, create_app
from agentic_api.settings import Settings
from agentic_core.enums import LlmCallState, LlmTier
from agentic_db.models import LlmCall
from agentic_db.spend import month_start
from agentic_gateway.service import DEFAULT_FREE_MODELS, DEFAULT_PAID_MODELS
from api_testkit import ADMIN, ORIGIN, FakeOrchestrator, FakeValkey, FakeVerifier, as_user

Factory = async_sessionmaker[AsyncSession]
ROLES = ["researcher", "screener", "analyst", "methodologist", "coder", "writer"]


@asynccontextmanager
async def _client(db: Factory, **settings: Any) -> AsyncIterator[httpx.AsyncClient]:
    """The API with explicit settings, so the developer's .env can't change what is tested."""
    app = create_app(
        Settings(environment="test", public_origin=ORIGIN, **settings),
        state=AppState(
            sessions=db,
            session_verifier=FakeVerifier(),
            valkey=FakeValkey(),
            orchestrator=FakeOrchestrator(),
        ),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers={"origin": ORIGIN}
    ) as client:
        yield client


def test_the_default_chains_are_the_gateways() -> None:
    assert catalog.DEFAULT_PAID_MODELS == DEFAULT_PAID_MODELS
    assert catalog.DEFAULT_FREE_MODELS == DEFAULT_FREE_MODELS
    for model_id in (*DEFAULT_PAID_MODELS, *DEFAULT_FREE_MODELS):
        assert model_id in catalog.CATALOG, model_id  # the defaults are priced
    assert [model_id for model_id in catalog.CATALOG if catalog.CATALOG[model_id].free] == [
        "google/gemma-4-31b-it:free",
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "meta-llama/llama-3.3-70b-instruct:free",
    ]


async def test_model_routing_shows_every_role_and_the_kill_switch(db: Factory) -> None:
    async with _client(db, paid_models="", free_models="") as api:
        assert (await api.get("/api/v1/admin/models", headers=as_user("bob"))).status_code == 403
        assert (await api.get("/api/v1/admin/models")).status_code == 401
        response = await api.get("/api/v1/admin/models", headers=ADMIN)
        assert response.status_code == 200, response.text
        routing = response.json()
        assert (routing["paid_models_enabled"], routing["demo"]) == (True, True)
        assert [role["role"] for role in routing["roles"]] == ROLES
        assert [role["max_output_tokens"] for role in routing["roles"]] == [
            1500,
            800,
            1200,
            2000,
            4096,
            4096,
        ]
        researcher = routing["roles"][0]
        assert researcher["paid"] == [
            {
                "id": "google/gemini-2.5-flash",
                "free": False,
                "in_catalog": True,
                "context_length": 1_048_576,
                "prompt_usd_per_mtok": "0.30",
                "completion_usd_per_mtok": "2.50",
            },
            {
                "id": "openai/gpt-4.1-mini",
                "free": False,
                "in_catalog": True,
                "context_length": 1_047_576,
                "prompt_usd_per_mtok": "0.40",
                "completion_usd_per_mtok": "1.60",
            },
        ]
        assert [(m["id"], m["free"], m["prompt_usd_per_mtok"]) for m in researcher["free"]] == [
            ("nvidia/nemotron-3-ultra-550b-a55b:free", True, "0"),
            ("google/gemma-4-31b-it:free", True, "0"),
        ]
        assert all(role["paid"] == researcher["paid"] for role in routing["roles"])

        await api.put("/api/v1/admin/settings/paid-models", json={"enabled": False}, headers=ADMIN)
        switched = (await api.get("/api/v1/admin/models", headers=ADMIN)).json()
        assert switched["paid_models_enabled"] is False


async def test_model_routing_follows_the_gateways_overrides(db: Factory) -> None:
    async with _client(
        db,
        paid_models=" openai/gpt-4.1 , unknown/model ",
        free_models="meta-llama/llama-3.3-70b-instruct:free",
    ) as api:
        routing = (await api.get("/api/v1/admin/models", headers=ADMIN)).json()
    coder = routing["roles"][4]
    assert [model["id"] for model in coder["paid"]] == ["openai/gpt-4.1", "unknown/model"]
    assert coder["paid"][1] == {
        "id": "unknown/model",
        "free": False,
        "in_catalog": False,
        "context_length": None,
        "prompt_usd_per_mtok": None,
        "completion_usd_per_mtok": None,
    }
    assert [(m["id"], m["context_length"]) for m in coder["free"]] == [
        ("meta-llama/llama-3.3-70b-instruct:free", 131_072)
    ]


async def _call(
    db: Factory,
    user: str,
    at: datetime,
    *,
    tier: LlmTier = LlmTier.PAID,
    state: LlmCallState = LlmCallState.SETTLED,
    cost: str | None = None,
    reserved: str = "0",
) -> None:
    async with db() as session:
        session.add(
            LlmCall(
                idempotency_key=str(uuid.uuid4()),
                user_id=user,
                role="screener",
                tier=tier,
                model="google/gemini-2.5-flash",
                state=state,
                reserved_usd=Decimal(reserved),
                cost_usd=Decimal(cost) if cost is not None else None,
                created_at=at,
            )
        )
        await session.commit()


async def test_the_lab_balance_uses_real_spend_and_free_use(db: Factory) -> None:
    now = datetime.now(UTC)
    this_month = month_start(now) + timedelta(minutes=1)
    today = datetime.combine(now.date(), time(), tzinfo=UTC) + timedelta(minutes=1)
    await _call(db, "bob", this_month, cost="1.25")
    await _call(db, "alice", this_month, state=LlmCallState.SENT, reserved="0.5")
    await _call(db, "alice", this_month, state=LlmCallState.RELEASED, reserved="5")
    await _call(db, "bob", month_start(now) - timedelta(days=1), cost="3")  # last month
    for state in (LlmCallState.SETTLED, LlmCallState.SETTLED, LlmCallState.RELEASED):
        # Every free request took a slot of the daily quota, failed ones too.
        await _call(db, "bob", today, tier=LlmTier.FREE, state=state, cost="0")
    await _call(db, "bob", today - timedelta(hours=2), tier=LlmTier.FREE, cost="0")  # yesterday

    async with _client(db, free_requests_per_day=1000) as api:
        denied = await api.get("/api/v1/admin/balance", headers=as_user("alice"))
        assert (denied.status_code, denied.json()) == (403, {"detail": "permission.denied"})
        assert (await api.get("/api/v1/admin/balance")).status_code == 401
        response = await api.get("/api/v1/admin/balance", headers=ADMIN)
    assert response.status_code == 200, response.text
    lab = response.json()
    spent = Decimal("1.75")
    assert Decimal(lab["spent_this_month_usd"]) == spent
    assert Decimal(lab["balance_usd"]) == lab_balance.balance(now, spent)
    assert lab["month"] == now.strftime("%Y-%m")
    assert (lab["free_daily_limit"], lab["free_calls_today"]) == (1000, 3)
    assert (lab["auto_top_up"], lab["alert_floor_usd"], lab["demo"]) == (False, "10.00", True)
    assert lab["below_floor"] is (Decimal(lab["balance_usd"]) < 10)
    assert datetime.fromisoformat(lab["checked_at"]) >= now


def test_the_generated_balance_is_stable_within_a_month() -> None:
    october = datetime(2026, 10, 3, tzinfo=UTC)
    opening = lab_balance.opening_balance(october)
    assert opening == lab_balance.opening_balance(datetime(2026, 10, 30, 23, 59, tzinfo=UTC))
    assert Decimal(38) <= opening <= Decimal(64)
    months = [datetime(2026, month, 1, tzinfo=UTC) for month in range(1, 13)]
    assert len({lab_balance.opening_balance(month) for month in months}) > 1  # month to month
    left = lab_balance.balance(october, Decimal("1.234"))
    assert left == (opening - Decimal("1.234")).quantize(Decimal("0.01"))
    assert lab_balance.balance(october, Decimal(1000)) == Decimal("0.00")  # never negative

import asyncio
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_api.main import AppState, create_app
from agentic_api.settings import Settings
from agentic_core.enums import LlmCallState, LlmTier
from agentic_db.lab_settings import LAB_ACCOUNT_KEY
from agentic_db.models import AuditLog, LlmCall, Setting
from agentic_db.spend import month_start
from api_testkit import (
    ADMIN,
    CATALOG_CHECKED_AT,
    ORIGIN,
    FakeOrchestrator,
    FakeValkey,
    FakeVerifier,
    as_user,
    seed_catalog,
)

Factory = async_sessionmaker[AsyncSession]
ROLES = ["researcher", "screener", "analyst", "methodologist", "coder", "writer"]
GEMINI = "google/gemini-2.5-flash"
MINI = "openai/gpt-4.1-mini"
SONNET = "anthropic/claude-sonnet-4.5"
NEMOTRON = "nvidia/nemotron-3-ultra-550b-a55b:free"
GEMMA = "google/gemma-4-31b-it:free"


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


def _role(routing: dict[str, Any], role: str) -> dict[str, Any]:
    return next(item for item in routing["roles"] if item["role"] == role)


def _chain(models: list[dict[str, Any]]) -> list[str]:
    return [model["id"] for model in models]


async def test_model_routing_shows_every_role_and_the_kill_switch(db: Factory) -> None:
    await seed_catalog(db)
    async with _client(db, paid_models="", free_models="") as api:
        assert (await api.get("/api/v1/admin/models", headers=as_user("bob"))).status_code == 403
        assert (await api.get("/api/v1/admin/models")).status_code == 401
        response = await api.get("/api/v1/admin/models", headers=ADMIN)
        assert response.status_code == 200, response.text
        routing = response.json()
        assert (routing["paid_models_enabled"], routing["demo"]) == (True, False)
        assert datetime.fromisoformat(routing["catalog_checked_at"]) == datetime.fromisoformat(
            CATALOG_CHECKED_AT
        )
        assert [role["role"] for role in routing["roles"]] == ROLES
        assert _chain(routing["lab_paid"]) == [GEMINI, MINI]
        assert _chain(routing["lab_free"]) == [NEMOTRON, GEMMA]
        # What the worker's calls ask for (a worker test keeps these in step).
        assert [role["max_output_tokens"] for role in routing["roles"]] == [
            1500,
            4000,
            4000,
            4000,
            16000,
            4000,
        ]
        researcher = routing["roles"][0]
        assert researcher["paid"] == [
            {
                "id": GEMINI,
                "free": False,
                "in_catalog": True,
                "context_length": 1_048_576,
                "prompt_usd_per_mtok": "0.30",
                "completion_usd_per_mtok": "2.50",
            },
            {
                "id": MINI,
                "free": False,
                "in_catalog": True,
                "context_length": 1_047_576,
                "prompt_usd_per_mtok": "0.40",
                "completion_usd_per_mtok": "1.60",
            },
        ]
        assert [(m["id"], m["free"], m["prompt_usd_per_mtok"]) for m in researcher["free"]] == [
            (NEMOTRON, True, "0"),
            (GEMMA, True, "0"),
        ]
        assert all(role["paid"] == researcher["paid"] for role in routing["roles"])
        assert all(
            role["paid_is_lab_default"] and role["free_is_lab_default"] for role in routing["roles"]
        )

        await api.put("/api/v1/admin/settings/paid-models", json={"enabled": False}, headers=ADMIN)
        switched = (await api.get("/api/v1/admin/models", headers=ADMIN)).json()
        assert switched["paid_models_enabled"] is False


async def test_model_routing_follows_the_gateways_overrides(db: Factory) -> None:
    await seed_catalog(db)
    async with _client(db, paid_models=f" {SONNET} , unknown/model ", free_models=GEMMA) as api:
        routing = (await api.get("/api/v1/admin/models", headers=ADMIN)).json()
    coder = _role(routing, "coder")
    assert _chain(coder["paid"]) == [SONNET, "unknown/model"]
    assert coder["paid"][1] == {
        "id": "unknown/model",
        "free": False,
        "in_catalog": False,
        "context_length": None,
        "prompt_usd_per_mtok": None,
        "completion_usd_per_mtok": None,
    }
    assert [(m["id"], m["context_length"]) for m in coder["free"]] == [(GEMMA, 131_072)]


async def test_routing_before_the_gateway_has_read_the_catalog(db: Factory) -> None:
    async with _client(db) as api:
        routing = (await api.get("/api/v1/admin/models", headers=ADMIN)).json()
        catalog = (await api.get("/api/v1/admin/models/catalog", headers=ADMIN)).json()
    assert routing["catalog_checked_at"] is None
    assert not any(model["in_catalog"] for model in routing["roles"][0]["paid"])
    assert catalog == {"models": [], "checked_at": None}


async def test_the_model_catalog_is_for_admins_and_lists_what_the_gateway_read(
    db: Factory,
) -> None:
    await seed_catalog(db)
    async with _client(db) as api:
        assert (await api.get("/api/v1/admin/models/catalog")).status_code == 401
        denied = await api.get("/api/v1/admin/models/catalog", headers=as_user("bob"))
        assert denied.status_code == 403
        catalog = (await api.get("/api/v1/admin/models/catalog", headers=ADMIN)).json()
    assert _chain(catalog["models"]) == [SONNET, GEMINI, GEMMA, NEMOTRON, MINI]
    assert catalog["models"][2]["free"] is True
    assert catalog["checked_at"] is not None


async def test_an_admin_gives_one_role_its_own_chains(db: Factory) -> None:
    await seed_catalog(db)
    async with _client(db, paid_models="", free_models="") as api:
        body = {"paid": [SONNET, GEMINI], "free": [GEMMA]}
        assert (await api.put("/api/v1/admin/models/coder", json=body)).status_code == 401
        denied = await api.put("/api/v1/admin/models/coder", json=body, headers=as_user("bob"))
        assert denied.status_code == 403

        response = await api.put("/api/v1/admin/models/coder", json=body, headers=ADMIN)
        assert response.status_code == 200, response.text
        coder = _role(response.json(), "coder")
        assert (_chain(coder["paid"]), _chain(coder["free"])) == ([SONNET, GEMINI], [GEMMA])
        assert (coder["paid_is_lab_default"], coder["free_is_lab_default"]) == (False, False)
        writer = _role(response.json(), "writer")  # the other roles keep the lab's
        assert (_chain(writer["paid"]), writer["paid_is_lab_default"]) == ([GEMINI, MINI], True)

        # One chain can stay the lab's; a second role doesn't disturb the first.
        one = await api.put(
            "/api/v1/admin/models/writer", json={"paid": None, "free": [GEMMA]}, headers=ADMIN
        )
        writer = _role(one.json(), "writer")
        assert (writer["paid_is_lab_default"], writer["free_is_lab_default"]) == (True, False)
        assert _chain(_role(one.json(), "coder")["paid"]) == [SONNET, GEMINI]

        # An empty paid chain keeps the role on free models.
        free_only = await api.put("/api/v1/admin/models/screener", json={"paid": []}, headers=ADMIN)
        screener = _role(free_only.json(), "screener")
        assert (screener["paid"], screener["paid_is_lab_default"]) == ([], False)

        # Both null: back on the lab's chains.
        reset = await api.put(
            "/api/v1/admin/models/coder", json={"paid": None, "free": None}, headers=ADMIN
        )
        coder = _role(reset.json(), "coder")
        assert (_chain(coder["paid"]), coder["paid_is_lab_default"]) == ([GEMINI, MINI], True)
        assert (await api.get("/api/v1/admin/models", headers=ADMIN)).json() == reset.json()

    async with db() as session:
        entries = (
            await session.scalars(
                select(AuditLog)
                .where(AuditLog.action == "settings.model_routing")
                .order_by(AuditLog.id)
            )
        ).all()
    assert entries[0].actor_id == "root"
    assert entries[0].details == {"role": "coder", "paid": [SONNET, GEMINI], "free": [GEMMA]}
    assert entries[-1].details == {"role": "coder", "paid": None, "free": None}


async def test_a_chain_must_name_models_openrouter_offers_of_its_own_kind(db: Factory) -> None:
    await seed_catalog(db)
    url = "/api/v1/admin/models/coder"
    async with _client(db) as api:

        async def refused(body: dict[str, Any]) -> tuple[int, Any]:
            response = await api.put(url, json=body, headers=ADMIN)
            return response.status_code, response.json()["detail"]

        assert await refused({"paid": ["gone/model"]}) == (422, "routing.unknown_model")
        assert await refused({"free": ["gone/model:free"]}) == (422, "routing.unknown_model")
        assert await refused({"paid": [NEMOTRON]}) == (422, "routing.wrong_tier")
        assert await refused({"free": [GEMINI]}) == (422, "routing.wrong_tier")
        for body in (
            {"paid": [GEMINI, GEMINI]},  # twice
            {"free": []},  # a role always has free models to fall to
            {"paid": ["a", "b", "c", "d", "e", "f"]},  # more than a call has time for
            {"paid": ["has space"]},
            {"paid": [""]},
            {"unknown": True},
        ):
            assert (await api.put(url, json=body, headers=ADMIN)).status_code == 422, body
        assert (
            await api.put("/api/v1/admin/models/janitor", json={}, headers=ADMIN)
        ).status_code == 422
        cross_site = await api.put(
            url, json={"paid": [GEMINI]}, headers={**ADMIN, "origin": "https://evil.test"}
        )
        assert cross_site.status_code == 403


async def test_two_admins_saving_at_once_both_keep_their_changes(db: Factory) -> None:
    await seed_catalog(db)
    async with _client(db) as api:
        answers = await asyncio.gather(
            api.put("/api/v1/admin/models/coder", json={"paid": [SONNET]}, headers=ADMIN),
            api.put("/api/v1/admin/models/writer", json={"paid": []}, headers=ADMIN),
        )
        assert [answer.status_code for answer in answers] == [200, 200]
        routing = (await api.get("/api/v1/admin/models", headers=ADMIN)).json()
    assert _chain(_role(routing, "coder")["paid"]) == [SONNET]
    assert _role(routing, "writer")["paid"] == []


async def test_before_the_catalog_is_read_the_name_decides_the_kind(db: Factory) -> None:
    url = "/api/v1/admin/models/coder"
    async with _client(db) as api:
        assert (
            await api.put(url, json={"paid": ["some/model"], "free": ["x:free"]}, headers=ADMIN)
        ).status_code == 200
        wrong = await api.put(url, json={"paid": ["x:free"]}, headers=ADMIN)
        assert (wrong.status_code, wrong.json()["detail"]) == (422, "routing.wrong_tier")


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
                model=GEMINI,
                state=state,
                reserved_usd=Decimal(reserved),
                cost_usd=Decimal(cost) if cost is not None else None,
                created_at=at,
            )
        )
        await session.commit()


async def _account(db: Factory, **value: Any) -> None:
    defaults = {
        "checked_at": "2026-11-04T09:30:00+00:00",
        "balance_usd": "17.5",
        "free_tier": False,
        "free_daily_limit": 1000,
    }
    async with db() as session:
        await session.merge(
            Setting(key=LAB_ACCOUNT_KEY, value=defaults | value, updated_by="gateway")
        )
        await session.commit()


async def test_the_lab_balance_is_what_the_gateway_read_with_real_spend_and_free_use(
    db: Factory,
) -> None:
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
    await _account(db)

    async with _client(db, free_requests_per_day=50) as api:
        denied = await api.get("/api/v1/admin/balance", headers=as_user("alice"))
        assert (denied.status_code, denied.json()) == (403, {"detail": "permission.denied"})
        assert (await api.get("/api/v1/admin/balance")).status_code == 401
        response = await api.get("/api/v1/admin/balance", headers=ADMIN)
    assert response.status_code == 200, response.text
    lab = response.json()
    assert Decimal(lab["spent_this_month_usd"]) == Decimal("1.75")
    assert Decimal(lab["balance_usd"]) == Decimal("17.5")
    assert lab["month"] == now.strftime("%Y-%m")
    # The account's own daily limit, not the setting, and today's calls from the journal.
    assert (lab["free_daily_limit"], lab["free_calls_today"]) == (1000, 3)
    assert (lab["free_tier"], lab["auto_top_up"], lab["demo"]) == (False, False, False)
    assert (Decimal(lab["alert_floor_usd"]), lab["below_floor"]) == (Decimal(2), False)
    assert datetime.fromisoformat(lab["checked_at"]) == datetime(2026, 11, 4, 9, 30, tzinfo=UTC)


async def test_the_balance_warns_below_the_floor(db: Factory) -> None:
    await _account(db, balance_usd="1.99")
    async with _client(db) as api:
        low = (await api.get("/api/v1/admin/balance", headers=ADMIN)).json()
    assert low["below_floor"] is True
    async with _client(db, balance_alert_floor_usd=Decimal("1.50")) as api:
        lowered = (await api.get("/api/v1/admin/balance", headers=ADMIN)).json()
    assert (Decimal(lowered["alert_floor_usd"]), lowered["below_floor"]) == (Decimal("1.5"), False)


async def test_a_free_tier_account_has_no_credit_to_run_out_of(db: Factory) -> None:
    await _account(db, balance_usd="0", free_tier=True, free_daily_limit=50)
    async with _client(db) as api:
        lab = (await api.get("/api/v1/admin/balance", headers=ADMIN)).json()
    assert (Decimal(lab["balance_usd"]), lab["free_tier"]) == (0, True)
    assert (lab["below_floor"], lab["free_daily_limit"]) == (False, 50)


async def test_a_balance_nobody_has_read_is_unknown_not_zero(db: Factory) -> None:
    async with _client(db, free_requests_per_day=50) as api:
        lab = (await api.get("/api/v1/admin/balance", headers=ADMIN)).json()
    assert (lab["balance_usd"], lab["checked_at"], lab["below_floor"]) == (None, None, False)
    assert lab["free_daily_limit"] == 50  # the setting, until the account says

    await _account(db, balance_usd=None, free_daily_limit=None)  # OpenRouter wouldn't say
    async with _client(db, free_requests_per_day=50) as api:
        lab = (await api.get("/api/v1/admin/balance", headers=ADMIN)).json()
    assert (lab["balance_usd"], lab["below_floor"], lab["free_daily_limit"]) == (None, False, 50)
    assert lab["checked_at"] is not None

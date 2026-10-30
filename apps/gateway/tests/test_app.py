from collections.abc import AsyncIterator

import httpx
import pytest
import redis.exceptions
from pydantic import SecretStr

from agentic_gateway.app import create_app
from agentic_gateway.catalog import CatalogUnavailableError
from agentic_gateway.openrouter import (
    AccountBalanceError,
    AuthError,
    FreeDailyLimitError,
    KeyLimitError,
    UpstreamError,
    UpstreamInterruptedError,
    UpstreamRateLimitError,
)
from agentic_gateway.quota import FreeQuota, QuotaExhaustedError
from agentic_gateway.service import (
    CallInProgressError,
    DeadlineExceededError,
    FreeModelsDisabledError,
    NoModelAvailableError,
    Router,
    RunInactiveError,
)
from agentic_gateway.settings import GatewaySettings
from gateway_testkit import FakeCounter

BODY = {
    "idempotency_key": "stage-1:call-1",
    "user_id": "bob",
    "role": "researcher",
    "messages": [{"role": "user", "content": "Summarize depth estimation."}],
}
AUTH = {"authorization": "Bearer secret"}


@pytest.fixture
async def client(router: Router) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(GatewaySettings(gateway_token=SecretStr("secret")), router=router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gw") as c:
        yield c


async def test_workers_need_the_gateway_token(client: httpx.AsyncClient) -> None:
    assert (await client.post("/v1/complete", json=BODY)).status_code == 401
    wrong = await client.post("/v1/complete", json=BODY, headers={"authorization": "Bearer nope"})
    assert wrong.status_code == 401


async def test_complete(client: httpx.AsyncClient) -> None:
    response = await client.post("/v1/complete", json=BODY, headers=AUTH)
    assert response.status_code == 200, response.text
    assert response.json()["tier"] == "free"


async def test_quota_exhaustion_is_429_with_retry_after(
    client: httpx.AsyncClient, router: Router, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def exhausted(user_id: str) -> None:
        raise QuotaExhaustedError(42, "day")

    monkeypatch.setattr(router._quota, "acquire", exhausted)
    response = await client.post("/v1/complete", json=BODY, headers=AUTH)
    assert response.status_code == 429
    assert response.headers["retry-after"] == "42"
    assert response.json() == {"detail": "free_quota.exhausted", "retry_after": 42.0}


async def test_a_valkey_outage_is_a_wait_not_a_500(
    client: httpx.AsyncClient, router: Router, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Down(FakeCounter):
        async def incr(self, name: str) -> int:
            raise redis.exceptions.TimeoutError("Timeout reading from 127.0.0.1:6379")

    monkeypatch.setattr(router, "_quota", FreeQuota(Down(), 20, 50, 20))
    response = await client.post("/v1/complete", json=BODY, headers=AUTH)
    assert (response.status_code, response.json()["detail"]) == (429, "free_quota.unavailable")
    assert response.headers["retry-after"] == "30"


@pytest.mark.parametrize(
    ("error", "status", "detail", "retry_after"),
    [
        (FreeDailyLimitError(3600), 429, "free_quota.exhausted", "3600"),
        (UpstreamRateLimitError(7.2), 429, "free_quota.exhausted", "8"),
        (CallInProgressError("stage-1:call-1"), 429, "call.in_progress", "30"),
        (AccountBalanceError("free/a:free"), 402, "lab_balance.exhausted", None),
        (KeyLimitError("free/a:free: openrouter_key_limit"), 402, "lab_balance.exhausted", None),
        (FreeModelsDisabledError(None), 403, "free_models.disabled", None),
        (RunInactiveError(None), 409, "run.inactive", None),
        (AuthError("No auth credentials found"), 502, "upstream.auth_failed", None),
        (NoModelAvailableError("none"), 502, "upstream.unavailable", None),
        (UpstreamError("paid/good returned HTTP 503"), 502, "upstream.unavailable", None),
        (UpstreamInterruptedError("paid/good: ReadTimeout"), 502, "upstream.unavailable", None),
        (CatalogUnavailableError("/models"), 503, "catalog.unavailable", None),
        (DeadlineExceededError("no free model answered"), 504, "upstream.timeout", None),
    ],
)
async def test_failures_map_to_the_worker_protocol(
    client: httpx.AsyncClient,
    router: Router,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status: int,
    detail: str,
    retry_after: str | None,
) -> None:
    async def fail(_: object) -> None:
        raise error

    monkeypatch.setattr(router, "complete", fail)
    response = await client.post("/v1/complete", json=BODY, headers=AUTH)
    assert (response.status_code, response.json()["detail"]) == (status, detail)
    assert response.headers.get("retry-after") == retry_after

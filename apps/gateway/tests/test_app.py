from collections.abc import AsyncIterator

import httpx
import pytest
from pydantic import SecretStr

from agentic_gateway.app import create_app
from agentic_gateway.quota import QuotaExhaustedError
from agentic_gateway.service import Router
from agentic_gateway.settings import GatewaySettings

BODY = {
    "idempotency_key": "stage-1:call-1",
    "user_id": "bob",
    "role": "researcher",
    "messages": [{"role": "user", "content": "Summarize depth estimation."}],
}


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
    response = await client.post(
        "/v1/complete", json=BODY, headers={"authorization": "Bearer secret"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["tier"] == "free"


async def test_quota_exhaustion_is_429_with_retry_after(
    client: httpx.AsyncClient, router: Router, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def exhausted(user_id: str) -> None:
        raise QuotaExhaustedError(42, "day")

    monkeypatch.setattr(router._quota, "acquire", exhausted)
    response = await client.post(
        "/v1/complete", json=BODY, headers={"authorization": "Bearer secret"}
    )
    assert response.status_code == 429
    assert response.headers["retry-after"] == "42"
    assert response.json() == {"detail": "free_quota.exhausted", "retry_after": 42.0}

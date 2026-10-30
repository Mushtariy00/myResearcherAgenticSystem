from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
import pytest
import respx

from agentic_scholarly.http import (
    RetryPolicy,
    make_client,
    request,
    retry_after_seconds,
    user_agent,
)
from agentic_scholarly.testing import RecordingSleep

URL = "https://api.example.org/items"


def test_user_agent_names_the_lab_contact() -> None:
    assert user_agent("lab@example.org") == "ARP/0.1 (+mailto:lab@example.org)"
    assert user_agent() == "ARP/0.1"
    with pytest.raises(ValueError, match="contact"):
        user_agent("lab@example.org\r\nX-Injected: 1")
    with pytest.raises(ValueError, match="contact"):
        user_agent("  ")


async def test_client_ignores_the_environment_and_does_not_follow_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    async with make_client("lab@example.org") as client:
        assert client.trust_env is False
        assert client.follow_redirects is False
        assert client.headers["User-Agent"] == "ARP/0.1 (+mailto:lab@example.org)"
        assert client.timeout.read == 20.0


async def test_429_waits_for_retry_after(
    respx_mock: respx.MockRouter,
    http: httpx.AsyncClient,
    retry: RetryPolicy,
    sleeps: RecordingSleep,
) -> None:
    route = respx_mock.get(URL).mock(
        side_effect=[httpx.Response(429, headers={"Retry-After": "2"}), httpx.Response(200)]
    )
    response = await request(http, "GET", URL, retry=retry)
    assert response.status_code == 200
    assert route.call_count == 2
    assert sleeps.waits == [2.0]


async def test_5xx_backs_off_and_returns_the_last_answer(
    respx_mock: respx.MockRouter,
    http: httpx.AsyncClient,
    retry: RetryPolicy,
    sleeps: RecordingSleep,
) -> None:
    route = respx_mock.get(URL).mock(return_value=httpx.Response(503))
    response = await request(http, "GET", URL, retry=retry)
    assert response.status_code == 503
    assert route.call_count == 3
    assert sleeps.waits == [1.0, 2.0]


async def test_client_errors_are_not_retried(
    respx_mock: respx.MockRouter, http: httpx.AsyncClient, retry: RetryPolicy
) -> None:
    route = respx_mock.get(URL).mock(return_value=httpx.Response(404))
    assert (await request(http, "GET", URL, retry=retry)).status_code == 404
    assert route.call_count == 1


async def test_a_long_retry_after_is_left_to_the_caller(
    respx_mock: respx.MockRouter,
    http: httpx.AsyncClient,
    retry: RetryPolicy,
    sleeps: RecordingSleep,
) -> None:
    respx_mock.get(URL).mock(return_value=httpx.Response(429, headers={"Retry-After": "3600"}))
    response = await request(http, "GET", URL, retry=retry)
    assert response.status_code == 429
    assert sleeps.waits == []


async def test_network_errors_are_retried_then_raised(
    respx_mock: respx.MockRouter,
    http: httpx.AsyncClient,
    retry: RetryPolicy,
    sleeps: RecordingSleep,
) -> None:
    flaky = respx_mock.get(URL).mock(
        side_effect=[httpx.ConnectError("refused"), httpx.Response(200)]
    )
    assert (await request(http, "GET", URL, retry=retry)).status_code == 200
    assert flaky.call_count == 2
    respx_mock.get(f"{URL}/down").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(httpx.ReadTimeout):
        await request(http, "GET", f"{URL}/down", retry=retry)
    assert sleeps.waits == [1.0, 1.0, 2.0]


async def test_every_try_passes_the_gate(
    respx_mock: respx.MockRouter, http: httpx.AsyncClient, retry: RetryPolicy
) -> None:
    entries: list[str] = []

    @asynccontextmanager
    async def gate() -> AsyncIterator[None]:
        entries.append("token")
        yield

    respx_mock.get(URL).mock(side_effect=[httpx.Response(500), httpx.Response(200)])
    await request(http, "GET", URL, gate=gate, retry=retry)
    assert entries == ["token", "token"]


def test_retry_after_accepts_seconds_and_http_dates() -> None:
    now = datetime(2026, 10, 30, 12, 0, 0, tzinfo=UTC)
    dated = httpx.Response(429, headers={"Retry-After": "Fri, 30 Oct 2026 12:00:30 GMT"})
    assert retry_after_seconds(dated, now=now) == 30.0
    assert retry_after_seconds(httpx.Response(429, headers={"Retry-After": "7"})) == 7.0
    assert retry_after_seconds(httpx.Response(429, headers={"Retry-After": "soon"})) is None
    assert retry_after_seconds(httpx.Response(429)) is None


def test_a_policy_needs_one_try() -> None:
    with pytest.raises(ValueError, match="at least one try"):
        RetryPolicy(tries=0)

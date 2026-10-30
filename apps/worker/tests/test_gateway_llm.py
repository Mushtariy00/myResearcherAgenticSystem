import json
import threading
from typing import Any

import httpx
import pytest

from agentic_worker.gateway_llm import (
    AttemptEndedError,
    FreeModelsDisabledError,
    GatewayLLM,
    GatewayRateLimitedError,
    GatewayUnavailableError,
    LabBalanceExhaustedError,
    RunInactiveError,
)

ANSWER = {"content": "ok", "model": "free/a", "tier": "free", "cost_usd": "0"}


def make_llm(handler: object, **fields: Any) -> GatewayLLM:
    llm = GatewayLLM(
        model="gateway",
        gateway_url="http://gw",
        gateway_token="secret",
        user_id="bob",
        agent_role="researcher",
        key_prefix="stage-run-1",
        run_id="run-1",
        **fields,
    )
    llm._client = httpx.Client(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]
    return llm


def test_each_call_gets_a_stable_idempotency_key_and_the_token() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret"
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=ANSWER)

    llm = make_llm(handler)
    assert llm.call("hello") == "ok"
    llm.call([{"role": "system", "content": "be brief"}, {"role": "tool", "content": "x"}])
    assert [b["idempotency_key"] for b in seen] == ["stage-run-1:call-1", "stage-run-1:call-2"]
    assert [m["role"] for m in seen[1]["messages"]] == ["system", "user"]  # type: ignore[index]
    assert len(llm.calls) == 2


def test_gateway_errors_become_typed_exceptions() -> None:
    llm = make_llm(
        lambda r: httpx.Response(429, json={"detail": "free_quota.exhausted", "retry_after": 42})
    )
    with pytest.raises(GatewayRateLimitedError) as exc:
        llm.call("hello")
    assert (exc.value.retry_after, exc.value.reason) == (42, "free_quota.exhausted")

    for status, error in (
        (402, LabBalanceExhaustedError),
        (403, FreeModelsDisabledError),
        (409, RunInactiveError),
        (500, GatewayUnavailableError),
        (502, GatewayUnavailableError),
    ):
        with pytest.raises(error):
            make_llm(lambda r, status=status: httpx.Response(status, json={})).call("hello")


def test_a_call_still_in_flight_waits_for_the_retry_after_header() -> None:
    llm = make_llm(
        lambda r: httpx.Response(
            429, json={"detail": "call.in_progress"}, headers={"Retry-After": "20"}
        )
    )
    with pytest.raises(GatewayRateLimitedError) as exc:
        llm.call("hello")
    assert (exc.value.retry_after, exc.value.reason) == (20, "call.in_progress")

    unknown = make_llm(lambda r: httpx.Response(429, json={"detail": "upstream.rate_limited"}))
    with pytest.raises(GatewayRateLimitedError) as exc:
        unknown.call("hello")
    assert (exc.value.retry_after, exc.value.reason) == (60, "free_quota.exhausted")


def test_an_unreachable_gateway_or_a_broken_answer_is_worth_retrying() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    for handler in (
        refuse,
        lambda r: httpx.Response(200, text="<html>proxy error</html>"),
        lambda r: httpx.Response(200, json={"model": "free/a"}),
    ):
        with pytest.raises(GatewayUnavailableError):
            make_llm(handler).call("hello")


def test_each_answer_reaches_the_attempt_as_it_arrives() -> None:
    answers: list[dict[str, Any]] = []
    llm = make_llm(lambda r: httpx.Response(200, json=ANSWER), on_call=answers.append)
    llm.call("hello")
    assert answers == [{**ANSWER, "idempotency_key": "stage-run-1:call-1"}]


def test_an_ended_attempt_makes_no_more_calls() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json=ANSWER)

    ended = threading.Event()
    llm = make_llm(handler, cancelled=ended)
    llm.call("plan")
    ended.set()  # execute_stage returned or was cancelled; CrewAI's thread runs on
    with pytest.raises(AttemptEndedError):
        llm.call("repair")
    assert len(sent) == 1

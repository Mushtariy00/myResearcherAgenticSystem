import json

import httpx
import pytest

from agentic_worker.gateway_llm import GatewayLLM, GatewayRateLimitedError, LabBalanceExhaustedError


def make_llm(handler: object) -> GatewayLLM:
    llm = GatewayLLM(
        model="gateway",
        gateway_url="http://gw",
        gateway_token="secret",
        user_id="bob",
        agent_role="researcher",
        key_prefix="stage-run-1",
        run_id="run-1",
    )
    llm._client = httpx.Client(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]
    return llm


def test_each_call_gets_a_stable_idempotency_key_and_the_token() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret"
        seen.append(json.loads(request.content))
        return httpx.Response(
            200, json={"content": "ok", "model": "free/a", "tier": "free", "cost_usd": "0"}
        )

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
    assert exc.value.retry_after == 42

    with pytest.raises(LabBalanceExhaustedError):
        make_llm(lambda r: httpx.Response(402, json={"detail": "lab_balance.exhausted"})).call(
            "hello"
        )

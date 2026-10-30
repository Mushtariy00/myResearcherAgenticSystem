"""CrewAI LLM that sends every call through the platform gateway (budget routing, spend journal).

Workers hold no provider keys: the gateway decides paid vs free and records each call.
"""

import threading
from collections.abc import Callable
from typing import Any

import httpx
from crewai.llms.base_llm import BaseLLM
from pydantic import ConfigDict, Field, PrivateAttr

_ROLES = {"system", "user", "assistant"}
# Why the gateway asks a call to wait (429): stage.waiting reasons, see agentic_core EventType.
WAIT_REASONS = frozenset({"free_quota.exhausted", "free_quota.unavailable", "call.in_progress"})
DEFAULT_RETRY_AFTER = 60.0


class GatewayRateLimitedError(Exception):
    """The gateway asks to send the call again after ``retry_after`` seconds."""

    def __init__(self, retry_after: float, reason: str = "free_quota.exhausted") -> None:
        super().__init__(f"{reason}; retry after {retry_after:.0f}s")
        self.retry_after = retry_after
        self.reason = reason


class LabBalanceExhaustedError(Exception):
    """The lab's OpenRouter balance is empty: even free models refuse calls."""


class FreeModelsDisabledError(Exception):
    """The project forbids free models and the budget can't pay."""


class RunInactiveError(Exception):
    """The run already ended; the gateway takes no more calls for it."""


class GatewayUnavailableError(Exception):
    """The gateway failed or could not be reached (worth retrying)."""


class AttemptEndedError(Exception):
    """The stage attempt has ended, so its CrewAI thread stops instead of calling the gateway."""


def _retry_after(response: httpx.Response, body: dict[str, Any]) -> float:
    """Seconds to wait: the Retry-After header, else the body's retry_after."""
    for value in (response.headers.get("retry-after"), body.get("retry_after")):
        if value is None:
            continue
        try:
            return max(1.0, float(value))
        except (TypeError, ValueError):
            continue
    return DEFAULT_RETRY_AFTER


def _body(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


class GatewayLLM(BaseLLM):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    model: str = "gateway"
    gateway_url: str
    gateway_token: str
    user_id: str  # the run owner; spend is charged to them
    agent_role: str  # routing role, e.g. "researcher"
    key_prefix: (
        str  # the stage attempt id; calls become "<prefix>:call-<n>" (stable across retries)
    )
    run_id: str | None = None
    project_id: str | None = None
    policy: str = "auto"
    budget_cap_usd: str | None = None
    max_output_tokens: int = 2048
    json_mode: bool = False
    # Above the gateway's 150 s deadline per call, so the gateway always answers first.
    timeout_seconds: float = 180.0
    calls: list[dict[str, Any]] = Field(
        default_factory=list
    )  # gateway answers, for llm.call events
    # Set when the stage attempt ends: the thread running CrewAI may outlive it.
    cancelled: threading.Event | None = None
    on_call: Callable[[dict[str, Any]], None] | None = None  # sees each answer as it arrives

    _counter: int = PrivateAttr(default=0)
    _client: httpx.Client | None = PrivateAttr(default=None)

    def call(
        self,
        messages: Any,
        tools: Any = None,
        callbacks: Any = None,
        available_functions: Any = None,
        from_task: Any = None,
        from_agent: Any = None,
        response_model: Any = None,
    ) -> str:
        if self.cancelled is not None and self.cancelled.is_set():
            raise AttemptEndedError(self.key_prefix)
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        self._counter += 1
        key = f"{self.key_prefix}:call-{self._counter}"
        payload = {
            "idempotency_key": key,
            "user_id": self.user_id,
            "role": self.agent_role,
            "messages": [
                {
                    "role": m.get("role") if m.get("role") in _ROLES else "user",
                    "content": str(m.get("content") or ""),
                }
                for m in messages
            ],
            "run_id": self.run_id,
            "project_id": self.project_id,
            "policy": self.policy,
            "budget_cap_usd": self.budget_cap_usd,
            "max_output_tokens": self.max_output_tokens,
            "json_mode": self.json_mode,
        }
        client = self._client or httpx.Client(timeout=self.timeout_seconds)
        try:
            response = client.post(
                f"{self.gateway_url.rstrip('/')}/v1/complete",
                json=payload,
                headers={"authorization": f"Bearer {self.gateway_token}"},
            )
        except httpx.TransportError as exc:  # connect errors and timeouts
            raise GatewayUnavailableError(f"{type(exc).__name__} for {key}") from exc
        finally:
            if self._client is None:
                client.close()
        body = _body(response)
        detail = body.get("detail")
        if response.status_code == 429:
            reason = detail if isinstance(detail, str) and detail in WAIT_REASONS else None
            raise GatewayRateLimitedError(
                _retry_after(response, body), reason or "free_quota.exhausted"
            )
        if response.status_code == 402:
            raise LabBalanceExhaustedError
        if response.status_code == 403:
            raise FreeModelsDisabledError
        if response.status_code == 409:
            raise RunInactiveError(key)
        if not response.is_success or not isinstance(body.get("content"), str):
            raise GatewayUnavailableError(f"HTTP {response.status_code} for {key}")
        call = {**body, "idempotency_key": key}
        self.calls.append(call)
        if self.on_call is not None:
            self.on_call(call)
        return body["content"]

    def supports_function_calling(self) -> bool:
        return False

    def supports_stop_words(self) -> bool:
        return False

    def get_context_window_size(self) -> int:
        return 32_000

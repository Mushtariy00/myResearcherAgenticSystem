"""CrewAI LLM that sends every call through the platform gateway (budget routing, spend journal).

Workers hold no provider keys: the gateway decides paid vs free and records each call.
"""

from typing import Any

import httpx
from crewai.llms.base_llm import BaseLLM
from pydantic import ConfigDict, Field, PrivateAttr

_ROLES = {"system", "user", "assistant"}


class GatewayRateLimitedError(Exception):
    def __init__(self, retry_after: float) -> None:
        super().__init__(f"free model quota exhausted; retry after {retry_after:.0f}s")
        self.retry_after = retry_after


class LabBalanceExhaustedError(Exception):
    """The lab's OpenRouter balance is empty: even free models refuse calls."""


class FreeModelsDisabledError(Exception):
    """The project forbids free models and the budget can't pay."""


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
    timeout_seconds: float = 180.0
    calls: list[dict[str, Any]] = Field(
        default_factory=list
    )  # gateway answers, for llm.call events

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
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        self._counter += 1
        payload = {
            "idempotency_key": f"{self.key_prefix}:call-{self._counter}",
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
        finally:
            if self._client is None:
                client.close()
        if response.status_code == 429:
            raise GatewayRateLimitedError(float(response.json().get("retry_after", 60)))
        if response.status_code == 402:
            raise LabBalanceExhaustedError
        if response.status_code == 403:
            raise FreeModelsDisabledError
        response.raise_for_status()
        body = response.json()
        self.calls.append(body)
        return str(body["content"])

    def supports_function_calling(self) -> bool:
        return False

    def supports_stop_words(self) -> bool:
        return False

    def get_context_window_size(self) -> int:
        return 32_000

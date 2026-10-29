"""Thin OpenRouter chat client with the error classes routing decisions depend on."""

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx


class UpstreamError(Exception):
    """Model unavailable, overloaded or timed out: try the next model in the chain."""


class KeyLimitError(Exception):
    """HTTP 402 with limit_source=openrouter_key_limit: this key's budget is used up."""


class AccountBalanceError(Exception):
    """HTTP 402 for the account itself (no credits): even free models stop working."""


class UpstreamRateLimitError(Exception):
    def __init__(self, retry_after: float) -> None:
        super().__init__(f"rate limited, retry after {retry_after}s")
        self.retry_after = retry_after


@dataclass(frozen=True)
class ChatResult:
    content: str
    model: str
    generation_id: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    cost_usd: Decimal | None
    latency_ms: int


class OpenRouterClient:
    def __init__(
        self, client: httpx.AsyncClient, base_url: str, api_key: str, referer: str
    ) -> None:
        self._client = client
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": referer,
            "X-Title": "Agentic Research Platform",
        }

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        json_mode: bool,
        deny_data_collection: bool,
        request_timeout: float,
    ) -> ChatResult:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "usage": {"include": True},  # actual cost in the response
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if deny_data_collection:
            body["provider"] = {"data_collection": "deny"}

        started = time.monotonic()
        try:
            response = await self._client.post(
                self._url, json=body, headers=self._headers, timeout=request_timeout
            )
        except httpx.TimeoutException as exc:
            raise UpstreamError(f"timeout calling {model}") from exc
        except httpx.HTTPError as exc:
            raise UpstreamError(f"network error calling {model}: {exc}") from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        if response.status_code == 402:
            metadata = (_error(response).get("metadata") or {}) if _is_json(response) else {}
            if metadata.get("limit_source") == "openrouter_key_limit":
                raise KeyLimitError(model)
            raise AccountBalanceError(model)
        if response.status_code == 429:
            raise UpstreamRateLimitError(_retry_after(response))
        if response.status_code >= 500 or response.status_code in (404, 408):
            raise UpstreamError(f"{model} returned HTTP {response.status_code}")
        response.raise_for_status()

        payload = response.json()
        if "error" in payload:  # OpenRouter can report provider errors with HTTP 200
            raise UpstreamError(f"{model}: {payload['error']}")
        choices = payload.get("choices") or []
        content = (choices[0].get("message") or {}).get("content") if choices else None
        if not content:
            raise UpstreamError(f"{model} returned an empty answer")
        usage = payload.get("usage") or {}
        cost = usage.get("cost")
        return ChatResult(
            content=content,
            model=str(payload.get("model") or model),
            generation_id=payload.get("id"),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            cost_usd=Decimal(str(cost)) if cost is not None else None,
            latency_ms=latency_ms,
        )


def _is_json(response: httpx.Response) -> bool:
    return response.headers.get("content-type", "").startswith("application/json")


def _error(response: httpx.Response) -> dict[str, Any]:
    body = response.json()
    return body.get("error") or {} if isinstance(body, dict) else {}


def _retry_after(response: httpx.Response) -> float:
    try:
        return max(1.0, float(response.headers.get("retry-after", "10")))
    except ValueError:
        return 10.0

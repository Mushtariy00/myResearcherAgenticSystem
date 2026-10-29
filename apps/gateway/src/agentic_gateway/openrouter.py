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
    """A per-model or per-minute limit: another model may still answer."""

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"rate limited, retry after {retry_after}s")
        self.retry_after = retry_after


class FreeDailyLimitError(Exception):
    """The account's free requests for the UTC day are used up (shared by every free model).

    Without purchased credits the cap is 50/day; $10 of lifetime credits raises it to 1,000/day.
    """

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"free daily limit reached, resets in {retry_after:.0f}s")
        self.retry_after = retry_after


class AuthError(Exception):
    """HTTP 401: the OpenRouter key is invalid or revoked (a configuration problem)."""


# Responses that cost nothing and are fully understood; anything else may have been billed.
KNOWN_UPSTREAM_ERRORS = (
    UpstreamError,
    KeyLimitError,
    AccountBalanceError,
    UpstreamRateLimitError,
    FreeDailyLimitError,
    AuthError,
)


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

        if response.status_code >= 400:
            error = _error(response) if _is_json(response) else {}
            metadata = error.get("metadata") or {}
            message = str(error.get("message") or response.reason_phrase)[:300]
            if response.status_code == 402:
                if metadata.get("limit_source") == "openrouter_key_limit":
                    raise KeyLimitError(model)
                raise AccountBalanceError(model)
            if response.status_code == 429:
                retry_after = _retry_after(response, metadata)
                if metadata.get("limit_source") == "openrouter_free_tier_daily":
                    raise FreeDailyLimitError(retry_after)
                raise UpstreamRateLimitError(retry_after)
            if response.status_code == 401:
                raise AuthError(message)
            # 400/403/404/5xx: this model can't serve the request (e.g. restricted to certain
            # apps, or overloaded). Another model in the chain may.
            raise UpstreamError(f"{model} returned HTTP {response.status_code}: {message}")

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
    try:
        body = response.json()
    except ValueError:
        return {}
    return (body.get("error") or {}) if isinstance(body, dict) else {}


def _retry_after(response: httpx.Response, metadata: dict[str, Any]) -> float:
    """Seconds until the limit resets: X-RateLimit-Reset (epoch ms) if given, else Retry-After."""
    headers = {k.lower(): v for k, v in (metadata.get("headers") or {}).items()}
    reset = headers.get("x-ratelimit-reset") or response.headers.get("x-ratelimit-reset")
    try:
        if reset is not None:
            return max(1.0, float(reset) / 1000 - time.time())
        return max(1.0, float(response.headers.get("retry-after", "10")))
    except ValueError:
        return 10.0

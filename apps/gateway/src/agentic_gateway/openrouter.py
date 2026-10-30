"""Thin OpenRouter chat client with the error classes routing decisions depend on."""

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

# Spending limits OpenRouter reports as 402 or 403: the key's own credit limit, or a guardrail or
# workspace budget. Retrying before the limit resets fails the same way.
BUDGET_LIMIT_SOURCES = frozenset(
    {"openrouter_key_limit", "openrouter_guardrail_budget", "openrouter_workspace_budget"}
)
# Failures before the request left this host: nothing reached OpenRouter, so nothing is billed.
# Any other transport error happened after (part of) the request was sent.
NOT_SENT_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    httpx.ProxyError,
    httpx.UnsupportedProtocol,
)


class UpstreamError(Exception):
    """Model unavailable, overloaded or unreachable: try the next model in the chain."""


class UpstreamInterruptedError(Exception):
    """The request was sent but no usable answer came back (read timeout, dropped connection,
    unreadable body). OpenRouter keeps processing a non-streaming request after the client gives
    up and bills it in full."""


class KeyLimitError(Exception):
    """A spending limit (BUDGET_LIMIT_SOURCES) is used up: paid calls stop working."""


class AccountBalanceError(Exception):
    """HTTP 402 that isn't a key limit: the account's credits can't pay for the call. If free
    models fail this way too, the lab balance is gone."""


class UpstreamRateLimitError(Exception):
    """A per-model or per-minute limit, or credit held by requests still in flight: another model
    may still answer, or this one after retry_after."""

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


@dataclass(frozen=True)
class ChatResult:
    content: str
    model: str
    generation_id: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    cost_usd: Decimal | None
    latency_ms: int


class NoAnswerError(Exception):
    """HTTP 200 without an answer: an error in the body, or empty content (a thinking model can
    spend all of max_tokens on reasoning). The provider may still bill it, so the reported cost
    and generation id come along in ``result``."""

    def __init__(self, reason: str, result: ChatResult) -> None:
        super().__init__(f"{result.model}: {reason}")
        self.reason = reason  # "provider_error" or "empty_answer"
        self.result = result


# Upstream answers the router records itself: it releases the row, or settles it when the
# answer may have been billed. Anything else may have been billed too and leaves the row unknown.
KNOWN_UPSTREAM_ERRORS = (
    UpstreamError,
    NoAnswerError,
    KeyLimitError,
    AccountBalanceError,
    UpstreamRateLimitError,
    FreeDailyLimitError,
    AuthError,
)


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
        except NOT_SENT_ERRORS as exc:
            raise UpstreamError(f"could not reach OpenRouter for {model}: {exc!r}") from exc
        except httpx.HTTPError as exc:
            raise UpstreamInterruptedError(f"{model}: {exc!r} after sending") from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        if response.status_code >= 400:
            error = _error(response) if _is_json(response) else {}
            metadata = _mapping(error.get("metadata"))
            limit_source = metadata.get("limit_source")
            message = str(error.get("message") or response.reason_phrase)[:300]
            if response.status_code in (402, 403) and limit_source in BUDGET_LIMIT_SOURCES:
                raise KeyLimitError(f"{model}: {limit_source}")
            if response.status_code == 402:
                if limit_source == "openrouter_in_flight_budget":
                    # Credit held by requests still running: wait for them and retry.
                    raise UpstreamRateLimitError(_retry_after(response, metadata))
                raise AccountBalanceError(model)
            if response.status_code == 429:
                retry_after = _retry_after(response, metadata)
                if limit_source == "openrouter_free_tier_daily":
                    raise FreeDailyLimitError(retry_after)
                raise UpstreamRateLimitError(retry_after)
            if response.status_code == 401:
                raise AuthError(message)
            # 400/403/404/5xx: this model can't serve the request (e.g. restricted to certain
            # apps, or overloaded). Another model in the chain may.
            raise UpstreamError(f"{model} returned HTTP {response.status_code}: {message}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise UpstreamInterruptedError(f"{model} returned an unreadable answer") from exc
        if not isinstance(payload, dict):
            raise UpstreamInterruptedError(f"{model} returned an unreadable answer")
        usage = _mapping(payload.get("usage"))
        cost = usage.get("cost")
        choices = payload.get("choices")
        first = _mapping(choices[0]) if isinstance(choices, list) and choices else {}
        content = _mapping(first.get("message")).get("content")
        result = ChatResult(
            content=content if isinstance(content, str) else "",
            model=str(payload.get("model") or model),
            generation_id=payload.get("id"),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            cost_usd=Decimal(str(cost)) if cost is not None else None,
            latency_ms=latency_ms,
        )
        if "error" in payload:  # OpenRouter reports errors met while generating with HTTP 200
            raise NoAnswerError("provider_error", result)
        if not result.content:
            raise NoAnswerError("empty_answer", result)
        return result


def _is_json(response: httpx.Response) -> bool:
    return response.headers.get("content-type", "").startswith("application/json")


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _error(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return _mapping(body.get("error")) if isinstance(body, dict) else {}


def _retry_after(response: httpx.Response, metadata: dict[str, Any]) -> float:
    """Seconds until the limit resets: X-RateLimit-Reset (epoch ms) if given, else Retry-After."""
    headers = {k.lower(): v for k, v in _mapping(metadata.get("headers")).items()}
    reset = headers.get("x-ratelimit-reset") or response.headers.get("x-ratelimit-reset")
    try:
        if reset is not None:
            return max(1.0, float(reset) / 1000 - time.time())
        return max(1.0, float(response.headers.get("retry-after", "10")))
    except ValueError:
        return 10.0

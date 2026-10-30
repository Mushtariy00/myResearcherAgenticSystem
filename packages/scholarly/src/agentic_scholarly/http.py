"""HTTP plumbing shared by the scholarly API clients: the client factory and the retry helper.

PDF downloads do not use this client: URLs found in metadata go through
``agentic_scholarly.fetch``, which adds the SSRF guard.
"""

import asyncio
import email.utils
from collections.abc import Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager, nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

import httpx

PRODUCT: Final = "ARP/0.1"
DEFAULT_TIMEOUT: Final = httpx.Timeout(20.0, connect=10.0)
# Transient failures worth another try; protocol misuse and bad URLs are not.
RETRYABLE_ERRORS: Final = (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)

# Something entered around every try, such as a rate-limit token or a mutex.
Gate = Callable[[], AbstractAsyncContextManager[object]]


def user_agent(contact: str | None = None) -> str:
    """ARP's User-Agent. APIs such as Crossref serve requests that carry a mailto more politely."""
    if contact is None:
        return PRODUCT
    contact = contact.strip()
    if not contact or any(char in contact for char in "\r\n()"):
        raise ValueError(f"not a usable contact address: {contact!r}")
    return f"{PRODUCT} (+mailto:{contact})"


def make_client(
    contact: str,
    *,
    timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    max_connections: int = 20,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """The AsyncClient for scholarly APIs; share one per process and close it on shutdown.

    ``trust_env=False`` keeps proxy and certificate settings in code, so a stray HTTPS_PROXY in
    the environment cannot reroute API traffic. Redirects are not followed: these APIs answer
    directly, and an unexpected redirect should surface as an error rather than be chased.
    """
    return httpx.AsyncClient(
        headers={"User-Agent": user_agent(contact)},
        timeout=timeout,
        limits=httpx.Limits(
            max_connections=max_connections, max_keepalive_connections=max_connections
        ),
        trust_env=False,
        follow_redirects=False,
        transport=transport,
    )


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """How ``request`` retries.

    ``backoff_seconds`` is the wait after the first failure and doubles after each one. A
    Retry-After longer than ``max_wait_seconds`` stops retrying: the response goes back to the
    caller, which can wait without holding a worker slot.
    """

    tries: int = 3
    backoff_seconds: float = 1.0
    max_wait_seconds: float = 30.0
    statuses: frozenset[int] = frozenset({429, *range(500, 600)})
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

    def __post_init__(self) -> None:
        if self.tries < 1:
            raise ValueError("a retry policy needs at least one try")


DEFAULT_RETRY: Final = RetryPolicy()


def retry_after_seconds(response: httpx.Response, *, now: datetime | None = None) -> float | None:
    """The wait a Retry-After header asks for (delta-seconds or an HTTP date), if any."""
    value = response.headers.get("retry-after", "").strip()
    if not value:
        return None
    if value.isdigit():
        return float(value)
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - (now or datetime.now(UTC))).total_seconds())


async def request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    params: Mapping[str, str | int] | None = None,
    headers: Mapping[str, str] | None = None,
    data: Mapping[str, str] | None = None,
    files: Mapping[str, tuple[str, bytes, str]] | None = None,
    timeout: httpx.Timeout | None = None,  # noqa: ASYNC109 - httpx's per-request timeouts
    gate: Gate | None = None,
    retry: RetryPolicy = DEFAULT_RETRY,
) -> httpx.Response:
    """Send a request, retrying 429 and 5xx answers and transient network errors.

    Every try enters ``gate()`` first, so retries spend rate-limit tokens like any request. The
    last response is returned whatever its status; a network error on the last try propagates.
    """
    attempt = 1
    while True:
        try:
            async with gate() if gate is not None else nullcontext():
                response = await client.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    data=data,
                    files=files,
                    timeout=timeout if timeout is not None else httpx.USE_CLIENT_DEFAULT,
                )
        except RETRYABLE_ERRORS:
            if attempt >= retry.tries:
                raise
            wait = retry.backoff_seconds * 2 ** (attempt - 1)
        else:
            if response.status_code not in retry.statuses or attempt >= retry.tries:
                return response
            asked = retry_after_seconds(response)
            if asked is not None and asked > retry.max_wait_seconds:
                return response
            wait = asked if asked is not None else retry.backoff_seconds * 2 ** (attempt - 1)
        await retry.sleep(wait)
        attempt += 1

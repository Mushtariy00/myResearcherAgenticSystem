"""The one way to download a URL found in paper metadata: an SSRF-guarded fetch of a PDF.

Metadata URLs come from third parties, so nothing about them is trusted:

- https only, no credentials in the URL;
- the host is resolved once and every address must be public (no loopback, private,
  link-local, CGNAT, multicast, reserved, unspecified, unique-local or site-local address, and
  IPv4-mapped, 6to4, Teredo and NAT64 forms are judged by the IPv4 address they carry);
- the socket connects to the vetted address itself, so a second DNS answer cannot swap in an
  internal one, while TLS SNI, certificate checks and the Host header keep the hostname;
- redirects are followed by hand, at most five, and each target is checked the same way;
- the body is streamed uncompressed under a size cap and a total deadline, and must be a PDF
  (an allowed Content-Type, ``%PDF-`` first, at least 10 KB).

The guard sits in the connection layer (an httpcore network backend under a custom httpx
transport), so even direct use of ``SafeClient`` cannot reach a private address.
"""

import asyncio
import hashlib
import ipaddress
import socket
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Final, cast

import httpcore
import httpx

from agentic_scholarly.http import user_agent

MAX_REDIRECTS: Final = 5
MIN_PDF_BYTES: Final = 10 * 1024
DEFAULT_MAX_BYTES: Final = 40_000_000
DEFAULT_DEADLINE_SECONDS: Final = 60.0
PDF_CONTENT_TYPES: Final = frozenset(
    {"application/pdf", "application/octet-stream", "binary/octet-stream"}
)
FETCH_TIMEOUT: Final = httpx.Timeout(20.0, connect=10.0)
PDF_MAGIC: Final = b"%PDF-"
_REDIRECT_STATUSES: Final = frozenset({301, 302, 303, 307, 308})
_SHARED_ADDRESS_SPACE: Final = ipaddress.IPv4Network("100.64.0.0/10")  # CGNAT, RFC 6598
_UNIQUE_LOCAL: Final = ipaddress.IPv6Network("fc00::/7")
_NAT64: Final = ipaddress.IPv6Network("64:ff9b::/96")

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
# (host, port) -> every address the host resolves to, as strings.
Resolver = Callable[[str, int], Awaitable[list[str]]]


class FetchError(Exception):
    """A PDF could not be fetched; ``code`` is a short message code such as ``fetch.too_large``."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class FetchRefused(FetchError):
    """The URL or the response breaks the fetch policy; the same URL will not work later."""


class FetchFailed(FetchError):
    """The network or the server failed (``status`` for HTTP errors); it may work later."""

    def __init__(self, code: str, detail: str = "", *, status: int | None = None) -> None:
        super().__init__(code, detail)
        self.status = status


@dataclass(frozen=True, slots=True)
class FetchedPdf:
    data: bytes = field(repr=False)
    final_url: str
    content_type: str
    sha256: str


def is_public_address(address: IPAddress) -> bool:
    """Whether a connection to address could only reach the public internet."""
    if isinstance(address, ipaddress.IPv6Address):
        embedded = _embedded_ipv4(address)
        if embedded:
            return all(is_public_address(inner) for inner in embedded)
        # Deprecated site-local (fec0::/10) passes Python's is_global. Unique-local and CGNAT
        # are named too, so the rule does not hinge on how a Python release sets its flags.
        if address.is_site_local or address in _UNIQUE_LOCAL:
            return False
    elif address in _SHARED_ADDRESS_SPACE:
        return False
    restricted = (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )
    return address.is_global and not restricted


def _embedded_ipv4(address: ipaddress.IPv6Address) -> list[ipaddress.IPv4Address]:
    """The IPv4 addresses a transition form tunnels to (IPv4-mapped, 6to4, Teredo, NAT64)."""
    if address.ipv4_mapped is not None:
        return [address.ipv4_mapped]
    if address.sixtofour is not None:
        return [address.sixtofour]
    if address.teredo is not None:
        return list(address.teredo)
    if address in _NAT64:
        return [ipaddress.IPv4Address(int(address) & 0xFFFF_FFFF)]
    return []


async def resolve_host(host: str, port: int) -> list[str]:
    """Every address the system resolver gives for host (an IP literal resolves to itself)."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


class _GuardedBackend(httpcore.AsyncNetworkBackend):
    """Resolves and vets the host, then connects the inner backend to a vetted IP address.

    httpcore passes the URL's hostname here and later uses that same hostname for TLS SNI and
    certificate verification, so only the TCP destination changes.
    """

    def __init__(self, resolver: Resolver | None, inner: httpcore.AsyncNetworkBackend) -> None:
        self._resolver = resolver
        self._inner = inner

    # The signatures below are httpcore's AsyncNetworkBackend interface.
    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        last_error: Exception | None = None
        for address in await self._vetted(host, port, timeout_seconds=timeout):
            try:
                return await self._inner.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_error = exc
        raise last_error or FetchFailed("fetch.dns", f"{host} has no address")

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise FetchRefused("fetch.scheme", "unix sockets are never reachable from metadata")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)

    async def _vetted(self, host: str, port: int, *, timeout_seconds: float | None) -> list[str]:
        # Looked up at call time so tests can monkeypatch the module's resolver.
        resolver = self._resolver or resolve_host
        try:
            async with asyncio.timeout(timeout_seconds):
                found = await resolver(host, port)
        except TimeoutError as exc:
            raise FetchFailed("fetch.dns", f"resolving {host} timed out") from exc
        except OSError as exc:
            raise FetchFailed("fetch.dns", f"cannot resolve {host}") from exc
        if not found:
            raise FetchFailed("fetch.dns", f"{host} has no address")
        vetted: list[str] = []
        for value in found:
            try:
                address = ipaddress.ip_address(value)
            except ValueError:
                raise FetchRefused("fetch.private_address", f"{host} gave {value!r}") from None
            if not is_public_address(address):
                raise FetchRefused("fetch.private_address", f"{host} resolves to {address}")
            vetted.append(str(address))
        return vetted


# httpcore errors and the httpx errors httpx's own transport turns them into, most specific
# first.
_ERRORS: Final[tuple[tuple[type[Exception], type[httpx.TransportError]], ...]] = (
    (httpcore.ConnectTimeout, httpx.ConnectTimeout),
    (httpcore.ReadTimeout, httpx.ReadTimeout),
    (httpcore.WriteTimeout, httpx.WriteTimeout),
    (httpcore.PoolTimeout, httpx.PoolTimeout),
    (httpcore.TimeoutException, httpx.TimeoutException),
    (httpcore.ConnectError, httpx.ConnectError),
    (httpcore.ReadError, httpx.ReadError),
    (httpcore.WriteError, httpx.WriteError),
    (httpcore.NetworkError, httpx.NetworkError),
    (httpcore.RemoteProtocolError, httpx.RemoteProtocolError),
    (httpcore.LocalProtocolError, httpx.LocalProtocolError),
    (httpcore.ProtocolError, httpx.ProtocolError),
    (httpcore.UnsupportedProtocol, httpx.UnsupportedProtocol),
)


@contextmanager
def _httpx_errors() -> Iterator[None]:
    try:
        yield
    except Exception as exc:
        for core_error, httpx_error in _ERRORS:
            if isinstance(exc, core_error):
                raise httpx_error(str(exc)) from exc
        raise


class _ResponseStream(httpx.AsyncByteStream):
    def __init__(self, stream: Iterable[bytes] | AsyncIterable[bytes]) -> None:
        self._stream = stream

    async def __aiter__(self) -> AsyncIterator[bytes]:
        if not isinstance(self._stream, AsyncIterable):
            raise TypeError("an async connection pool returned a sync stream")
        with _httpx_errors():
            async for chunk in self._stream:
                yield chunk

    async def aclose(self) -> None:
        close = getattr(self._stream, "aclose", None)
        if close is not None:
            await close()


class SafeTransport(httpx.AsyncBaseTransport):
    """An httpx transport that only opens https connections to vetted public addresses.

    httpx's own transport cannot take an httpcore network backend, so this one wraps an httpcore
    connection pool directly, translating requests, responses and errors as httpx does.
    """

    def __init__(
        self,
        *,
        resolver: Resolver | None = None,
        network_backend: httpcore.AsyncNetworkBackend | None = None,
        max_connections: int = 16,
    ) -> None:
        # httpcore declares a placeholder AnyIOBackend for installs without anyio; httpx always
        # brings anyio, so this is the real asyncio backend.
        inner = network_backend or cast(httpcore.AsyncNetworkBackend, httpcore.AnyIOBackend())
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpx.create_ssl_context(trust_env=False),
            max_connections=max_connections,
            keepalive_expiry=5.0,
            network_backend=_GuardedBackend(resolver, inner),
        )

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.scheme != "https":
            raise FetchRefused("fetch.scheme", f"{request.url.scheme or 'no'} scheme")
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        with _httpx_errors():
            response = await self._pool.handle_async_request(core_request)
        return httpx.Response(
            status_code=response.status,
            headers=response.headers,
            stream=_ResponseStream(response.stream),
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        await self._pool.aclose()


class SafeClient(httpx.AsyncClient):
    """The httpx client for URLs found in metadata: every connection goes through the guard.

    Share one per worker process (it pools connections) and close it on shutdown.
    """

    def __init__(
        self,
        *,
        contact: str | None = None,
        resolver: Resolver | None = None,
        network_backend: httpcore.AsyncNetworkBackend | None = None,
        timeout: httpx.Timeout = FETCH_TIMEOUT,
        max_connections: int = 16,
    ) -> None:
        super().__init__(
            transport=SafeTransport(
                resolver=resolver,
                network_backend=network_backend,
                max_connections=max_connections,
            ),
            headers={
                "User-Agent": user_agent(contact),
                "Accept": "application/pdf, application/octet-stream;q=0.9, */*;q=0.1",
                "Accept-Encoding": "identity",
            },
            timeout=timeout,
            trust_env=False,
            follow_redirects=False,
        )


async def fetch_pdf(
    url: str,
    *,
    client: SafeClient | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
) -> FetchedPdf:
    """Download the PDF at url under the rules in the module docstring.

    Raises FetchRefused for policy refusals and FetchFailed for network or HTTP failures.
    Without a client, a temporary SafeClient is used and closed.
    """
    if client is not None and not isinstance(client, SafeClient):
        raise TypeError("fetch_pdf needs a SafeClient; other clients bypass the SSRF guard")
    if client is None:
        async with SafeClient() as temporary:
            return await _fetch_within(temporary, url, max_bytes, deadline_seconds)
    return await _fetch_within(client, url, max_bytes, deadline_seconds)


async def _fetch_within(
    client: SafeClient, url: str, max_bytes: int, deadline_seconds: float
) -> FetchedPdf:
    try:
        async with asyncio.timeout(deadline_seconds):
            return await _fetch(client, url, max_bytes)
    except TimeoutError as exc:
        raise FetchFailed("fetch.deadline", f"no PDF within {deadline_seconds:g} s") from exc


async def _fetch(client: SafeClient, url: str, max_bytes: int) -> FetchedPdf:
    target = checked_url(url)
    for redirects in range(MAX_REDIRECTS + 1):
        with _fetch_errors():
            response = await client.send(
                client.build_request("GET", target), stream=True, follow_redirects=False
            )
            try:
                if response.status_code not in _REDIRECT_STATUSES:
                    return await _read_pdf(response, max_bytes)
                if redirects == MAX_REDIRECTS:
                    raise FetchRefused("fetch.too_many_redirects", f"more than {MAX_REDIRECTS}")
                target = _redirect_target(response)
            finally:
                await response.aclose()
    # The last pass returns or raises; this satisfies the type checker.
    raise FetchRefused("fetch.too_many_redirects", f"more than {MAX_REDIRECTS}")


def checked_url(url: str) -> httpx.URL:
    """url parsed, if it is an https URL with a host and no credentials."""
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL as exc:
        raise FetchRefused("fetch.bad_url", str(exc)) from exc
    if parsed.scheme != "https":
        raise FetchRefused("fetch.scheme", f"{parsed.scheme or 'no'} scheme")
    if not parsed.host:
        raise FetchRefused("fetch.bad_url", "no host")
    if parsed.userinfo:
        raise FetchRefused("fetch.bad_url", "credentials in the URL")
    return parsed


@contextmanager
def _fetch_errors() -> Iterator[None]:
    """httpx failures as FetchFailed; policy errors pass through unchanged."""
    try:
        yield
    except httpx.TimeoutException as exc:
        raise FetchFailed("fetch.timeout", type(exc).__name__) from exc
    except httpx.ConnectError as exc:
        raise FetchFailed("fetch.connect", str(exc)) from exc
    except httpx.RequestError as exc:
        raise FetchFailed("fetch.network", type(exc).__name__) from exc


def _redirect_target(response: httpx.Response) -> httpx.URL:
    location = response.headers.get("location")
    if not location:
        raise FetchFailed(
            "fetch.bad_redirect", "redirect without a Location", status=response.status_code
        )
    try:
        joined = response.url.join(location)
    except httpx.InvalidURL as exc:
        raise FetchRefused("fetch.bad_url", str(exc)) from exc
    return checked_url(str(joined))


async def _read_pdf(response: httpx.Response, max_bytes: int) -> FetchedPdf:
    if response.status_code != 200:
        raise FetchFailed(
            "fetch.http_status", f"HTTP {response.status_code}", status=response.status_code
        )
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in PDF_CONTENT_TYPES:
        raise FetchRefused("fetch.content_type", content_type or "no Content-Type")
    # The request asks for identity; decoding a compressed body would let a small download
    # expand past the size cap before it could be checked.
    encoding = response.headers.get("content-encoding", "").strip().lower()
    if encoding not in ("", "identity"):
        raise FetchRefused("fetch.content_encoding", encoding)
    declared = response.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > max_bytes:
        raise FetchRefused("fetch.too_large", f"{declared} bytes declared")
    body = bytearray()
    async for chunk in response.aiter_raw():
        body += chunk
        if len(body) > max_bytes:
            raise FetchRefused("fetch.too_large", f"more than {max_bytes} bytes")
        # Stop at the first bytes of an HTML error page instead of downloading all of it.
        if len(body) >= len(PDF_MAGIC) and not body.startswith(PDF_MAGIC):
            raise FetchRefused("fetch.not_pdf", "the body does not start with %PDF-")
    if not body.startswith(PDF_MAGIC):
        raise FetchRefused("fetch.not_pdf", "the body does not start with %PDF-")
    if len(body) < MIN_PDF_BYTES:
        raise FetchRefused("fetch.too_small", f"{len(body)} bytes")
    data = bytes(body)
    return FetchedPdf(
        data=data,
        final_url=str(response.url),
        content_type=content_type,
        sha256=hashlib.sha256(data).hexdigest(),
    )

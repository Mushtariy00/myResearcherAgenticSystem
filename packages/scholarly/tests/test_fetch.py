"""The SSRF guard and the PDF rules of agentic_scholarly.fetch.

Requests run through the real SafeClient, transport and httpcore pool; only the resolver and
the sockets are replaced (FakeNetwork), so these tests exercise what production runs.
"""

import hashlib
import ipaddress
from collections.abc import Mapping

import httpx
import pytest

from agentic_scholarly import fetch
from agentic_scholarly.fetch import (
    DEFAULT_MAX_BYTES,
    MIN_PDF_BYTES,
    FetchFailed,
    FetchRefused,
    SafeClient,
    fetch_pdf,
    is_public_address,
)
from agentic_scholarly.testing import FakeNetwork, http_response

PUBLIC_IP = "93.184.215.14"
OTHER_PUBLIC_IP = "151.101.1.69"
PDF_BODY = b"%PDF-1.7\n" + b"0" * (MIN_PDF_BYTES + 100)
PDF_HEADERS = {"Content-Type": "application/pdf"}


class Resolver:
    """A resolver stub that counts lookups per host."""

    def __init__(self, answers: Mapping[str, list[str]]) -> None:
        self.answers = answers
        self.lookups: list[str] = []

    async def __call__(self, host: str, port: int) -> list[str]:
        self.lookups.append(host)
        return self.answers[host]


def client_for(resolver: Resolver, network: FakeNetwork) -> SafeClient:
    return SafeClient(contact="lab@example.org", resolver=resolver, network_backend=network)


def stub_resolver(monkeypatch: pytest.MonkeyPatch, addresses: list[str]) -> None:
    async def resolve(host: str, port: int) -> list[str]:
        return addresses

    monkeypatch.setattr(fetch, "resolve_host", resolve)


@pytest.mark.parametrize(
    "address",
    [
        "169.254.169.254",
        "127.0.0.1",
        "10.0.0.1",
        "172.16.5.4",
        "192.168.1.1",
        "100.64.0.1",
        "0.0.0.0",  # noqa: S104 - an address to refuse, not one to bind
        "224.0.0.1",
        "240.0.0.1",
        "::1",
        "fe80::1",
        "fc00::1",
        "fd12:3456::1",
        "fec0::1",
        "::",
        "::ffff:127.0.0.1",
        "::ffff:169.254.169.254",
        "2002:a00:1::",
        "64:ff9b::a00:1",
    ],
)
async def test_private_and_special_addresses_are_refused(
    monkeypatch: pytest.MonkeyPatch, address: str
) -> None:
    stub_resolver(monkeypatch, [address])
    with pytest.raises(FetchRefused) as caught:
        await fetch_pdf("https://papers.example.org/paper.pdf")
    assert caught.value.code == "fetch.private_address"


async def test_one_private_address_among_public_ones_is_enough_to_refuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_resolver(monkeypatch, [PUBLIC_IP, "10.0.0.7"])
    with pytest.raises(FetchRefused) as caught:
        await fetch_pdf("https://papers.example.org/paper.pdf")
    assert caught.value.code == "fetch.private_address"


@pytest.mark.parametrize(
    "url",
    [
        "https://localhost/paper.pdf",
        "https://127.0.0.1/paper.pdf",
        "https://169.254.169.254/latest/meta-data/",
        "https://[::1]:8443/paper.pdf",
        "https://2130706433/paper.pdf",
    ],
)
async def test_local_targets_are_refused_with_the_real_resolver(url: str) -> None:
    with pytest.raises(FetchRefused) as caught:
        await fetch_pdf(url)
    assert caught.value.code == "fetch.private_address"


def test_public_addresses_pass() -> None:
    for address in (PUBLIC_IP, "8.8.8.8", "2606:4700:4700::1111", "::ffff:8.8.8.8"):
        assert is_public_address(ipaddress.ip_address(address)), address


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("http://papers.example.org/paper.pdf", "fetch.scheme"),
        ("ftp://papers.example.org/paper.pdf", "fetch.scheme"),
        ("file:///etc/passwd", "fetch.scheme"),
        ("https://user:secret@papers.example.org/paper.pdf", "fetch.bad_url"),
        ("https:///paper.pdf", "fetch.bad_url"),
    ],
)
async def test_only_plain_https_urls_are_fetched(url: str, code: str) -> None:
    with pytest.raises(FetchRefused) as caught:
        await fetch_pdf(url)
    assert caught.value.code == code


async def test_the_connection_goes_to_the_vetted_address() -> None:
    resolver = Resolver({"papers.example.org": [PUBLIC_IP]})
    network = FakeNetwork({PUBLIC_IP: [http_response(200, PDF_BODY, PDF_HEADERS)]})
    async with client_for(resolver, network) as client:
        pdf = await fetch_pdf("https://papers.example.org/files/paper.pdf", client=client)
    assert pdf.data == PDF_BODY
    # One lookup, and the socket dialled the address that lookup vetted, not the name.
    assert resolver.lookups == ["papers.example.org"]
    assert network.connections == [PUBLIC_IP]
    # TLS and HTTP still speak to the hostname, so certificates and virtual hosts work.
    assert network.server_names == ["papers.example.org"]
    request = network.sent_text()
    assert request.startswith("GET /files/paper.pdf HTTP/1.1\r\n")
    assert "Host: papers.example.org\r\n" in request
    assert "User-Agent: ARP/0.1 (+mailto:lab@example.org)\r\n" in request
    assert "Accept-Encoding: identity\r\n" in request


async def test_a_redirect_to_a_private_address_is_refused() -> None:
    resolver = Resolver({"papers.example.org": [PUBLIC_IP], "internal.example.org": ["10.1.2.3"]})
    network = FakeNetwork(
        {
            PUBLIC_IP: [
                http_response(302, headers={"Location": "https://internal.example.org/x.pdf"})
            ],
            "10.1.2.3": [http_response(200, PDF_BODY, PDF_HEADERS)],
        }
    )
    async with client_for(resolver, network) as client:
        with pytest.raises(FetchRefused) as caught:
            await fetch_pdf("https://papers.example.org/paper.pdf", client=client)
    assert caught.value.code == "fetch.private_address"
    assert network.connections == [PUBLIC_IP]


async def test_a_redirect_to_plain_http_is_refused() -> None:
    resolver = Resolver({"papers.example.org": [PUBLIC_IP]})
    network = FakeNetwork(
        {PUBLIC_IP: [http_response(301, headers={"Location": "http://papers.example.org/x"})]}
    )
    async with client_for(resolver, network) as client:
        with pytest.raises(FetchRefused) as caught:
            await fetch_pdf("https://papers.example.org/paper.pdf", client=client)
    assert caught.value.code == "fetch.scheme"


def redirects(hops: int) -> list[bytes]:
    """hops relative redirects on one host."""
    return [http_response(302, headers={"Location": f"/hop/{index + 1}"}) for index in range(hops)]


async def test_five_redirects_are_followed() -> None:
    resolver = Resolver({"papers.example.org": [PUBLIC_IP], "cdn.example.net": [OTHER_PUBLIC_IP]})
    to_cdn = http_response(307, headers={"Location": "https://cdn.example.net/final.pdf"})
    network = FakeNetwork(
        {
            PUBLIC_IP: [*redirects(4), to_cdn],
            OTHER_PUBLIC_IP: [http_response(200, PDF_BODY, PDF_HEADERS)],
        }
    )
    async with client_for(resolver, network) as client:
        pdf = await fetch_pdf("https://papers.example.org/start", client=client)
    assert pdf.final_url == "https://cdn.example.net/final.pdf"
    # Redirect bodies are never read, so each hop opens a new connection and is vetted again.
    assert resolver.lookups == ["papers.example.org"] * 5 + ["cdn.example.net"]
    assert network.connections == [PUBLIC_IP] * 5 + [OTHER_PUBLIC_IP]
    assert network.server_names[-1] == "cdn.example.net"


async def test_a_sixth_redirect_is_refused() -> None:
    resolver = Resolver({"papers.example.org": [PUBLIC_IP]})
    network = FakeNetwork({PUBLIC_IP: [*redirects(6), http_response(200, PDF_BODY, PDF_HEADERS)]})
    async with client_for(resolver, network) as client:
        with pytest.raises(FetchRefused) as caught:
            await fetch_pdf("https://papers.example.org/start", client=client)
    assert caught.value.code == "fetch.too_many_redirects"


async def fetch_one(response: list[bytes], *, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
    resolver = Resolver({"papers.example.org": [PUBLIC_IP]})
    network = FakeNetwork({PUBLIC_IP: response})
    async with client_for(resolver, network) as client:
        await fetch_pdf("https://papers.example.org/paper.pdf", client=client, max_bytes=max_bytes)


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (
            [http_response(200, b"<html><body>Sign in</body></html>" * 400, PDF_HEADERS)],
            "fetch.not_pdf",
        ),
        (
            [http_response(200, PDF_BODY, {"Content-Type": "text/html; charset=utf-8"})],
            "fetch.content_type",
        ),
        ([http_response(200, PDF_BODY, {})], "fetch.content_type"),
        ([http_response(200, b"%PDF-1.4\n%%EOF\n", PDF_HEADERS)], "fetch.too_small"),
        ([http_response(200, b"%PD", PDF_HEADERS)], "fetch.not_pdf"),
        (
            [http_response(200, PDF_BODY, {**PDF_HEADERS, "Content-Encoding": "gzip"})],
            "fetch.content_encoding",
        ),
    ],
)
async def test_bodies_must_be_real_pdfs(response: list[bytes], code: str) -> None:
    with pytest.raises(FetchRefused) as caught:
        await fetch_one(response)
    assert caught.value.code == code


@pytest.mark.parametrize("content_type", ["application/octet-stream", "binary/octet-stream"])
async def test_octet_streams_are_accepted(content_type: str) -> None:
    resolver = Resolver({"papers.example.org": [PUBLIC_IP]})
    network = FakeNetwork(
        {PUBLIC_IP: [http_response(200, PDF_BODY, {"Content-Type": content_type})]}
    )
    async with client_for(resolver, network) as client:
        pdf = await fetch_pdf("https://papers.example.org/paper.pdf", client=client)
    assert pdf.content_type == content_type


async def test_a_declared_oversize_body_is_refused_before_reading() -> None:
    headers = {**PDF_HEADERS, "Content-Length": "50000000"}
    with pytest.raises(FetchRefused) as caught:
        await fetch_one([http_response(200, PDF_BODY, headers, content_length=False)])
    assert caught.value.code == "fetch.too_large"


async def test_an_undeclared_oversize_body_is_cut_off() -> None:
    head = http_response(200, b"", PDF_HEADERS, content_length=False)
    chunks = [head, b"%PDF-1.7\n", *([b"0" * 16_384] * 8)]
    with pytest.raises(FetchRefused) as caught:
        await fetch_one(chunks, max_bytes=50_000)
    assert caught.value.code == "fetch.too_large"


async def test_http_errors_are_failures_not_refusals() -> None:
    with pytest.raises(FetchFailed) as caught:
        await fetch_one([http_response(404, b"missing", {"Content-Type": "text/plain"})])
    assert caught.value.code == "fetch.http_status"
    assert caught.value.status == 404


async def test_the_total_deadline_covers_slow_servers() -> None:
    resolver = Resolver({"papers.example.org": [PUBLIC_IP]})
    network = FakeNetwork(
        {PUBLIC_IP: [http_response(200, PDF_BODY, PDF_HEADERS)]}, read_delay_seconds=1.0
    )
    async with client_for(resolver, network) as client:
        with pytest.raises(FetchFailed) as caught:
            await fetch_pdf(
                "https://papers.example.org/paper.pdf", client=client, deadline_seconds=0.05
            )
    assert caught.value.code == "fetch.deadline"


async def test_unreachable_and_unresolvable_hosts_fail() -> None:
    resolver = Resolver({"papers.example.org": [PUBLIC_IP]})
    async with client_for(resolver, FakeNetwork({})) as client:
        with pytest.raises(FetchFailed) as caught:
            await fetch_pdf("https://papers.example.org/paper.pdf", client=client)
    assert caught.value.code == "fetch.connect"

    async def no_such_host(host: str, port: int) -> list[str]:
        raise OSError("Name or service not known")

    async with SafeClient(resolver=no_such_host, network_backend=FakeNetwork({})) as client:
        with pytest.raises(FetchFailed) as caught:
            await fetch_pdf("https://nowhere.example.org/paper.pdf", client=client)
    assert caught.value.code == "fetch.dns"


async def test_the_sha256_and_final_url_describe_the_file() -> None:
    resolver = Resolver({"papers.example.org": [PUBLIC_IP]})
    network = FakeNetwork({PUBLIC_IP: [http_response(200, PDF_BODY, PDF_HEADERS)]})
    async with client_for(resolver, network) as client:
        pdf = await fetch_pdf("https://papers.example.org/paper.pdf?download=1", client=client)
    assert pdf.sha256 == hashlib.sha256(PDF_BODY).hexdigest()
    assert pdf.final_url == "https://papers.example.org/paper.pdf?download=1"
    assert "data" not in repr(pdf)


async def test_other_clients_cannot_bypass_the_guard() -> None:
    async with httpx.AsyncClient() as plain:
        with pytest.raises(TypeError, match="SafeClient"):
            await fetch_pdf("https://papers.example.org/paper.pdf", client=plain)  # type: ignore[arg-type]


async def test_the_safe_client_itself_refuses_private_addresses() -> None:
    async def internal(host: str, port: int) -> list[str]:
        return ["192.168.0.10"]

    async with SafeClient(resolver=internal) as client:
        with pytest.raises(FetchRefused):
            await client.get("https://router.example.org/")
        with pytest.raises(FetchRefused):
            await client.get("http://router.example.org/")

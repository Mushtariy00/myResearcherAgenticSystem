"""Test helpers for code built on this package; the library itself never uses them.

``FakeNetwork`` serves canned HTTP responses to ``SafeClient`` without sockets, so the whole
fetch path (resolver, address vetting, TLS hand-off, redirects, streaming) runs in tests.
``make_pdf`` builds small valid PDFs with real, extractable text.
"""

import asyncio
import ssl
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import httpcore

_REASONS = {200: "OK", 301: "Moved Permanently", 302: "Found", 404: "Not Found"}


class RecordingSleep:
    """A stand-in for asyncio.sleep that records the waits and returns at once."""

    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


def http_response(
    status: int = 200,
    body: bytes = b"",
    headers: Mapping[str, str] | None = None,
    *,
    content_length: bool = True,
) -> bytes:
    """An HTTP/1.1 response; without content_length the body ends when the connection does."""
    lines = [f"HTTP/1.1 {status} {_REASONS.get(status, 'Status')}"]
    lines += [f"{name}: {value}" for name, value in (headers or {}).items()]
    if content_length:
        lines.append(f"Content-Length: {len(body)}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body


class FakeNetwork(httpcore.AsyncNetworkBackend):
    """Pretends to be the internet: each IP address answers with its queue of byte chunks.

    Successive reads on any connection to an address take the next chunk; an empty queue reads
    as a closed connection. Records the addresses dialled, the TLS server names and the bytes
    sent. Connecting to an address without a queue fails like a refused connection.
    """

    def __init__(
        self, responses: Mapping[str, Sequence[bytes]], *, read_delay_seconds: float = 0.0
    ) -> None:
        self._queues = {address: list(chunks) for address, chunks in responses.items()}
        self._read_delay = read_delay_seconds
        self.connections: list[str] = []
        self.server_names: list[str | None] = []
        self.sent: list[bytes] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore's interface
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        self.connections.append(host)
        if host not in self._queues:
            raise httpcore.ConnectError(f"nothing listens on {host}:{port}")
        return _FakeStream(self, host)

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore's interface
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise httpcore.ConnectError("no unix sockets here")

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    def sent_text(self) -> str:
        return b"".join(self.sent).decode("latin-1")

    async def _read(self, address: str) -> bytes:
        if self._read_delay:
            await asyncio.sleep(self._read_delay)
        queue = self._queues[address]
        return queue.pop(0) if queue else b""


class _FakeStream(httpcore.AsyncNetworkStream):
    def __init__(self, network: FakeNetwork, address: str) -> None:
        self._network = network
        self._address = address

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:  # noqa: ASYNC109
        return await self._network._read(self._address)

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:  # noqa: ASYNC109
        self._network.sent.append(buffer)

    async def aclose(self) -> None:
        return None

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> httpcore.AsyncNetworkStream:
        self._network.server_names.append(server_hostname)
        return self

    def get_extra_info(self, info: str) -> Any:
        # No ssl_object means no ALPN, so httpcore speaks HTTP/1.1.
        return None


def make_pdf(pages: Sequence[str | Sequence[str]]) -> bytes:
    """A PDF 1.4 file with one page per item, each a list of lines (or a string split on
    newlines) set in Helvetica, so PDFium extracts the text back. Text must fit Windows-1252
    (the font's WinAnsiEncoding), which includes curly quotes and dashes."""
    page_lines = [page.split("\n") if isinstance(page, str) else list(page) for page in pages]
    count = len(page_lines)
    kids = " ".join(f"{3 + 2 * index} 0 R" for index in range(count))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {count} >>".encode(),
    ]
    font_number = 3 + 2 * count
    for index, lines in enumerate(page_lines):
        operations = ["BT", "/F1 11 Tf", "14 TL", "72 740 Td"]
        operations += [f"({_pdf_string(line)}) Tj T*" for line in lines]
        operations.append("ET")
        stream = "\n".join(operations).encode("cp1252")
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_number} 0 R >> >> "
                f"/Contents {4 + 2 * index} 0 R >>"
            ).encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
    objects.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )
    output = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(output)
    output += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    output += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    output += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(output)


def _pdf_string(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

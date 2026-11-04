"""The client against a real socket, where httpx's own timeouts apply."""

import asyncio
import contextlib
import time

import httpx
import pytest

from agentic_gateway.openrouter import OpenRouterClient, UpstreamTimeoutError


async def _keep_alive_forever(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """As OpenRouter holds a non-streaming request while the model writes: headers at once, then
    whitespace, which keeps resetting a read timeout. The answer never comes."""
    await reader.readuntil(b"\r\n\r\n")
    writer.write(
        b"HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ntransfer-encoding: chunked\r\n\r\n"
    )
    with contextlib.suppress(ConnectionError):
        while True:
            writer.write(b"1\r\n\n\r\n")
            await writer.drain()
            await asyncio.sleep(0.05)
    writer.close()


async def test_keep_alive_whitespace_does_not_outlast_the_time_limit() -> None:
    server = await asyncio.start_server(_keep_alive_forever, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server, httpx.AsyncClient() as http:
        client = OpenRouterClient(http, f"http://127.0.0.1:{port}", "key", "http://localhost")
        started = time.monotonic()
        with pytest.raises(UpstreamTimeoutError):
            await client.chat(
                model="stuck/model",
                messages=[{"role": "user", "content": "hello"}],
                max_tokens=16,
                json_mode=False,
                deny_data_collection=False,
                request_timeout=0.4,
            )
        assert 0.3 < time.monotonic() - started < 5

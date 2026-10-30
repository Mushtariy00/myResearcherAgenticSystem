"""Browser-hardening headers on every API response (docs/PLAN.md).

API responses are JSON and files, never pages, so their policy allows nothing. The interactive
docs (development only: production serves none) load Swagger UI from its CDN and start it with
an inline script, so only their pages get a policy that allows exactly that.
"""

from collections.abc import Iterable

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

API_POLICY = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
DOCS_POLICY = (
    "default-src 'none'; "
    "script-src 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)


class SecurityHeaders:
    """Plain ASGI, so streamed responses (SSE, downloads) pass through untouched."""

    def __init__(self, app: ASGIApp, docs_paths: Iterable[str] = ()) -> None:
        self.app = app
        self.docs_paths = frozenset(docs_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        policy = DOCS_POLICY if scope["path"] in self.docs_paths else API_POLICY

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Content-Security-Policy"] = policy
            await send(message)

        await self.app(scope, receive, send_with_headers)

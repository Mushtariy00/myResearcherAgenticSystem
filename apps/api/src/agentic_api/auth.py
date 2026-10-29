"""Who is calling: Better Auth session cookies, checked against the Next.js app (ADR 0003)."""

import hashlib
import time
from dataclasses import dataclass

import httpx
from fastapi import HTTPException, Request, status


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    name: str
    role: str  # Better Auth admin plugin role: "admin" or "user"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class SessionVerifier:
    """Asks Better Auth's `get-session` endpoint who owns a cookie; caches answers briefly.

    Caching for at most `ttl_seconds` bounds how long a revoked session keeps working.
    """

    def __init__(self, auth_url: str, ttl_seconds: int, client: httpx.AsyncClient) -> None:
        self._url = f"{auth_url.rstrip('/')}/api/auth/get-session"
        self._ttl = ttl_seconds
        self._client = client
        self._cache: dict[str, tuple[float, CurrentUser | None]] = {}

    async def verify(self, cookie_header: str) -> CurrentUser | None:
        key = hashlib.sha256(cookie_header.encode()).hexdigest()
        cached = self._cache.get(key)
        now = time.monotonic()
        if cached and cached[0] > now:
            return cached[1]

        try:
            response = await self._client.get(self._url, headers={"cookie": cookie_header})
        except httpx.HTTPError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "auth.unavailable") from exc
        body = response.json() if response.status_code == 200 else None
        user = None
        if isinstance(body, dict) and isinstance(body.get("user"), dict):
            raw = body["user"]
            user = CurrentUser(
                id=str(raw["id"]),
                email=str(raw.get("email", "")),
                name=str(raw.get("name", "")),
                role=str(raw.get("role") or "user"),
            )
        if len(self._cache) > 10_000:
            self._cache.clear()
        self._cache[key] = (now + self._ttl, user)
        return user


async def current_user(request: Request) -> CurrentUser:
    cookie_header = request.headers.get("cookie", "")
    if not cookie_header:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "auth.required")
    verifier: SessionVerifier = request.app.state.session_verifier
    user = await verifier.verify(cookie_header)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "auth.required")
    return user

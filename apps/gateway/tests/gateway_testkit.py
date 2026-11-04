"""A fake OpenRouter (catalog + chat) and an in-memory counter for the free quota."""

import asyncio
import json
import time
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import httpx

BASE_URL = "https://openrouter.test/api/v1"
PAID, PAID_BACKUP, FREE_A, FREE_B = "paid/good", "paid/backup", "free/a:free", "free/b:free"
PRICES = {"prompt": "0.000001", "completion": "0.000002"}
CATALOG = {
    "data": [
        {"id": PAID, "pricing": PRICES, "context_length": 128_000},
        {"id": PAID_BACKUP, "pricing": PRICES, "context_length": 64_000},
        {"id": FREE_A, "pricing": {"prompt": "0", "completion": "0"}, "context_length": 32_000},
        {"id": FREE_B, "pricing": {"prompt": "0", "completion": "0"}, "context_length": 32_000},
    ]
}
KEY_LIMIT = (
    402,
    {
        "error": {
            "code": 402,
            "message": "limit",
            "metadata": {"limit_source": "openrouter_key_limit"},
        }
    },
)
NO_CREDITS = (402, {"error": {"code": 402, "message": "Insufficient credits"}})
OVERLOADED = (503, {"error": {"code": 503, "message": "overloaded"}})
# Real responses seen on 2026-10-30 (messages shortened).
FORBIDDEN = (403, {"error": {"code": 403, "message": "only available on agentic harnesses"}})
UNAUTHORIZED = (401, {"error": {"code": 401, "message": "No auth credentials found"}})

# A zero-priced model that outputs audio (like google/lyria-*): must never be chosen.
AUDIO = "music/lyria-like"
CATALOG["data"].append(
    {
        "id": AUDIO,
        "pricing": {"prompt": "0", "completion": "0"},
        "context_length": 2_000_000,
        "architecture": {"input_modalities": ["text"], "output_modalities": ["text", "audio"]},
    }
)

# OpenRouter's auto-router: negative prices, not a model anyone can price or pick.
AUTO_ROUTER = "openrouter/auto"
CATALOG["data"].append(
    {
        "id": AUTO_ROUTER,
        "pricing": {"prompt": "-1", "completion": "-1"},
        "context_length": 2_000_000,
    }
)

# What a model does next: (status, JSON body), a whole response, or an error to raise.
Planned = tuple[int, dict[str, Any]] | httpx.Response | Exception


def hanging() -> httpx.Response:
    """A model that never answers: OpenRouter keeps the request alive with whitespace meanwhile,
    which resets a read timeout (seen live: answers took up to 454 s past a 120 s read timeout)."""

    async def whitespace() -> AsyncIterator[bytes]:
        while True:
            yield b"\n"
            await asyncio.sleep(0.01)

    return httpx.Response(200, content=whitespace())


def daily_limit(reset_in_seconds: float) -> tuple[int, dict[str, Any]]:
    """OpenRouter's 429 when the account's free requests for the UTC day are used up."""
    reset_ms = int((time.time() + reset_in_seconds) * 1000)
    headers = {
        "X-RateLimit-Limit": "50",
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": str(reset_ms),
    }
    return (
        429,
        {
            "error": {
                "code": 429,
                "message": "Rate limit exceeded: free-models-per-day",
                "metadata": {"headers": headers, "limit_source": "openrouter_free_tier_daily"},
            }
        },
    )


def budget_limit(status: int, limit_source: str) -> tuple[int, dict[str, Any]]:
    """A spending limit as OpenRouter's errors reference documents it."""
    return (
        status,
        {
            "error": {
                "code": status,
                "message": "budget",
                "metadata": {"limit_source": limit_source},
            }
        },
    )


class FakeOpenRouter:
    """Answers OK by default; `plan[model]` queues what that model does next."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.bodies: list[dict[str, Any]] = []
        self.timeouts: list[float] = []  # each chat request's read timeout
        self.plan: dict[str, list[Planned]] = defaultdict(list)
        self.delays: dict[str, float] = {}  # seconds a model takes to answer
        self.hold: asyncio.Event | None = None  # chat requests wait for it while it is unset
        self.sent = asyncio.Event()  # a chat request has arrived
        self.costs: dict[str, float] = {}  # what /generation reports, by generation id
        self.lookups: list[str] = []
        self.during_lookup: Callable[[], Awaitable[None]] | None = None
        # What the account endpoints answer, and the keys they were asked with.
        self.credits: tuple[int, dict[str, Any]] = (
            200,
            {"data": {"total_credits": 25, "total_usage": 7.5}},
        )
        self.key: tuple[int, dict[str, Any]] = (
            200,
            {
                "data": {
                    "is_free_tier": False,
                    "free_model_daily_requests": {"used": 3, "limit": 1000, "remaining": 997},
                }
            },
        )
        self.account_keys: list[str] = []

    async def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=CATALOG)
        if request.url.path.endswith(("/credits", "/key")):
            self.account_keys.append(request.headers["authorization"])
            status, body = self.credits if request.url.path.endswith("/credits") else self.key
            return httpx.Response(status, json=body)
        if request.url.path.endswith("/generation"):
            return await self._generation(request.url.params["id"])
        body = json.loads(request.content)
        model = body["model"]
        self.calls.append(model)
        self.bodies.append(body)
        self.timeouts.append(request.extensions["timeout"]["read"])
        self.sent.set()
        if self.hold is not None:
            await self.hold.wait()
        await asyncio.sleep(self.delays.get(model, 0))
        if self.plan[model]:
            planned = self.plan[model].pop(0)
            if isinstance(planned, Exception):
                raise planned
            if isinstance(planned, httpx.Response):
                return planned
            status, error = planned
            return httpx.Response(status, json=error)
        cost = 0.0021 if not model.endswith(":free") else 0
        return httpx.Response(
            200,
            json={
                "id": f"gen-{uuid.uuid4()}",
                "model": model,
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 40, "cost": cost},
            },
        )

    async def _generation(self, generation_id: str) -> httpx.Response:
        self.lookups.append(generation_id)
        if self.during_lookup is not None:
            await self.during_lookup()
        if generation_id not in self.costs:
            return httpx.Response(404, json={"error": {"code": 404, "message": "not found"}})
        cost = self.costs[generation_id]
        return httpx.Response(200, json={"data": {"id": generation_id, "total_cost": cost}})


class FakeCounter:
    def __init__(self) -> None:
        self.values: dict[str, int] = defaultdict(int)

    async def incr(self, name: str) -> int:
        self.values[name] += 1
        return self.values[name]

    async def decr(self, name: str) -> int:
        self.values[name] -= 1
        return self.values[name]

    async def expire(self, name: str, time: int) -> bool:
        return True

"""A fake OpenRouter (catalog + chat) and an in-memory counter for the free quota."""

import json
import time
import uuid
from collections import defaultdict
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
        "architecture": {"input_modalities": ["text"], "output_modalities": ["audio"]},
    }
)


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


class FakeOpenRouter:
    """Answers OK by default; `plan[model]` queues (status, body) failures for that model."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.bodies: list[dict[str, Any]] = []
        self.plan: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=CATALOG)
        body = json.loads(request.content)
        model = body["model"]
        self.calls.append(model)
        self.bodies.append(body)
        if self.plan[model]:
            status, error = self.plan[model].pop(0)
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

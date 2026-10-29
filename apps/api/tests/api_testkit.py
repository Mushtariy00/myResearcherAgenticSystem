"""Test doubles for the API: auth from a cookie, a recording orchestrator, a quiet Valkey."""

import asyncio
import uuid
from dataclasses import dataclass, field
from http.cookies import SimpleCookie

from agentic_api.auth import CurrentUser
from agentic_api.orchestrator import DecisionRejectedError
from agentic_core.contracts import DecisionInput

ORIGIN = "http://localhost:8080"


def as_user(user_id: str, role: str = "user") -> dict[str, str]:
    return {"cookie": f"test-user={user_id}:{role}"}


class FakeVerifier:
    """Reads `test-user=<id>:<role>` cookies instead of asking Better Auth."""

    async def verify(self, cookie_header: str) -> CurrentUser | None:
        cookie = SimpleCookie(cookie_header).get("test-user")
        if cookie is None:
            return None
        user_id, role = cookie.value.split(":")
        return CurrentUser(id=user_id, email=f"{user_id}@lab.test", name=user_id, role=role)


@dataclass
class FakeOrchestrator:
    started: list[uuid.UUID] = field(default_factory=list)
    decisions: list[tuple[uuid.UUID, DecisionInput]] = field(default_factory=list)
    cancelled: list[uuid.UUID] = field(default_factory=list)
    fail_start: bool = False
    reject_decisions: bool = False

    async def start_run(self, run_id: uuid.UUID) -> str:
        if self.fail_start:
            raise RuntimeError("temporal down")
        self.started.append(run_id)
        return f"run-{run_id}"

    async def decide(self, run_id: uuid.UUID, decision: DecisionInput) -> None:
        if self.reject_decisions:
            raise DecisionRejectedError("stale")
        self.decisions.append((run_id, decision))

    async def cancel_run(self, run_id: uuid.UUID) -> None:
        self.cancelled.append(run_id)


class _QuietPubSub:
    async def subscribe(self, *channels: str) -> None:
        return None

    async def get_message(self, ignore_subscribe_messages: bool, timeout: float) -> None:  # noqa: ASYNC109 (mirrors redis)
        await asyncio.sleep(0.01)

    async def aclose(self) -> None:
        return None


class FakeValkey:
    def pubsub(self) -> _QuietPubSub:
        return _QuietPubSub()

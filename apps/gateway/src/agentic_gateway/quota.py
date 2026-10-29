"""Free-tier quota: one account-wide bucket (per minute and per UTC day) plus a per-user share."""

from datetime import UTC, datetime
from typing import Any, Protocol


class QuotaExhaustedError(Exception):
    def __init__(self, retry_after: float, scope: str) -> None:
        super().__init__(f"free quota exhausted ({scope}); retry after {retry_after:.0f}s")
        self.retry_after = retry_after
        self.scope = scope


class Counter(Protocol):
    """The subset of the redis/valkey client used here (a test fake implements it too)."""

    async def incr(self, name: str) -> int: ...

    async def decr(self, name: str) -> int: ...

    async def expire(self, name: str, time: int) -> Any: ...


class FreeQuota:
    def __init__(
        self, counter: Counter, per_minute: int, per_day: int, per_user_per_day: int
    ) -> None:
        self._counter = counter
        self._limits = (per_minute, per_day, per_user_per_day)

    async def acquire(self, user_id: str, now: datetime | None = None) -> None:
        """Take one free request or raise QuotaExhaustedError with how long to wait."""
        now = (now or datetime.now(UTC)).astimezone(UTC)
        per_minute, per_day, per_user = self._limits
        seconds_to_minute = 60 - now.second
        seconds_to_day = int(
            (now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() + 86400)
            - now.timestamp()
        )
        buckets = [
            (f"free:min:{now:%Y%m%d%H%M}", per_minute, 120, seconds_to_minute, "minute"),
            (f"free:day:{now:%Y%m%d}", per_day, 172800, seconds_to_day, "day"),
            (f"free:user:{user_id}:{now:%Y%m%d}", per_user, 172800, seconds_to_day, "user"),
        ]
        taken: list[str] = []
        for key, limit, ttl, retry_after, scope in buckets:
            count = await self._counter.incr(key)
            if count == 1:
                await self._counter.expire(key, ttl)
            taken.append(key)
            if count > limit:
                for done in taken:  # give back what this request took
                    await self._counter.decr(done)
                raise QuotaExhaustedError(float(retry_after), scope)

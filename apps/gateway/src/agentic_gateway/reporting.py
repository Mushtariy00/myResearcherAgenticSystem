"""What the gateway reads from OpenRouter for the rest of the platform: the model catalog and the
account, written to the settings table. The API shows them; only the gateway holds the key."""

import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_db.lab_settings import LAB_ACCOUNT_KEY, MODEL_CATALOG_KEY
from agentic_db.models import Setting
from agentic_gateway.catalog import Catalog, CatalogUnavailableError, ModelInfo

log = logging.getLogger(__name__)

WRITER = "gateway"
ACCOUNT_TIMEOUT_SECONDS = 15
_MILLION = Decimal(1_000_000)


def _per_million(per_token: Decimal) -> str:
    return format((per_token * _MILLION).normalize(), "f")


async def _store(
    sessions: async_sessionmaker[AsyncSession], key: str, value: dict[str, Any]
) -> None:
    async with sessions() as session, session.begin():
        await session.merge(Setting(key=key, value=value, updated_by=WRITER))


async def store_catalog(
    sessions: async_sessionmaker[AsyncSession], models: dict[str, ModelInfo]
) -> None:
    """The text models with their prices. OpenRouter's auto-router has negative prices: not a model
    anyone can price or pick."""
    await _store(
        sessions,
        MODEL_CATALOG_KEY,
        {
            "checked_at": datetime.now(UTC).isoformat(),
            "models": [
                {
                    "id": info.id,
                    "free": info.is_free,
                    "context_length": info.context_length,
                    "prompt_usd_per_mtok": _per_million(info.prompt_usd_per_token),
                    "completion_usd_per_mtok": _per_million(info.completion_usd_per_token),
                }
                for info in sorted(models.values(), key=lambda item: item.id)
                if info.text_io
                and info.prompt_usd_per_token >= 0
                and info.completion_usd_per_token >= 0
            ],
        },
    )


async def _data(http: httpx.AsyncClient, url: str, api_key: str) -> dict[str, Any] | None:
    """The ``data`` object of an OpenRouter account endpoint; None when it won't say."""
    try:
        response = await http.get(
            url, headers={"Authorization": f"Bearer {api_key}"}, timeout=ACCOUNT_TIMEOUT_SECONDS
        )
    except httpx.HTTPError as exc:
        log.warning("%s unreachable: %s", url, type(exc).__name__)
        return None
    if response.status_code != 200:
        log.warning("%s answered HTTP %s", url, response.status_code)
        return None
    try:
        data = response.json().get("data")
    except (ValueError, AttributeError):
        return None
    return data if isinstance(data, dict) else None


def _balance(credits: dict[str, Any] | None, key: dict[str, Any] | None) -> Decimal | None:
    """Credits bought minus credits used. OpenRouter documents /credits for management keys only;
    where it refuses, what this key may still spend is the closest figure."""
    try:
        if credits is not None:
            return Decimal(str(credits["total_credits"])) - Decimal(str(credits["total_usage"]))
        left = key.get("limit_remaining") if key is not None else None
        return Decimal(str(left)) if left is not None else None
    except (KeyError, InvalidOperation):
        return None


async def report_account(
    sessions: async_sessionmaker[AsyncSession],
    http: httpx.AsyncClient,
    base_url: str,
    api_key: str,
) -> None:
    """Store the account as OpenRouter describes it now. When it answers nothing, the last report
    stays, with its older ``checked_at``."""
    base = base_url.rstrip("/")
    credits = await _data(http, f"{base}/credits", api_key)
    key = await _data(http, f"{base}/key", api_key)
    if credits is None and key is None:
        return
    balance = _balance(credits, key)
    free_requests = (key or {}).get("free_model_daily_requests")
    limit = free_requests.get("limit") if isinstance(free_requests, dict) else None
    await _store(
        sessions,
        LAB_ACCOUNT_KEY,
        {
            "checked_at": datetime.now(UTC).isoformat(),
            "balance_usd": format(balance, "f") if balance is not None else None,
            "free_tier": bool((key or {}).get("is_free_tier", False)),
            "free_daily_limit": limit if isinstance(limit, int) else None,
        },
    )


class Reporter:
    """One round of reports: the catalog when a new one was read, and the account."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        catalog: Catalog,
        http: httpx.AsyncClient,
        base_url: str,
        api_key: str,
    ) -> None:
        self._sessions = sessions
        self._catalog = catalog
        self._http = http
        self._base_url = base_url
        self._api_key = api_key
        self._stored_refreshes = 0

    async def report(self) -> None:
        try:
            models = await self._catalog.models()
        except CatalogUnavailableError:
            pass  # the catalog logged why; the account can still be read
        else:
            if self._catalog.refreshes != self._stored_refreshes:
                await store_catalog(self._sessions, models)
                self._stored_refreshes = self._catalog.refreshes
        if self._api_key:
            await report_account(self._sessions, self._http, self._base_url, self._api_key)

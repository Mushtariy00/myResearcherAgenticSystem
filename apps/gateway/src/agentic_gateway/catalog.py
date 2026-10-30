"""OpenRouter model catalog: prices and context lengths, refreshed hourly. No probing calls."""

import asyncio
import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

log = logging.getLogger(__name__)

REFRESH_SECONDS = 3600
FETCH_TIMEOUT_SECONDS = 30
# After a failed refresh the cached catalog keeps serving, and the next fetch waits this long
# instead of slowing every call down. Without a catalog no call can be routed, so retry sooner.
RETRY_SECONDS = 300
RETRY_SECONDS_WITHOUT_CATALOG = 15


class CatalogUnavailableError(Exception):
    """There is no catalog yet and OpenRouter's /models can't be read."""


@dataclass(frozen=True)
class ModelInfo:
    id: str
    prompt_usd_per_token: Decimal
    completion_usd_per_token: Decimal
    context_length: int
    # Reads and writes text. Zero-priced music/image models exist and must never be picked.
    text_io: bool = True

    @property
    def is_free(self) -> bool:
        return self.id.endswith(":free") or (
            self.prompt_usd_per_token == 0 and self.completion_usd_per_token == 0
        )

    def estimate_usd(self, prompt_tokens: int, max_completion_tokens: int) -> Decimal:
        return (
            self.prompt_usd_per_token * prompt_tokens
            + self.completion_usd_per_token * max_completion_tokens
        )


def parse_models(payload: Any) -> dict[str, ModelInfo]:
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError("not a model catalog")
    models: dict[str, ModelInfo] = {}
    for item in items:
        try:
            pricing = item.get("pricing") or {}
            architecture = item.get("architecture") or {}
            inputs = architecture.get("input_modalities")
            outputs = architecture.get("output_modalities")
            if inputs is None or outputs is None:  # older catalog shape: "text+image->text"
                modality = str(architecture.get("modality") or "text->text")
                source, _, target = modality.partition("->")
                inputs, outputs = source.split("+"), (target or "text").split("+")
            models[item["id"]] = ModelInfo(
                id=item["id"],
                prompt_usd_per_token=Decimal(str(pricing.get("prompt", "0"))),
                completion_usd_per_token=Decimal(str(pricing.get("completion", "0"))),
                context_length=int(item.get("context_length") or 0),
                text_io="text" in inputs and "text" in outputs,
            )
        except (KeyError, ArithmeticError, ValueError, TypeError, AttributeError):
            continue  # one malformed entry must not hide the others
    return models


class Catalog:
    def __init__(self, client: httpx.AsyncClient, base_url: str) -> None:
        self._client = client
        self._url = f"{base_url.rstrip('/')}/models"
        self._models: dict[str, ModelInfo] = {}
        self._next_refresh = 0.0  # time.monotonic() after which the next lookup fetches
        self._lock = asyncio.Lock()  # concurrent lookups share one fetch

    async def models(self) -> dict[str, ModelInfo]:
        if time.monotonic() >= self._next_refresh:
            async with self._lock:
                if time.monotonic() >= self._next_refresh:  # not refreshed while we waited
                    await self._refresh()
        if not self._models:
            raise CatalogUnavailableError(self._url)
        return self._models

    async def get(self, model_id: str) -> ModelInfo | None:
        return (await self.models()).get(model_id)

    async def _refresh(self) -> None:
        try:
            response = await self._client.get(self._url, timeout=FETCH_TIMEOUT_SECONDS)
            response.raise_for_status()
            models = parse_models(response.json())
            if not models:
                raise ValueError("the catalog lists no models")
        except (httpx.HTTPError, ValueError) as exc:
            wait = RETRY_SECONDS if self._models else RETRY_SECONDS_WITHOUT_CATALOG
            self._next_refresh = time.monotonic() + wait
            log.warning("model catalog refresh failed (%r); next try in %ss", exc, wait)
            return
        self._models = models
        self._next_refresh = time.monotonic() + REFRESH_SECONDS

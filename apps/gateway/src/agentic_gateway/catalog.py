"""OpenRouter model catalog: prices and context lengths, refreshed hourly. No probing calls."""

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

REFRESH_SECONDS = 3600


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


def parse_models(payload: dict[str, Any]) -> dict[str, ModelInfo]:
    models: dict[str, ModelInfo] = {}
    for item in payload.get("data", []):
        pricing = item.get("pricing") or {}
        architecture = item.get("architecture") or {}
        inputs = architecture.get("input_modalities")
        outputs = architecture.get("output_modalities")
        if inputs is None or outputs is None:  # older catalog shape: "text+image->text"
            source, _, target = str(architecture.get("modality") or "text->text").partition("->")
            inputs, outputs = source.split("+"), (target or "text").split("+")
        try:
            models[item["id"]] = ModelInfo(
                id=item["id"],
                prompt_usd_per_token=Decimal(str(pricing.get("prompt", "0"))),
                completion_usd_per_token=Decimal(str(pricing.get("completion", "0"))),
                context_length=int(item.get("context_length") or 0),
                text_io="text" in inputs and "text" in outputs,
            )
        except (KeyError, ArithmeticError, ValueError):
            continue
    return models


class Catalog:
    def __init__(self, client: httpx.AsyncClient, base_url: str) -> None:
        self._client = client
        self._url = f"{base_url.rstrip('/')}/models"
        self._models: dict[str, ModelInfo] = {}
        self._loaded_at = 0.0

    async def models(self) -> dict[str, ModelInfo]:
        if not self._models or time.monotonic() - self._loaded_at > REFRESH_SECONDS:
            try:
                response = await self._client.get(self._url, timeout=30)
                response.raise_for_status()
                self._models = parse_models(response.json())
                self._loaded_at = time.monotonic()
            except httpx.HTTPError:
                if not self._models:
                    raise
        return self._models

    async def get(self, model_id: str) -> ModelInfo | None:
        return (await self.models()).get(model_id)

"""Lab-wide settings stored in the ``settings`` table."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agentic_db.models import Setting

# The paid-models kill switch, as the admin settings endpoint writes it and the gateway reads it.
PAID_MODELS_KEY = "paid_models_enabled"
# The executor's heartbeat, written every few seconds while it runs: {"alive_at", "gpu", "job_id",
# "waiting_for_vram"}. gpu: the latest nvidia-smi sample, or null. job_id: the job on the GPU, or
# null. waiting_for_vram: {"free_mb", "needed_mb"} while a queued job waits for GPU memory.
EXECUTOR_STATUS_KEY = "executor.status"
# Each agent role's own model chains, as the admin endpoint writes them and the gateway reads them:
# {"roles": {role: {"paid": [...] | null, "free": [...] | null}}}.
MODEL_ROUTING_KEY = "model_routing"
# What the gateway last read from OpenRouter, for the API to show (only the gateway holds the key).
# The catalog: {"checked_at", "models": [{"id", "free", "context_length", "prompt_usd_per_mtok",
# "completion_usd_per_mtok"}]}. The account: {"checked_at", "balance_usd", "free_tier",
# "free_daily_limit"}.
MODEL_CATALOG_KEY = "openrouter.catalog"
LAB_ACCOUNT_KEY = "openrouter.account"


async def paid_models_enabled(session: AsyncSession) -> bool:
    """False once an admin turned paid models off; on until anyone has set it."""
    setting = await session.get(Setting, PAID_MODELS_KEY)
    return bool(setting.value.get("enabled", True)) if setting else True


@dataclass(frozen=True)
class RoleChains:
    """One role's own chains. None: the lab's chain. An empty paid chain keeps it on free models."""

    paid: list[str] | None = None
    free: list[str] | None = None


def _chain(value: Any) -> list[str] | None:
    return [model for model in value if isinstance(model, str)] if isinstance(value, list) else None


async def model_routing(session: AsyncSession) -> dict[str, RoleChains]:
    """The roles an admin gave their own chains, by agent role."""
    setting = await session.get(Setting, MODEL_ROUTING_KEY)
    roles = setting.value.get("roles") if setting else None
    if not isinstance(roles, dict):
        return {}
    return {
        role: RoleChains(paid=_chain(chains.get("paid")), free=_chain(chains.get("free")))
        for role, chains in roles.items()
        if isinstance(chains, dict)
    }


@dataclass(frozen=True)
class CatalogModel:
    id: str
    free: bool
    context_length: int
    prompt_usd_per_mtok: Decimal  # USD per million prompt tokens
    completion_usd_per_mtok: Decimal


@dataclass(frozen=True)
class ModelCatalog:
    checked_at: datetime
    models: dict[str, CatalogModel]


async def model_catalog(session: AsyncSession) -> ModelCatalog | None:
    """OpenRouter's text models as the gateway last read them; None before it has."""
    setting = await session.get(Setting, MODEL_CATALOG_KEY)
    if setting is None:
        return None
    try:
        models = [
            CatalogModel(
                id=entry["id"],
                free=bool(entry["free"]),
                context_length=int(entry["context_length"]),
                prompt_usd_per_mtok=Decimal(entry["prompt_usd_per_mtok"]),
                completion_usd_per_mtok=Decimal(entry["completion_usd_per_mtok"]),
            )
            for entry in setting.value["models"]
        ]
        return ModelCatalog(
            checked_at=datetime.fromisoformat(setting.value["checked_at"]),
            models={model.id: model for model in models},
        )
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return None


@dataclass(frozen=True)
class LabAccount:
    checked_at: datetime
    balance_usd: Decimal | None  # None: OpenRouter would not say
    free_tier: bool  # the account has never bought credits: only free models work
    free_daily_limit: int | None


async def lab_account(session: AsyncSession) -> LabAccount | None:
    """The OpenRouter account as the gateway last read it; None before it has."""
    setting = await session.get(Setting, LAB_ACCOUNT_KEY)
    if setting is None:
        return None
    try:
        balance = setting.value["balance_usd"]
        limit = setting.value["free_daily_limit"]
        return LabAccount(
            checked_at=datetime.fromisoformat(setting.value["checked_at"]),
            balance_usd=Decimal(balance) if balance is not None else None,
            free_tier=bool(setting.value["free_tier"]),
            free_daily_limit=int(limit) if limit is not None else None,
        )
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return None

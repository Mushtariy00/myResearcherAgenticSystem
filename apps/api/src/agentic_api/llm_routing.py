"""The model chains the gateway follows, with what its catalog says about each model.

A role's chains are its own where an admin set them (agentic_db.lab_settings.model_routing), else
the lab's: ARP_PAID_MODELS and ARP_FREE_MODELS, read here from the same variables as the gateway,
or the built-in ones.
"""

from collections.abc import Mapping

from agentic_api.schemas import AgentRole, RoleRoutingOut, RoutedModelOut
from agentic_api.settings import Settings
from agentic_core.routing import (
    DEFAULT_FREE_MODELS,
    DEFAULT_PAID_MODELS,
    MAX_OUTPUT_TOKENS,
    ROUTING_ROLES,
)
from agentic_db.lab_settings import CatalogModel, RoleChains


def model_chain(configured: str, default: tuple[str, ...]) -> list[str]:
    """A comma-separated chain as the gateway reads it (``_split`` there); empty: the default."""
    items = [item.strip() for item in configured.split(",") if item.strip()]
    return items or list(default)


def lab_paid_chain(settings: Settings) -> list[str]:
    return model_chain(settings.paid_models, DEFAULT_PAID_MODELS)


def lab_free_chain(settings: Settings) -> list[str]:
    return model_chain(settings.free_models, DEFAULT_FREE_MODELS)


def paid_chains(
    settings: Settings, routing: Mapping[str, RoleChains]
) -> dict[AgentRole, list[str]]:
    """Every role's paid chain. Empty: the role stays on free models."""
    lab = lab_paid_chain(settings)
    chains: dict[AgentRole, list[str]] = {}
    for role in ROUTING_ROLES:
        own = routing.get(role, RoleChains()).paid
        chains[role] = lab if own is None else own
    return chains


def routed_model(model_id: str, models: Mapping[str, CatalogModel]) -> RoutedModelOut:
    model = models.get(model_id)
    if model is None:
        return RoutedModelOut(
            id=model_id,
            free=model_id.endswith(":free"),
            in_catalog=False,
            context_length=None,
            prompt_usd_per_mtok=None,
            completion_usd_per_mtok=None,
        )
    return RoutedModelOut(
        id=model.id,
        free=model.free,
        in_catalog=True,
        context_length=model.context_length,
        prompt_usd_per_mtok=model.prompt_usd_per_mtok,
        completion_usd_per_mtok=model.completion_usd_per_mtok,
    )


def role_routing(
    settings: Settings, routing: Mapping[str, RoleChains], models: Mapping[str, CatalogModel]
) -> list[RoleRoutingOut]:
    """Every role's chains, in the order the gateway tries them."""
    lab_paid = lab_paid_chain(settings)
    lab_free = lab_free_chain(settings)
    roles = []
    for role in ROUTING_ROLES:
        own = routing.get(role, RoleChains())
        roles.append(
            RoleRoutingOut(
                role=role,
                max_output_tokens=MAX_OUTPUT_TOKENS[role],
                paid=[
                    routed_model(model_id, models)
                    for model_id in (lab_paid if own.paid is None else own.paid)
                ],
                free=[
                    routed_model(model_id, models)
                    for model_id in (lab_free if own.free is None else own.free)
                ],
                paid_is_lab_default=own.paid is None,
                free_is_lab_default=own.free is None,
            )
        )
    return roles

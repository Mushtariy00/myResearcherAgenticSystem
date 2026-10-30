"""The model catalog and the routing per agent role, as the gateway is configured.

The default chains mirror agentic_gateway.service.DEFAULT_PAID_MODELS and DEFAULT_FREE_MODELS
(the API never imports gateway code; a test keeps the two in step), and ARP_PAID_MODELS /
ARP_FREE_MODELS override them for both services. Context lengths and prices are demo values in
the shape of OpenRouter's /models catalog, until the gateway stores its catalog in the database.
"""

from dataclasses import dataclass
from decimal import Decimal

from agentic_api.schemas import AgentRole, RoleRoutingOut, RoutedModelOut

DEFAULT_PAID_MODELS = ("google/gemini-2.5-flash", "openai/gpt-4.1-mini")
DEFAULT_FREE_MODELS = ("nvidia/nemotron-3-ultra-550b-a55b:free", "google/gemma-4-31b-it:free")
AGENT_ROLES: tuple[AgentRole, ...] = (
    "researcher",
    "screener",
    "analyst",
    "methodologist",
    "coder",
    "writer",
)
# The most a call by each role may write; the gateway reserves budget for all of it.
MAX_OUTPUT_TOKENS: dict[AgentRole, int] = {
    "researcher": 1500,
    "screener": 800,
    "analyst": 1200,
    "methodologist": 2000,
    "coder": 4096,
    "writer": 4096,
}


@dataclass(frozen=True)
class CatalogModel:
    id: str
    context_length: int
    prompt_usd_per_mtok: Decimal  # USD per million prompt tokens
    completion_usd_per_mtok: Decimal

    @property
    def free(self) -> bool:
        """As agentic_gateway.catalog.ModelInfo.is_free decides it."""
        return self.id.endswith(":free") or (
            self.prompt_usd_per_mtok == 0 and self.completion_usd_per_mtok == 0
        )


CATALOG: dict[str, CatalogModel] = {
    model.id: model
    for model in (
        CatalogModel("google/gemini-2.5-flash", 1_048_576, Decimal("0.30"), Decimal("2.50")),
        CatalogModel("openai/gpt-4.1-mini", 1_047_576, Decimal("0.40"), Decimal("1.60")),
        CatalogModel("openai/gpt-4.1", 1_047_576, Decimal("2.00"), Decimal("8.00")),
        CatalogModel("anthropic/claude-sonnet-4.5", 1_000_000, Decimal("3.00"), Decimal("15.00")),
        CatalogModel("deepseek/deepseek-chat-v3.1", 163_840, Decimal("0.25"), Decimal("1.00")),
        CatalogModel("google/gemma-4-31b-it:free", 131_072, Decimal(0), Decimal(0)),
        CatalogModel("nvidia/nemotron-3-ultra-550b-a55b:free", 262_144, Decimal(0), Decimal(0)),
        CatalogModel("meta-llama/llama-3.3-70b-instruct:free", 131_072, Decimal(0), Decimal(0)),
    )
}


def model_chain(configured: str, default: tuple[str, ...]) -> list[str]:
    """A comma-separated chain as the gateway reads it (``_split`` there); empty: the default."""
    items = [item.strip() for item in configured.split(",") if item.strip()]
    return items or list(default)


def routed_model(model_id: str) -> RoutedModelOut:
    model = CATALOG.get(model_id)
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


def role_routing(paid_chain: list[str], free_chain: list[str]) -> list[RoleRoutingOut]:
    """Every role's chains. The gateway uses the same chains for every role today; the roles
    differ in how much output they may write."""
    paid = [routed_model(model_id) for model_id in paid_chain]
    free = [routed_model(model_id) for model_id in free_chain]
    return [
        RoleRoutingOut(role=role, max_output_tokens=MAX_OUTPUT_TOKENS[role], paid=paid, free=free)
        for role in AGENT_ROLES
    ]

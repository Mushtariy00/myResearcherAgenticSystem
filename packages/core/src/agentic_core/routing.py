"""Which models each agent role uses: the gateway follows this, the API shows and edits it."""

from typing import Literal, get_args

RoutingRole = Literal["researcher", "screener", "analyst", "methodologist", "coder", "writer"]
ROUTING_ROLES: tuple[RoutingRole, ...] = get_args(RoutingRole)

# The lab's chains, for a role without its own. ARP_PAID_MODELS and ARP_FREE_MODELS replace them.
DEFAULT_PAID_MODELS = ("google/gemini-2.5-flash", "openai/gpt-4.1-mini")
# Free models change often; unlisted ones are skipped and the catalog fills in text models.
# Nemotron first: on 2026-10-30 Gemma answered empty or rate-limited on every live call.
DEFAULT_FREE_MODELS = ("nvidia/nemotron-3-ultra-550b-a55b:free", "google/gemma-4-31b-it:free")
MAX_CHAIN_MODELS = 5  # each one tried can take the call's whole time limit

# The gateway `role` of each kind of call the worker makes, and the agent role it is routed as.
CALL_ROLES: dict[str, RoutingRole] = {
    "researcher": "researcher",
    "literature.screen": "screener",
    "literature.analyze": "analyst",
    "literature.synthesize": "analyst",
    "method.propose": "methodologist",
    "coding.write": "coder",
    "coding.repair": "coder",
    "writing.outline": "writer",
    "writing.section": "writer",
}

# The most one call of each role may write: the largest its calls ask for (a worker test keeps
# this in step). The gateway reserves budget for all of it.
MAX_OUTPUT_TOKENS: dict[RoutingRole, int] = {
    "researcher": 1500,
    "screener": 4000,
    "analyst": 4000,
    "methodologist": 4000,
    "coder": 16000,
    "writer": 4000,
}


def routing_role(call_role: str) -> RoutingRole | None:
    """The agent role a call is routed as; None uses the lab's chains (a call role not listed)."""
    return CALL_ROLES.get(call_role)

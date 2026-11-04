"""The routing table in agentic_core names the calls the worker really makes."""

from agentic_core.routing import CALL_ROLES, MAX_OUTPUT_TOKENS, ROUTING_ROLES
from agentic_worker.coding import code
from agentic_worker.literature import analysis, screening, synthesis
from agentic_worker.method import proposals
from agentic_worker.writing import outline, sections

# The role of each kind of call, with the most it asks for. "researcher" is the research plan's
# call in agentic_worker.stages.
CALLS = {
    "researcher": 1500,
    screening.ROLE: screening.MAX_OUTPUT_TOKENS,
    analysis.ROLE: analysis.MAX_OUTPUT_TOKENS,
    synthesis.ROLE: synthesis.MAX_OUTPUT_TOKENS,
    proposals.ROLE: proposals.MAX_OUTPUT_TOKENS,
    code.WRITE_ROLE: code.MAX_OUTPUT_TOKENS,
    code.REPAIR_ROLE: code.MAX_OUTPUT_TOKENS,
    outline.ROLE: outline.MAX_OUTPUT_TOKENS,
    sections.ROLE: sections.MAX_OUTPUT_TOKENS,
}


def test_every_kind_of_call_is_routed_as_an_agent_role() -> None:
    assert set(CALL_ROLES) == set(CALLS)
    assert set(CALL_ROLES.values()) == set(ROUTING_ROLES)


def test_each_roles_limit_is_the_most_its_calls_ask_for() -> None:
    for role in ROUTING_ROLES:
        asked = [tokens for call, tokens in CALLS.items() if CALL_ROLES[call] == role]
        assert MAX_OUTPUT_TOKENS[role] == max(asked), role

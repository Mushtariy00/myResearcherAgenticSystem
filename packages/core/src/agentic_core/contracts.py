"""Contracts between the API and the Temporal worker. Neither side imports the other's code.

Workflow inputs are dataclasses (Temporal's default JSON converter handles them).
"""

from dataclasses import dataclass
from enum import StrEnum

TASK_QUEUE = "arp-main"
RUN_WORKFLOW = "RunWorkflow"
DECIDE_UPDATE = "decide"
STATUS_QUERY = "status"


def workflow_id_for(run_id: str) -> str:
    return f"run-{run_id}"


@dataclass(frozen=True)
class RunInput:
    run_id: str


@dataclass(frozen=True)
class DecisionInput:
    """A reviewer's decision on one stage output. The workflow rejects stale or duplicate ones."""

    stage: str
    stage_output_id: str
    sha256: str  # hash of the content the reviewer saw
    decision: str  # agentic_core.enums.Decision value
    actor_id: str
    comment: str = ""


class EventType(StrEnum):
    """Run event types streamed to the browser (names follow AG-UI style: noun.verb)."""

    RUN_CREATED = "run.created"
    RUN_STATUS = "run.status"
    STAGE_STARTED = "stage.started"
    STAGE_OUTPUT_READY = "stage.output_ready"
    STAGE_DECIDED = "stage.decided"
    STAGE_FAILED = "stage.failed"
    LLM_CALL = "llm.call"
    LOG = "log"

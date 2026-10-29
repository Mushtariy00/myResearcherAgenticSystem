"""Contracts between the API and the Temporal worker. Neither side imports the other's code.

Workflow inputs are dataclasses (Temporal's default JSON converter handles them).
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

TASK_QUEUE = "arp-main"
RUN_WORKFLOW = "RunWorkflow"
DECIDE_UPDATE = "decide"
STATUS_QUERY = "status"


def workflow_id_for(run_id: str) -> str:
    return f"run-{run_id}"


def events_channel(run_id: object) -> str:
    """Valkey channel published after a run event commits; it only wakes SSE streams."""
    return f"run-events:{run_id}"


@dataclass(frozen=True)
class RunInput:
    run_id: str
    # Set by a retry: the run restarts at this stage and keeps the approved outputs before it.
    start_stage: str | None = None


@dataclass(frozen=True)
class DecisionInput:
    """A reviewer's decision on one stage output. The workflow rejects stale or duplicate ones."""

    stage: str
    stage_output_id: str
    sha256: str  # hash of the content the reviewer saw
    decision: str  # agentic_core.enums.Decision value
    actor_id: str
    comment: str = ""
    # Approve with edits (decision="approve" only): the reviewer's corrected output. It is stored
    # as a new version of the stage output, and that version is the one approved.
    edited_data: dict[str, Any] | None = None


class EventType(StrEnum):
    """Run event types streamed to the browser (names follow AG-UI style: noun.verb)."""

    RUN_CREATED = "run.created"
    RUN_STATUS = "run.status"
    STAGE_STARTED = "stage.started"
    STAGE_OUTPUT_READY = "stage.output_ready"
    STAGE_DECIDED = "stage.decided"
    STAGE_FAILED = "stage.failed"
    STAGE_INVALIDATED = "stage.invalidated"  # a retry of an earlier stage made this output stale
    RUN_RETRIED = "run.retried"
    LLM_CALL = "llm.call"
    LOG = "log"

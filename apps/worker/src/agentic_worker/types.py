"""Activity inputs and outputs (dataclasses: Temporal's default converter serializes them).

New fields always get defaults: histories of runs started earlier hold payloads without them.
"""

from dataclasses import dataclass, field

from agentic_core.contracts import DecisionInput


@dataclass(frozen=True)
class RunPrepareIn:
    run_id: str
    start_stage: str | None = None  # set by a retry


@dataclass(frozen=True)
class RunPlan:
    stages: list[str]  # the stages this execution runs, in pipeline order
    first_attempts: dict[str, int]  # each stage's first attempt number (a retry continues them)


@dataclass(frozen=True)
class StageStartIn:
    run_id: str
    stage: str
    attempt: int
    feedback: str = ""
    # The last attempt this execution allows for the stage (stage_runs.last_attempt).
    last_attempt: int | None = None


@dataclass(frozen=True)
class StageStarted:
    stage_run_id: str


@dataclass(frozen=True)
class StageExecIn:
    run_id: str
    stage_run_id: str
    stage: str
    attempt: int
    feedback: str = ""
    # False for runs started before project settings existed: they keep a 7-day wait and
    # never auto-approve (see RUN_SETTINGS_PATCH in workflows.py).
    apply_project_settings: bool = False
    # A request-changes attempt: the output the reviewer asked to change, and every comment
    # that led to this attempt, oldest first.
    revises_output_id: str | None = None
    feedback_history: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StageResult:
    stage_output_id: str
    sha256: str
    degraded: bool
    auto_approve: bool = False  # the project approves this stage without a reviewer
    approval_expiry_days: int | None = None  # the project's wait before the run is cancelled


@dataclass(frozen=True)
class DecisionRecordIn:
    run_id: str
    stage_run_id: str
    decision: DecisionInput
    automatic: bool = False  # made by the project's auto-approve setting, not a reviewer


@dataclass(frozen=True)
class FinishIn:
    run_id: str
    status: str
    error: str | None = None


@dataclass(frozen=True)
class StageWaitIn:
    """A stage attempt waits until ``retry_at`` (ISO 8601, UTC), then runs again."""

    run_id: str
    stage: str
    attempt: int
    reason: str  # an error code, e.g. free_quota.exhausted
    retry_at: str
    pause: bool = False  # the lab's balance is exhausted: the run is paused_budget meanwhile


@dataclass(frozen=True)
class RunResumeIn:
    run_id: str


@dataclass(frozen=True)
class PendingDecision:
    stage: str
    stage_output_id: str
    sha256: str
    attempt: int = 1
    # Request changes on this attempt would leave the stage nothing to run (None: no cap).
    last_attempt: int | None = None

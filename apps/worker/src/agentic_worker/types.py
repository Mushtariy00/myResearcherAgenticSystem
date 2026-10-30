"""Activity inputs and outputs (dataclasses: Temporal's default converter serializes them).

New fields always get defaults: histories of runs started earlier hold payloads without them.
"""

from dataclasses import dataclass

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
class PendingDecision:
    stage: str
    stage_output_id: str
    sha256: str

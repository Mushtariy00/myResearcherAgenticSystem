"""Activity inputs and outputs (dataclasses: Temporal's default converter serializes them)."""

from dataclasses import dataclass

from agentic_core.contracts import DecisionInput


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


@dataclass(frozen=True)
class StageResult:
    stage_output_id: str
    sha256: str
    degraded: bool


@dataclass(frozen=True)
class DecisionRecordIn:
    run_id: str
    stage_run_id: str
    decision: DecisionInput


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

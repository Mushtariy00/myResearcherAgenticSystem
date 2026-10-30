"""Request and response bodies (the OpenAPI the web client is generated from)."""

import logging
import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from agentic_core.enums import (
    Decision,
    LlmPolicy,
    LlmTier,
    Privacy,
    ProjectRole,
    RunStatus,
    StageStatus,
)
from agentic_core.schemas import EvidenceQuote, PaperSource, RunConfig, ScreeningDecision
from agentic_core.stages import MAX_ATTEMPTS

log = logging.getLogger(__name__)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b-\x1f]")  # C0 controls but tab and newline


def _without_control_characters(value: Any) -> Any:
    """Postgres refuses NUL in text and JSONB, and pasted text can carry other controls."""
    return _CONTROL_CHARACTERS.sub("", value) if isinstance(value, str) else value


# Free text people type, stored and shown as it is: control characters are dropped before the
# length limits apply.
PlainText = Annotated[str, BeforeValidator(_without_control_characters)]
# USD as the database stores it (agentic_db.models.Money): more decimals would be rounded away.
Usd = Annotated[Decimal, Field(max_digits=12, decimal_places=6)]


def stored_run_config(value: Any) -> RunConfig:
    """``runs.config`` as a RunConfig. Runs from before run options were added store ``{}``, the
    defaults; a stored value that no longer validates also reads as the defaults (and is logged)
    instead of failing every response that lists the run. Keys RunConfig doesn't have are the
    worker's internal knobs (``simulated``, ``demo_stage_seconds``) and are left out, as the
    worker does."""
    if isinstance(value, RunConfig):
        return value
    known = {key: item for key, item in (value or {}).items() if key in RunConfig.model_fields}
    try:
        return RunConfig.model_validate(known)
    except ValidationError:
        log.warning("a stored run config does not validate; using the defaults")
        return RunConfig()


class RunConfigOut(RunConfig):
    """A run's options as responses carry them: always complete, so every field is required."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class ProjectCreate(_In):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)


class ProjectOut(_Out):
    id: uuid.UUID
    name: str
    description: str
    privacy: Privacy
    allow_free_models: bool
    created_by: str
    created_at: datetime
    my_role: ProjectRole | None = None


class ProjectSettings(_In):
    """Project options; read by every member, written by owners and lab admins."""

    privacy: Privacy
    allow_free_models: bool
    auto_approve: bool  # never applies to coding (agentic_core.stages.NEVER_AUTO_APPROVE)
    # An approval left unanswered this long cancels the run.
    approval_expiry_days: int = Field(ge=1, le=30)


class MemberAdd(_In):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+$", max_length=320)
    role: ProjectRole


class MemberUpdate(_In):
    role: ProjectRole


class MemberOut(BaseModel):
    user_id: str
    email: str
    name: str
    role: ProjectRole


class RunCreate(_In):
    topic: PlainText = Field(min_length=3, max_length=500)
    llm_policy: LlmPolicy = LlmPolicy.AUTO
    budget_cap_usd: Usd | None = Field(default=None, ge=0, le=1000)
    config: RunConfig = Field(default_factory=RunConfig)


class RunOut(_Out):
    id: uuid.UUID
    project_id: uuid.UUID
    owner_id: str
    topic: str
    status: RunStatus
    llm_policy: LlmPolicy
    budget_cap_usd: Decimal | None
    config: RunConfigOut
    error: str | None
    created_at: datetime
    updated_at: datetime

    @field_validator("config", mode="before")
    @classmethod
    def _stored_config(cls, value: Any) -> dict[str, Any]:
        return stored_run_config(value).model_dump()


class RecentRunOut(RunOut):
    project_name: str


class StageOutputOut(_Out):
    id: uuid.UUID
    version: int
    data: dict[str, Any]
    sha256: str
    model: str | None
    degraded: bool
    degraded_reason: str | None
    created_at: datetime


class StageRunOut(_Out):
    id: uuid.UUID
    stage: str
    attempt: int
    status: StageStatus
    feedback: str | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    outputs: list[StageOutputOut] = []


class RunDetail(RunOut):
    stages: list[StageRunOut]
    # The output waiting for a decision, if any. Approvals must echo its id and sha256.
    awaiting: StageOutputOut | None = None
    awaiting_stage: str | None = None
    can_steer: bool = False  # may approve, request changes, reject, cancel or retry
    max_attempts: int = MAX_ATTEMPTS  # per stage in one execution (a retry starts a new one)
    # Change requests still possible on the awaiting stage: 0 means only approve or reject.
    # None when nothing awaits a decision or the attempt predates the cap being recorded.
    attempts_left: int | None = None
    # What the run has cost so far, failed and cancelled attempts included: settled calls at
    # their cost, calls still in flight at their reservation.
    spend_usd: Decimal = Decimal(0)


class ApprovalOut(BaseModel):
    decision: Decision
    comment: str
    actor_id: str
    actor_name: str | None  # None once the account no longer exists
    at: datetime


class OutputVersionOut(BaseModel):
    id: uuid.UUID
    version: int
    sha256: str
    data: dict[str, Any]
    degraded: bool
    degraded_reason: str | None
    model: str | None
    prompt_version: str | None
    edited_by: str | None  # the reviewer who wrote this version (approve with edits)
    edited_by_name: str | None
    created_at: datetime
    schema_ok: bool  # data passes the stage's strict output schema; old placeholders don't
    approval: ApprovalOut | None


class StageAttemptOut(BaseModel):
    id: uuid.UUID
    attempt: int
    status: StageStatus
    feedback: str | None  # the reviewer comment that started this attempt
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    outputs: list[OutputVersionOut]  # oldest version first


class StageDetail(BaseModel):
    run_id: uuid.UUID
    stage: str
    attempts: list[StageAttemptOut]  # oldest attempt first


class DecisionIn(_In):
    stage_output_id: uuid.UUID
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Decision
    comment: PlainText = Field(default="", max_length=5000)  # required for request_changes
    # Approve with edits (decision "approve" only): the corrected output, checked against the
    # stage's output schema. The workflow stores it as a new version and approves that version.
    edited_data: dict[str, Any] | None = None


class Accepted(BaseModel):
    status: Literal["accepted"] = "accepted"


class EventOut(BaseModel):
    seq: int
    type: str
    payload: dict[str, Any]
    created_at: datetime


class BudgetIn(_In):
    monthly_usd: Usd = Field(ge=0, le=10_000)


class BudgetOut(BaseModel):
    user_id: str
    monthly_usd: Decimal
    spent_usd: Decimal


class PaidModelsSetting(_In):
    enabled: bool


class MeOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    budget_usd: Decimal
    spent_usd: Decimal


NotificationKind = Literal[
    "approval_needed",
    "approval_expiring",
    "run_completed",
    "run_failed",
    "run_cancelled",
    "run_rejected",
    "budget_alert",
    "run_paused",  # the lab's OpenRouter balance ran out; the run resumes after a top-up
]


class NotificationOut(BaseModel):
    key: str  # stable while the notification exists; read state is stored under it
    kind: NotificationKind
    created_at: datetime
    read: bool
    run_id: uuid.UUID | None
    project_id: uuid.UUID | None
    stage: str | None
    params: dict[str, str | int | None]  # values for the translated message


class NotificationList(BaseModel):
    items: list[NotificationOut]  # newest first, at most 50
    unread_count: int  # over every current notification, not only the listed ones


class NotificationsReadIn(_In):
    keys: list[Annotated[str, StringConstraints(min_length=1, max_length=200)]] = Field(
        default_factory=list, max_length=500
    )
    all: bool = False  # mark every current notification read

    @model_validator(mode="after")
    def _keys_or_all(self) -> "NotificationsReadIn":
        if not self.keys and not self.all:
            raise ValueError("send keys or all=true")
        return self


Locale = Literal["en", "ko"]  # the UI languages (apps/web/src/i18n/config.ts)


class MySettingsOut(BaseModel):
    # Approvals, finished, failed and paused runs, and budget alerts by email too.
    email_notifications: bool
    locale: Locale  # the language of those emails; the web saves the UI language here


class MySettingsIn(_In):
    """Only the fields sent change: the language switches send the locale alone, so they never
    undo an email choice made in another tab."""

    email_notifications: bool | None = None
    locale: Locale | None = None

    @model_validator(mode="after")
    def _something_to_change(self) -> "MySettingsIn":
        if self.email_notifications is None and self.locale is None:
            raise ValueError("send email_notifications, locale or both")
        return self


class AuditEntryOut(BaseModel):
    id: int
    actor_id: str
    actor_name: str | None  # None once the account no longer exists
    actor_email: str | None
    action: str
    target_type: str
    target_id: str
    details: dict[str, Any]
    created_at: datetime


class AuditPage(BaseModel):
    items: list[AuditEntryOut]  # newest first
    total: int  # rows matching the filter, for paging


HealthStatus = Literal["ok", "degraded", "down", "unknown"]
HealthCheckName = Literal["postgres", "valkey", "temporal", "gateway", "worker"]


class HealthCheckOut(BaseModel):
    name: HealthCheckName
    status: HealthStatus
    latency_ms: float  # how long the probe took, timeouts and failures included
    detail: str | None  # message code explaining any status other than ok


class SystemHealthOut(BaseModel):
    status: HealthStatus  # the worst check: down, then degraded, then ok
    checked_at: datetime
    checks: list[HealthCheckOut]


# Responses that carry generated content (agentic_api.demo) have ``demo: bool``, true when any of
# their content is generated. Real figures are never generated: empty real data reads as zeros.

# --- Papers ---------------------------------------------------------------------------------


class PaperOut(BaseModel):
    """A paper's bibliographic record, as the lab's paper library stores it."""

    paper_id: str
    title: str
    authors: list[str]
    year: int
    venue: str | None
    doi: str | None
    arxiv_id: str | None
    url: str | None
    abstract: str
    citation_count: int | None
    source: PaperSource
    pdf_available: bool


class LibraryPaperOut(BaseModel):
    paper: PaperOut
    run_count: int  # runs whose literature stage screened the paper
    project_count: int
    best_relevance: float | None
    decisions: list[ScreeningDecision]  # every screening decision it got, in pipeline order
    last_seen_at: datetime  # when the newest run that screened it found it
    demo: bool  # a seeded demo paper


class PaperPage(BaseModel):
    items: list[LibraryPaperOut]  # best relevance first
    total: int  # papers matching the filters, for paging
    demo: bool


class PaperRunOut(BaseModel):
    """A run whose literature stage found the paper, with that run's screening of it."""

    id: uuid.UUID
    topic: str
    status: RunStatus
    project_id: uuid.UUID
    project_name: str
    created_at: datetime
    relevance: float
    decision: ScreeningDecision
    decision_reason: str
    demo: bool


class PaperAnalysisOut(BaseModel):
    """One literature output's reading notes on the paper; evidence points into its PDF."""

    run_id: uuid.UUID
    stage_output_id: uuid.UUID
    attempt: int
    created_at: datetime
    contribution: str
    method: str
    results: str
    limitations: str
    evidence: list[EvidenceQuote]
    demo: bool


class PaperDetail(BaseModel):
    paper: PaperOut
    best_relevance: float
    runs: list[PaperRunOut]  # newest first
    analyses: list[PaperAnalysisOut]  # newest first
    demo: bool


# --- Artifacts ------------------------------------------------------------------------------

ArtifactKind = Literal[
    "code_file",
    "code_archive",
    "experiment_log",
    "metrics",
    "checkpoint",  # best.pt of a training job, from the GPU host's job folder
    "draft",
    "references",
]


class ArtifactOut(BaseModel):
    id: str  # opaque; download it from /artifacts/{id}
    stage: str
    kind: ArtifactKind
    filename: str
    path: str | None  # code files: the path inside the code archive
    media_type: str
    size_bytes: int
    sha256: str
    stage_output_id: uuid.UUID
    version: int
    created_at: datetime
    demo: bool


class ArtifactList(BaseModel):
    run_id: uuid.UUID
    items: list[ArtifactOut]  # in pipeline order: coding, experiment, writing
    demo: bool


# --- Datasets and the GPU queue -------------------------------------------------------------


class DatasetSplitOut(BaseModel):
    name: str
    samples: int


class DataContractOut(BaseModel):
    """What the experiment harness may rely on when it loads the dataset."""

    inputs: str
    targets: str
    units: str | None
    valid_range: str | None
    missing_values: str | None
    evaluation: str | None


class DatasetOut(BaseModel):
    id: str  # the RunConfig.dataset value
    name: str
    version: str
    tasks: list[str]
    modality: str
    scenes: str
    description: str
    width: int  # pixels of the stored frames
    height: int
    samples: int  # in the lab's copy
    splits: list[DatasetSplitOut]
    size_bytes: int | None  # None until measured
    license: str
    homepage: str | None
    mount_path: str  # mounted read-only into experiment containers
    # sha256 of the dataset's file list (the executor computes it); None until it has.
    checksum_sha256: str | None
    registered_at: datetime
    contract: DataContractOut
    demo: bool


class DatasetList(BaseModel):
    items: list[DatasetOut]
    demo: bool


class GpuOut(BaseModel):
    """The GPU's latest nvidia-smi readings, as the executor reports them every few seconds. A
    reading this GPU or driver does not give (under WSL, say) is None."""

    name: str
    memory_total_mb: int
    memory_used_mb: int
    utilization_percent: int | None
    temperature_c: int | None
    power_draw_w: float | None
    power_limit_w: float | None
    fan_percent: int | None
    sampled_at: datetime
    demo: bool


class GpuJobOut(BaseModel):
    id: str  # the GPU job's id
    kind: Literal["smoke", "train"] | None = None  # a coding stage's smoke test, or training
    status: Literal["running", "queued"]
    run_id: uuid.UUID | None  # None for demo jobs and for runs the caller can't open
    topic: str | None
    project_name: str | None
    owner_name: str | None
    is_mine: bool
    dataset: str | None
    progress: float  # 0 to 1
    epoch: int | None
    total_epochs: int | None
    gpu_memory_mb: int | None
    submitted_at: datetime
    started_at: datetime | None  # None while queued
    estimated_start_at: datetime
    estimated_finish_at: datetime
    eta_seconds: int  # until it finishes, waiting time included
    estimated: bool  # progress and ETA guessed from the elapsed time (no executor reports yet)
    demo: bool


class GpuQueueOut(BaseModel):
    gpu: GpuOut | None  # None while the executor reports no readings
    # Whether the executor's heartbeat is recent; queued jobs wait while it isn't.
    executor_alive: bool
    concurrency: int  # jobs the GPU runs at once
    running: list[GpuJobOut]
    queued: list[GpuJobOut]  # in the order they will run
    my_position: int | None  # 0: the caller's job is running; n: n-th in the queue; None: none
    my_jobs: int
    per_user_limit: int  # jobs one user may have running or queued
    demo: bool


# --- Usage, estimates and model routing -----------------------------------------------------

UsageScope = Literal["me", "lab"]
AgentRole = Literal["researcher", "screener", "analyst", "methodologist", "coder", "writer"]


class UsageTotalsOut(BaseModel):
    paid_usd: Decimal  # settled cost, plus reservations of calls still open
    paid_calls: int
    free_calls: int
    prompt_tokens: int
    completion_tokens: int


class UsageDayOut(UsageTotalsOut):
    day: date  # UTC


class UsageModelOut(UsageTotalsOut):
    model: str
    tier: LlmTier


class UsageRunOut(UsageTotalsOut):
    run_id: uuid.UUID
    topic: str
    project_id: uuid.UUID
    project_name: str


class UsageUserOut(UsageTotalsOut):
    user_id: str
    name: str | None  # None once the account no longer exists
    email: str | None


class BudgetStatusOut(BaseModel):
    month: str  # UTC month, YYYY-MM
    monthly_usd: Decimal
    spent_usd: Decimal
    remaining_usd: Decimal


class UsageOut(BaseModel):
    scope: UsageScope
    days: int
    since: datetime  # start of the first day (UTC)
    until: datetime  # end of today (UTC)
    totals: UsageTotalsOut
    by_day: list[UsageDayOut]  # every day of the window, oldest first; zeros on quiet days
    by_model: list[UsageModelOut]  # the most expensive first
    top_runs: list[UsageRunOut]  # at most 10, the most expensive first
    by_user: list[UsageUserOut]  # lab scope only; empty for "me"
    budget: BudgetStatusOut  # the caller's own budget this month
    demo: bool  # always false: these are real journal figures


class RunEstimateIn(_In):
    config: RunConfig = Field(default_factory=RunConfig)
    llm_policy: LlmPolicy = LlmPolicy.AUTO
    budget_cap_usd: Decimal | None = Field(default=None, ge=0, le=1000)


class ModelPriceOut(BaseModel):
    id: str
    prompt_usd_per_mtok: Decimal
    completion_usd_per_mtok: Decimal
    known: bool  # false: not in the catalog, so a conservative price is assumed


class EstimateStepOut(BaseModel):
    """One step's assumed calls and their cost (before any cap)."""

    stage: str
    role: AgentRole
    calls_low: int
    calls_expected: int
    calls_high: int
    prompt_tokens_per_call: int
    completion_tokens_per_call: int
    low_usd: Decimal
    expected_usd: Decimal
    high_usd: Decimal


class EstimateAssumptions(BaseModel):
    paid_chain: list[ModelPriceOut]  # the order the gateway tries them in
    steps: list[EstimateStepOut]


class RunEstimateOut(BaseModel):
    llm_policy: LlmPolicy
    low_usd: Decimal  # what the run is likely to be charged: zero when paid models can't be used
    expected_usd: Decimal
    high_usd: Decimal
    calls_low: int
    expected_calls: int
    calls_high: int
    paid_possible: bool
    paid_blocked_by: Literal["policy", "kill_switch", "budget", "run_cap"] | None
    paid_models_enabled: bool  # the lab's kill switch
    budget_remaining_usd: Decimal  # the caller's paid budget left this month
    capped_by: Literal["run_cap", "budget"] | None  # what limited the range, if anything
    assumptions: EstimateAssumptions
    demo: bool


class RoutedModelOut(BaseModel):
    id: str
    free: bool
    in_catalog: bool
    context_length: int | None
    prompt_usd_per_mtok: Decimal | None
    completion_usd_per_mtok: Decimal | None


class RoleRoutingOut(BaseModel):
    role: AgentRole
    max_output_tokens: int  # the gateway reserves budget for this much output per call
    paid: list[RoutedModelOut]  # tried in order while the budget allows
    free: list[RoutedModelOut]  # otherwise


class ModelRoutingOut(BaseModel):
    paid_models_enabled: bool  # the real kill switch
    roles: list[RoleRoutingOut]
    demo: bool


class LabBalanceOut(BaseModel):
    balance_usd: Decimal  # OpenRouter credit left
    month: str  # UTC month, YYYY-MM
    spent_this_month_usd: Decimal  # every user's paid calls this month
    free_daily_limit: int  # free-model requests per UTC day for the whole lab
    free_calls_today: int
    auto_top_up: bool
    alert_floor_usd: Decimal  # admins are alerted below this balance
    below_floor: bool
    checked_at: datetime
    demo: bool

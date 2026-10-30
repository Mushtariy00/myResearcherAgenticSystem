"""Domain enums shared by the API, workers and gateway (stored as strings in Postgres)."""

from enum import StrEnum


class ProjectRole(StrEnum):
    OWNER = "owner"
    RESEARCHER = "researcher"
    VIEWER = "viewer"


class Privacy(StrEnum):
    STANDARD = "standard"
    CONFIDENTIAL = "confidential"  # routes with data_collection=deny; may exclude free models


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED_BUDGET = "paused_budget"  # only when the lab's OpenRouter balance is exhausted

    @property
    def is_terminal(self) -> bool:
        return self in {
            RunStatus.COMPLETED,
            RunStatus.REJECTED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    OUTPUT_READY = "output_ready"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INVALIDATED = "invalidated"  # a retry of an earlier stage made this output stale


class Decision(StrEnum):
    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    REJECT = "reject"


class LlmPolicy(StrEnum):
    AUTO = "auto"  # paid models while the budget allows, then free
    FREE = "free"


class LlmTier(StrEnum):
    PAID = "paid"
    FREE = "free"


class LlmCallState(StrEnum):
    RESERVED = "reserved"
    SENT = "sent"
    SETTLED = "settled"
    UNKNOWN = "unknown"  # crashed or timed out mid-call; the sweeper settles it later
    RELEASED = "released"  # never sent, or failed before any cost


class PdfStatus(StrEnum):
    """Whether the library holds a paper's full text."""

    UNKNOWN = "unknown"  # not looked for yet
    AVAILABLE = "available"  # stored; papers.pdf_sha256 names the file
    ABSTRACT_ONLY = "abstract_only"  # no open-access copy anywhere in the waterfall
    FAILED = "failed"  # a copy was found but could not be fetched or was not a valid PDF


class GpuJobKind(StrEnum):
    """What a GPU job is for (docs/design/experiments.md)."""

    SMOKE = "smoke"  # the coding stage's dry run of generated code
    TRAIN = "train"  # the experiment stage's training run


class GpuJobStatus(StrEnum):
    """queued → starting → running → succeeded | failed | timeout | cancelled."""

    QUEUED = "queued"
    STARTING = "starting"  # claimed by the executor; its container is being created
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {
            GpuJobStatus.SUCCEEDED,
            GpuJobStatus.FAILED,
            GpuJobStatus.TIMEOUT,
            GpuJobStatus.CANCELLED,
        }

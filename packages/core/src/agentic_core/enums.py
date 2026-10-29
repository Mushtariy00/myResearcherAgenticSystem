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

"""Request and response bodies (the OpenAPI the web client is generated from)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agentic_core.enums import Decision, LlmPolicy, Privacy, ProjectRole, RunStatus, StageStatus


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


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


class MemberAdd(_In):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+$", max_length=320)
    role: ProjectRole


class MemberOut(BaseModel):
    user_id: str
    email: str
    name: str
    role: ProjectRole


class RunCreate(_In):
    topic: str = Field(min_length=3, max_length=500)
    llm_policy: LlmPolicy = LlmPolicy.AUTO
    budget_cap_usd: Decimal | None = Field(default=None, ge=0, le=1000)


class RunOut(_Out):
    id: uuid.UUID
    project_id: uuid.UUID
    owner_id: str
    topic: str
    status: RunStatus
    llm_policy: LlmPolicy
    budget_cap_usd: Decimal | None
    error: str | None
    created_at: datetime
    updated_at: datetime


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
    can_steer: bool = False  # may approve, request changes, reject or cancel


class DecisionIn(_In):
    stage_output_id: uuid.UUID
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Decision
    comment: str = Field(default="", max_length=5000)


class Accepted(BaseModel):
    status: Literal["accepted"] = "accepted"


class EventOut(BaseModel):
    seq: int
    type: str
    payload: dict[str, Any]
    created_at: datetime


class BudgetIn(_In):
    monthly_usd: Decimal = Field(ge=0, le=10_000)


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

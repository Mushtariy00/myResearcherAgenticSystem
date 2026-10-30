"""Database models. Better Auth owns the `auth` schema; `*_id` user columns hold its user ids."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from agentic_core.enums import (
    Decision,
    LlmCallState,
    LlmPolicy,
    LlmTier,
    Privacy,
    ProjectRole,
    RunStatus,
    StageStatus,
)

Money = Numeric(12, 6)  # USD with sub-cent precision (OpenRouter bills fractions of a cent)


class Base(DeclarativeBase):
    # Stable constraint names, so Alembic migrations stay readable and reversible.
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSONB, list[Any]: JSONB}


def str_enum(enum_class: type[enum.StrEnum]) -> Enum:
    """Store enum values as strings with a CHECK constraint (easier to migrate than PG enums)."""
    return Enum(
        enum_class,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
    )


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    privacy: Mapped[Privacy] = mapped_column(str_enum(Privacy), default=Privacy.STANDARD)
    allow_free_models: Mapped[bool] = mapped_column(default=True)
    # Approve stages automatically (never coding: agentic_core.stages.NEVER_AUTO_APPROVE).
    auto_approve: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    # Unanswered approvals cancel the run after this many days.
    approval_expiry_days: Mapped[int] = mapped_column(Integer, default=7, server_default="7")
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = _created_at()


class ProjectMember(Base):
    __tablename__ = "project_members"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    role: Mapped[ProjectRole] = mapped_column(str_enum(ProjectRole))
    added_at: Mapped[datetime] = _created_at()


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (Index("ix_runs_project_created", "project_id", "created_at"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    owner_id: Mapped[str] = mapped_column(String(64))
    topic: Mapped[str] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
    status: Mapped[RunStatus] = mapped_column(str_enum(RunStatus), default=RunStatus.QUEUED)
    llm_policy: Mapped[LlmPolicy] = mapped_column(str_enum(LlmPolicy), default=LlmPolicy.AUTO)
    budget_cap_usd: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    workflow_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    last_event_seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StageRun(Base):
    __tablename__ = "stage_runs"
    __table_args__ = (UniqueConstraint("run_id", "stage", "attempt"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    stage: Mapped[str] = mapped_column(String(32))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[StageStatus] = mapped_column(str_enum(StageStatus), default=StageStatus.PENDING)
    # The reviewer comment that caused this attempt (request changes).
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The last attempt number this execution of the run allows for the stage (MAX_ATTEMPTS), so
    # the API can say how many change requests are left. NULL for attempts recorded before it.
    last_attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StageOutput(Base):
    __tablename__ = "stage_outputs"
    __table_args__ = (UniqueConstraint("stage_run_id", "version"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    stage_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stage_runs.id", ondelete="CASCADE"))
    # Greater than 1 when a reviewer approved with edits.
    version: Mapped[int] = mapped_column(Integer, default=1)
    data: Mapped[dict[str, Any]] = mapped_column()
    sha256: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    degraded: Mapped[bool] = mapped_column(default=False)
    degraded_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set on versions a reviewer wrote (approve with edits): that reviewer's user id.
    edited_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = _created_at()


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = _uuid_pk()
    # One decision per output version: a second decision on the same output is a conflict (409).
    stage_output_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stage_outputs.id", ondelete="CASCADE"), unique=True
    )
    sha256: Mapped[str] = mapped_column(String(64))  # the content the reviewer actually saw
    decision: Mapped[Decision] = mapped_column(str_enum(Decision))
    comment: Mapped[str] = mapped_column(Text, default="")
    actor_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = _created_at()


class RunEvent(Base):
    __tablename__ = "run_events"

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = _created_at()


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = _created_at()


class Budget(Base):
    __tablename__ = "budgets"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Paid-model budget per UTC calendar month (OpenRouter key limits reset monthly in UTC).
    monthly_usd: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    updated_by: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LlmCall(Base):
    """Spend journal: reserved → sent → settled | unknown | released."""

    __tablename__ = "llm_calls"
    __table_args__ = (
        Index("ix_llm_calls_user_created", "user_id", "created_at"),
        Index("ix_llm_calls_run_id", "run_id"),
        # The gateway finds a call's attempts with `LIKE '<key>#%'`. The database collation is
        # not C, so only a pattern_ops index serves a prefix match.
        Index(
            "ix_llm_calls_idempotency_key_prefix",
            "idempotency_key",
            postgresql_ops={"idempotency_key": "varchar_pattern_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(64))
    tier: Mapped[LlmTier] = mapped_column(str_enum(LlmTier))
    model: Mapped[str] = mapped_column(String(128))
    state: Mapped[LlmCallState] = mapped_column(
        str_enum(LlmCallState), default=LlmCallState.RESERVED
    )
    reserved_usd: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    cost_usd: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    generation_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
    response: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)  # replayed after a crash
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column()
    updated_by: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class NotificationRead(Base):
    """Read state of in-app notifications. Notifications themselves are derived from run state,
    keyed like "approval:<stage_output_id>" or "run.finished:<run_id>"."""

    __tablename__ = "notification_reads"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    notification_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    read_at: Mapped[datetime] = _created_at()

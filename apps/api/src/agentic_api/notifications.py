"""In-app notifications, derived from run, approval and spend state on every request.

Only read state is stored (``notification_reads``). Keys are stable, so a notification keeps
its read flag for as long as it is derived:

- ``approval:<stage_output_id>``: an output the user may decide on is waiting (approval_needed).
- ``approval.expiring:<stage_output_id>``: it has waited longer than the project's approval
  expiry minus one day (approval_expiring).
- ``run.finished:<run_id>``: one of the user's own runs finished in the last 14 days
  (run_completed, run_failed, run_cancelled, run_rejected). A retry forgets the read flag, so
  the run's next finish shows as new.
- ``budget:<yyyy-mm>:<80|100>``: the user's paid spend this UTC month reached 80% or 100% of
  their monthly budget (budget_alert).
- ``run.paused:<run_id>:<seq>``: a run waits for the lab's OpenRouter balance to be topped up
  (run_paused), for its owner and every lab admin. ``seq`` is the run event that began this
  pause, so a later pause of the same run is news again.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from agentic_api.auth import CurrentUser
from agentic_api.schemas import NotificationKind, NotificationList, NotificationOut
from agentic_core.contracts import EventType
from agentic_core.enums import LlmCallState, LlmTier, ProjectRole, RunStatus, StageStatus
from agentic_db.models import (
    Approval,
    LlmCall,
    NotificationRead,
    Project,
    ProjectMember,
    Run,
    RunEvent,
    StageOutput,
    StageRun,
)
from agentic_db.spend import month_spend, month_start, monthly_budget

LIST_LIMIT = 50
SOURCE_LIMIT = 200  # rows read per source; far more than a lab of 30 people produces
FINISHED_WINDOW = timedelta(days=14)
EXPIRY_WARNING = timedelta(days=1)
BUDGET_THRESHOLDS = (80, 100)
_FINISHED_KINDS: dict[RunStatus, NotificationKind] = {
    RunStatus.COMPLETED: "run_completed",
    RunStatus.FAILED: "run_failed",
    RunStatus.CANCELLED: "run_cancelled",
    RunStatus.REJECTED: "run_rejected",
}
# Calls that count against the budget, as in agentic_db.spend.month_spend.
_SPENDING_STATES = (
    LlmCallState.SETTLED,
    LlmCallState.RESERVED,
    LlmCallState.SENT,
    LlmCallState.UNKNOWN,
)


def approval_key(stage_output_id: uuid.UUID) -> str:
    return f"approval:{stage_output_id}"


def approval_expiring_key(stage_output_id: uuid.UUID) -> str:
    return f"approval.expiring:{stage_output_id}"


def run_finished_key(run_id: uuid.UUID) -> str:
    return f"run.finished:{run_id}"


def budget_key(month: str, percent: int) -> str:
    return f"budget:{month}:{percent}"


def run_paused_key(run_id: uuid.UUID, seq: int) -> str:
    return f"run.paused:{run_id}:{seq}"


async def derive_notifications(
    db: AsyncSession, user: CurrentUser, now: datetime | None = None
) -> list[NotificationOut]:
    """Every current notification for ``user``, newest first, all marked unread."""
    now = now or datetime.now(UTC)
    items = [
        *await _approvals(db, user, now),
        *await _finished_runs(db, user, now),
        *await _paused_runs(db, user),
        *await _budget_alerts(db, user, now),
    ]
    items.sort(key=lambda item: (item.created_at, item.key), reverse=True)
    return items


async def with_read_state(
    db: AsyncSession, user: CurrentUser, items: list[NotificationOut]
) -> NotificationList:
    """Attach the user's read flags and keep the newest LIST_LIMIT items."""
    keys = [item.key for item in items]
    read = (
        set(
            await db.scalars(
                select(NotificationRead.notification_key).where(
                    NotificationRead.user_id == user.id,
                    NotificationRead.notification_key.in_(keys),
                )
            )
        )
        if keys
        else set()
    )
    marked = [item.model_copy(update={"read": item.key in read}) for item in items]
    return NotificationList(
        items=marked[:LIST_LIMIT], unread_count=sum(not item.read for item in marked)
    )


async def mark_read(db: AsyncSession, user: CurrentUser, keys: set[str]) -> None:
    """Store read flags; keys that are already read stay as they are (idempotent)."""
    if not keys:
        return
    await db.execute(
        insert(NotificationRead)
        .values([{"user_id": user.id, "notification_key": key} for key in sorted(keys)])
        .on_conflict_do_nothing()
    )
    await db.commit()


async def _approvals(db: AsyncSession, user: CurrentUser, now: datetime) -> list[NotificationOut]:
    """Outputs waiting for a decision the user may make (the rule of authz.can_steer, in SQL)."""
    newer = aliased(StageOutput)
    query = (
        select(
            StageOutput.id.label("output_id"),
            StageOutput.created_at.label("ready_at"),
            StageRun.stage,
            Run.id.label("run_id"),
            Run.topic,
            Project.id.label("project_id"),
            Project.name.label("project_name"),
            Project.approval_expiry_days,
        )
        .join(StageRun, StageRun.id == StageOutput.stage_run_id)
        .join(Run, Run.id == StageRun.run_id)
        .join(Project, Project.id == Run.project_id)
        .where(
            Run.status == RunStatus.AWAITING_APPROVAL,
            StageRun.status == StageStatus.OUTPUT_READY,
            ~exists().where(Approval.stage_output_id == StageOutput.id),
            ~exists().where(
                newer.stage_run_id == StageOutput.stage_run_id, newer.version > StageOutput.version
            ),
        )
    )
    if not user.is_admin:
        query = query.join(
            ProjectMember,
            and_(ProjectMember.project_id == Run.project_id, ProjectMember.user_id == user.id),
        ).where(
            or_(
                ProjectMember.role == ProjectRole.OWNER,
                and_(ProjectMember.role == ProjectRole.RESEARCHER, Run.owner_id == user.id),
            )
        )
    rows = await db.execute(query.order_by(StageOutput.created_at.desc()).limit(SOURCE_LIMIT))

    items: list[NotificationOut] = []
    for output_id, ready_at, stage, run_id, topic, project_id, project_name, expiry_days in rows:
        params: dict[str, str | int | None] = {
            "topic": topic,
            "project": project_name,
            "stage": stage,
        }
        items.append(
            NotificationOut(
                key=approval_key(output_id),
                kind="approval_needed",
                created_at=ready_at,
                read=False,
                run_id=run_id,
                project_id=project_id,
                stage=stage,
                params=params,
            )
        )
        expires_at = ready_at + timedelta(days=expiry_days)
        warn_at = expires_at - EXPIRY_WARNING
        if now > warn_at:
            items.append(
                NotificationOut(
                    key=approval_expiring_key(output_id),
                    kind="approval_expiring",
                    created_at=warn_at,
                    read=False,
                    run_id=run_id,
                    project_id=project_id,
                    stage=stage,
                    params={**params, "days": expiry_days, "expires_at": expires_at.isoformat()},
                )
            )
    return items


async def _finished_runs(
    db: AsyncSession, user: CurrentUser, now: datetime
) -> list[NotificationOut]:
    """The user's own runs that finished recently, in projects they can still open.

    ``updated_at`` serves as the finish time: finishing is normally a run's last change.
    """
    query = (
        select(
            Run.id,
            Run.status,
            Run.topic,
            Run.error,
            Run.updated_at,
            Project.id.label("project_id"),
            Project.name.label("project_name"),
        )
        .join(Project, Project.id == Run.project_id)
        .where(
            Run.owner_id == user.id,
            Run.status.in_(list(_FINISHED_KINDS)),
            Run.updated_at >= now - FINISHED_WINDOW,
        )
    )
    if not user.is_admin:
        query = query.join(
            ProjectMember,
            and_(ProjectMember.project_id == Run.project_id, ProjectMember.user_id == user.id),
        )
    rows = await db.execute(query.order_by(Run.updated_at.desc()).limit(SOURCE_LIMIT))
    return [
        NotificationOut(
            key=run_finished_key(run_id),
            kind=_FINISHED_KINDS[RunStatus(run_status)],
            created_at=finished_at,
            read=False,
            run_id=run_id,
            project_id=project_id,
            stage=None,
            params={"topic": topic, "project": project_name, "error": error},
        )
        for run_id, run_status, topic, error, finished_at, project_id, project_name in rows
    ]


async def _paused_runs(db: AsyncSession, user: CurrentUser) -> list[NotificationOut]:
    """Runs waiting for the lab's OpenRouter balance: news for each run's owner (in projects they
    can still open) and for lab admins, who can top the balance up."""
    query = (
        select(
            Run.id,
            Run.topic,
            Run.updated_at,
            Project.id.label("project_id"),
            Project.name.label("project_name"),
        )
        .join(Project, Project.id == Run.project_id)
        .where(Run.status == RunStatus.PAUSED_BUDGET)
    )
    if not user.is_admin:
        query = query.join(
            ProjectMember,
            and_(ProjectMember.project_id == Run.project_id, ProjectMember.user_id == user.id),
        ).where(Run.owner_id == user.id)
    runs = (await db.execute(query.order_by(Run.updated_at.desc()).limit(SOURCE_LIMIT))).all()
    if not runs:
        return []

    # The pause began with the first paused status after the last other status.
    began: dict[uuid.UUID, tuple[int, datetime]] = {}
    for run_id, seq, payload, at in await db.execute(
        select(RunEvent.run_id, RunEvent.seq, RunEvent.payload, RunEvent.created_at)
        .where(
            RunEvent.run_id.in_([run.id for run in runs]),
            RunEvent.type == EventType.RUN_STATUS,
        )
        .order_by(RunEvent.run_id, RunEvent.seq)
    ):
        if payload.get("status") == RunStatus.PAUSED_BUDGET.value:
            began.setdefault(run_id, (seq, at))
        else:
            began.pop(run_id, None)

    items: list[NotificationOut] = []
    for run_id, topic, updated_at, project_id, project_name in runs:
        seq, paused_at = began.get(run_id, (0, updated_at))  # 0: a row written without events
        items.append(
            NotificationOut(
                key=run_paused_key(run_id, seq),
                kind="run_paused",
                created_at=paused_at,
                read=False,
                run_id=run_id,
                project_id=project_id,
                stage=None,
                params={"topic": topic, "project": project_name},
            )
        )
    return items


async def _budget_alerts(
    db: AsyncSession, user: CurrentUser, now: datetime
) -> list[NotificationOut]:
    budget = await monthly_budget(db, user.id)
    if budget <= 0:
        return []  # no paid budget: everything runs on free models, so there is nothing to warn
    spent = await month_spend(db, user.id, now)
    month = month_start(now).strftime("%Y-%m")
    items: list[NotificationOut] = []
    for percent in BUDGET_THRESHOLDS:
        threshold = budget * percent / 100
        if spent < threshold:
            break
        reached_at = await _spend_reached_at(db, user.id, threshold, now)
        items.append(
            NotificationOut(
                key=budget_key(month, percent),
                kind="budget_alert",
                created_at=reached_at or now,
                read=False,
                run_id=None,
                project_id=None,
                stage=None,
                params={
                    "percent": percent,
                    "month": month,
                    "budget_usd": str(budget),
                    "spent_usd": str(spent),
                },
            )
        )
    return items


async def _spend_reached_at(
    db: AsyncSession, user_id: str, threshold: Decimal, now: datetime
) -> datetime | None:
    """When this month's running total of paid spend first reached ``threshold``. Each call
    counts as in month_spend: its settled cost, or its reservation while still open."""
    amount = case(
        (LlmCall.state == LlmCallState.SETTLED, func.coalesce(LlmCall.cost_usd, 0)),
        else_=LlmCall.reserved_usd,
    )
    calls = (
        select(
            LlmCall.created_at,
            func.sum(amount).over(order_by=(LlmCall.created_at, LlmCall.id)).label("total"),
        )
        .where(
            LlmCall.user_id == user_id,
            LlmCall.tier == LlmTier.PAID,
            LlmCall.state.in_(_SPENDING_STATES),
            LlmCall.created_at >= month_start(now),
        )
        .subquery()
    )
    return await db.scalar(
        select(calls.c.created_at)
        .where(calls.c.total >= threshold)
        .order_by(calls.c.created_at)
        .limit(1)
    )

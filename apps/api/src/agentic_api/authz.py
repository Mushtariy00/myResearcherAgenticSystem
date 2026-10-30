"""Permission checks (docs/PLAN.md, Permissions). Non-members get 404 so projects don't leak."""

import uuid
from collections.abc import AsyncIterator

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_api.auth import CurrentUser
from agentic_core.enums import ProjectRole
from agentic_db.models import Project, ProjectMember, Run

EDITORS = frozenset({ProjectRole.OWNER, ProjectRole.RESEARCHER})
OWNERS = frozenset({ProjectRole.OWNER})  # members and settings (lab admins pass every check)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    sessions = request.app.state.sessions
    if sessions is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "db.unavailable")
    async with sessions() as session:
        yield session


async def project_role(
    db: AsyncSession, project_id: uuid.UUID, user: CurrentUser
) -> ProjectRole | None:
    member = await db.get(ProjectMember, (project_id, user.id))
    return member.role if member else None


async def load_project(
    db: AsyncSession, project_id: uuid.UUID, user: CurrentUser
) -> tuple[Project, ProjectRole | None]:
    """Return the project and the caller's role (None for a lab admin who isn't a member)."""
    project = await db.get(Project, project_id)
    role = await project_role(db, project_id, user) if project else None
    if project is None or (role is None and not user.is_admin):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project.not_found")
    return project, role


def require_role(
    user: CurrentUser, role: ProjectRole | None, allowed: frozenset[ProjectRole]
) -> None:
    if not user.is_admin and role not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "permission.denied")


def require_admin(user: CurrentUser) -> None:
    """Lab-wide views and settings (model routing, the lab balance, lab usage), and creating
    projects."""
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "permission.denied")


def membership_scope(user: CurrentUser) -> str | None:
    """Whose project memberships bound what ``user`` may see across projects: their own id, or
    None for a lab admin (every project). For queries over many runs, such as the paper library."""
    return None if user.is_admin else user.id


async def load_run(
    db: AsyncSession, run_id: uuid.UUID, user: CurrentUser
) -> tuple[Run, ProjectRole | None]:
    """Return the run and the caller's role in its project. A run in a project the caller can't
    open gets the same 404 as a run that doesn't exist."""
    run = await db.get(Run, run_id)
    role = await project_role(db, run.project_id, user) if run else None
    if run is None or (role is None and not user.is_admin):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run.not_found")
    return run, role


def can_steer(user: CurrentUser, role: ProjectRole | None, run: Run) -> bool:
    """Approve, request changes, reject, cancel, retry. Spending is charged to the run owner."""
    return (
        user.is_admin
        or role == ProjectRole.OWNER
        or (role == ProjectRole.RESEARCHER and run.owner_id == user.id)
    )


async def member_projects(
    db: AsyncSession, user: CurrentUser
) -> list[tuple[Project, ProjectRole | None]]:
    if user.is_admin:
        query = select(Project, ProjectMember.role).outerjoin(
            ProjectMember,
            (ProjectMember.project_id == Project.id) & (ProjectMember.user_id == user.id),
        )
    else:
        query = select(Project, ProjectMember.role).join(
            ProjectMember,
            (ProjectMember.project_id == Project.id) & (ProjectMember.user_id == user.id),
        )
    rows = await db.execute(query.order_by(Project.created_at.desc()))
    return [(project, role) for project, role in rows.all()]

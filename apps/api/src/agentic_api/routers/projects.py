import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_api.auth import CurrentUser, current_user
from agentic_api.authz import get_db, load_project, member_projects, require_role
from agentic_api.schemas import MemberAdd, MemberOut, ProjectCreate, ProjectOut
from agentic_core.enums import ProjectRole
from agentic_db.models import AuditLog, Project, ProjectMember

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])
User = Annotated[CurrentUser, Depends(current_user)]
Db = Annotated[AsyncSession, Depends(get_db)]

# Better Auth's user table (ADR 0003). Read-only: look-ups by email and display names.
_USER_BY_EMAIL = text('SELECT id, email, name FROM auth."user" WHERE lower(email) = lower(:email)')
_USERS_BY_ID = text('SELECT id, email, name FROM auth."user" WHERE id = ANY(:ids)')


def _out(project: Project, role: ProjectRole | None) -> ProjectOut:
    return ProjectOut.model_validate(project).model_copy(update={"my_role": role})


@router.post("", status_code=status.HTTP_201_CREATED, operation_id="createProject")
async def create_project(body: ProjectCreate, user: User, db: Db) -> ProjectOut:
    project = Project(name=body.name, description=body.description, created_by=user.id)
    db.add(project)
    await db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role=ProjectRole.OWNER))
    db.add(
        AuditLog(
            actor_id=user.id,
            action="project.create",
            target_type="project",
            target_id=str(project.id),
            details={"name": body.name},
        )
    )
    await db.commit()
    return _out(project, ProjectRole.OWNER)


@router.get("", operation_id="listProjects")
async def list_projects(user: User, db: Db) -> list[ProjectOut]:
    return [_out(project, role) for project, role in await member_projects(db, user)]


@router.get("/{project_id}", operation_id="getProject")
async def get_project(project_id: uuid.UUID, user: User, db: Db) -> ProjectOut:
    project, role = await load_project(db, project_id, user)
    return _out(project, role)


@router.get("/{project_id}/members", operation_id="listMembers")
async def list_members(project_id: uuid.UUID, user: User, db: Db) -> list[MemberOut]:
    await load_project(db, project_id, user)
    members = (
        (
            await db.execute(
                ProjectMember.__table__.select().where(ProjectMember.project_id == project_id)
            )
        )
        .mappings()
        .all()
    )
    ids = [m["user_id"] for m in members]
    users = (
        {row.id: row for row in (await db.execute(_USERS_BY_ID, {"ids": ids})).all()} if ids else {}
    )
    return [
        MemberOut(
            user_id=m["user_id"],
            email=users[m["user_id"]].email if m["user_id"] in users else "",
            name=users[m["user_id"]].name if m["user_id"] in users else "",
            role=m["role"],
        )
        for m in members
    ]


@router.post("/{project_id}/members", status_code=status.HTTP_201_CREATED, operation_id="addMember")
async def add_member(project_id: uuid.UUID, body: MemberAdd, user: User, db: Db) -> MemberOut:
    _, role = await load_project(db, project_id, user)
    require_role(user, role, frozenset({ProjectRole.OWNER}))
    found = (await db.execute(_USER_BY_EMAIL, {"email": body.email})).first()
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user.not_found")
    member = await db.get(ProjectMember, (project_id, found.id))
    if member is None:
        db.add(ProjectMember(project_id=project_id, user_id=found.id, role=body.role))
    else:
        member.role = body.role
    db.add(
        AuditLog(
            actor_id=user.id,
            action="project.member_set",
            target_type="project",
            target_id=str(project_id),
            details={"user_id": found.id, "role": body.role.value},
        )
    )
    await db.commit()
    return MemberOut(user_id=found.id, email=found.email, name=found.name, role=body.role)

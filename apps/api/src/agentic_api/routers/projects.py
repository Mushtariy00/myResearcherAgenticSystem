import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_api.auth import CurrentUser, current_user
from agentic_api.authz import OWNERS, get_db, load_project, member_projects, require_role
from agentic_api.schemas import (
    MemberAdd,
    MemberOut,
    MemberUpdate,
    ProjectCreate,
    ProjectOut,
    ProjectSettings,
)
from agentic_api.users import user_by_email, users_by_id
from agentic_core.enums import ProjectRole
from agentic_db.models import AuditLog, Project, ProjectMember

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])
User = Annotated[CurrentUser, Depends(current_user)]
Db = Annotated[AsyncSession, Depends(get_db)]
MemberId = Annotated[str, Path(min_length=1, max_length=64)]


def _out(project: Project, role: ProjectRole | None) -> ProjectOut:
    return ProjectOut.model_validate(project).model_copy(update={"my_role": role})


async def _keep_an_owner(
    db: AsyncSession, project_id: uuid.UUID, user_id: str, new_role: ProjectRole | None
) -> None:
    """Refuse to demote or remove (``new_role`` None) the project's last owner.

    The owner rows stay locked until commit, so two owners demoting each other at the same
    time can't both succeed.
    """
    owners = (
        await db.scalars(
            select(ProjectMember.user_id)
            .where(ProjectMember.project_id == project_id, ProjectMember.role == ProjectRole.OWNER)
            .with_for_update()
        )
    ).all()
    if new_role != ProjectRole.OWNER and list(owners) == [user_id]:
        raise HTTPException(status.HTTP_409_CONFLICT, "member.last_owner")


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


@router.get("/{project_id}/settings", operation_id="getProjectSettings")
async def get_project_settings(project_id: uuid.UUID, user: User, db: Db) -> ProjectSettings:
    project, _ = await load_project(db, project_id, user)
    return ProjectSettings.model_validate(project, from_attributes=True)


@router.put("/{project_id}/settings", operation_id="updateProjectSettings")
async def update_project_settings(
    project_id: uuid.UUID, body: ProjectSettings, user: User, db: Db
) -> ProjectSettings:
    project, role = await load_project(db, project_id, user)
    require_role(user, role, OWNERS)
    project.privacy = body.privacy
    project.allow_free_models = body.allow_free_models
    project.auto_approve = body.auto_approve
    project.approval_expiry_days = body.approval_expiry_days
    db.add(
        AuditLog(
            actor_id=user.id,
            action="project.settings",
            target_type="project",
            target_id=str(project_id),
            details=body.model_dump(mode="json"),
        )
    )
    await db.commit()
    return body


@router.get("/{project_id}/members", operation_id="listMembers")
async def list_members(project_id: uuid.UUID, user: User, db: Db) -> list[MemberOut]:
    await load_project(db, project_id, user)
    members = (
        await db.scalars(
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id)
            .order_by(ProjectMember.added_at, ProjectMember.user_id)
        )
    ).all()
    users = await users_by_id(db, [m.user_id for m in members])
    return [
        MemberOut(
            user_id=m.user_id,
            email=users[m.user_id].email if m.user_id in users else "",
            name=users[m.user_id].name if m.user_id in users else "",
            role=m.role,
        )
        for m in members
    ]


@router.post("/{project_id}/members", status_code=status.HTTP_201_CREATED, operation_id="addMember")
async def add_member(project_id: uuid.UUID, body: MemberAdd, user: User, db: Db) -> MemberOut:
    _, role = await load_project(db, project_id, user)
    require_role(user, role, OWNERS)
    found = await user_by_email(db, body.email)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user.not_found")
    member = await db.get(ProjectMember, (project_id, found.id))
    if member is None:
        db.add(ProjectMember(project_id=project_id, user_id=found.id, role=body.role))
    else:
        if member.role != body.role:
            await _keep_an_owner(db, project_id, found.id, body.role)
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


@router.patch("/{project_id}/members/{user_id}", operation_id="updateMember")
async def update_member(
    project_id: uuid.UUID, user_id: MemberId, body: MemberUpdate, user: User, db: Db
) -> MemberOut:
    """Change a member's role (owners and lab admins). The last owner can't be demoted."""
    _, role = await load_project(db, project_id, user)
    require_role(user, role, OWNERS)
    member = await db.get(ProjectMember, (project_id, user_id))
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "member.not_found")
    if member.role != body.role:
        await _keep_an_owner(db, project_id, user_id, body.role)
        member.role = body.role
        db.add(
            AuditLog(
                actor_id=user.id,
                action="project.member_set",
                target_type="project",
                target_id=str(project_id),
                details={"user_id": user_id, "role": body.role.value},
            )
        )
        await db.commit()
    account = (await users_by_id(db, [user_id])).get(user_id)
    return MemberOut(
        user_id=user_id,
        email=account.email if account else "",
        name=account.name if account else "",
        role=body.role,
    )


@router.delete(
    "/{project_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="removeMember",
)
async def remove_member(project_id: uuid.UUID, user_id: MemberId, user: User, db: Db) -> None:
    """Remove a member (owners and lab admins). The last owner can't be removed."""
    _, role = await load_project(db, project_id, user)
    require_role(user, role, OWNERS)
    member = await db.get(ProjectMember, (project_id, user_id))
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "member.not_found")
    await _keep_an_owner(db, project_id, user_id, None)
    removed_role = ProjectRole(member.role)
    await db.delete(member)
    db.add(
        AuditLog(
            actor_id=user.id,
            action="project.member_remove",
            target_type="project",
            target_id=str(project_id),
            details={"user_id": user_id, "role": removed_role.value},
        )
    )
    await db.commit()

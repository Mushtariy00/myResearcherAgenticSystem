import asyncio
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.enums import Privacy
from agentic_db.models import AuditLog, Project
from api_testkit import ADMIN, as_user, create_project, team_project

Factory = async_sessionmaker[AsyncSession]
SETTINGS = {
    "privacy": "confidential",
    "allow_free_models": False,
    "auto_approve": True,
    "approval_expiry_days": 3,
}


async def _project(client: httpx.AsyncClient, owner: str = "alice") -> str:
    return await create_project(client, "Depth", owner)


async def test_lab_admins_create_projects_and_become_their_owner(
    client: httpx.AsyncClient,
) -> None:
    for user in ("alice", "bob", "vera"):  # PLAN permissions: creating projects is admin work
        denied = await client.post("/api/v1/projects", json={"name": "Mine"}, headers=as_user(user))
        assert (denied.status_code, denied.json()["detail"]) == (403, "permission.denied")
    assert (await client.get("/api/v1/projects", headers=ADMIN)).json() == []

    created = await client.post("/api/v1/projects", json={"name": "Depth"}, headers=ADMIN)
    assert created.status_code == 201, created.text
    assert (created.json()["created_by"], created.json()["my_role"]) == ("root", "owner")
    assert await _roles(client, created.json()["id"]) == {"root": "owner"}


async def test_creator_becomes_owner_and_others_cannot_see_it(client: httpx.AsyncClient) -> None:
    project_id = await _project(client)
    mine = await client.get("/api/v1/projects", headers=as_user("alice"))
    assert [(p["id"], p["my_role"]) for p in mine.json()] == [(project_id, "owner")]

    assert (await client.get("/api/v1/projects", headers=as_user("bob"))).json() == []
    hidden = await client.get(f"/api/v1/projects/{project_id}", headers=as_user("bob"))
    assert hidden.status_code == 404  # not 403: non-members don't learn the project exists


async def test_lab_admin_sees_every_project(client: httpx.AsyncClient) -> None:
    project_id = await _project(client)
    projects = (await client.get("/api/v1/projects", headers=as_user("root", "admin"))).json()
    assert [p["id"] for p in projects] == [project_id]


async def test_requests_need_a_session(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/projects")).status_code == 401


async def test_state_changes_need_our_origin(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/projects",
        json={"name": "x"},
        headers={**as_user("alice"), "origin": "https://evil.example"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "csrf.origin_mismatch"


async def test_only_owners_add_members(client: httpx.AsyncClient) -> None:
    project_id = await _project(client)
    added = await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"email": "BOB@lab.test", "role": "researcher"},
        headers=as_user("alice"),
    )
    assert added.status_code == 201
    assert added.json()["user_id"] == "bob"

    denied = await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"email": "vera@lab.test", "role": "viewer"},
        headers=as_user("bob"),
    )
    assert denied.status_code == 403

    members = (
        await client.get(f"/api/v1/projects/{project_id}/members", headers=as_user("bob"))
    ).json()
    assert {(m["user_id"], m["role"]) for m in members} == {
        ("alice", "owner"),
        ("bob", "researcher"),
    }


async def test_unknown_member_email_is_404(client: httpx.AsyncClient) -> None:
    project_id = await _project(client)
    response = await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"email": "nobody@lab.test", "role": "viewer"},
        headers=as_user("alice"),
    )
    assert response.status_code == 404


async def test_adding_an_existing_member_is_a_conflict(client: httpx.AsyncClient) -> None:
    """Roles change through updateMember (which guards the last owner), never through add."""
    project_id = await team_project(client)
    members = f"/api/v1/projects/{project_id}/members"
    for email, role in (
        ("bob@lab.test", "owner"),
        ("BOB@lab.test", "researcher"),  # the same role, in other letters
        ("alice@lab.test", "viewer"),  # the last owner "adding" herself as a viewer
    ):
        response = await client.post(
            members, json={"email": email, "role": role}, headers=as_user("alice")
        )
        assert (response.status_code, response.json()["detail"]) == (409, "member.exists")
    assert await _roles(client, project_id) == {
        "alice": "owner",
        "bob": "researcher",
        "vera": "viewer",
    }


async def test_members_read_project_settings(client: httpx.AsyncClient) -> None:
    project_id = await team_project(client)
    url = f"/api/v1/projects/{project_id}/settings"
    defaults = {
        "privacy": "standard",
        "allow_free_models": True,
        "auto_approve": False,
        "approval_expiry_days": 7,
    }
    for user in (as_user("vera"), as_user("bob"), as_user("alice"), ADMIN):
        response = await client.get(url, headers=user)
        assert (response.status_code, response.json()) == (200, defaults)
    assert (await client.get(url, headers=as_user("carol"))).status_code == 404
    assert (await client.get(url)).status_code == 401


async def test_owners_and_admins_change_project_settings(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project_id = await team_project(client)
    url = f"/api/v1/projects/{project_id}/settings"
    for user, status in ((as_user("bob"), 403), (as_user("vera"), 403), (as_user("carol"), 404)):
        assert (await client.put(url, json=SETTINGS, headers=user)).status_code == status

    response = await client.put(url, json=SETTINGS, headers=as_user("alice"))
    assert (response.status_code, response.json()) == (200, SETTINGS)
    assert (await client.get(url, headers=as_user("vera"))).json() == SETTINGS
    project = (await client.get(f"/api/v1/projects/{project_id}", headers=as_user("vera"))).json()
    assert (project["privacy"], project["allow_free_models"]) == ("confidential", False)
    by_admin = {**SETTINGS, "approval_expiry_days": 30}
    assert (await client.put(url, json=by_admin, headers=ADMIN)).status_code == 200

    async with db() as session:
        stored = await session.get(Project, uuid.UUID(project_id))
        audit = (
            await session.scalars(
                select(AuditLog).where(AuditLog.action == "project.settings").order_by(AuditLog.id)
            )
        ).all()
    assert stored is not None
    assert (stored.privacy, stored.auto_approve, stored.approval_expiry_days) == (
        Privacy.CONFIDENTIAL,
        True,
        30,
    )
    assert [(a.actor_id, a.details) for a in audit] == [("alice", SETTINGS), ("root", by_admin)]


async def test_project_settings_are_validated(client: httpx.AsyncClient) -> None:
    project_id = await team_project(client)
    url = f"/api/v1/projects/{project_id}/settings"
    for body in (
        {**SETTINGS, "approval_expiry_days": 0},
        {**SETTINGS, "approval_expiry_days": 31},
        {**SETTINGS, "privacy": "secret"},
        {k: v for k, v in SETTINGS.items() if k != "auto_approve"},
        {**SETTINGS, "name": "Renamed"},
    ):
        assert (await client.put(url, json=body, headers=as_user("alice"))).status_code == 422


async def _roles(client: httpx.AsyncClient, project_id: str) -> dict[str, str]:
    members = (await client.get(f"/api/v1/projects/{project_id}/members", headers=ADMIN)).json()
    return {m["user_id"]: m["role"] for m in members}


async def test_owners_and_admins_change_member_roles(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project_id = await team_project(client)
    members = f"/api/v1/projects/{project_id}/members"
    response = await client.patch(
        f"{members}/bob", json={"role": "viewer"}, headers=as_user("alice")
    )
    assert (response.status_code, response.json()) == (
        200,
        {"user_id": "bob", "email": "bob@lab.test", "name": "Bob", "role": "viewer"},
    )
    assert (
        await client.patch(f"{members}/bob", json={"role": "owner"}, headers=ADMIN)
    ).status_code == 200
    assert await _roles(client, project_id) == {"alice": "owner", "bob": "owner", "vera": "viewer"}

    for user, status in ((as_user("vera"), 403), (as_user("carol"), 404), ({}, 401)):
        denied = await client.patch(f"{members}/vera", json={"role": "owner"}, headers=user)
        assert denied.status_code == status
    missing = await client.patch(
        f"{members}/carol", json={"role": "viewer"}, headers=as_user("alice")
    )
    assert (missing.status_code, missing.json()["detail"]) == (404, "member.not_found")
    invalid = await client.patch(f"{members}/vera", json={"role": "boss"}, headers=as_user("alice"))
    assert invalid.status_code == 422

    async with db() as session:
        audit = (
            await session.scalars(
                select(AuditLog)
                .where(AuditLog.action == "project.member_set")
                .order_by(AuditLog.id.desc())
                .limit(2)
            )
        ).all()
    assert [(a.actor_id, a.details) for a in audit] == [
        ("root", {"user_id": "bob", "role": "owner"}),
        ("alice", {"user_id": "bob", "role": "viewer"}),
    ]


async def test_owners_and_admins_remove_members(client: httpx.AsyncClient, db: Factory) -> None:
    project_id = await team_project(client)
    members = f"/api/v1/projects/{project_id}/members"
    assert (await client.delete(f"{members}/vera", headers=as_user("bob"))).status_code == 403
    assert (await client.delete(f"{members}/vera", headers=as_user("carol"))).status_code == 404

    removed = await client.delete(f"{members}/vera", headers=as_user("alice"))
    assert (removed.status_code, removed.content) == (204, b"")
    assert "vera" not in await _roles(client, project_id)
    hidden = await client.get(f"/api/v1/projects/{project_id}", headers=as_user("vera"))
    assert hidden.status_code == 404
    again = await client.delete(f"{members}/vera", headers=as_user("alice"))
    assert (again.status_code, again.json()["detail"]) == (404, "member.not_found")
    assert (await client.delete(f"{members}/bob", headers=ADMIN)).status_code == 204
    assert await _roles(client, project_id) == {"alice": "owner"}

    async with db() as session:
        audit = (
            await session.scalars(
                select(AuditLog)
                .where(AuditLog.action == "project.member_remove")
                .order_by(AuditLog.id)
            )
        ).all()
    assert [(a.actor_id, a.details) for a in audit] == [
        ("root", {"user_id": "root", "role": "owner"}),  # the creating admin stepping down
        ("alice", {"user_id": "vera", "role": "viewer"}),
        ("root", {"user_id": "bob", "role": "researcher"}),
    ]


async def test_the_last_owner_cannot_be_demoted_or_removed(client: httpx.AsyncClient) -> None:
    project_id = await team_project(client)
    members = f"/api/v1/projects/{project_id}/members"
    for response in (
        await client.patch(
            f"{members}/alice", json={"role": "researcher"}, headers=as_user("alice")
        ),
        await client.delete(f"{members}/alice", headers=as_user("alice")),
        await client.delete(f"{members}/alice", headers=ADMIN),
    ):
        assert (response.status_code, response.json()["detail"]) == (409, "member.last_owner")
    same = await client.patch(f"{members}/alice", json={"role": "owner"}, headers=as_user("alice"))
    assert same.status_code == 200

    # With a second owner either one may step down, but not both.
    await client.patch(f"{members}/bob", json={"role": "owner"}, headers=as_user("alice"))
    stepped_down = await client.patch(
        f"{members}/alice", json={"role": "viewer"}, headers=as_user("alice")
    )
    assert stepped_down.status_code == 200
    last = await client.delete(f"{members}/bob", headers=as_user("bob"))
    assert (last.status_code, last.json()["detail"]) == (409, "member.last_owner")
    assert await _roles(client, project_id) == {"alice": "viewer", "bob": "owner", "vera": "viewer"}


async def test_two_owners_stepping_down_at_once_leave_one_owner(
    client: httpx.AsyncClient,
) -> None:
    """The owner rows are locked while a change is checked: the second change waits for the
    first and then sees it, so one of the two is refused."""
    project_id = await team_project(client)
    members = f"/api/v1/projects/{project_id}/members"
    await client.patch(f"{members}/bob", json={"role": "owner"}, headers=as_user("alice"))

    responses = await asyncio.gather(
        client.patch(f"{members}/alice", json={"role": "viewer"}, headers=as_user("alice")),
        client.patch(f"{members}/bob", json={"role": "viewer"}, headers=as_user("bob")),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert list((await _roles(client, project_id)).values()).count("owner") == 1

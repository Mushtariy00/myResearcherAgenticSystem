import httpx

from api_testkit import as_user


async def _project(client: httpx.AsyncClient, owner: str = "alice") -> str:
    response = await client.post("/api/v1/projects", json={"name": "Depth"}, headers=as_user(owner))
    assert response.status_code == 201, response.text
    return response.json()["id"]


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

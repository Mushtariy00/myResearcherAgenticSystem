from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_api import health
from agentic_api.main import AppState, create_app
from agentic_api.orchestrator import TaskQueuePollers
from agentic_api.settings import Settings
from agentic_db.models import AuditLog
from api_testkit import (
    ADMIN,
    ORIGIN,
    FakeOrchestrator,
    FakeValkey,
    FakeVerifier,
    as_user,
    team_project,
)

Factory = async_sessionmaker[AsyncSession]
AUDIT = "/api/v1/admin/audit"
HEALTH = "/api/v1/admin/health"


async def test_audit_log_is_for_admins(client: httpx.AsyncClient) -> None:
    assert (await client.get(AUDIT, headers=as_user("alice"))).status_code == 403
    assert (await client.get(AUDIT)).status_code == 401


async def test_audit_log_pages_newest_first_with_actors(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project_id = await team_project(client)  # project.create, then two project.member_set
    await client.put("/api/v1/admin/budgets/bob", json={"monthly_usd": "5"}, headers=ADMIN)
    await client.delete(f"/api/v1/projects/{project_id}/members/vera", headers=as_user("alice"))
    async with db() as session:
        session.add(
            AuditLog(actor_id="ghost", action="run.cancel", target_type="run", target_id="x")
        )
        await session.commit()

    page = (await client.get(AUDIT, headers=ADMIN)).json()
    assert page["total"] == 6
    assert [entry["action"] for entry in page["items"]] == [
        "run.cancel",
        "project.member_remove",
        "budget.set",
        "project.member_set",
        "project.member_set",
        "project.create",
    ]
    ghost, removal, budget = page["items"][:3]
    assert (ghost["actor_id"], ghost["actor_name"], ghost["actor_email"]) == ("ghost", None, None)
    assert removal == {
        "id": removal["id"],
        "actor_id": "alice",
        "actor_name": "Alice",
        "actor_email": "alice@lab.test",
        "action": "project.member_remove",
        "target_type": "project",
        "target_id": project_id,
        "details": {"user_id": "vera", "role": "viewer"},
        "created_at": removal["created_at"],
    }
    assert (budget["actor_name"], budget["actor_email"]) == ("Root", "root@lab.test")

    second = (await client.get(f"{AUDIT}?limit=2&offset=2", headers=ADMIN)).json()
    assert second["total"] == 6
    assert [entry["id"] for entry in second["items"]] == [e["id"] for e in page["items"][2:4]]
    members = (await client.get(f"{AUDIT}?action=project.member_set", headers=ADMIN)).json()
    assert members["total"] == 2
    assert {entry["action"] for entry in members["items"]} == {"project.member_set"}
    for query in ("limit=0", "limit=201", "offset=-1", "action="):
        assert (await client.get(f"{AUDIT}?{query}", headers=ADMIN)).status_code == 422


async def _health(
    db: Factory | None,
    *,
    orchestrator: FakeOrchestrator | None = None,
    valkey: FakeValkey | None = None,
    gateway: httpx.MockTransport | None = None,
) -> dict[str, Any]:
    gateway = gateway or httpx.MockTransport(lambda _: httpx.Response(200, json={"status": "ok"}))
    async with httpx.AsyncClient(transport=gateway) as http:
        app = create_app(
            Settings(environment="test", public_origin=ORIGIN, gateway_url="http://gateway.test/"),
            state=AppState(
                sessions=db,
                session_verifier=FakeVerifier(),
                valkey=valkey or FakeValkey(),
                orchestrator=orchestrator or FakeOrchestrator(),
                http=http,
            ),
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(HEALTH, headers=ADMIN)
    assert response.status_code == 200, response.text
    return response.json()


def _statuses(report: dict[str, Any]) -> dict[str, tuple[str, str | None]]:
    return {check["name"]: (check["status"], check["detail"]) for check in report["checks"]}


async def test_health_checks_every_dependency(db: Factory) -> None:
    requested: list[str] = []

    def gateway(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, json={"status": "ok"})

    report = await _health(db, gateway=httpx.MockTransport(gateway))
    assert report["status"] == "ok"
    assert [check["name"] for check in report["checks"]] == [
        "postgres",
        "valkey",
        "temporal",
        "gateway",
        "worker",
    ]
    assert all(check["status"] == "ok" and check["detail"] is None for check in report["checks"])
    assert all(check["latency_ms"] >= 0 for check in report["checks"])
    assert requested == ["http://gateway.test/v1/health"]
    assert report["checked_at"]


async def test_health_reports_what_is_down(db: Factory) -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    report = await _health(
        None,
        orchestrator=FakeOrchestrator(namespace_ok=False),
        valkey=FakeValkey(down=True),
        gateway=httpx.MockTransport(refused),
    )
    assert report["status"] == "down"
    assert _statuses(report) == {
        "postgres": ("down", "db.unavailable"),
        "valkey": ("down", "health.unreachable"),
        "temporal": ("down", "health.unreachable"),
        "gateway": ("down", "health.unreachable"),
        "worker": ("unknown", "health.unreachable"),  # Temporal can't tell us
    }
    failing = await _health(db, gateway=httpx.MockTransport(lambda _: httpx.Response(503)))
    assert _statuses(failing)["gateway"] == ("down", "health.bad_status")


@pytest.mark.parametrize(
    ("pollers", "expected", "overall"),
    [
        (TaskQueuePollers(workflow=0, activity=0), ("down", "health.no_pollers"), "down"),
        (
            TaskQueuePollers(workflow=2, activity=0),
            ("degraded", "health.partial_pollers"),
            "degraded",
        ),
        (None, ("unknown", "health.unsupported"), "ok"),
    ],
)
async def test_health_reads_the_worker_pollers(
    db: Factory, pollers: TaskQueuePollers | None, expected: tuple[str, str], overall: str
) -> None:
    report = await _health(db, orchestrator=FakeOrchestrator(pollers=pollers))
    assert (_statuses(report)["worker"], report["status"]) == (expected, overall)


async def test_health_probes_time_out_and_slow_answers_degrade(
    db: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health, "PROBE_TIMEOUT_SECONDS", 0.05)
    report = await _health(None, valkey=FakeValkey(ping_delay=1.0))
    [valkey] = [check for check in report["checks"] if check["name"] == "valkey"]
    assert (valkey["status"], valkey["detail"]) == ("down", "health.timeout")
    assert valkey["latency_ms"] >= 50

    monkeypatch.setattr(health, "PROBE_TIMEOUT_SECONDS", 2.0)
    monkeypatch.setattr(health, "SLOW_MS", -1.0)  # every answer counts as slow
    slow = await _health(db)
    assert set(_statuses(slow).values()) == {("degraded", "health.slow")}
    assert slow["status"] == "degraded"


async def test_health_is_for_admins(client: httpx.AsyncClient) -> None:
    assert (await client.get(HEALTH, headers=as_user("alice"))).status_code == 403
    assert (await client.get(HEALTH)).status_code == 401
    report = (await client.get(HEALTH, headers=ADMIN)).json()  # the test app has no HTTP client
    assert _statuses(report)["gateway"] == ("unknown", "health.unconfigured")
    assert _statuses(report)["postgres"] == ("ok", None)

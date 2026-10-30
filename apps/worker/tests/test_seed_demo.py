"""The demo seed's building blocks, on the test database (and a time-skipping Temporal server
for the live runs). The seed itself is never run against the dev database here."""

import asyncio
import dataclasses
import random
import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, text
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from agentic_core.contracts import TASK_QUEUE
from agentic_core.enums import LlmTier, ProjectRole, RunStatus, StageStatus
from agentic_core.schemas import validate_stage_output
from agentic_core.stages import STAGE_ORDER, Stage
from agentic_db.models import (
    Approval,
    Budget,
    LlmCall,
    Paper,
    Project,
    ProjectMember,
    Run,
    RunEvent,
    RunPaper,
    StageOutput,
    StageRun,
)
from agentic_db.spend import month_spend
from agentic_worker import seed_demo
from agentic_worker.activities import StageActivities
from agentic_worker.outputs import content_sha256
from agentic_worker.stages import PipelineStageRunner
from agentic_worker.workflows import AUTO_APPROVE_ACTOR, RunWorkflow
from worker_testkit import Factory, FakePlanner, FakeValkey

USERS = {account.key: f"user-{account.key}" for account in seed_demo.DEMO_ACCOUNTS}
NOW = datetime(2026, 10, 30, 6, 0, tzinfo=UTC)
# The same stand-in for Better Auth's user table as the API tests (the migrations create the
# auth schema; the web app creates the real table).
AUTH_USER_TABLE = text(
    'CREATE TABLE IF NOT EXISTS auth."user" (id text PRIMARY KEY, email text, name text)'
)


async def seeded(db: Factory) -> seed_demo.SeedSummary:
    return await seed_demo.seed_static(db, USERS, NOW, random.Random(7))  # noqa: S311 - demo data


async def runs_by_topic(db: Factory) -> dict[str, Run]:
    async with db() as session:
        return {run.topic: run for run in await session.scalars(select(Run))}


async def test_demo_users_are_found_by_email(db: Factory) -> None:
    async with db() as session:
        await session.execute(AUTH_USER_TABLE)
        for account in seed_demo.DEMO_ACCOUNTS:
            await session.execute(
                text('INSERT INTO auth."user" (id, email, name) VALUES (:id, :email, :name)'),
                {"id": f"id-{account.key}", "email": account.email.upper(), "name": account.name},
            )
        await session.commit()
    try:
        async with db() as session:
            assert await seed_demo.load_demo_users(session) == {
                account.key: f"id-{account.key}" for account in seed_demo.DEMO_ACCOUNTS
            }
            await session.execute(text("DELETE FROM auth.\"user\" WHERE id = 'id-mateo'"))
            with pytest.raises(seed_demo.SeedError, match=re.escape("mateo.silva@lab.test")):
                await seed_demo.load_demo_users(session)
    finally:
        async with db() as session:
            await session.execute(text("DELETE FROM auth.\"user\" WHERE id LIKE 'id-%'"))
            await session.commit()


async def test_projects_have_members_in_every_role_and_the_users_have_budgets(
    db: Factory,
) -> None:
    await seeded(db)
    async with db() as session:
        projects = (await session.scalars(select(Project))).all()
        members = (await session.scalars(select(ProjectMember))).all()
        budgets = {b.user_id: b.monthly_usd for b in await session.scalars(select(Budget))}
    assert {project.id for project in projects} == set(seed_demo.demo_project_ids())
    assert {member.role for member in members} == set(ProjectRole)
    for project in projects:
        owners = [m for m in members if m.project_id == project.id and m.role == "owner"]
        assert len(owners) == 1 and owners[0].user_id == project.created_by
    assert any(project.auto_approve for project in projects)
    assert budgets == {USERS[key]: monthly for key, (monthly, _) in seed_demo._BUDGETS.items()}


async def test_spend_history_covers_a_month_of_paid_and_free_calls(db: Factory) -> None:
    summary = await seeded(db)
    async with db() as session:
        calls = (await session.scalars(select(LlmCall).where(LlmCall.run_id.is_(None)))).all()
        spent = {key: await month_spend(session, user, NOW) for key, user in USERS.items()}
    assert len(calls) == summary.llm_calls > 1000
    assert {call.tier for call in calls} == {LlmTier.PAID, LlmTier.FREE}
    assert len({call.created_at.date() for call in calls}) >= 25
    assert all(NOW - timedelta(days=31) < call.created_at < NOW for call in calls)
    for call in calls:
        assert call.state == "settled" and call.cost_usd is not None
        assert (call.cost_usd > 0) == (call.tier == LlmTier.PAID)
        assert call.idempotency_key.startswith(seed_demo.SEED_KEY_PREFIX)
    for key, (monthly, share) in seed_demo._BUDGETS.items():
        # The share of the budget each user has used this month (plus seeded plan calls).
        assert abs(spent[key] - monthly * Decimal(str(share))) < Decimal("0.2"), key


async def test_finished_runs_look_like_what_the_workflow_writes(db: Factory) -> None:
    await seeded(db)
    runs = await runs_by_topic(db)
    assert {run.status for run in runs.values()} == {
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.REJECTED,
        RunStatus.PAUSED_BUDGET,
    }
    async with db() as session:
        for run in runs.values():
            await assert_consistent(session, run)


async def assert_consistent(session: Any, run: Run) -> None:
    event_rows = (
        await session.scalars(
            select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.seq)
        )
    ).all()
    assert [e.seq for e in event_rows] == list(range(1, run.last_event_seq + 1))
    times = [e.created_at for e in event_rows]
    assert times == sorted(times) and times[-1] <= NOW, run.topic
    assert event_rows[0].type == "run.created"
    assert (event_rows[-1].type, event_rows[-1].payload) == (
        "run.status",
        {"status": run.status.value, "error": run.error},
    )
    stage_runs = (await session.scalars(select(StageRun).where(StageRun.run_id == run.id))).all()
    outputs = (
        await session.scalars(
            select(StageOutput).where(StageOutput.stage_run_id.in_([s.id for s in stage_runs]))
        )
    ).all()
    by_id = {output.id: output for output in outputs}
    stage_of = {s.id: s.stage for s in stage_runs}
    for output in outputs:
        validate_stage_output(stage_of[output.stage_run_id], output.data)
        assert output.sha256 == content_sha256(output.data)
    approvals = (
        await session.scalars(select(Approval).where(Approval.stage_output_id.in_(list(by_id))))
    ).all()
    for approval in approvals:
        assert approval.sha256 == by_id[approval.stage_output_id].sha256
    decided = [e.payload for e in event_rows if e.type == "stage.decided"]
    assert sorted(d["stage_output_id"] for d in decided) == sorted(
        str(a.stage_output_id) for a in approvals
    )
    for event in event_rows:
        if event.type == "log":
            assert set(event.payload) == {"stage", "code", "params", "message"}


async def stage_statuses(db: Factory, run: Run) -> list[tuple[str, int, StageStatus]]:
    async with db() as session:
        rows = await session.scalars(
            select(StageRun).where(StageRun.run_id == run.id).order_by(StageRun.started_at)
        )
        return [(row.stage, row.attempt, StageStatus(row.status)) for row in rows]


async def test_each_finished_run_tells_its_story(db: Factory) -> None:
    await seeded(db)
    runs = await runs_by_topic(db)
    completed = runs["Lightweight monocular depth estimation for indoor robots"]
    assert await stage_statuses(db, completed) == [
        ("literature", 1, StageStatus.CHANGES_REQUESTED),
        ("literature", 2, StageStatus.APPROVED),
        ("method", 1, StageStatus.APPROVED),
        ("coding", 1, StageStatus.APPROVED),
        ("experiment", 1, StageStatus.APPROVED),
        ("writing", 1, StageStatus.APPROVED),
    ]
    async with db() as session:
        edited = (
            await session.scalars(select(StageOutput).where(StageOutput.edited_by.is_not(None)))
        ).all()
    assert [(o.version, o.edited_by, o.degraded) for o in edited] == [(2, USERS["admin"], False)]

    failed = runs["Boundary-aware segmentation for driving scenes"]
    assert (failed.status, failed.error) == (RunStatus.FAILED, "stage.too_many_attempts")
    assert [s for s in await stage_statuses(db, failed) if s[0] == "coding"] == [
        ("coding", attempt, StageStatus.CHANGES_REQUESTED) for attempt in (1, 2, 3)
    ]
    selected = runs["Semantic segmentation of urban scenes with limited labels"]
    assert [stage for stage, _, _ in await stage_statuses(db, selected)] == [
        "literature",
        "method",
    ]
    rejected = runs["Open-vocabulary segmentation of aerial images"]
    assert await stage_statuses(db, rejected) == [("literature", 1, StageStatus.REJECTED)]
    expired = runs["Night-time semantic segmentation with domain adaptation"]
    assert (expired.status, expired.error) == (RunStatus.CANCELLED, "approval.expired")
    assert (await stage_statuses(db, expired))[-1] == ("experiment", 1, StageStatus.CANCELLED)
    paused = runs["Knowledge distillation for small CNN classifiers"]
    assert (await stage_statuses(db, paused))[-1] == ("method", 1, StageStatus.RUNNING)
    assert paused.workflow_id is None

    automatic = runs["Calibrated long-tailed image classification"]
    async with db() as session:
        decided = (
            await session.scalars(
                select(RunEvent.payload)
                .where(RunEvent.run_id == automatic.id, RunEvent.type == "stage.decided")
                .order_by(RunEvent.seq)
            )
        ).all()
    assert [(d["stage"], d["automatic"]) for d in decided] == [
        ("literature", True),
        ("method", True),
        ("coding", False),
        ("experiment", True),
        ("writing", True),
    ]
    assert {d["actor_id"] for d in decided if d["automatic"]} == {AUTO_APPROVE_ACTOR}


class FakeTemporal:
    """Records terminate calls the way the seed makes them."""

    def __init__(self) -> None:
        self.terminated: list[str] = []

    def get_workflow_handle(self, workflow_id: str) -> "FakeTemporal":
        self.terminated.append(workflow_id)
        return self

    async def terminate(self, reason: str) -> None:
        return None


async def test_seeding_again_replaces_the_demo_projects_and_nothing_else(db: Factory) -> None:
    async with db() as session:
        other = Project(name="Real research", created_by="carol")
        session.add(other)
        await session.flush()
        session.add(
            LlmCall(
                idempotency_key="real:call-1",
                user_id="carol",
                role="researcher",
                tier=LlmTier.PAID,
                model="openai/gpt-4.1-mini",
                state="settled",
                cost_usd=Decimal("0.01"),
            )
        )
        await session.commit()
    first = await seeded(db)
    async with db() as session:
        live = Run(
            project_id=seed_demo.demo_project_id("depth"),
            owner_id=USERS["jiwoo"],
            topic="A live demo run",
            status=RunStatus.AWAITING_APPROVAL,
            workflow_id="run-live-demo",
        )
        session.add(live)
        await session.commit()
    temporal = FakeTemporal()
    removed = await seed_demo.remove_previous(db, temporal)  # type: ignore[arg-type]
    assert removed == len(seed_demo.FINISHED_RUNS) + 1
    assert temporal.terminated == ["run-live-demo"]  # finished runs have nothing to stop
    second = await seeded(db)

    async with db() as session:
        projects = (await session.scalars(select(Project.id))).all()
        runs = (await session.scalars(select(Run))).all()
        real = (
            await session.scalars(select(LlmCall).where(LlmCall.idempotency_key == "real:call-1"))
        ).all()
        seeded_calls = (
            await session.scalars(
                select(LlmCall).where(LlmCall.idempotency_key.startswith("demo-seed:"))
            )
        ).all()
    assert sorted(projects) == sorted([other.id, *seed_demo.demo_project_ids()])
    assert len(runs) == len(seed_demo.FINISHED_RUNS)
    assert len(real) == 1
    run_calls = sum(1 for call in seeded_calls if call.run_id is not None)
    assert len(seeded_calls) - run_calls == second.llm_calls == first.llm_calls


async def library_by_stage_run(db: Factory) -> dict[uuid.UUID, list[tuple[str, RunPaper]]]:
    """The (paper key, run_papers row) pairs of each stage run, best ranked first."""
    async with db() as session:
        rows = await session.execute(
            select(Paper.key, RunPaper).join(RunPaper, RunPaper.paper_id == Paper.id)
        )
        found: dict[uuid.UUID, list[tuple[str, RunPaper]]] = {}
        for key, entry in sorted(rows, key=lambda row: row[1].rank):
            found.setdefault(entry.stage_run_id, []).append((key, entry))
        return found


async def literature_outputs(db: Factory) -> dict[uuid.UUID, StageOutput]:
    async with db() as session:
        rows = await session.scalars(
            select(StageOutput)
            .join(StageRun, StageRun.id == StageOutput.stage_run_id)
            .where(StageRun.stage == "literature", StageOutput.version == 1)
        )
        return {output.stage_run_id: output for output in rows}


async def test_the_seeded_literature_papers_are_in_the_library(db: Factory) -> None:
    for _ in range(2):  # seeding again replaces them
        await seed_demo.remove_previous(db, FakeTemporal())  # type: ignore[arg-type]
        await seeded(db)
        outputs = await literature_outputs(db)
        library = await library_by_stage_run(db)
        assert set(library) == set(outputs)
        for stage_run_id, output in outputs.items():
            refs = output.data["papers"]
            entries = library[stage_run_id]
            assert [key for key, _ in entries] == [ref["paper_id"] for ref in refs]
            assert [entry.decision for _, entry in entries] == [ref["decision"] for ref in refs]
            analysed = {key: entry.analysis for key, entry in entries if entry.analysis}
            assert analysed == {a["paper_id"]: a for a in output.data["analyses"]}
            # Last seen when the backdated output was stored, not when the seed ran.
            assert {entry.created_at for _, entry in entries} == {output.created_at}
        async with db() as session:
            papers = (await session.scalars(select(Paper))).all()
        assert all(paper.demo for paper in papers)
        # Every demo paper belongs to a seeded output: the last seed's papers are gone.
        assert {paper.key for paper in papers} == {
            ref["paper_id"] for output in outputs.values() for ref in output.data["papers"]
        }


# --- live runs ----------------------------------------------------------------------------------


@pytest.fixture
async def temporal(db: Factory) -> AsyncIterator[Client]:
    activities = StageActivities(
        db, FakeValkey(), PipelineStageRunner(FakePlanner(), demo_stage_seconds=0)
    )
    async with (
        await WorkflowEnvironment.start_time_skipping() as env,
        Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[RunWorkflow],
            activities=activities.all(),
        ),
    ):
        yield env.client


async def test_live_runs_wait_for_review_at_their_stage(db: Factory, temporal: Client) -> None:
    async with db() as session:
        await seed_demo.write_projects(session, USERS, NOW)
        await session.commit()
    # The long stage lasts long enough to be seen running, not ten minutes.
    specs = tuple(
        spec
        if spec.advance
        else dataclasses.replace(spec, config={**spec.config, "demo_stage_seconds": 30})
        for spec in seed_demo.LIVE_RUNS
    )
    started = await seed_demo.start_live_runs(db, temporal, USERS, specs)
    await asyncio.gather(
        *(
            seed_demo.advance_live_run(
                db, temporal, USERS, spec, run_id, patience=timedelta(seconds=60)
            )
            for spec, run_id in started
            if spec.advance
        )
    )
    for spec, run_id in started:
        async with db() as session:
            run = await session.get(Run, uuid.UUID(run_id))
            found = await session.scalars(
                select(StageRun).where(StageRun.run_id == uuid.UUID(run_id))
            )
        # In pipeline order, not by started_at: a WSL clock may step back between two stages.
        stage_runs = sorted(found, key=lambda s: (STAGE_ORDER.index(Stage(s.stage)), s.attempt))
        assert run is not None and run.workflow_id == f"run-{run_id}"
        if not spec.advance:
            assert run.status == RunStatus.RUNNING
            assert [(s.stage, s.status) for s in stage_runs] == [("literature", "running")]
            continue
        assert run.status == RunStatus.AWAITING_APPROVAL, spec.topic
        assert stage_runs[-1].stage == spec.wait_at
        assert stage_runs[-1].status == StageStatus.OUTPUT_READY
        assert all(s.status == StageStatus.APPROVED for s in stage_runs[:-1])

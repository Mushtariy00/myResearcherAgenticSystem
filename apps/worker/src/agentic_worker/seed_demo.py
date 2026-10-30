"""Demo data for building the front end: `make demo-seed` runs this after the demo users exist.

    uv run --package agentic-worker python -m agentic_worker.seed_demo

It replaces three demo projects (recognised by fixed ids, so running it again is safe) with:

- members in every project role, monthly budgets, and about 30 days of settled LLM calls,
  paid and free, for the spend charts;
- finished runs in every final state (completed, failed, cancelled, rejected) and one paused for
  budget, written directly with the stage runs, outputs, approvals and events the workflow
  writes (the stage outputs come from the same demo stage runner the worker uses);
- live runs: real RunWorkflow executions, started through Temporal and advanced with real
  decisions until each waits for review at its stage, plus one run in a 10-minute stage.

Live runs need the dev stack and a worker running this code (`make worker`). Each live run
makes one real LLM call, the literature plan, through the gateway.
"""

import os

# Same CrewAI opt-outs as the worker entry point, before anything imports crewai.
for _name, _value in {
    "CREWAI_DISABLE_TELEMETRY": "true",
    "CREWAI_TRACING_ENABLED": "false",
    "OTEL_SDK_DISABLED": "true",
}.items():
    os.environ.setdefault(_name, _value)

import asyncio  # noqa: E402
import copy  # noqa: E402
import logging  # noqa: E402
import random  # noqa: E402
import sys  # noqa: E402
import uuid  # noqa: E402
from collections.abc import Callable  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402
from decimal import Decimal  # noqa: E402
from typing import Any  # noqa: E402

from sqlalchemy import delete, insert, select, text  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: E402
from temporalio.api.enums.v1 import TaskQueueType  # noqa: E402
from temporalio.api.taskqueue.v1 import TaskQueue  # noqa: E402
from temporalio.api.workflowservice.v1 import DescribeTaskQueueRequest  # noqa: E402
from temporalio.client import Client, WorkflowUpdateFailedError  # noqa: E402
from temporalio.service import RPCError  # noqa: E402

from agentic_core import demo  # noqa: E402
from agentic_core.contracts import (  # noqa: E402
    DECIDE_UPDATE,
    RUN_WORKFLOW,
    TASK_QUEUE,
    DecisionInput,
    EventType,
    RunInput,
    workflow_id_for,
)
from agentic_core.enums import (  # noqa: E402
    Decision,
    LlmCallState,
    LlmPolicy,
    LlmTier,
    Privacy,
    ProjectRole,
    RunStatus,
    StageStatus,
)
from agentic_core.schemas import RunConfig, validate_stage_output  # noqa: E402
from agentic_core.stages import STAGE_ORDER, Stage  # noqa: E402
from agentic_db import append_event, create_engine, session_factory  # noqa: E402
from agentic_db.models import (  # noqa: E402
    Approval,
    Budget,
    LlmCall,
    Project,
    ProjectMember,
    Run,
    RunEvent,
    StageOutput,
    StageRun,
)
from agentic_worker import events  # noqa: E402
from agentic_worker.outputs import content_sha256, demo_seed  # noqa: E402
from agentic_worker.settings import WorkerSettings  # noqa: E402
from agentic_worker.stages import (  # noqa: E402
    PipelineStageRunner,
    PlannedSearch,
    StageContext,
)
from agentic_worker.workflows import AUTO_APPROVE_ACTOR  # noqa: E402

log = logging.getLogger(__name__)
Sessions = async_sessionmaker[AsyncSession]

SEED_KEY_PREFIX = "demo-seed:"  # idempotency keys of the seeded llm_calls rows
LONG_STAGE_SECONDS = 600  # the live run that shows a stage in progress
DECISION_TIMEOUT = timedelta(minutes=10)  # per live stage: the literature plan is a real call
_PROJECT_NAMESPACE = uuid.UUID("5d0f3c8e-2b7a-4a51-9c64-3e1f0b9a7d21")


class SeedError(Exception):
    """The seed cannot continue; the message says what to do."""


# --- who and where ------------------------------------------------------------------------------


@dataclass(frozen=True)
class DemoAccount:
    key: str
    email: str
    name: str


# Keep in sync with apps/web/scripts/seed-demo-users.ts, which creates these accounts (the
# first one as a lab admin).
DEMO_ACCOUNTS = (
    DemoAccount("admin", "demo-admin@lab.test", "Demo Admin"),
    DemoAccount("jiwoo", "jiwoo.park@lab.test", "Ji-woo Park"),
    DemoAccount("dilnoza", "dilnoza.karimova@lab.test", "Dilnoza Karimova"),
    DemoAccount("mateo", "mateo.silva@lab.test", "Mateo Silva"),
)

# Monthly paid budget and the share of it already spent this month (the spend history).
_BUDGETS = {
    "admin": (Decimal(50), 0.12),
    "jiwoo": (Decimal(25), 0.38),
    "dilnoza": (Decimal(10), 0.86),  # past the 80% alert
    "mateo": (Decimal(5), 1.06),  # over budget: later calls switched to free models
}


@dataclass(frozen=True)
class ProjectSpec:
    key: str
    name: str
    description: str
    members: dict[str, ProjectRole]  # account key -> role; exactly one owner
    privacy: Privacy = Privacy.STANDARD
    auto_approve: bool = False
    approval_expiry_days: int = 7

    @property
    def id(self) -> uuid.UUID:
        return demo_project_id(self.key)

    @property
    def owner(self) -> str:
        return next(key for key, role in self.members.items() if role is ProjectRole.OWNER)


def demo_project_id(key: str) -> uuid.UUID:
    """Fixed ids mark the demo projects, so a new seed finds and replaces the old ones."""
    return uuid.uuid5(_PROJECT_NAMESPACE, f"arp-demo-seed:{key}")


_DEMO_NOTE = " Demo data: make demo-seed replaces this project and its runs."
PROJECTS = (
    ProjectSpec(
        key="depth",
        name="Monocular Depth on NYU Depth V2",
        description="Compact depth networks that train on the lab's 6 GB GPU." + _DEMO_NOTE,
        members={
            "admin": ProjectRole.OWNER,
            "jiwoo": ProjectRole.RESEARCHER,
            "dilnoza": ProjectRole.RESEARCHER,
            "mateo": ProjectRole.VIEWER,
        },
    ),
    ProjectSpec(
        key="segmentation",
        name="Urban Scene Segmentation",
        description="Label-efficient segmentation for driving scenes (partner data)." + _DEMO_NOTE,
        members={
            "dilnoza": ProjectRole.OWNER,
            "mateo": ProjectRole.RESEARCHER,
            "jiwoo": ProjectRole.VIEWER,
        },
        privacy=Privacy.CONFIDENTIAL,
        approval_expiry_days=7,
    ),
    ProjectSpec(
        key="classification",
        name="Calibrated Image Classification",
        description="Small classifiers with honest confidence scores." + _DEMO_NOTE,
        members={
            "mateo": ProjectRole.OWNER,
            "jiwoo": ProjectRole.RESEARCHER,
            "admin": ProjectRole.RESEARCHER,
            "dilnoza": ProjectRole.VIEWER,
        },
        auto_approve=True,
        approval_expiry_days=3,
    ),
)
_PROJECTS_BY_KEY = {spec.key: spec for spec in PROJECTS}


def demo_project_ids() -> list[uuid.UUID]:
    return [spec.id for spec in PROJECTS]


# --- finished runs ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Step:
    """One stage attempt and what happened to its output."""

    stage: Stage
    decision: Decision | None = Decision.APPROVE  # None: the run ended while this waited
    reviewer: str = ""  # account key; empty for a project-level automatic approval
    comment: str = ""
    edit: Callable[[dict[str, Any]], dict[str, Any]] | None = None  # approve with edits
    in_progress: bool = False  # the run stopped while this stage was running

    @property
    def automatic(self) -> bool:
        return self.decision is Decision.APPROVE and not self.reviewer


@dataclass(frozen=True)
class FinishedRunSpec:
    project: str
    owner: str
    topic: str
    days_ago: float
    steps: tuple[Step, ...]
    status: RunStatus
    error: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    tier: LlmTier = LlmTier.PAID


def _focus_on_small_models(data: dict[str, Any]) -> dict[str, Any]:
    edited = copy.deepcopy(data)
    edited["implementation_focus"] = (
        "Start with the smallest variant (32 base channels) on NYU Depth V2 and add the "
        "gradient term only if object boundaries look blurry in the validation images."
    )
    return edited


def _approve(stage: Stage, reviewer: str, comment: str = "") -> Step:
    return Step(stage, Decision.APPROVE, reviewer, comment)


FINISHED_RUNS = (
    FinishedRunSpec(
        project="depth",
        owner="jiwoo",
        topic="Lightweight monocular depth estimation for indoor robots",
        days_ago=12.3,
        status=RunStatus.COMPLETED,
        steps=(
            Step(
                Stage.LITERATURE,
                Decision.REQUEST_CHANGES,
                "admin",
                "Drop the surveys and keep papers that report NYU Depth V2 numbers.",
            ),
            _approve(Stage.LITERATURE, "admin", "Much better, thanks."),
            Step(
                Stage.METHOD,
                Decision.APPROVE,
                "admin",
                "Approved with a narrower implementation focus.",
                edit=_focus_on_small_models,
            ),
            _approve(Stage.CODING, "jiwoo", "Tests look reasonable."),
            _approve(Stage.EXPERIMENT, "admin"),
            _approve(Stage.WRITING, "admin", "Good first draft for the lab meeting."),
        ),
    ),
    FinishedRunSpec(
        project="depth",
        owner="dilnoza",
        topic="Self-supervised depth from indoor video",
        days_ago=5.4,
        status=RunStatus.CANCELLED,
        steps=(
            _approve(Stage.LITERATURE, "dilnoza"),
            Step(Stage.METHOD, decision=None),  # cancelled while waiting for review
        ),
    ),
    FinishedRunSpec(
        project="segmentation",
        owner="dilnoza",
        topic="Semantic segmentation of urban scenes with limited labels",
        days_ago=20.1,
        status=RunStatus.COMPLETED,
        config={"stages": ["literature", "method"], "dataset": "cityscapes", "max_papers": 15},
        steps=(_approve(Stage.LITERATURE, "dilnoza"), _approve(Stage.METHOD, "dilnoza")),
    ),
    FinishedRunSpec(
        project="segmentation",
        owner="mateo",
        topic="Boundary-aware segmentation for driving scenes",
        days_ago=9.2,
        status=RunStatus.FAILED,
        error="stage.too_many_attempts",
        config={"dataset": "cityscapes"},
        tier=LlmTier.FREE,
        steps=(
            _approve(Stage.LITERATURE, "dilnoza"),
            _approve(Stage.METHOD, "dilnoza"),
            Step(
                Stage.CODING,
                Decision.REQUEST_CHANGES,
                "dilnoza",
                "Use GroupNorm: batch size 4 is too small for BatchNorm.",
            ),
            Step(
                Stage.CODING,
                Decision.REQUEST_CHANGES,
                "dilnoza",
                "The dry run is too slow; reduce the base channels.",
            ),
            Step(
                Stage.CODING,
                Decision.REQUEST_CHANGES,
                "dilnoza",
                "The tests still miss the ignore-index case.",
            ),
        ),
    ),
    FinishedRunSpec(
        project="segmentation",
        owner="dilnoza",
        topic="Open-vocabulary segmentation of aerial images",
        days_ago=15.7,
        status=RunStatus.REJECTED,
        config={"dataset": "ade20k"},
        steps=(
            Step(
                Stage.LITERATURE,
                Decision.REJECT,
                "dilnoza",
                "Off-topic for this project: we only work on street scenes.",
            ),
        ),
    ),
    FinishedRunSpec(
        project="segmentation",
        owner="mateo",
        topic="Night-time semantic segmentation with domain adaptation",
        days_ago=26.5,
        status=RunStatus.CANCELLED,
        error="approval.expired",
        config={"dataset": "cityscapes"},
        tier=LlmTier.FREE,
        steps=(
            _approve(Stage.LITERATURE, "dilnoza"),
            _approve(Stage.METHOD, "dilnoza"),
            _approve(Stage.CODING, "dilnoza"),
            Step(Stage.EXPERIMENT, decision=None),  # nobody answered within 7 days
        ),
    ),
    FinishedRunSpec(
        project="classification",
        owner="jiwoo",
        topic="Calibrated long-tailed image classification",
        days_ago=3.1,
        status=RunStatus.COMPLETED,
        config={"dataset": "cifar100", "max_papers": 12},
        steps=(
            Step(Stage.LITERATURE),
            Step(Stage.METHOD),
            _approve(Stage.CODING, "mateo", "Coding is always reviewed by a person."),
            Step(Stage.EXPERIMENT),
            Step(Stage.WRITING),
        ),
    ),
    FinishedRunSpec(
        project="classification",
        owner="mateo",
        topic="Knowledge distillation for small CNN classifiers",
        days_ago=0.8,
        status=RunStatus.PAUSED_BUDGET,
        error="lab_balance.exhausted",
        config={"dataset": "cifar100"},
        steps=(Step(Stage.LITERATURE), Step(Stage.METHOD, decision=None, in_progress=True)),
    ),
)


# --- live runs ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class LiveRunSpec:
    project: str
    owner: str
    topic: str
    wait_at: Stage  # the stage whose output waits for review
    reviewer: str  # who approves the stages before it
    config: dict[str, Any] = field(default_factory=dict)
    advance: bool = True  # False: leave it running (the long stage)


LIVE_RUNS = (
    LiveRunSpec(
        "depth",
        "jiwoo",
        "Transformers for monocular depth estimation on NYU Depth V2",
        Stage.LITERATURE,
        "admin",
        {"max_papers": 20, "year_from": 2021},
    ),
    LiveRunSpec(
        "depth",
        "dilnoza",
        "Uncertainty-aware monocular depth estimation",
        Stage.METHOD,
        "admin",
        {"max_papers": 12, "sources": ["arxiv", "semantic_scholar"]},
    ),
    LiveRunSpec(
        "classification",
        "mateo",
        "Label smoothing and calibration for compact image classifiers",
        Stage.CODING,
        "mateo",  # the project approves literature and method by itself
        {"dataset": "cifar100", "max_papers": 10},
    ),
    LiveRunSpec(
        "depth",
        "admin",
        "Edge-preserving depth networks for embedded GPUs",
        Stage.EXPERIMENT,
        "admin",
        {"max_papers": 15},
    ),
    LiveRunSpec(
        "depth",
        "jiwoo",
        "Distilling depth foundation models into small students",
        Stage.WRITING,
        "admin",
        {"max_papers": 16, "sources": ["arxiv", "openalex", "crossref"]},
    ),
    LiveRunSpec(
        "depth",
        "admin",
        "Metric depth from a single image without per-dataset fine-tuning",
        Stage.LITERATURE,
        "admin",
        {"max_papers": 25, "demo_stage_seconds": LONG_STAGE_SECONDS},
        advance=False,
    ),
)


# --- users --------------------------------------------------------------------------------------

_USERS_BY_EMAIL = text(
    'SELECT id, lower(email) AS email FROM auth."user" WHERE lower(email) = ANY(:emails)'
)


async def load_demo_users(session: AsyncSession) -> dict[str, str]:
    """Account key -> Better Auth user id for the demo accounts (all must exist)."""
    emails = [account.email for account in DEMO_ACCOUNTS]
    rows = (await session.execute(_USERS_BY_EMAIL, {"emails": emails})).all()
    ids = {email: user_id for user_id, email in rows}
    missing = [account.email for account in DEMO_ACCOUNTS if account.email not in ids]
    if missing:
        raise SeedError(
            f"demo users missing: {', '.join(missing)}. Create them first with "
            "`pnpm --filter @agentic/web exec node scripts/seed-demo-users.ts` "
            "(make demo-seed runs it)."
        )
    return {account.key: str(ids[account.email]) for account in DEMO_ACCOUNTS}


# --- replace ------------------------------------------------------------------------------------


async def remove_previous(sessions: Sessions, client: Client | None) -> int:
    """Delete the demo projects (their runs and events cascade) and the seeded LLM calls.

    Workflows of unfinished demo runs are terminated first, so none of them writes into rows
    that are being deleted. Real LLM calls of earlier live runs stay: they were real spend.
    """
    ids = demo_project_ids()
    async with sessions() as session:
        runs = (
            await session.execute(
                select(Run.workflow_id, Run.status).where(Run.project_id.in_(ids))
            )
        ).all()
    if client is not None:
        for workflow_id, status in runs:
            if workflow_id and not RunStatus(status).is_terminal:
                try:
                    await client.get_workflow_handle(workflow_id).terminate(
                        reason="replaced by make demo-seed"
                    )
                except RPCError:  # already closed, or it never started
                    log.info("workflow %s was not running", workflow_id)
    async with sessions() as session:
        await session.execute(delete(Project).where(Project.id.in_(ids)))
        await session.execute(
            delete(LlmCall).where(LlmCall.idempotency_key.startswith(SEED_KEY_PREFIX))
        )
        await session.commit()
    return len(runs)


# --- projects, budgets, spend history -----------------------------------------------------------


async def write_projects(session: AsyncSession, users: dict[str, str], now: datetime) -> None:
    for index, spec in enumerate(PROJECTS):
        session.add(
            Project(
                id=spec.id,
                name=spec.name,
                description=spec.description,
                privacy=spec.privacy,
                allow_free_models=True,
                auto_approve=spec.auto_approve,
                approval_expiry_days=spec.approval_expiry_days,
                created_by=users[spec.owner],
                created_at=now - timedelta(days=40 - index * 3),
            )
        )
    await session.flush()
    for spec in PROJECTS:
        for key, role in spec.members.items():
            session.add(ProjectMember(project_id=spec.id, user_id=users[key], role=role))


async def write_budgets(session: AsyncSession, users: dict[str, str]) -> None:
    for key, (monthly, _) in _BUDGETS.items():
        statement = pg_insert(Budget).values(
            user_id=users[key], monthly_usd=monthly, updated_by=users["admin"]
        )
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[Budget.user_id],
                set_={"monthly_usd": monthly, "updated_by": users["admin"]},
            )
        )


# (model, USD per million input tokens, USD per million output tokens)
_PAID_MODELS = (
    ("google/gemini-2.5-flash", Decimal("0.30"), Decimal("2.50")),
    ("openai/gpt-4.1-mini", Decimal("0.40"), Decimal("1.60")),
)
_WRITING_MODEL = ("anthropic/claude-sonnet-4.5", Decimal("3.00"), Decimal("15.00"))
_FREE_MODELS = ("google/gemma-4-31b-it:free", "nvidia/nemotron-3-ultra-550b-a55b:free")
_ROLES = (
    ("researcher", 0.32),
    ("method_analyst", 0.18),
    ("coding_architect", 0.2),
    ("experiment_designer", 0.1),
    ("writing_strategist", 0.2),
)


def _office_time(rng: random.Random, day: datetime) -> datetime:
    """A moment in Korean office hours (09:00-19:00 KST is 00:00-10:00 UTC)."""
    return day.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
        seconds=rng.uniform(0, 10 * 3600)
    )


def spend_history(users: dict[str, str], now: datetime, rng: random.Random) -> list[dict[str, Any]]:
    """About 30 days of settled calls per user, paid while the month's target allows.

    Token counts are scaled per user so the paid spend this month reaches the user's target
    share of their budget; costs always equal tokens times the model's price.
    """
    rows: list[dict[str, Any]] = []
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    for key, (budget, share) in _BUDGETS.items():
        planned = _planned_calls(rng, now)
        natural_cost = sum(
            _price(model, prompt, completion)
            for when, _, model, prompt, completion in planned
            if model and when >= month_start
        )
        target = budget * Decimal(str(share))
        # Bounded, so token counts stay plausible early in a month (when little history counts).
        scale = min(6.0, max(0.25, float(target / natural_cost))) if natural_cost else 1.0
        spent = Decimal(0)
        for index, (when, role, model, prompt, completion) in enumerate(planned):
            prompt, completion = round(prompt * scale), round(completion * scale)
            cost = _price(model, prompt, completion) if model else Decimal(0)
            # Over the month's target: the gateway switches the user to free models.
            if model and when >= month_start and spent + cost > target * Decimal("1.0001"):
                model, cost = None, Decimal(0)
            if model and when >= month_start:
                spent += cost
            free_model = _FREE_MODELS[index % len(_FREE_MODELS)]
            latency = rng.randint(1_200, 14_000)
            rows.append(
                {
                    "idempotency_key": f"{SEED_KEY_PREFIX}{key}:{index}",
                    "user_id": users[key],
                    "role": role,
                    "tier": LlmTier.PAID if model else LlmTier.FREE,
                    "model": model or free_model,
                    "state": LlmCallState.SETTLED,
                    "reserved_usd": (cost * Decimal("1.8")).quantize(Decimal("0.000001")),
                    "cost_usd": cost,
                    "generation_id": f"gen-demo-{uuid.uuid4().hex}",
                    "prompt_tokens": prompt,
                    "completion_tokens": completion,
                    "latency_ms": latency,
                    "created_at": when,
                    "updated_at": when + timedelta(milliseconds=latency),
                }
            )
    return rows


def _price(model: str | None, prompt: int, completion: int) -> Decimal:
    prices = {name: (inp, out) for name, inp, out in (*_PAID_MODELS, _WRITING_MODEL)}
    if model is None:
        return Decimal(0)
    per_input, per_output = prices[model]
    cost = (per_input * prompt + per_output * completion) / Decimal(1_000_000)
    return cost.quantize(Decimal("0.000001"))


def _planned_calls(
    rng: random.Random, now: datetime
) -> list[tuple[datetime, str, str | None, int, int]]:
    """(time, role, paid model or None for free, prompt tokens, completion tokens)."""
    calls = []
    for days_back in range(30, 0, -1):
        day = now - timedelta(days=days_back)
        count = rng.randint(14, 34) if day.weekday() < 5 else rng.randint(0, 4)
        for _ in range(count):
            role = rng.choices([r for r, _ in _ROLES], weights=[w for _, w in _ROLES])[0]
            if rng.random() < 0.25:
                model = None
            elif role == "writing_strategist":
                model = _WRITING_MODEL[0]
            else:
                model = rng.choice(_PAID_MODELS)[0]
            prompt = rng.randint(2_000, 16_000) if role != "researcher" else rng.randint(800, 4_000)
            calls.append((_office_time(rng, day), role, model, prompt, rng.randint(250, 2_400)))
    return sorted(calls)


# --- finished runs ------------------------------------------------------------------------------


@dataclass
class _Recorder:
    """Collects the progress lines a stage reports, to write them as log events."""

    lines: list[tuple[str, dict[str, Any], str]] = field(default_factory=list)

    async def __call__(self, code: str, params: dict[str, Any], message: str) -> None:
        self.lines.append((code, params, message))


@dataclass
class _SeedPlanner:
    """The literature plan without an LLM; reports the call a real plan would have made."""

    model: str
    tier: LlmTier
    cost: Decimal

    async def plan(self, ctx: StageContext) -> PlannedSearch:
        plan = demo.research_plan(
            ctx.topic,
            demo_seed(ctx.run_id, "plan", ctx.attempt),
            config=ctx.config,
            feedback=ctx.feedback,
        )
        call = {
            "model": self.model,
            "tier": self.tier.value,
            "cost_usd": str(self.cost),
            "switched_to_free": False,
            "replayed": False,
        }
        return PlannedSearch(plan=plan, model=self.model, llm_calls=[call])


class _RunHistory:
    """Writes one finished run the way the workflow would have: rows plus a gap-free event log
    with timestamps that advance like a real run (stage work, then reviewer think time)."""

    def __init__(self, session: AsyncSession, run: Run, started: datetime) -> None:
        self.session = session
        self.run = run
        self.clock = started
        self.seq = 0

    def advance(self, seconds: float) -> datetime:
        self.clock += timedelta(seconds=seconds)
        return self.clock

    def event(self, event: events.Event, *, after: float = 0.3) -> None:
        event_type, payload = event
        self.seq += 1
        self.session.add(
            RunEvent(
                run_id=self.run.id,
                seq=self.seq,
                type=event_type.value,
                payload=payload,
                created_at=self.advance(after),
            )
        )


_STAGE_SECONDS = {
    Stage.LITERATURE: 48.0,  # the plan call plus the simulated search
    Stage.METHOD: 6.0,
    Stage.CODING: 6.0,
    Stage.EXPERIMENT: 6.0,  # replaced by the training time in the provenance
    Stage.WRITING: 6.0,
}


async def write_finished_run(
    session: AsyncSession,
    spec: FinishedRunSpec,
    users: dict[str, str],
    now: datetime,
    rng: random.Random,
) -> Run:
    project = _PROJECTS_BY_KEY[spec.project]
    started = _office_time(rng, now - timedelta(days=spec.days_ago))
    run = Run(
        id=uuid.uuid4(),
        project_id=project.id,
        owner_id=users[spec.owner],
        topic=spec.topic,
        config=spec.config,
        status=spec.status,
        llm_policy=LlmPolicy.FREE if spec.tier is LlmTier.FREE else LlmPolicy.AUTO,
        error=spec.error,
        created_at=started,
    )
    # Only runs that really ran a workflow carry its id; a retry starts a new one either way.
    if spec.status is not RunStatus.PAUSED_BUDGET:
        run.workflow_id = workflow_id_for(str(run.id))
    session.add(run)
    await session.flush()
    history = _RunHistory(session, run, started)
    history.event((EventType.RUN_CREATED, {"topic": spec.topic, "owner_id": run.owner_id}))
    model = "google/gemini-2.5-flash" if spec.tier is LlmTier.PAID else _FREE_MODELS[0]
    cost = Decimal("0.001184") if spec.tier is LlmTier.PAID else Decimal(0)
    runner = PipelineStageRunner(
        _SeedPlanner(model, spec.tier, cost),
        demo_stage_seconds=0,
        # Experiments end about 40 minutes after they start (the provenance holds the details).
        clock=lambda: history.clock + timedelta(minutes=40),
    )
    config = RunConfig.model_validate(spec.config)
    approved: dict[str, dict[str, Any]] = {}
    attempts: dict[Stage, int] = {}
    feedback = ""
    open_stage: StageRun | None = None
    for step in spec.steps:
        attempt = attempts.get(step.stage, 0) + 1
        attempts[step.stage] = attempt
        stage_run = StageRun(
            run_id=run.id,
            stage=step.stage.value,
            attempt=attempt,
            status=StageStatus.RUNNING,
            feedback=feedback or None,
            started_at=history.advance(2),
        )
        session.add(stage_run)
        await session.flush()
        history.event(events.stage_started(step.stage.value, attempt))
        history.event(events.run_status(RunStatus.RUNNING))
        open_stage = stage_run
        if step.in_progress:
            break
        recorder = _Recorder()
        ctx = StageContext(
            run_id=str(run.id),
            stage_run_id=str(stage_run.id),
            stage=step.stage.value,
            attempt=attempt,
            feedback=feedback,
            topic=spec.topic,
            owner_id=run.owner_id,
            project_id=str(project.id),
            llm_policy=run.llm_policy.value,
            budget_cap_usd=None,
            config=config,
            inputs=dict(approved),
            log=recorder,
        )
        outcome = await runner.run(ctx)
        seconds = _STAGE_SECONDS[step.stage]
        if step.stage is Stage.EXPERIMENT:
            finished = datetime.fromisoformat(outcome.data["provenance"]["finished_at"])
            seconds = max(seconds, (finished - history.clock).total_seconds())
        for code, params, message in recorder.lines:
            history.event(
                events.log(step.stage.value, code, params, message),
                after=seconds / len(recorder.lines),
            )
        for index, call in enumerate(outcome.llm_calls, 1):
            session.add(_llm_call_row(run, stage_run, index, call, history.clock))
            history.event(events.llm_call(step.stage.value, call))
        output = StageOutput(
            stage_run_id=stage_run.id,
            data=outcome.data,
            sha256=content_sha256(outcome.data),
            model=outcome.model,
            degraded=outcome.degraded,
            degraded_reason=outcome.degraded_reason,
            prompt_version=outcome.prompt_version,
            created_at=history.advance(0.2),
        )
        session.add(output)
        await session.flush()
        stage_run.status = StageStatus.OUTPUT_READY
        history.event(
            events.stage_output_ready(step.stage.value, attempt, str(output.id), output.degraded)
        )
        if not step.automatic:
            history.event(events.run_status(RunStatus.AWAITING_APPROVAL))
        if step.decision is None:
            break
        decided = await _decide(session, history, stage_run, output, step, users, rng)
        open_stage = None
        if step.decision is Decision.APPROVE:
            approved[step.stage.value] = decided.data
            feedback = ""
        elif step.decision is Decision.REQUEST_CHANGES:
            feedback = step.comment
        else:
            break
    _finish(history, spec, open_stage, rng)
    run.last_event_seq = history.seq
    run.updated_at = history.clock
    return run


def _llm_call_row(
    run: Run, stage_run: StageRun, index: int, call: dict[str, Any], when: datetime
) -> LlmCall:
    cost = Decimal(str(call["cost_usd"]))
    return LlmCall(
        idempotency_key=f"{SEED_KEY_PREFIX}run:{stage_run.id}:call-{index}",
        run_id=run.id,
        user_id=run.owner_id,
        role="researcher",
        tier=LlmTier(call["tier"]),
        model=str(call["model"]),
        state=LlmCallState.SETTLED,
        reserved_usd=(cost * 2).quantize(Decimal("0.000001")),
        cost_usd=cost,
        generation_id=f"gen-demo-{uuid.uuid4().hex}",
        prompt_tokens=1_210,
        completion_tokens=402,
        latency_ms=6_850,
        created_at=when - timedelta(seconds=40),
        updated_at=when - timedelta(seconds=33),
    )


async def _decide(
    session: AsyncSession,
    history: _RunHistory,
    stage_run: StageRun,
    output: StageOutput,
    step: Step,
    users: dict[str, str],
    rng: random.Random,
) -> StageOutput:
    """Record the step's decision like record_decision does; returns the decided version."""
    # Reviewers answer minutes to hours later; the project approves at once.
    history.advance(0.2 if step.automatic else rng.uniform(4 * 60, 3 * 3600))
    actor = AUTO_APPROVE_ACTOR if step.automatic else users[step.reviewer]
    decided = output
    if step.edit is not None:
        # Stored like record_decision stores an edit: validated and normalized.
        edited = validate_stage_output(stage_run.stage, step.edit(output.data))
        data = edited.model_dump(mode="json")
        decided = StageOutput(
            stage_run_id=stage_run.id,
            version=output.version + 1,
            data=data,
            sha256=content_sha256(data),
            schema_version=output.schema_version,
            prompt_version=output.prompt_version,
            model=output.model,
            degraded=False,
            degraded_reason=None,
            edited_by=actor,
            created_at=history.clock,
        )
        session.add(decided)
        await session.flush()
    decision = step.decision or Decision.APPROVE
    session.add(
        Approval(
            stage_output_id=decided.id,
            sha256=decided.sha256,
            decision=decision,
            comment=step.comment,
            actor_id=actor,
            created_at=history.clock,
        )
    )
    stage_run.status = {
        Decision.APPROVE: StageStatus.APPROVED,
        Decision.REQUEST_CHANGES: StageStatus.CHANGES_REQUESTED,
        Decision.REJECT: StageStatus.REJECTED,
    }[decision]
    stage_run.finished_at = history.clock
    history.event(
        events.stage_decided(
            stage=stage_run.stage,
            decision=decision.value,
            actor_id=actor,
            comment=step.comment,
            attempt=stage_run.attempt,
            stage_output_id=str(decided.id),
            version=decided.version,
            edited=decided is not output,
            automatic=step.automatic,
        ),
        after=0,
    )
    return decided


def _finish(
    history: _RunHistory, spec: FinishedRunSpec, open_stage: StageRun | None, rng: random.Random
) -> None:
    """The final status change, like finish_run (cancelled runs wait before it happens)."""
    if spec.error == "approval.expired":
        history.advance(spec_expiry_seconds(spec))
    elif spec.status is RunStatus.CANCELLED:
        history.advance(rng.uniform(600, 7200))
    elif spec.status is RunStatus.PAUSED_BUDGET:
        history.advance(rng.uniform(20, 90))
    if open_stage is not None and spec.status in (RunStatus.CANCELLED, RunStatus.FAILED):
        open_stage.status = (
            StageStatus.CANCELLED if spec.status is RunStatus.CANCELLED else StageStatus.FAILED
        )
        open_stage.error = spec.error
        open_stage.finished_at = history.advance(0.1)
        if spec.status is RunStatus.FAILED:
            history.event(events.stage_failed(open_stage.stage, open_stage.attempt, spec.error))
    history.event(events.run_finished(spec.status, spec.error))


def spec_expiry_seconds(spec: FinishedRunSpec) -> float:
    return _PROJECTS_BY_KEY[spec.project].approval_expiry_days * 86_400.0


# --- live runs ----------------------------------------------------------------------------------


async def start_live_runs(
    sessions: Sessions,
    client: Client,
    users: dict[str, str],
    specs: tuple[LiveRunSpec, ...] = LIVE_RUNS,
) -> list[tuple[LiveRunSpec, str]]:
    """Create the live runs like the API does, and start a RunWorkflow execution for each."""
    started = []
    for spec in specs:
        async with sessions() as session:
            run = Run(
                project_id=_PROJECTS_BY_KEY[spec.project].id,
                owner_id=users[spec.owner],
                topic=spec.topic,
                config=spec.config,
            )
            session.add(run)
            await session.flush()
            await append_event(
                session,
                run.id,
                EventType.RUN_CREATED,
                {"topic": spec.topic, "owner_id": run.owner_id},
            )
            await session.commit()
            run_id = str(run.id)
            await client.start_workflow(
                RUN_WORKFLOW,
                RunInput(run_id=run_id),
                id=workflow_id_for(run_id),
                task_queue=TASK_QUEUE,
            )
            run.workflow_id = workflow_id_for(run_id)
            await session.commit()
        started.append((spec, run_id))
    return started


async def advance_live_run(
    sessions: Sessions,
    client: Client,
    users: dict[str, str],
    spec: LiveRunSpec,
    run_id: str,
    *,
    patience: timedelta = DECISION_TIMEOUT,
) -> None:
    """Approve each stage before ``spec.wait_at`` once its output is ready (projects with
    auto-approve skip that), then wait until the ``wait_at`` output waits for review."""
    handle = client.get_workflow_handle(workflow_id_for(run_id))
    for stage in STAGE_ORDER[: STAGE_ORDER.index(spec.wait_at)]:
        output = await _wait_for_review(sessions, run_id, stage, patience)
        if output is None:
            continue  # approved automatically
        decision = DecisionInput(
            stage=stage.value,
            stage_output_id=str(output.id),
            sha256=output.sha256,
            decision=Decision.APPROVE.value,
            actor_id=users[spec.reviewer],
            comment="Looks good, continue.",
        )
        await _send_decision(sessions, run_id, handle, decision)
    if await _wait_for_review(sessions, run_id, spec.wait_at, patience) is None:
        raise SeedError(f"run {run_id}: {spec.wait_at} was approved before anyone reviewed it")


async def _latest_stage_run(session: AsyncSession, run_id: str, stage: str) -> StageRun | None:
    return await session.scalar(
        select(StageRun)
        .where(StageRun.run_id == uuid.UUID(run_id), StageRun.stage == stage)
        .order_by(StageRun.attempt.desc())
        .limit(1)
    )


async def _wait_for_review(
    sessions: Sessions, run_id: str, stage: Stage, patience: timedelta
) -> StageOutput | None:
    """The output of ``stage`` once it waits for review, or None once it is approved."""
    deadline = asyncio.get_running_loop().time() + patience.total_seconds()
    while asyncio.get_running_loop().time() < deadline:
        async with sessions() as session:
            run = await session.get(Run, uuid.UUID(run_id))
            if run is not None and run.status.is_terminal:
                raise SeedError(f"run {run_id} ended as {run.status.value} ({run.error})")
            stage_run = await _latest_stage_run(session, run_id, stage.value)
            if stage_run is not None and stage_run.status is StageStatus.APPROVED:
                return None
            if stage_run is not None and stage_run.status is StageStatus.OUTPUT_READY:
                output = await session.scalar(
                    select(StageOutput)
                    .where(StageOutput.stage_run_id == stage_run.id)
                    .order_by(StageOutput.version.desc())
                    .limit(1)
                )
                if output is not None:
                    return output
        await asyncio.sleep(0.5)
    raise SeedError(f"run {run_id}: {stage.value} produced no output in time")


async def _send_decision(
    sessions: Sessions, run_id: str, handle: Any, decision: DecisionInput
) -> None:
    """Send an approval the way the API does.

    The output is committed a moment before the workflow waits for a decision on it, and the
    workflow refuses decisions in that gap (decision.not_awaited), so this tries again. With
    auto-approve the project may approve the output itself meanwhile; that is fine too.
    """
    for _ in range(60):
        try:
            await handle.execute_update(DECIDE_UPDATE, decision, rpc_timeout=timedelta(seconds=30))
            return
        except WorkflowUpdateFailedError as exc:
            async with sessions() as session:
                stage_run = await _latest_stage_run(session, run_id, decision.stage)
            if stage_run is not None and stage_run.status is StageStatus.APPROVED:
                return
            if "decision.not_awaited" not in str(exc.cause):
                raise SeedError(f"run {run_id}: the workflow refused {decision.stage}") from exc
        await asyncio.sleep(0.5)
    raise SeedError(f"run {run_id}: the workflow never accepted a decision on {decision.stage}")


# --- the whole seed -----------------------------------------------------------------------------


@dataclass
class SeedSummary:
    removed_runs: int = 0
    finished_runs: int = 0
    llm_calls: int = 0
    live_runs: list[tuple[LiveRunSpec, str]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


async def seed_static(
    sessions: Sessions, users: dict[str, str], now: datetime, rng: random.Random
) -> SeedSummary:
    """Projects, members, budgets, spend history and finished runs, in one transaction."""
    summary = SeedSummary()
    async with sessions() as session:
        await write_projects(session, users, now)
        await write_budgets(session, users)
        history = spend_history(users, now, rng)
        if history:
            await session.execute(insert(LlmCall), history)
        summary.llm_calls = len(history)
        for spec in FINISHED_RUNS:
            await write_finished_run(session, spec, users, now, rng)
        summary.finished_runs = len(FINISHED_RUNS)
        await session.commit()
    return summary


async def seed(
    sessions: Sessions, client: Client, users: dict[str, str], now: datetime
) -> SeedSummary:
    rng = random.Random(20261030)  # noqa: S311 - reproducible demo data, not secrets
    removed = await remove_previous(sessions, client)
    summary = await seed_static(sessions, users, now, rng)
    summary.removed_runs = removed
    summary.live_runs = await start_live_runs(sessions, client, users)
    results = await asyncio.gather(
        *(
            advance_live_run(sessions, client, users, spec, run_id)
            for spec, run_id in summary.live_runs
            if spec.advance
        ),
        return_exceptions=True,
    )
    summary.problems = [str(result) for result in results if isinstance(result, BaseException)]
    return summary


async def require_worker(client: Client) -> None:
    """Fail fast when no worker polls the task queue (live runs would never move)."""
    response = await client.workflow_service.describe_task_queue(
        DescribeTaskQueueRequest(
            namespace=client.namespace,
            task_queue=TaskQueue(name=TASK_QUEUE),
            task_queue_type=TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW,
        )
    )
    if not response.pollers:
        raise SeedError(f"no worker polls the {TASK_QUEUE} task queue; start one: make worker")


async def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    settings = WorkerSettings()
    if not settings.database_url:
        print("demo-seed: ARP_DATABASE_URL is not set (see .env)", file=sys.stderr)
        return 1
    engine = create_engine(settings.database_url)
    try:
        sessions = session_factory(engine)
        async with sessions() as session:
            users = await load_demo_users(session)
        try:
            client = await Client.connect(settings.temporal_address)
            await require_worker(client)
        except (RPCError, RuntimeError) as exc:  # the SDK reports a failed connect as RuntimeError
            raise SeedError(
                f"Temporal at {settings.temporal_address} is not reachable ({exc}); run make up"
            ) from exc
        summary = await seed(sessions, client, users, datetime.now(UTC))
    except SeedError as exc:
        print(f"demo-seed: {exc}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()
    print(
        f"demo-seed: replaced {len(PROJECTS)} demo projects ({summary.removed_runs} old runs), "
        f"wrote {summary.finished_runs} finished runs and {summary.llm_calls} LLM calls."
    )
    for spec, run_id in summary.live_runs:
        state = f"waiting for review at {spec.wait_at}" if spec.advance else "in a long stage"
        print(f"  live run {run_id}: {state} ({spec.topic})")
    for problem in summary.problems:
        print(f"  problem: {problem}", file=sys.stderr)
    print("Sign in as demo-admin@lab.test; the password is in .data/demo-users.env.")
    return 1 if summary.problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

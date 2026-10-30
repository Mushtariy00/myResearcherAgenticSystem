"""Test doubles for the API (auth from a cookie, a recording orchestrator, a quiet Valkey) and
helpers that build projects, runs and stage outputs the way the worker would."""

import asyncio
import hashlib
import json
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_api.auth import CurrentUser
from agentic_api.orchestrator import (
    DecisionRejectedError,
    OrchestratorUnavailableError,
    TaskQueuePollers,
    WorkflowNotFoundError,
    WorkflowStillRunningError,
)
from agentic_core.contracts import DecisionInput
from agentic_core.enums import RunStatus, StageStatus
from agentic_db.models import Run, StageOutput, StageRun

ORIGIN = "http://localhost:8080"
Factory = async_sessionmaker[AsyncSession]


def as_user(user_id: str, role: str = "user") -> dict[str, str]:
    return {"cookie": f"test-user={user_id}:{role}"}


ADMIN = as_user("root", "admin")


@dataclass
class FakeVerifier:
    """Reads `test-user=<id>:<role>` cookies instead of asking Better Auth."""

    signed_out: set[str] = field(default_factory=set)  # users whose sessions were revoked
    calls: int = 0

    async def verify(self, cookie_header: str) -> CurrentUser | None:
        self.calls += 1
        cookie = SimpleCookie(cookie_header).get("test-user")
        if cookie is None:
            return None
        user_id, role = cookie.value.split(":")
        if user_id in self.signed_out:
            return None
        return CurrentUser(id=user_id, email=f"{user_id}@lab.test", name=user_id, role=role)


@dataclass
class FakeOrchestrator:
    """Records what the API asks Temporal for. A run has a workflow once it was started here."""

    started: list[uuid.UUID] = field(default_factory=list)
    restarted: list[tuple[uuid.UUID, str]] = field(default_factory=list)
    decisions: list[tuple[uuid.UUID, DecisionInput]] = field(default_factory=list)
    decide_calls: int = 0
    cancelled: list[uuid.UUID] = field(default_factory=list)
    fail_start: bool = False  # Temporal unreachable: starts, restarts and cancels fail
    start_delay: float = 0.0  # seconds each start takes
    still_running: bool = False  # restarts find the previous execution still open
    reject_decisions: bool = False  # the validator refuses every decision as stale
    refusals: list[str] = field(default_factory=list)  # validator codes for the next decisions
    decide_error: Exception | None = None  # raised by every decision (after before_decide)
    before_decide: Callable[[uuid.UUID], Awaitable[None]] | None = None
    before_cancel: Callable[[uuid.UUID], Awaitable[None]] | None = None
    namespace_ok: bool = True
    pollers: TaskQueuePollers | None = field(
        default_factory=lambda: TaskQueuePollers(workflow=1, activity=1)
    )

    async def start_run(self, run_id: uuid.UUID) -> str:
        await asyncio.sleep(self.start_delay)
        if self.fail_start:
            raise OrchestratorUnavailableError("temporal down")
        self.started.append(run_id)
        return f"run-{run_id}"

    async def restart_run(self, run_id: uuid.UUID, start_stage: str) -> str:
        if self.fail_start:
            raise OrchestratorUnavailableError("temporal down")
        if self.still_running:
            raise WorkflowStillRunningError(f"run-{run_id}")
        self.restarted.append((run_id, start_stage))
        return f"run-{run_id}"

    async def decide(self, run_id: uuid.UUID, decision: DecisionInput) -> None:
        self.decide_calls += 1
        if self.before_decide is not None:
            await self.before_decide(run_id)
        if self.decide_error is not None:
            raise self.decide_error
        if self.reject_decisions:
            raise DecisionRejectedError("decision.stale")
        if self.refusals:
            raise DecisionRejectedError(self.refusals.pop(0))
        self.decisions.append((run_id, decision))

    async def cancel_run(self, run_id: uuid.UUID) -> None:
        if self.before_cancel is not None:
            await self.before_cancel(run_id)
        if self.fail_start:
            raise OrchestratorUnavailableError("temporal down")
        if run_id not in self.started and run_id not in {r for r, _ in self.restarted}:
            raise WorkflowNotFoundError(f"run-{run_id}")
        self.cancelled.append(run_id)

    async def check_namespace(self) -> None:
        if not self.namespace_ok:
            raise RuntimeError("temporal down")

    async def task_queue_pollers(self) -> TaskQueuePollers | None:
        if not self.namespace_ok:
            raise RuntimeError("temporal down")
        return self.pollers


@dataclass
class FakePubSub:
    """A quiet channel. ``on_wait`` runs each time a stream waits for a wake-up."""

    on_wait: Callable[[], Awaitable[None]] | None = None
    channels: list[str] = field(default_factory=list)
    closed: bool = False

    async def subscribe(self, *channels: str) -> None:
        self.channels.extend(channels)

    async def get_message(self, ignore_subscribe_messages: bool, timeout: float) -> None:  # noqa: ASYNC109 (mirrors redis)
        if self.on_wait is not None:
            await self.on_wait()
        await asyncio.sleep(0.01)

    async def aclose(self) -> None:
        self.closed = True


@dataclass
class FakeValkey:
    down: bool = False
    ping_delay: float = 0.0
    on_wait: Callable[[], Awaitable[None]] | None = None  # for every stream's FakePubSub
    pubsubs: list[FakePubSub] = field(default_factory=list)

    def pubsub(self) -> FakePubSub:
        self.pubsubs.append(FakePubSub(on_wait=self.on_wait))
        return self.pubsubs[-1]

    async def ping(self) -> bool:
        await asyncio.sleep(self.ping_delay)
        if self.down:
            raise ConnectionError("valkey down")
        return True


# --- Building data -------------------------------------------------------------------------


async def create_project(client: httpx.AsyncClient, name: str, owner: str = "alice") -> str:
    """A project that ``owner`` owns alone. Lab admins create projects; the admin hands this
    one over to ``owner`` and steps down."""
    response = await client.post("/api/v1/projects", json={"name": name}, headers=ADMIN)
    assert response.status_code == 201, response.text
    project_id = response.json()["id"]
    if owner != "root":
        members = f"/api/v1/projects/{project_id}/members"
        added = await client.post(
            members, json={"email": f"{owner}@lab.test", "role": "owner"}, headers=ADMIN
        )
        assert added.status_code == 201, added.text
        removed = await client.delete(f"{members}/root", headers=ADMIN)
        assert removed.status_code == 204, removed.text
    return project_id


async def team_project(client: httpx.AsyncClient, name: str = "Depth") -> str:
    """alice owns it; bob is a researcher; vera is a viewer."""
    project_id = await create_project(client, name)
    for email, role in (("bob@lab.test", "researcher"), ("vera@lab.test", "viewer")):
        response = await client.post(
            f"/api/v1/projects/{project_id}/members",
            json={"email": email, "role": role},
            headers=as_user("alice"),
        )
        assert response.status_code == 201, response.text
    return project_id


async def start_run(
    client: httpx.AsyncClient, project_id: str, user: str = "bob", **body: Any
) -> str:
    response = await client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={"topic": "Monocular depth", **body},
        headers=as_user(user),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def content_sha256(data: dict[str, Any]) -> str:
    """The worker's content hash (agentic_worker.activities.content_sha256)."""
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


async def set_run_status(
    db: Factory, run_id: str, status: RunStatus, error: str | None = None
) -> None:
    async with db() as session:
        run = await session.get(Run, uuid.UUID(run_id))
        assert run is not None
        run.status, run.error = status, error
        await session.commit()


async def add_stage_run(
    db: Factory,
    run_id: str,
    stage: str = "literature",
    status: StageStatus = StageStatus.OUTPUT_READY,
    attempt: int = 1,
    **fields: Any,
) -> str:
    async with db() as session:
        stage_run = StageRun(
            run_id=uuid.UUID(run_id), stage=stage, attempt=attempt, status=status, **fields
        )
        session.add(stage_run)
        await session.commit()
        return str(stage_run.id)


async def add_output(
    db: Factory, stage_run_id: str, data: dict[str, Any], version: int = 1, **fields: Any
) -> tuple[str, str]:
    sha = content_sha256(data)
    async with db() as session:
        output = StageOutput(
            stage_run_id=uuid.UUID(stage_run_id), version=version, data=data, sha256=sha, **fields
        )
        session.add(output)
        await session.commit()
        return str(output.id), sha


async def awaiting_output(
    db: Factory,
    run_id: str,
    stage: str = "literature",
    data: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Simulate the worker: ``stage`` produced an output that waits for review."""
    stage_run_id = await add_stage_run(db, run_id, stage)
    output = await add_output(db, stage_run_id, data or {"summary": "two papers"})
    await set_run_status(db, run_id, RunStatus.AWAITING_APPROVAL)
    return output


# Outputs that pass the strict stage schemas (agentic_core.schemas), in normalized form.
METHOD_OUTPUT: dict[str, Any] = {
    "research_gaps": ["Metric scale without per-dataset fine-tuning"],
    "proposals": [
        {
            "name": "Scale-aware distillation",
            "rationale": "Distil metric cues from a stereo teacher.",
            "expected_benefit": "Lower AbsRel on NYU2 without labels.",
            "risk": "Teacher errors transfer to the student.",
            "evidence_paper_ids": ["arxiv:2406.09414"],
        }
    ],
    "recommended_option": "Scale-aware distillation",
    "implementation_focus": "A lightweight student for a 6 GB GPU.",
    "datasets": ["nyu2"],
    "evaluation_metrics": ["abs_rel", "rmse", "delta1"],
}

LITERATURE_OUTPUT: dict[str, Any] = {
    "plan": {
        "topic": "Monocular depth estimation",
        "queries": ["monocular depth", "depth foundation model", "zero-shot depth"],
        "scope": "Recent learning-based monocular depth estimation.",
        "inclusion_criteria": ["Published 2023 or later"],
        "subtopics": ["Foundation models"],
    },
    "papers": [
        {
            "paper_id": "arxiv:2406.09414",
            "title": "Depth Anything V2",
            "authors": ["Lihe Yang", "Bingyi Kang"],
            "year": 2024,
            "venue": "NeurIPS",
            "doi": None,
            "arxiv_id": "2406.09414",
            "url": "https://arxiv.org/abs/2406.09414",
            "abstract": "Synthetic labels plus a large teacher improve fine detail.",
            "citation_count": None,
            "source": "arxiv",
            "pdf_available": True,
            "relevance": 0.92,
            "decision": "include",
            "decision_reason": "Directly studies monocular depth with foundation models.",
        }
    ],
    "analyses": [],
    "key_findings": [
        {
            "title": "Depth Anything V2",
            "source": "arXiv",
            "summary": "Synthetic labels plus a large teacher improve fine detail.",
            "url": "https://arxiv.org/abs/2406.09414",
            "paper_id": "arxiv:2406.09414",
        }
    ],
    "synthesis": "Foundation models dominate zero-shot relative depth.",
}


# --- Outputs for the paper library and artifacts ----------------------------------------------


def paper(paper_id: str, title: str, **fields: Any) -> dict[str, Any]:
    """A screened paper (agentic_core.schemas.PaperRef) as literature outputs store it."""
    return {
        "paper_id": paper_id,
        "title": title,
        "authors": ["Lihe Yang", "Bingyi Kang"],
        "year": 2024,
        "venue": "NeurIPS",
        "doi": None,
        "arxiv_id": None,
        "url": None,
        "abstract": f"What {title} is about.",
        "citation_count": None,
        "source": "arxiv",
        "pdf_available": True,
        "relevance": 0.8,
        "decision": "include",
        "decision_reason": "Directly on topic.",
        **fields,
    }


def analysis(paper_id: str, *evidence: tuple[str, int], **fields: str) -> dict[str, Any]:
    """Reading notes on one paper, with (quote, page) evidence."""
    return {
        "paper_id": paper_id,
        "contribution": f"What {paper_id} contributes.",
        "method": "An encoder-decoder network.",
        "results": "Better than the baselines.",
        "limitations": "Indoor scenes only.",
        "evidence": [{"quote": quote, "page": page} for quote, page in evidence],
        **fields,
    }


def literature(
    papers: list[dict[str, Any]], analyses: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """A literature stage output (LiteratureOutput as JSON) with these papers."""
    first = papers[0]
    return {
        "plan": LITERATURE_OUTPUT["plan"],
        "papers": papers,
        "analyses": analyses or [],
        "key_findings": [
            {
                "title": first["title"],
                "source": "arXiv",
                "summary": "A finding.",
                "url": None,
                "paper_id": first["paper_id"],
            }
        ],
        "synthesis": "What the papers say together.",
    }


async def add_stage_output(
    db: Factory,
    run_id: str,
    stage: str,
    data: dict[str, Any],
    *,
    status: StageStatus = StageStatus.APPROVED,
    attempt: int = 1,
    **fields: Any,
) -> str:
    """One attempt of ``stage`` with a single output version; returns the output's id."""
    stage_run_id = await add_stage_run(db, run_id, stage, status, attempt)
    output_id, _ = await add_output(db, stage_run_id, data, **fields)
    return output_id


CODING_OUTPUT: dict[str, Any] = {
    "summary": "A small U-Net and a scale-invariant loss.",
    "files": [
        {
            "path": "model.py",
            "language": "python",
            "role": "model",
            "content": "class DepthNet:\n    pass\n",
        },
        {
            "path": "losses.py",
            "language": "python",
            "role": "loss",
            "content": "def silog(prediction, target):\n    return 0.0\n",
        },
        {
            "path": "configs/train.yaml",
            "language": "yaml",
            "role": "config",
            "content": "epochs: 20\nbatch_size: 8\n",
        },
    ],
    "entrypoint": "model.py:DepthNet",
    "smoke_test": {"passed": True, "duration_seconds": 12.5, "log": "2 passed"},
}

EXPERIMENT_OUTPUT: dict[str, Any] = {
    "status": "succeeded",
    "summary": "Trained DepthNet for two epochs.",
    "config": {"epochs": 2, "batch_size": 8, "dataset": "nyu2"},
    "series": [
        {
            "name": "loss",
            "split": "train",
            "higher_is_better": False,
            "points": [{"epoch": 0, "value": 1.5}, {"epoch": 1, "value": 0.9}],
        },
        {
            "name": "delta1",
            "split": "val",
            "higher_is_better": True,
            "points": [{"epoch": 0, "value": None}, {"epoch": 1, "value": 0.81}],
        },
    ],
    "final_metrics": {"delta1": 0.81, "train_loss": 0.9},
    "logs_tail": "epoch 0 loss 1.5\nepoch 1 loss 0.9",
    "provenance": {
        "image_digest": "sha256:" + "a" * 64,
        "code_sha256": "b" * 64,
        "config_sha256": "c" * 64,
        "dataset": "nyu2",
        "dataset_version": "2025.03",
        "seed": 42,
        "gpu_name": "NVIDIA GeForce GTX 1060 6GB",
        "gpu_seconds": 61.5,
        "started_at": "2026-10-30T01:00:00Z",
        "finished_at": "2026-10-30T01:01:30Z",
    },
}

WRITING_OUTPUT: dict[str, Any] = {
    "title": "Scale-aware depth on a 6 GB GPU",
    "abstract": "A small network trained on NYU Depth V2.",
    "markdown": "# Scale-aware depth\n\nFoundation models [1] and distillation [2] help.\n",
    "sections": [{"name": "Introduction", "objective": "Motivate the problem."}],
    "citations": [
        {"key": 1, "paper_id": "arxiv:2406.09414"},
        {"key": 2, "paper_id": "doi:10.5555/missing"},
    ],
    "output_format": "Markdown draft",
    "review_focus": "Check the citations.",
}


# --- Reading the PDFs the API writes --------------------------------------------------------

_PDF_STRING = re.compile(rb"/(F\d) [\d.]+ Tf|\(((?:\\[0-7]{3}|\\.|[^\\)])*)\) Tj")
_PDF_ESCAPE = re.compile(rb"\\([0-7]{3}|.)", re.S)
# Enough of the Symbol font's encoding for the tests.
_SYMBOL_TEXT = {
    ord("d"): "\N{GREEK SMALL LETTER DELTA}",
    0xB3: "\N{GREATER-THAN OR EQUAL TO}",
}


def pdf_objects(data: bytes) -> dict[int, bytes]:
    """Object number -> body, for every ``n 0 obj ... endobj`` of the PDF."""
    return {
        int(match[1]): match[2]
        for match in re.finditer(rb"(\d+) 0 obj\n(.*?)\nendobj\n", data, re.S)
    }


def assert_pdf_structure(data: bytes) -> int:
    """Check what a reader relies on (the cross-reference table points at every object, stream
    lengths are exact, the page tree counts every page) and return the number of pages."""
    end = re.search(rb"startxref\n(\d+)\n%%EOF\n$", data)
    assert end is not None
    table = re.match(
        rb"xref\n0 (\d+)\n0000000000 65535 f \n((?:\d{10} 00000 n \n)*)trailer\n",
        data[int(end[1]) :],
    )
    assert table is not None
    offsets = [int(entry[:10]) for entry in re.findall(rb"\d{10} 00000 n \n", table[2])]
    assert len(offsets) == int(table[1]) - 1
    for number, offset in enumerate(offsets, start=1):
        assert data[offset:].startswith(b"%d 0 obj\n" % number), number
    objects = pdf_objects(data)
    assert len(objects) == len(offsets)
    for body in objects.values():
        length = re.match(rb"<< /Length (\d+) >>\nstream\n", body)
        if length is not None:
            content = body[length.end() :]
            assert content == content[: int(length[1])] + b"\nendstream"
    count = re.search(rb"/Count (\d+)", objects[2])
    pages = re.findall(rb"/Type /Page ", data)
    assert count is not None and int(count[1]) == len(pages)
    return len(pages)


def _pdf_unescape(raw: bytes) -> bytes:
    return _PDF_ESCAPE.sub(
        lambda match: bytes([int(match[1], 8)]) if len(match[1]) == 3 else match[1], raw
    )


def pdf_page_texts(data: bytes) -> list[str]:
    """The text of each page in page-tree order, one line per text object."""
    objects = pdf_objects(data)
    kids = re.search(rb"/Kids \[([^\]]*)\]", objects[2])
    assert kids is not None
    pages = []
    for page_number in re.findall(rb"(\d+) 0 R", kids[1]):
        contents = re.search(rb"/Contents (\d+) 0 R", objects[int(page_number)])
        assert contents is not None
        stream = objects[int(contents[1])].split(b"stream\n", 1)[1].rsplit(b"\nendstream", 1)[0]
        lines = []
        for block in re.findall(rb"BT\n(.*?)\nET", stream, re.S):
            font, text = b"F1", ""
            for match in _PDF_STRING.finditer(block):
                if match[1]:
                    font = match[1]
                    continue
                raw = _pdf_unescape(match[2])
                if font == b"F4":
                    text += "".join(_SYMBOL_TEXT.get(byte, "?") for byte in raw)
                else:
                    text += raw.decode("cp1252")
            lines.append(text)
        pages.append("\n".join(lines))
    return pages

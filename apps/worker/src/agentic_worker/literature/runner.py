"""The literature stage: plan, search, screen, full text, analyse, synthesise.

Each step stores its results before the next one starts, and an attempt that runs again skips
what is stored:
- the search, once run_papers rows exist for the stage run;
- a screening batch, once its candidates have decisions;
- a paper's PDF, once it is on disk (or was looked for lately), and its text, once a
  paper_texts row exists;
- an analysis, once run_papers.analysis is set.
The plan and the synthesis are not stored: the gateway replays their calls from its journal.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import batched
from typing import Any

from agentic_core.schemas import ResearchPlan
from agentic_db.models import Paper, PaperText
from agentic_scholarly.models import PaperMeta
from agentic_worker.gateway_llm import AttemptEndedError
from agentic_worker.literature import (
    analysis,
    fulltext,
    library,
    progress,
    screening,
    search,
    synthesis,
)
from agentic_worker.literature.agents import LiteratureAgents
from agentic_worker.literature.library import Candidate, Sessions
from agentic_worker.literature.output import degraded_reason, literature_output
from agentic_worker.literature.progress import Earlier, Progress
from agentic_worker.literature.sources import Scholarly
from agentic_worker.outputs import LITERATURE_PROMPT_VERSION
from agentic_worker.stages import ResearchPlanner, StageContext, StageFailedError, StageOutcome

CANDIDATES_PER_PAPER = 3  # screening sees up to 3 x max_papers candidates
FETCH_CONCURRENCY = 4
ANALYSIS_CONCURRENCY = 3

type Calls = list[dict[str, Any]]


def check(ctx: StageContext) -> None:
    """Stop once the attempt has ended: cancelled, or failed while other work still ran."""
    if ctx.cancelled.is_set():
        raise AttemptEndedError(ctx.stage_run_id)


async def bounded[T](items: Sequence[T], limit: int, work: Callable[[T], Awaitable[None]]) -> None:
    """work(item) for every item, ``limit`` at a time. After a failure no new item starts; the
    running ones finish, so what they did is stored, then the first failure is raised."""
    gate = asyncio.Semaphore(limit)
    failures: list[Exception] = []

    async def one(item: T) -> None:
        async with gate:
            if failures:
                return
            try:
                await work(item)
            except Exception as exc:  # raised below, once the others have finished
                failures.append(exc)

    await asyncio.gather(*(one(item) for item in items))
    if failures:
        raise failures[0]


@dataclass
class _Found:
    """A search record, as kept for its library row."""

    meta: PaperMeta
    score: float
    hits: list[dict[str, Any]] = field(default_factory=list)


class LiteratureRunner:
    def __init__(
        self,
        planner: ResearchPlanner,
        scholarly: Scholarly,
        sessions: Sessions,
        agents: LiteratureAgents,
    ) -> None:
        self._planner = planner
        self._scholarly = scholarly
        self._sessions = sessions
        self._agents = agents

    async def run(self, ctx: StageContext) -> StageOutcome:
        stage_run_id = uuid.UUID(ctx.stage_run_id)
        earlier = await progress.earlier_lines(self._sessions, uuid.UUID(ctx.run_id), ctx.attempt)
        say = Progress(ctx, earlier)
        calls: Calls = []

        planned = await self._planner.plan(ctx)
        plan = planned.plan
        check(ctx)
        found, failed = await self._search(ctx, plan, say, earlier)
        check(ctx)
        await self._screen(ctx, plan, calls)
        candidates = await library.candidates(self._sessions, stage_run_id)
        selected = screening.select(candidates, ctx.config.max_papers)
        included = [c for c in selected if c.entry.decision == "include"]
        await say.screened(len(candidates), len(included))
        check(ctx)
        texts = await self._full_text(ctx, included, found, say)
        check(ctx)
        await self._analyse(ctx, plan, included, texts, calls)

        # The analyses as stored, read back like everything else.
        candidates = await library.candidates(self._sessions, stage_run_id)
        selected = screening.select(candidates, ctx.config.max_papers)
        included = [c for c in selected if c.entry.decision == "include"]
        await say.analyzed(sum(c.entry.analysis is not None for c in included))
        check(ctx)
        reading = included or [c for c in selected if c.entry.decision == "maybe"]
        if not reading:
            raise StageFailedError("literature.no_papers: screening excluded every candidate")
        answer = await self._agents.ask(ctx, synthesis.request(ctx, plan, reading))
        calls.extend(answer.calls)
        findings, text = answer.value
        await say.synthesized(len(findings))
        output = literature_output(plan, selected, reading, findings, text)
        reason = degraded_reason(failed, included, texts)
        return StageOutcome(
            data=output.model_dump(mode="json"),
            model=answer.model,
            degraded=reason is not None,
            degraded_reason=reason,
            prompt_version=LITERATURE_PROMPT_VERSION,
            llm_calls=[*planned.llm_calls, *calls],
        )

    async def _search(
        self, ctx: StageContext, plan: ResearchPlan, say: Progress, earlier: Earlier
    ) -> tuple[dict[uuid.UUID, PaperMeta], tuple[str, ...]]:
        """The candidates' records by paper id (empty when the search was done before), and the
        sources that failed."""
        stage_run_id = uuid.UUID(ctx.stage_run_id)
        if await library.has_candidates(self._sessions, stage_run_id):
            return {}, earlier.failed_sources
        result = await search.search(self._scholarly.search, plan, ctx.config)
        # Logged before the candidates are stored: a resumed attempt reads the failures back.
        for source, error in result.failed.items():
            await say.source_failed(source, error)
        kept: dict[uuid.UUID, _Found] = {}
        limit = CANDIDATES_PER_PAPER * ctx.config.max_papers
        for meta, score in zip(result.papers, result.scores, strict=True):
            if len(kept) >= limit:
                break
            paper = await library.upsert_paper(self._sessions, meta)
            if paper is None:
                continue
            hits = [hit.model_dump(mode="json") for hit in meta.hits]
            if paper.id in kept:
                # The sources' records disagreed, but the library knows them as one paper.
                known = kept[paper.id].hits
                known += [hit for hit in hits if hit not in known]
                continue
            kept[paper.id] = _Found(meta=meta, score=score, hits=hits)
        await library.add_candidates(
            self._sessions,
            [
                {
                    "stage_run_id": stage_run_id,
                    "paper_id": paper_id,
                    "run_id": uuid.UUID(ctx.run_id),
                    "hits": entry.hits,
                    "rank": rank,
                    "score": entry.score,
                }
                for rank, (paper_id, entry) in enumerate(kept.items(), start=1)
            ],
        )
        await say.searched(len(plan.queries), result.sources, result.found, result.incomplete)
        if not kept:
            raise StageFailedError(
                "literature.no_papers: the search found no paper with authors, a year and an "
                f"abstract (failed sources: {', '.join(result.failed) or 'none'})"
            )
        return {paper_id: entry.meta for paper_id, entry in kept.items()}, tuple(result.failed)

    async def _screen(self, ctx: StageContext, plan: ResearchPlan, calls: Calls) -> None:
        stage_run_id = uuid.UUID(ctx.stage_run_id)
        candidates = await library.candidates(self._sessions, stage_run_id)
        for number, batch in enumerate(batched(candidates, screening.BATCH_SIZE), start=1):
            if all(candidate.entry.decision is not None for candidate in batch):
                continue  # screened before the attempt last stopped
            check(ctx)
            answer = await self._agents.ask(ctx, screening.request(ctx, plan, number, batch))
            calls.extend(answer.calls)
            await library.record_screening(
                self._sessions, stage_run_id, screening.decisions(batch, answer.value)
            )

    async def _full_text(
        self,
        ctx: StageContext,
        included: Sequence[Candidate],
        found: Mapping[uuid.UUID, PaperMeta],
        say: Progress,
    ) -> dict[uuid.UUID, PaperText]:
        scholarly = self._scholarly
        now = datetime.now(UTC)

        async def fetch(candidate: Candidate) -> None:
            check(ctx)
            paper = candidate.paper
            await fulltext.fetch(self._sessions, scholarly, paper, found.get(paper.id))

        data_dir = scholarly.data_dir
        missing = [c for c in included if fulltext.needs_fetch(c.paper, data_dir, now)]
        await bounded(missing, FETCH_CONCURRENCY, fetch)
        ids = [candidate.paper.id for candidate in included]
        papers = await library.papers(self._sessions, ids)
        with_pdf = [papers[i] for i in ids if fulltext.stored(papers[i], data_dir)]
        await say.fetched(len(with_pdf), len(ids) - len(with_pdf))

        texts = await library.paper_texts(self._sessions, ids)
        unparsed = [paper for paper in with_pdf if paper.id not in texts]
        grobid = asyncio.Lock() if unparsed and await scholarly.grobid.is_alive() else None

        async def parse(paper: Paper) -> None:
            check(ctx)
            await fulltext.parse(self._sessions, scholarly, paper, grobid=grobid)

        await bounded(unparsed, FETCH_CONCURRENCY, parse)
        texts = await library.paper_texts(self._sessions, ids)
        await say.parsed(sum(analysis.has_text(texts.get(i)) for i in ids))
        return texts

    async def _analyse(
        self,
        ctx: StageContext,
        plan: ResearchPlan,
        included: Sequence[Candidate],
        texts: Mapping[uuid.UUID, PaperText],
        calls: Calls,
    ) -> None:
        stage_run_id = uuid.UUID(ctx.stage_run_id)

        async def analyse(candidate: Candidate) -> None:
            check(ctx)
            paper, text = candidate.paper, texts.get(candidate.paper.id)
            answer = await self._agents.ask(ctx, analysis.request(ctx, plan, paper, text))
            calls.extend(answer.calls)
            result = analysis.analysis(paper, answer.value, text)
            await library.record_analysis(
                self._sessions, stage_run_id, paper.id, result.model_dump(mode="json"), answer.model
            )

        pending = [c for c in included if c.entry.analysis is None]
        await bounded(pending, ANALYSIS_CONCURRENCY, analyse)

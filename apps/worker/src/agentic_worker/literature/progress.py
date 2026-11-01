"""The literature stage's progress lines, and what an attempt that runs again reads back from them.

Each line is a run event (``StageActivities._logger``): a code and params the web translates,
plus an English message. A resumed attempt learns from its earlier lines which sources failed
(the output's degraded reason) and does not repeat the lines of steps it already finished.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.demo import SOURCE_LABELS
from agentic_core.stages import Stage
from agentic_worker.progress import attempt_lines
from agentic_worker.stages import StageContext

SEARCHED = "literature.searched"
SOURCE_FAILED = "literature.source_failed"
SCREENED = "literature.screened"
FETCHED = "literature.fetched"
PARSED = "literature.parsed"
ANALYZED = "literature.analyzed"
SYNTHESIZED = "literature.synthesized"


@dataclass(frozen=True)
class Earlier:
    """The literature lines this attempt wrote before it stopped (none for a fresh attempt)."""

    codes: frozenset[str] = frozenset()
    failed_sources: tuple[str, ...] = ()


@dataclass
class Progress:
    """Writes the attempt's progress lines, each step's line once per attempt."""

    ctx: StageContext
    earlier: Earlier = field(default_factory=Earlier)

    async def say(self, code: str, params: dict[str, Any], message: str) -> None:
        if code in self.earlier.codes:
            return  # written before this attempt last stopped
        await self.ctx.log(code, params, message)

    async def searched(
        self, queries: int, sources: Sequence[str], found: int, incomplete: int
    ) -> None:
        message = f"Searched {_labels(sources)} with {queries} queries: {found} papers found"
        if incomplete:
            message += f", {incomplete} of them left out for lack of authors, a year or an abstract"
        params = {"queries": queries, "sources": list(sources), "found": found}
        await self.say(SEARCHED, params | {"incomplete": incomplete}, message)

    async def source_failed(self, source: str, error: str, answered: int, queries: int) -> None:
        # Not deduplicated: a source fails at most once per search, and a search runs again only
        # when the attempt stopped before storing its results.
        label = SOURCE_LABELS.get(source, source)
        if answered:  # the papers it found for those count
            message = (
                f"{label} stopped answering after {answered} of {queries} queries ({error}); the "
                "papers it found before that are kept"
            )
        else:
            message = f"{label} could not be searched ({error}); continuing without it"
        await self.ctx.log(
            SOURCE_FAILED,
            {"source": source, "error": error, "answered": answered, "queries": queries},
            message,
        )

    async def screened(self, candidates: int, included: int) -> None:
        await self.say(
            SCREENED,
            {"candidates": candidates, "included": included},
            f"Screened {candidates} candidates and included {included} for full reading",
        )

    async def fetched(self, pdfs: int, abstract_only: int) -> None:
        await self.say(
            FETCHED,
            {"pdfs": pdfs, "abstract_only": abstract_only},
            f"Fetched {pdfs} open-access PDFs; {abstract_only} papers have only an abstract",
        )

    async def parsed(self, papers: int) -> None:
        await self.say(PARSED, {"papers": papers}, f"Parsed the full text of {papers} papers")

    async def analyzed(self, papers: int) -> None:
        await self.say(ANALYZED, {"papers": papers}, f"Analysed {papers} papers")

    async def synthesized(self, findings: int) -> None:
        await self.say(
            SYNTHESIZED,
            {"findings": findings},
            f"Wrote the synthesis from {findings} key findings",
        )


def _labels(sources: Sequence[str]) -> str:
    return ", ".join(SOURCE_LABELS.get(source, source) for source in sources) or "no sources"


async def earlier_lines(
    sessions: async_sessionmaker[AsyncSession], run_id: uuid.UUID, attempt: int
) -> Earlier:
    """The literature lines written since this attempt's stage.started event."""
    payloads = await attempt_lines(sessions, run_id, Stage.LITERATURE.value, attempt)
    codes = {str(payload.get("code")) for payload in payloads}
    failed = [
        str(payload["params"]["source"])
        for payload in payloads
        if payload.get("code") == SOURCE_FAILED and "source" in payload.get("params", {})
    ]
    return Earlier(codes=frozenset(codes), failed_sources=tuple(dict.fromkeys(failed)))

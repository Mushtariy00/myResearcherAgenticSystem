"""Fakes for the literature stage: the scholarly APIs, the internet that serves PDFs, GROBID and
the LLM gateway (a journal that replays answered keys, like the real one), plus the papers they
know about."""

import json
import re
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import httpx

from agentic_scholarly.clients import (
    ArxivClient,
    CoreClient,
    CrossrefClient,
    OpenAlexClient,
    SemanticScholarClient,
    UnpaywallClient,
)
from agentic_scholarly.fetch import MIN_PDF_BYTES, SafeClient, fetch_pdf
from agentic_scholarly.grobid import GrobidError, Section, TeiDocument, TeiHeader
from agentic_scholarly.http import RetryPolicy, make_client
from agentic_scholarly.ratelimit import SOURCE_LIMITS, Limit, MemoryMutex, MemoryRateLimiter
from agentic_scholarly.testing import FakeNetwork, RecordingSleep, http_response, make_pdf
from agentic_worker.activities import StageActivities
from agentic_worker.agents import LlmFactory, StageAgents, gateway_llms
from agentic_worker.gateway_llm import GatewayLLM
from agentic_worker.literature.runner import LiteratureRunner
from agentic_worker.literature.sources import Scholarly
from agentic_worker.stages import PipelineStageRunner, StageContext
from agentic_worker.types import StageExecIn, StageStartIn
from worker_testkit import Factory, FakePlanner, FakeValkey, create_run

TOPIC = "Monocular depth estimation"

# --- the papers the fake sources know -----------------------------------------------------------


@dataclass(frozen=True)
class FakePaper:
    title: str
    abstract: str | None
    authors: tuple[str, ...]
    year: int
    arxiv_id: str | None = None  # found in arXiv under this id
    openalex_id: str | None = None  # found in OpenAlex under this W id
    doi: str | None = None  # the DOI OpenAlex gives
    pdf_url: str | None = None  # OpenAlex's open-access PDF link
    venue: str | None = None
    citations: int = 0


DEPTH_ANYTHING = FakePaper(
    title="Depth Anything: Unleashing the Power of Large-Scale Unlabeled Data",
    abstract=(
        "We present a practical solution for robust monocular depth estimation trained on "
        "large-scale unlabeled images, with strong zero-shot results."
    ),
    authors=("Lihe Yang", "Bingyi Kang", "Zilong Huang", "Xiaogang Xu"),
    year=2024,
    arxiv_id="2401.10891",
    openalex_id="W4391000001",
    doi="10.48550/arxiv.2401.10891",  # arXiv's own DOI: the paper's key stays its arXiv id
    venue="CVPR",
    citations=420,
)
ADABINS = FakePaper(
    title="AdaBins: Depth Estimation Using Adaptive Bins",
    abstract="AdaBins divides the depth range into adaptive bins for monocular depth estimation.",
    authors=("Shariq Farooq Bhat", "Ibraheem Alhashim", "Peter Wonka"),
    year=2021,
    openalex_id="W3200000002",
    doi="10.1109/cvpr46437.2021.00400",
    pdf_url="https://repository.example.edu/adabins.pdf",
    venue="CVPR",
    citations=900,
)
DPT = FakePaper(
    title="Vision Transformers for Dense Prediction and Depth Estimation",
    abstract="Dense prediction transformers improve monocular depth estimation on NYU Depth V2.",
    authors=("Rene Ranftl", "Alexey Bochkovskiy", "Vladlen Koltun"),
    year=2021,
    openalex_id="W3200000003",
    doi="10.1109/iccv48922.2021.01196",  # no open-access copy anywhere: abstract only
    venue="ICCV",
    citations=1500,
)
SURVEY = FakePaper(
    title="A Survey of Indoor Scene Understanding",
    abstract="We survey scene understanding methods for indoor robots, including geometry.",
    authors=("Ana Lima", "Ben Ford"),
    year=2023,
    openalex_id="W4300000004",
    doi="10.1000/survey.2023.4",
    citations=30,
)
MOLECULES = FakePaper(
    title="Graph Neural Networks for Molecular Property Prediction",
    abstract="Message passing networks predict molecular properties from graphs.",
    authors=("Chen Wu",),
    year=2020,
    openalex_id="W3000000005",
    doi="10.1000/molecules.2020.5",
    citations=50,
)
NO_ABSTRACT = FakePaper(
    title="Depth Completion from Sparse Lidar",
    abstract=None,  # left out: a PaperRef needs an abstract
    authors=("Dana Kim",),
    year=2022,
    arxiv_id="2205.00006",
)
PAPERS = (DEPTH_ANYTHING, ADABINS, DPT, SURVEY, MOLECULES, NO_ABSTRACT)
KEYS = {
    DEPTH_ANYTHING: "arxiv:2401.10891",
    ADABINS: "doi:10.1109/cvpr46437.2021.00400",
    DPT: "doi:10.1109/iccv48922.2021.01196",
    SURVEY: "doi:10.1000/survey.2023.4",
    MOLECULES: "doi:10.1000/molecules.2020.5",
}
INCLUDED = (DEPTH_ANYTHING, ADABINS, DPT)  # what the fake screener includes ("depth" titles)

# Sentences on known pages of the PDFs, for evidence quotes.
DEPTH_ANYTHING_RESULT = (
    "Depth Anything reduces the absolute relative error by 12.5 percent on NYU Depth V2."
)
DEPTH_ANYTHING_DATA = "We train on 62 million unlabeled images with pseudo labels from a teacher."
ADABINS_METHOD = "AdaBins estimates the bin centers of the depth range for every image."


def _filler(page: int, count: int) -> list[str]:
    return [
        f"Line {n} of page {page} describes the experimental protocol and the training schedule."
        for n in range(count)
    ]


def paper_pdf(pages: Sequence[Sequence[str]]) -> bytes:
    """A PDF with the given lines on each page, padded with filler lines; three pages are past
    the fetcher's 10 KB minimum."""
    pdf = make_pdf([[*lines, *_filler(number, 40)] for number, lines in enumerate(pages, 1)])
    assert len(pdf) >= MIN_PDF_BYTES, "too small for fetch_pdf: add a page"
    return pdf


DEPTH_ANYTHING_PDF = paper_pdf(
    [
        [DEPTH_ANYTHING.title, "1 Introduction", "Monocular depth estimation is ill-posed."],
        ["4 Experiments", DEPTH_ANYTHING_RESULT],
        [DEPTH_ANYTHING_DATA, "References", "[1] A. Author. A cited paper. 2020."],
    ]
)
ADABINS_PDF = paper_pdf(
    [[ADABINS.title, ADABINS_METHOD], ["5 Results", "Bins help."], ["6 Conclusion"]]
)

# What the fake analyst quotes for each paper: (quote, page). Some quotes are made up or cite
# the wrong page; the stage keeps only those found on their page.
QUOTES: dict[str, list[tuple[str, int]]] = {
    KEYS[DEPTH_ANYTHING]: [
        (DEPTH_ANYTHING_RESULT, 2),
        ("Depth Anything achieves state-of-the-art results on every benchmark ever.", 2),
        (DEPTH_ANYTHING_DATA, 1),  # it is on page 3
    ],
    KEYS[ADABINS]: [(ADABINS_METHOD, 1)],
    KEYS[DPT]: [("Dense prediction transformers improve monocular depth estimation", 1)],
}

# --- the scholarly APIs -------------------------------------------------------------------------


def _inverted(text: str) -> dict[str, list[int]]:
    index: dict[str, list[int]] = {}
    for position, word in enumerate(text.split()):
        index.setdefault(word, []).append(position)
    return index


def openalex_work(paper: FakePaper) -> dict[str, Any]:
    location = {"is_oa": True, "pdf_url": paper.pdf_url} if paper.pdf_url else None
    return {
        "id": f"https://openalex.org/{paper.openalex_id}",
        "doi": f"https://doi.org/{paper.doi}" if paper.doi else None,
        "title": paper.title,
        "publication_year": paper.year,
        "type": "article",
        "authorships": [{"author": {"display_name": name}} for name in paper.authors],
        "primary_location": {"source": {"display_name": paper.venue}} if paper.venue else None,
        "best_oa_location": location,
        "locations": [location] if location else [],
        "abstract_inverted_index": _inverted(paper.abstract) if paper.abstract else None,
        "cited_by_count": paper.citations,
        "ids": {},
        "is_retracted": False,
    }


def arxiv_feed(papers: Iterable[FakePaper]) -> str:
    entries = "".join(
        f"""<entry>
<id>http://arxiv.org/abs/{paper.arxiv_id}v1</id>
<title>{escape(paper.title)}</title>
<summary>{escape(paper.abstract or "")}</summary>
<published>{paper.year}-03-01T00:00:00Z</published>
{"".join(f"<author><name>{escape(name)}</name></author>" for name in paper.authors)}
</entry>"""
        for paper in papers
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">'
        f"{entries}</feed>"
    )


@dataclass
class FakeApis:
    """api.openalex.org, export.arxiv.org and api.semanticscholar.org, answering every query
    with the papers they know; Semantic Scholar is rate limited unless told otherwise, and
    OpenAlex after ``openalex_answers`` requests if that is set."""

    papers: Sequence[FakePaper] = PAPERS
    s2_status: int = 429
    openalex_answers: int | None = None
    requests: list[str] = field(default_factory=list)  # hosts, in order

    def handle(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        self.requests.append(host)
        limit = self.openalex_answers
        if host == "api.openalex.org" and limit is not None and self.requests.count(host) > limit:
            return httpx.Response(429, headers={"Retry-After": "120"})
        if host == "api.openalex.org":
            works = [openalex_work(p) for p in self.papers if p.openalex_id]
            return httpx.Response(200, json={"results": works})
        if host == "export.arxiv.org":
            feed = arxiv_feed(p for p in self.papers if p.arxiv_id)
            return httpx.Response(200, text=feed, headers={"Content-Type": "application/atom+xml"})
        if host == "api.semanticscholar.org" and self.s2_status != 200:
            # Retry-After beyond the clients' patience: no retry, the source just fails.
            return httpx.Response(self.s2_status, headers={"Retry-After": "120"})
        return httpx.Response(404)


# --- the internet that serves PDFs --------------------------------------------------------------

ARXIV_IP = "151.101.3.42"
REPOSITORY_IP = "93.184.215.14"


def pdf_network(responses: Mapping[str, Sequence[bytes]] | None = None) -> FakeNetwork:
    """arxiv.org and repository.example.edu serving the known PDFs once each."""
    if responses is None:
        responses = {
            ARXIV_IP: [_pdf_response(DEPTH_ANYTHING_PDF)],
            REPOSITORY_IP: [_pdf_response(ADABINS_PDF)],
        }
    return FakeNetwork(responses)


def _pdf_response(pdf: bytes) -> bytes:
    return http_response(200, pdf, {"Content-Type": "application/pdf"})


async def resolve(host: str, port: int) -> list[str]:
    addresses = {"arxiv.org": [ARXIV_IP], "repository.example.edu": [REPOSITORY_IP]}
    if host not in addresses:
        raise OSError(f"no such host: {host}")
    return addresses[host]


@dataclass
class FakeGrobid:
    alive: bool = False
    sections: list[Section] = field(default_factory=list)
    parsed: int = 0

    async def is_alive(self) -> bool:
        return self.alive

    async def fulltext(self, pdf: bytes) -> TeiDocument:
        self.parsed += 1
        if not self.sections:
            raise GrobidError("grobid.no_content", status=204)
        return TeiDocument(header=TeiHeader(), sections=self.sections, references=[])


def scholarly_for(
    data_dir: Path,
    apis: FakeApis,
    network: FakeNetwork,
    grobid: FakeGrobid | None = None,
) -> Scholarly:
    """The worker's clients, talking to fakes; nothing waits for a rate limit or a retry."""
    http = make_client("tests@example.invalid", transport=httpx.MockTransport(apis.handle))
    safe = SafeClient(resolver=resolve, network_backend=network)
    limiter = MemoryRateLimiter({source: Limit(1000) for source in SOURCE_LIMITS})
    mutex = MemoryMutex()
    retry = RetryPolicy(sleep=RecordingSleep())
    return Scholarly(
        search={
            "arxiv": ArxivClient(http, limiter, mutex=mutex, retry=retry),
            "openalex": OpenAlexClient(http, limiter, retry=retry),
            "semantic_scholar": SemanticScholarClient(http, limiter, retry=retry),
            "crossref": CrossrefClient(http, limiter, retry=retry),
        },
        unpaywall=UnpaywallClient(http, limiter, email=None),
        core=CoreClient(http, limiter, api_key=None),
        fetch=partial(fetch_pdf, client=safe),
        grobid=grobid or FakeGrobid(),
        limiter=limiter,
        arxiv_mutex=mutex,
        data_dir=data_dir,
        clients=(http, safe),
    )


# --- the LLM gateway ----------------------------------------------------------------------------

_CANDIDATE = re.compile(r"^\[(\d+)\] (.+)$", re.MULTILINE)


def _block(prompt: str, label: str) -> str:
    return prompt.split(f"--- BEGIN {label} ---", 1)[1].split(f"--- END {label} ---", 1)[0]


def screen_answer(prompt: str) -> str:
    """Include papers about depth, exclude molecules, maybe for the rest."""
    decisions = []
    for number, title in _CANDIDATE.findall(_block(prompt, "CANDIDATES")):
        if "depth" in title.lower():
            decision, relevance = "include", 0.9 - int(number) / 100
        elif "molecul" in title.lower():
            decision, relevance = "exclude", 0.1
        else:
            decision, relevance = "maybe", 0.5
        decisions.append(
            {
                "id": int(number),
                "decision": decision,
                "relevance": relevance,
                "reason": f"Judged by its title: {title[:40]}.",
            }
        )
    return json.dumps({"decisions": decisions})


def analysis_answer(paper_key: str) -> str:
    quotes = [{"quote": quote, "page": page} for quote, page in QUOTES.get(paper_key, [])]
    return json.dumps(
        {
            "contribution": f"The contribution of {paper_key}.",
            "method": "A monocular depth network.",
            "results": "Better depth on NYU Depth V2.",
            "limitations": "Indoor scenes only.",
            "evidence": quotes,
        }
    )


def synthesis_answer(prompt: str) -> str:
    numbers = [int(n) for n, _ in _CANDIDATE.findall(_block(prompt, "PAPERS"))]
    findings = [{"paper": n, "summary": f"Finding from paper {n}."} for n in numbers[:3]]
    return json.dumps(
        {
            "key_findings": findings,
            "synthesis": ["Depth networks improve.", "Open problems remain."],
        }
    )


@dataclass(frozen=True)
class GatewayCall:
    key: str
    role: str
    messages: list[dict[str, str]]
    status: int
    replayed: bool


@dataclass
class FakeGateway:
    """/v1/complete with a journal: a key answered once is replayed (free) when sent again.

    ``failures`` are (matches key, response) pairs, each used once, before any answer.
    ``answers`` overrides the answer per role (a function of the prompt). Answers for keys that
    ``cut_off`` matches report the whole output budget used, as a truncated answer would.
    """

    failures: list[tuple[Callable[[str], bool], httpx.Response]] = field(default_factory=list)
    answers: dict[str, Callable[[str], str]] = field(default_factory=dict)
    cut_off: Callable[[str], bool] = field(default=lambda key: False)
    calls: list[GatewayCall] = field(default_factory=list)
    journal: dict[str, dict[str, Any]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        key, role, messages = body["idempotency_key"], body["role"], body["messages"]
        with self.lock:
            if key in self.journal:
                self.calls.append(GatewayCall(key, role, messages, 200, replayed=True))
                return httpx.Response(200, json={**self.journal[key], "replayed": True})
            failure = next((f for f in self.failures if f[0](key)), None)
            if failure is not None:
                self.failures.remove(failure)
                self.calls.append(GatewayCall(key, role, messages, failure[1].status_code, False))
                return failure[1]
            # A repair request repeats the original prompt, so the blocks are found in it too.
            content = self._answer(key, role, "\n".join(m["content"] for m in messages))
            answer = {
                "content": content,
                "model": "fake/free-model:free",
                "tier": "free",
                "cost_usd": "0",
                "prompt_tokens": 100,
                "completion_tokens": body["max_output_tokens"] if self.cut_off(key) else 50,
                "switched_to_free": False,
                "replayed": False,
            }
            self.journal[key] = answer
            self.calls.append(GatewayCall(key, role, messages, 200, replayed=False))
            return httpx.Response(200, json=answer)

    def _answer(self, key: str, role: str, prompt: str) -> str:
        if role in self.answers:
            return self.answers[role](prompt)
        if role == "literature.screen":
            return screen_answer(prompt)
        if role == "literature.analyze":
            return analysis_answer(key.split(":analyze:", 1)[1].rsplit(":call-", 1)[0])
        if role == "literature.synthesize":
            return synthesis_answer(prompt)
        raise AssertionError(f"unexpected role {role}")

    def answered(self) -> list[str]:
        """Keys answered for the first time (paid for), in order."""
        return [call.key for call in self.calls if call.status == 200 and not call.replayed]

    def keys(self, role: str) -> list[str]:
        return [call.key for call in self.calls if call.role == role]


def rate_limited(retry_after: int = 42) -> httpx.Response:
    return httpx.Response(429, json={"detail": "free_quota.exhausted", "retry_after": retry_after})


def fake_llms(gateway: FakeGateway) -> LlmFactory:
    """The worker's GatewayLLMs, sending to the fake gateway."""
    make_real = gateway_llms("http://gateway.test", "gateway-token")

    def make(
        ctx: StageContext, *, role: str, key_prefix: str, max_output_tokens: int
    ) -> GatewayLLM:
        llm = make_real(ctx, role=role, key_prefix=key_prefix, max_output_tokens=max_output_tokens)
        llm._client = httpx.Client(transport=httpx.MockTransport(gateway.handle))
        return llm

    return make


# --- a literature stage on the test database ----------------------------------------------------


@dataclass
class Harness:
    """Everything one literature test needs: the fakes, the runner and the activities."""

    db: Factory
    apis: FakeApis
    network: FakeNetwork
    gateway: FakeGateway
    grobid: FakeGrobid
    scholarly: Scholarly
    runner: LiteratureRunner
    activities: StageActivities

    async def start(self, config: dict[str, Any] | None = None) -> tuple[str, str]:
        """A new run with its first literature attempt started, as start_stage leaves it:
        (run id, stage run id)."""
        run_id = await create_run(
            self.db,
            topic=TOPIC,
            config={"max_papers": 5, "sources": ["arxiv", "openalex"], **(config or {})},
        )
        started = await self.activities.start_stage(
            StageStartIn(run_id=run_id, stage="literature", attempt=1)
        )
        return run_id, started.stage_run_id

    def execute(self, run_id: str, stage_run_id: str) -> StageExecIn:
        return StageExecIn(run_id=run_id, stage_run_id=stage_run_id, stage="literature", attempt=1)


def harness(
    db: Factory,
    data_dir: Path,
    *,
    apis: FakeApis | None = None,
    network: FakeNetwork | None = None,
    gateway: FakeGateway | None = None,
    grobid: FakeGrobid | None = None,
) -> Harness:
    apis = apis or FakeApis()
    network = network or pdf_network()
    gateway = gateway or FakeGateway()
    grobid = grobid or FakeGrobid()
    scholarly = scholarly_for(data_dir, apis, network, grobid)
    planner = FakePlanner()
    runner = LiteratureRunner(planner, scholarly, db, StageAgents(fake_llms(gateway)))
    activities = StageActivities(
        db, FakeValkey(), PipelineStageRunner(planner, literature=runner, demo_stage_seconds=0)
    )
    return Harness(db, apis, network, gateway, grobid, scholarly, runner, activities)

import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_api.files import CHUNK_BYTES, path_response
from agentic_api.routers import papers as papers_router
from agentic_api.settings import Settings
from agentic_core.enums import PdfStatus, StageStatus
from agentic_core.schemas import validate_stage_output
from agentic_scholarly.storage import store_pdf
from api_testkit import (
    ORIGIN,
    add_output,
    add_paper,
    add_paper_text,
    add_screenings,
    add_stage_output,
    analysis,
    as_user,
    assert_pdf_structure,
    create_project,
    literature,
    paper,
    pdf_page_texts,
    screening,
    start_run,
    team_project,
)

Factory = async_sessionmaker[AsyncSession]
URL = "/api/v1/papers"
NOW = datetime.now(UTC)
PRISM = "doi:10.5555/cvpr.2024.91234"
DELTA = "\N{GREEK SMALL LETTER DELTA}"
UMLAUT = "\N{LATIN SMALL LETTER U WITH DIAERESIS}"
PREVIEW_NOTICE = "Generated preview, not the published paper."


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Each test stores its PDFs in a data directory of its own."""
    return Settings(environment="test", public_origin=ORIGIN, data_dir=tmp_path)


async def _library(
    client: httpx.AsyncClient, user: str = "bob", role: str = "user", **params: Any
) -> dict[str, Any]:
    response = await client.get(URL, params=params, headers=as_user(user, role))
    assert response.status_code == 200, response.text
    return response.json()


def _ids(page: dict[str, Any]) -> list[str]:
    return [item["paper"]["paper_id"] for item in page["items"]]


async def _project(client: httpx.AsyncClient, name: str, owner: str) -> str:
    return await create_project(client, name, owner)


def _stored_pdf(size: int = 3 * CHUNK_BYTES + 100) -> bytes:
    body = bytes(range(256)) * (size // 256 + 1)
    return b"%PDF-1.7\n" + body[:size] + b"\n%%EOF\n"


def test_the_builders_make_valid_literature_outputs() -> None:
    data = literature(
        [paper("arxiv:1", "One"), paper(PRISM, "Two", decision="exclude", source="crossref")],
        [analysis("arxiv:1", ("A quote.", 3))],
    )
    assert validate_stage_output("literature", data).model_dump(mode="json") == data


async def test_the_library_merges_papers_across_runs(
    client: httpx.AsyncClient, db: Factory
) -> None:
    depth = await team_project(client)
    other = await _project(client, "Other", "carol")
    bobs = await start_run(client, depth, user="bob")
    alices = await start_run(client, depth, user="alice")
    carols = await start_run(client, other, user="carol")
    for key, title in (
        ("arxiv:1", "Depth Anything V2"),
        ("arxiv:2", "A Survey"),
        ("arxiv:3", "Off Topic"),
        ("arxiv:4", "Only in Other"),
    ):
        await add_paper(db, key, title)
    first = [
        screening("arxiv:1", relevance=0.9, source="semantic_scholar"),
        screening("arxiv:2", relevance=0.6, decision="maybe"),
    ]
    second = [
        screening("arxiv:1", relevance=0.7),
        screening("arxiv:3", relevance=0.3, decision="exclude"),
    ]
    hidden = [
        screening("arxiv:1", relevance=0.95, decision="maybe", source="openalex"),
        screening("arxiv:4", relevance=0.5),
    ]
    for run_id, screenings, hours in ((bobs, first, 3), (alices, second, 2), (carols, hidden, 1)):
        await add_screenings(db, run_id, screenings, found_at=NOW - timedelta(hours=hours))

    page = await _library(client, "bob")
    assert (page["total"], _ids(page), page["demo"]) == (
        3,
        ["arxiv:1", "arxiv:2", "arxiv:3"],
        False,
    )
    merged = page["items"][0]
    assert merged == {
        "paper": {
            "paper_id": "arxiv:1",
            "title": "Depth Anything V2",
            "authors": ["Lihe Yang", "Bingyi Kang"],
            "year": 2024,
            "venue": "NeurIPS",
            "doi": None,
            "arxiv_id": None,
            "url": None,
            "abstract": "What Depth Anything V2 is about.",
            "citation_count": None,
            "source": "arxiv",  # where the newest run bob can see found it
            "pdf_available": False,  # no file stored
        },
        "run_count": 2,
        "project_count": 1,
        "best_relevance": 0.9,
        "decisions": ["include"],
        "last_seen_at": merged["last_seen_at"],
        "demo": False,
    }
    assert datetime.fromisoformat(merged["last_seen_at"]) == NOW - timedelta(hours=2)
    assert (await _library(client, "vera"))["total"] == 3  # viewers read the library too
    assert _ids(await _library(client, "carol")) == ["arxiv:1", "arxiv:4"]

    everything = await _library(client, "root", "admin")
    assert _ids(everything) == ["arxiv:1", "arxiv:2", "arxiv:4", "arxiv:3"]
    merged = everything["items"][0]
    assert merged["paper"]["source"] == "openalex"
    assert (merged["run_count"], merged["project_count"], merged["best_relevance"]) == (3, 2, 0.95)
    assert merged["decisions"] == ["include", "maybe"]
    assert datetime.fromisoformat(merged["last_seen_at"]) == NOW - timedelta(hours=1)


async def test_runs_count_once_and_only_screened_papers_count(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project = await team_project(client)
    run_id = await start_run(client, project)
    for key in ("arxiv:1", "arxiv:2", "arxiv:3", "arxiv:4"):
        await add_paper(db, key, f"Paper {key}")
    await add_paper(db, "arxiv:5", "Undated", year=None)
    await add_screenings(
        db,
        run_id,
        [screening("arxiv:1"), screening("arxiv:2")],
        status=StageStatus.CHANGES_REQUESTED,
    )
    await add_screenings(
        db,
        run_id,
        [screening("arxiv:1", relevance=0.6), screening("arxiv:3")],
        attempt=2,
        status=StageStatus.OUTPUT_READY,
    )
    # A candidate that was ranked but not screened, and a paper without a year (the paper
    # record needs one), stay out; so does a paper that only a stage output lists.
    later = await start_run(client, project)
    unscreened = screening("arxiv:4", relevance=None, decision=None, decision_reason=None)
    await add_screenings(db, later, [unscreened, screening("arxiv:5")])
    outputs_only = await start_run(client, project)
    await add_stage_output(
        db, outputs_only, "literature", literature([paper("arxiv:9", "Only in an output")])
    )

    page = await _library(client)
    assert (page["total"], sorted(_ids(page))) == (3, ["arxiv:1", "arxiv:2", "arxiv:3"])
    assert [item["run_count"] for item in page["items"]] == [1, 1, 1]
    for paper_id in ("arxiv:4", "arxiv:5", "arxiv:9"):
        missing = await client.get(f"{URL}/{paper_id}", headers=as_user("bob"))
        assert (missing.status_code, missing.json()["detail"]) == (404, "paper.not_found")


async def test_search_and_filters(client: httpx.AsyncClient, db: Factory) -> None:
    depth = await team_project(client)
    second = await _project(client, "Second", "bob")
    await add_paper(
        db,
        "arxiv:1",
        "Monocular Depth with Transformers",
        authors=["Ana Silva"],
        year=2021,
        venue="CVPR",
        abstract="A study of attention for indoor scenes.",
    )
    await add_paper(
        db,
        PRISM,
        "Segmentation at Scale",
        authors=["Ji-woo Kim", "Bo Li"],
        year=2023,
        venue="ICCV",
        abstract="Uses 100% synthetic_data labels.",
    )
    await add_paper(
        db,
        "openalex:W3",
        "Edge Devices",
        authors=["Carla Gomez"],
        year=2025,
        venue="IEEE TPAMI",
        abstract="Runs on phones.",
    )
    await add_paper(db, "arxiv:9", "Older Work", year=2020)
    await add_screenings(
        db,
        await start_run(client, depth),
        [
            screening("arxiv:1", relevance=0.9),
            screening(PRISM, source="crossref", relevance=0.7, decision="maybe"),
            screening("openalex:W3", source="openalex", relevance=0.4, decision="exclude"),
        ],
    )
    await add_screenings(db, await start_run(client, second), [screening("arxiv:9", relevance=0.6)])

    async def ids(**params: Any) -> list[str]:
        return _ids(await _library(client, **params))

    assert await ids() == ["arxiv:1", PRISM, "arxiv:9", "openalex:W3"]
    assert await ids(q="monocular") == ["arxiv:1"]  # title, any case
    assert await ids(q="ATTENTION") == ["arxiv:1"]  # abstract
    assert await ids(q="kim") == [PRISM]  # an author
    assert await ids(q="tpami") == ["openalex:W3"]  # venue
    assert await ids(q="%") == [PRISM]  # LIKE wildcards are plain characters
    assert await ids(q="_") == [PRISM]
    assert await ids(q="   ") == await ids()
    assert await ids(q="nothing like it") == []
    assert await ids(year_from=2023) == [PRISM, "openalex:W3"]
    assert await ids(year_to=2021) == ["arxiv:1", "arxiv:9"]
    assert await ids(year_from=2022, year_to=2024) == [PRISM]
    assert await ids(decision="maybe") == [PRISM]
    assert await ids(source="openalex") == ["openalex:W3"]
    assert await ids(year_from=2021, source="arxiv") == ["arxiv:1"]
    assert await ids(project_id=second) == ["arxiv:9"]
    assert await ids(project_id=depth, q="e", decision="exclude") == ["openalex:W3"]

    first_page = await _library(client, limit=2)
    second_page = await _library(client, limit=2, offset=2)
    assert (first_page["total"], _ids(first_page)) == (4, ["arxiv:1", PRISM])
    assert (second_page["total"], _ids(second_page)) == (4, ["arxiv:9", "openalex:W3"])

    invalid = await client.get(f"{URL}?year_from=2025&year_to=2020", headers=as_user("bob"))
    assert (invalid.status_code, invalid.json()) == (422, {"detail": "papers.invalid_year_range"})
    for query in ("decision=accept", "source=google", "limit=0", "limit=201", "offset=-1"):
        response = await client.get(f"{URL}?{query}", headers=as_user("bob"))
        assert response.status_code == 422, query
    long_query = await client.get(URL, params={"q": "x" * 201}, headers=as_user("bob"))
    assert long_query.status_code == 422


async def test_full_text_search_reads_the_parsed_text(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project = await team_project(client)
    other = await _project(client, "Other", "carol")
    body = await add_paper(db, "arxiv:1", "Monocular Depth", abstract="Depth from a single image.")
    await add_paper(db, "arxiv:2", "Transformers for Depth", abstract="A transformer sees depth.")
    await add_paper(db, "arxiv:3", "Stereo Matching", abstract="Depth from two views.")
    hidden = await add_paper(db, "arxiv:4", "Hidden Work")
    await add_paper_text(
        db,
        body,
        ("Method", "A transformer decoder refines depth, and the transformer runs at 30 FPS."),
        ("Results", "Our xylophonic loss lowers the error by 9.8%."),
    )
    await add_paper_text(db, hidden, ("Method", "A xylophonic regulariser."))
    await add_screenings(
        db,
        await start_run(client, project),
        [
            screening("arxiv:1", relevance=0.9),
            screening("arxiv:2", relevance=0.5),
            screening("arxiv:3", relevance=0.7),
        ],
    )
    await add_screenings(db, await start_run(client, other, user="carol"), [screening("arxiv:4")])

    async def ids(q: str, user: str = "bob", role: str = "user") -> list[str]:
        return _ids(await _library(client, user, role, q=q))

    # Only a section of the parsed text has the word; carol's paper stays hidden from bob.
    assert await ids("xylophonic") == ["arxiv:1"]
    assert sorted(await ids("xylophonic", "root", "admin")) == ["arxiv:1", "arxiv:4"]
    # Best match first, whatever the relevance: the title and abstract outweigh the body.
    assert await ids("transformers") == ["arxiv:2", "arxiv:1"]
    assert await ids("stereo or xylophonic") == ["arxiv:3", "arxiv:1"]
    assert await ids('"single image"') == ["arxiv:1"]
    assert sorted(await ids("depth -stereo")) == ["arxiv:1", "arxiv:2"]


async def test_the_library_is_for_members(client: httpx.AsyncClient) -> None:
    other = await _project(client, "Other", "carol")
    assert (await client.get(URL)).status_code == 401
    hidden = await client.get(URL, params={"project_id": other}, headers=as_user("bob"))
    assert (hidden.status_code, hidden.json()["detail"]) == (404, "project.not_found")
    missing = await client.get(
        URL, params={"project_id": str(uuid.uuid4())}, headers=as_user("bob")
    )
    assert missing.status_code == 404
    admin = await _library(client, "root", "admin", project_id=other)
    assert admin == {"items": [], "total": 0, "demo": False}


async def test_seeded_demo_papers_are_marked_demo(client: httpx.AsyncClient, db: Factory) -> None:
    project = await team_project(client)
    # The seed marks a generated paper with a PDF available, though no file is stored.
    await add_paper(db, "arxiv:1", "Generated", demo=True, pdf_status=PdfStatus.AVAILABLE)
    await add_paper(
        db, "arxiv:2", "Generated without a PDF", demo=True, pdf_status=PdfStatus.ABSTRACT_ONLY
    )
    await add_paper(db, "arxiv:3", "Real", pdf_status=PdfStatus.AVAILABLE)  # but no file
    await add_paper(db, "arxiv:4", "Generated from CORE", demo=True)
    await add_screenings(
        db,
        await start_run(client, project),
        [
            screening("arxiv:1"),
            screening("arxiv:2"),
            screening("arxiv:3"),
            screening("arxiv:4", source=None),  # the seed records no hit for CORE
        ],
    )
    page = await _library(client)
    assert page["demo"] is True
    assert {
        item["paper"]["paper_id"]: (
            item["demo"],
            item["paper"]["pdf_available"],
            item["paper"]["source"],
        )
        for item in page["items"]
    } == {
        "arxiv:1": (True, True, "arxiv"),  # the generated preview stands in for the PDF
        "arxiv:2": (True, False, "arxiv"),
        "arxiv:3": (False, False, "arxiv"),
        "arxiv:4": (True, False, "demo"),
    }
    real_only = await _library(client, q="Real")
    assert (_ids(real_only), real_only["demo"]) == (["arxiv:3"], False)


async def test_a_paper_is_listed_under_the_source_of_its_best_hit(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project = await team_project(client)
    await add_paper(db, "arxiv:1", "Found Three Times")
    hits = [
        {"source": "openalex", "query": "depth", "position": 4},
        {"source": "arxiv", "query": "depth", "position": 1},
        {"source": "semantic_scholar", "query": "monocular depth", "position": 1},
    ]
    await add_screenings(db, await start_run(client, project), [screening("arxiv:1", hits=hits)])
    # The lowest position wins, and of two hits at one position the one searched first
    # (Semantic Scholar before arXiv), as the stage output's PaperRef has it.
    [item] = (await _library(client))["items"]
    assert item["paper"]["source"] == "semantic_scholar"
    assert _ids(await _library(client, source="semantic_scholar")) == ["arxiv:1"]
    assert _ids(await _library(client, source="openalex")) == []


async def _prism_runs(client: httpx.AsyncClient, db: Factory) -> tuple[str, str, str, str]:
    """PRISM, a seeded demo paper, found by bob's run (with an analysis) and later by alice's.
    Returns the project, both runs and the first run's output."""
    project = await team_project(client)
    first = await start_run(client, project, user="bob")
    second = await start_run(client, project, user="alice")
    await add_paper(
        db,
        PRISM,
        "PRISM: Scale-Aware Depth",
        authors=["Ji-woo Kim", f"J{UMLAUT}rgen M{UMLAUT}ller"],
        doi="10.5555/cvpr.2024.91234",
        venue="CVPR",
        demo=True,
        pdf_status=PdfStatus.AVAILABLE,
    )
    notes = analysis(
        PRISM,
        ("We train for 30 epochs with AdamW (Table 2).", 4),
        (f"On NYU Depth V2, PRISM achieves {DELTA}1 of 0.871.", 6),
        ("Removing the decoder increases the error by 9.8%.", 9),
    )
    found = screening(PRISM, relevance=0.9, decision_reason="Strong.", analysis=notes)
    attempt = await add_screenings(db, first, [found], found_at=NOW - timedelta(hours=2))
    output_id, _ = await add_output(
        db,
        attempt,
        literature([paper(PRISM, "PRISM", relevance=0.9, decision_reason="Strong.")], [notes]),
        created_at=NOW - timedelta(hours=2),
    )
    repeated = analysis(PRISM, ("We train for 30 epochs with AdamW (Table 2).", 4))
    again = screening(
        PRISM,
        relevance=0.7,
        decision="maybe",
        decision_reason="Unclear protocol.",
        analysis=repeated,
    )
    attempt = await add_screenings(db, second, [again], found_at=NOW - timedelta(hours=1))
    await add_output(
        db,
        attempt,
        literature([paper(PRISM, "PRISM: Scale-Aware Depth", relevance=0.7)], [repeated]),
        created_at=NOW - timedelta(hours=1),
    )
    return project, first, second, output_id


async def test_paper_detail_has_every_run_and_analysis(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project, first, second, output_id = await _prism_runs(client, db)
    # A third run has analysed it too, but shows the analysis only once it has an output.
    third = await start_run(client, project)
    pending = screening(PRISM, relevance=0.5, analysis=analysis(PRISM, ("Pending.", 2)))
    await add_screenings(
        db, third, [pending], status=StageStatus.RUNNING, found_at=NOW - timedelta(minutes=30)
    )

    response = await client.get(f"{URL}/{PRISM}", headers=as_user("vera"))
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["paper"]["title"] == "PRISM: Scale-Aware Depth"
    assert (detail["paper"]["doi"], detail["paper"]["pdf_available"]) == (
        "10.5555/cvpr.2024.91234",
        True,  # its generated preview
    )
    assert (detail["best_relevance"], detail["demo"]) == (0.9, True)
    assert [
        (run["id"], run["decision"], run["relevance"], run["decision_reason"], run["demo"])
        for run in detail["runs"]
    ] == [
        (third, "include", 0.5, "Directly on topic.", True),
        (second, "maybe", 0.7, "Unclear protocol.", True),
        (first, "include", 0.9, "Strong.", True),
    ]
    assert (detail["runs"][1]["topic"], detail["runs"][1]["project_name"]) == (
        "Monocular depth",
        "Depth",
    )
    assert detail["runs"][1]["status"] == "queued"
    newest, oldest = detail["analyses"]
    assert (newest["run_id"], newest["demo"], len(newest["evidence"])) == (second, True, 1)
    assert (oldest["run_id"], oldest["stage_output_id"], oldest["attempt"]) == (first, output_id, 1)
    assert datetime.fromisoformat(oldest["created_at"]) == NOW - timedelta(hours=2)
    assert [e["page"] for e in oldest["evidence"]] == [4, 6, 9]
    assert oldest["contribution"] == f"What {PRISM} contributes."

    # Clients encode the id; the slash may arrive encoded or not.
    encoded = await client.get(f"{URL}/doi%3A10.5555%2Fcvpr.2024.91234", headers=as_user("vera"))
    assert encoded.json() == detail
    for user, paper_id in (("carol", PRISM), ("bob", "arxiv:0000.00000")):
        missing = await client.get(f"{URL}/{paper_id}", headers=as_user(user))
        assert (missing.status_code, missing.json()["detail"]) == (404, "paper.not_found")
    assert (await client.get(f"{URL}/{PRISM}", headers=as_user("root", "admin"))).status_code == 200
    assert (await client.get(f"{URL}/{PRISM}")).status_code == 401


async def test_a_demo_paper_gets_a_pdf_preview_with_each_quote_on_its_page(
    client: httpx.AsyncClient, db: Factory
) -> None:
    await _prism_runs(client, db)
    response = await client.get(f"{URL}/{PRISM}/file", headers=as_user("vera"))
    assert response.status_code == 200, response.text
    body = response.content
    assert body.startswith(b"%PDF-1.4\n") and body.endswith(b"%%EOF\n")
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        'attachment; filename="doi-10.5555-cvpr.2024.91234.pdf"'
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private"
    assert response.headers["content-length"] == str(len(body))

    assert assert_pdf_structure(body) == 9  # the last quote cites page 9
    pages = [" ".join(text.split()) for text in pdf_page_texts(body)]
    quotes = {
        4: "We train for 30 epochs with AdamW (Table 2).",  # once, though two runs quote it
        6: f"On NYU Depth V2, PRISM achieves {DELTA}1 of 0.871.",
        9: "Removing the decoder increases the error by 9.8%.",
    }
    for number, text in enumerate(pages, start=1):
        for page, quote in quotes.items():
            assert text.count(quote) == (1 if page == number else 0), (number, quote)
    assert PREVIEW_NOTICE in pages[0]
    assert "PRISM: Scale-Aware Depth" in pages[0]
    assert f"Ji-woo Kim, J{UMLAUT}rgen M{UMLAUT}ller" in pages[0]
    assert "CVPR, 2024" in pages[0] and "DOI 10.5555/cvpr.2024.91234" in pages[0]
    assert "Abstract What PRISM: Scale-Aware Depth is about." in pages[0]
    assert all(f"Page {n} of 9" in text for n, text in enumerate(pages, start=1))
    assert re.search(rb"/Title <FEFF[0-9A-F]+>", body)

    again = await client.get(f"{URL}/{PRISM}/file", headers=as_user("bob"))
    assert again.content == body  # the same paper and analyses give the same file
    hidden = await client.get(f"{URL}/{PRISM}/file", headers=as_user("carol"))
    assert (hidden.status_code, hidden.json()["detail"]) == (404, "paper.not_found")


async def test_a_demo_paper_without_analyses_still_gets_a_preview(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project = await team_project(client)
    await add_paper(db, "arxiv:cs/0701234", "Old Paper", year=2007, demo=True)
    await add_screenings(db, await start_run(client, project), [screening("arxiv:cs/0701234")])
    response = await client.get(f"{URL}/arxiv:cs/0701234/file", headers=as_user("bob"))
    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"] == 'attachment; filename="arxiv-cs-0701234.pdf"'
    assert assert_pdf_structure(response.content) == 4
    detail = await client.get(f"{URL}/arxiv:cs/0701234", headers=as_user("bob"))
    assert (detail.json()["analyses"], detail.json()["demo"]) == ([], True)


async def test_a_stored_pdf_is_streamed_from_the_data_directory(
    client: httpx.AsyncClient, db: Factory, tmp_path: Path
) -> None:
    data = _stored_pdf()
    sha256, _ = store_pdf(tmp_path, data)
    project = await team_project(client)
    stored = {"pdf_status": PdfStatus.AVAILABLE, "pdf_sha256": sha256}
    await add_paper(db, "arxiv:2406.09414", "Depth Anything V2", **stored)
    # A demo paper with a stored file gets the file, not the preview.
    await add_paper(db, "arxiv:1", "Seeded", demo=True, **stored)
    await add_screenings(
        db,
        await start_run(client, project),
        [screening("arxiv:2406.09414"), screening("arxiv:1")],
    )

    response = await client.get(f"{URL}/arxiv:2406.09414/file", headers=as_user("vera"))
    assert response.status_code == 200, response.text
    assert response.content == data
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        'attachment; filename="arxiv-2406.09414.pdf"'
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private"
    assert response.headers["content-length"] == str(len(data))
    seeded = await client.get(f"{URL}/arxiv:1/file", headers=as_user("bob"))
    assert seeded.content == data
    detail = await client.get(f"{URL}/arxiv:2406.09414", headers=as_user("bob"))
    assert detail.json()["paper"]["pdf_available"] is True

    hidden = await client.get(f"{URL}/arxiv:2406.09414/file", headers=as_user("carol"))
    assert (hidden.status_code, hidden.json()["detail"]) == (404, "paper.not_found")


async def test_a_paper_without_a_stored_file_is_not_found(
    client: httpx.AsyncClient, db: Factory, tmp_path: Path
) -> None:
    project = await team_project(client)
    await add_paper(db, "arxiv:1", "Not looked for")
    await add_paper(db, "arxiv:2", "No open copy", pdf_status=PdfStatus.ABSTRACT_ONLY)
    # Stored, says the database, but the file is not in the data directory.
    await add_paper(db, "arxiv:3", "Lost", pdf_status=PdfStatus.AVAILABLE, pdf_sha256="f" * 64)
    await add_screenings(
        db,
        await start_run(client, project),
        [screening("arxiv:1"), screening("arxiv:2"), screening("arxiv:3")],
    )
    for paper_id in ("arxiv:1", "arxiv:2", "arxiv:3"):
        response = await client.get(f"{URL}/{paper_id}/file", headers=as_user("bob"))
        assert (response.status_code, response.json()["detail"]) == (404, "paper.not_found")
    assert not (tmp_path / "papers").exists()


async def test_only_a_valid_stored_sha256_names_a_file(
    client: httpx.AsyncClient, db: Factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _stored_pdf(1000)
    sha256, _ = store_pdf(tmp_path, data)
    # The same bytes under an upper-case name, which a path built from that value would find.
    upper = sha256.upper()
    (tmp_path / "papers" / upper[:2]).mkdir(exist_ok=True)
    (tmp_path / "papers" / upper[:2] / f"{upper}.pdf").write_bytes(data)
    built: list[str] = []
    pdf_path = papers_router.pdf_path

    def spy(root: Path, value: str) -> Path:
        built.append(value)
        return pdf_path(root, value)

    monkeypatch.setattr(papers_router, "pdf_path", spy)
    project = await team_project(client)
    invalid = {
        "arxiv:1": upper,
        "arxiv:2": "../../../../../../../../etc/passwd",
        "arxiv:3": "g" * 64,
        "arxiv:4": "",
    }
    for key, value in invalid.items():
        await add_paper(db, key, key, pdf_status=PdfStatus.AVAILABLE, pdf_sha256=value)
    await add_paper(db, "arxiv:5", "Failed", pdf_status=PdfStatus.FAILED, pdf_sha256=sha256)
    await add_paper(
        db, "arxiv:6", "Seeded", demo=True, pdf_status=PdfStatus.AVAILABLE, pdf_sha256=upper
    )
    await add_paper(db, "arxiv:7", "Stored", pdf_status=PdfStatus.AVAILABLE, pdf_sha256=sha256)
    keys = [*invalid, "arxiv:5", "arxiv:6", "arxiv:7"]
    await add_screenings(db, await start_run(client, project), [screening(key) for key in keys])

    for key in [*invalid, "arxiv:5"]:
        response = await client.get(f"{URL}/{key}/file", headers=as_user("bob"))
        assert (response.status_code, response.json()["detail"]) == (404, "paper.not_found"), key
        detail = await client.get(f"{URL}/{key}", headers=as_user("bob"))
        assert detail.json()["paper"]["pdf_available"] is False, key
    seeded = await client.get(f"{URL}/arxiv:6/file", headers=as_user("bob"))
    assert PREVIEW_NOTICE in pdf_page_texts(seeded.content)[0]
    assert built == []
    stored = await client.get(f"{URL}/arxiv:7/file", headers=as_user("bob"))
    assert (stored.content, built) == (data, [sha256])


async def test_stored_files_are_read_a_chunk_at_a_time(tmp_path: Path) -> None:
    path = tmp_path / "paper.pdf"
    path.write_bytes(b"x" * (2 * CHUNK_BYTES + 5))
    response = path_response(path, media_type="application/pdf", filename="paper.pdf")
    path.unlink()  # the response reads the file it opened
    chunks = [chunk async for chunk in response.body_iterator]
    assert [len(chunk) for chunk in chunks] == [CHUNK_BYTES, CHUNK_BYTES, 5]
    assert response.headers["content-length"] == str(2 * CHUNK_BYTES + 5)
    with pytest.raises(FileNotFoundError):
        path_response(path, media_type="application/pdf", filename="paper.pdf")


def test_the_data_directory_is_outside_the_repo_unless_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # away from the repo's .env
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ARP_DATA_DIR", raising=False)
    default = tmp_path / ".local" / "share" / "arp"
    assert Settings().data_dir == default
    monkeypatch.setenv("ARP_DATA_DIR", "")  # as .env.example has it
    assert Settings().data_dir == default
    monkeypatch.setenv("ARP_DATA_DIR", "~/arp-files")
    assert Settings().data_dir == tmp_path / "arp-files"
    monkeypatch.setenv("ARP_DATA_DIR", "/srv/arp")
    assert Settings().data_dir == Path("/srv/arp")

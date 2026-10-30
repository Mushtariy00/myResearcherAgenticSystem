import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentic_core.enums import StageStatus
from agentic_core.schemas import validate_stage_output
from api_testkit import (
    add_output,
    add_stage_output,
    add_stage_run,
    analysis,
    as_user,
    assert_pdf_structure,
    create_project,
    literature,
    paper,
    pdf_page_texts,
    start_run,
    team_project,
)

Factory = async_sessionmaker[AsyncSession]
URL = "/api/v1/papers"
NOW = datetime.now(UTC)
PRISM = "doi:10.5555/cvpr.2024.91234"
DELTA = "\N{GREEK SMALL LETTER DELTA}"
UMLAUT = "\N{LATIN SMALL LETTER U WITH DIAERESIS}"


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
    first = [
        paper("arxiv:1", "Depth Anything", relevance=0.9),
        paper("arxiv:2", "A Survey", relevance=0.6, decision="maybe"),
    ]
    second = [
        paper("arxiv:1", "Depth Anything V2", relevance=0.7),
        paper("arxiv:3", "Off Topic", relevance=0.3, decision="exclude"),
    ]
    hidden = [
        paper("arxiv:1", "Depth Anything (Other)", relevance=0.95, decision="maybe"),
        paper("arxiv:4", "Only in Other", relevance=0.5),
    ]
    for run_id, papers, hours in ((bobs, first, 3), (alices, second, 2), (carols, hidden, 1)):
        await add_stage_output(
            db, run_id, "literature", literature(papers), created_at=NOW - timedelta(hours=hours)
        )

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
            "title": "Depth Anything V2",  # the newest record bob can see
            "authors": ["Lihe Yang", "Bingyi Kang"],
            "year": 2024,
            "venue": "NeurIPS",
            "doi": None,
            "arxiv_id": None,
            "url": None,
            "abstract": "What Depth Anything V2 is about.",
            "citation_count": None,
            "source": "arxiv",
            "pdf_available": True,
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
    assert merged["paper"]["title"] == "Depth Anything (Other)"
    assert (merged["run_count"], merged["project_count"], merged["best_relevance"]) == (3, 2, 0.95)
    assert merged["decisions"] == ["include", "maybe"]


async def test_each_literature_attempt_counts_with_its_latest_version(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project = await team_project(client)
    run_id = await start_run(client, project)
    first = await add_stage_run(db, run_id, "literature", StageStatus.CHANGES_REQUESTED, 1)
    await add_output(db, first, literature([paper("arxiv:1", "Kept"), paper("arxiv:2", "Cut")]))
    await add_output(db, first, literature([paper("arxiv:1", "Kept")]), version=2, edited_by="bob")
    second = await add_stage_run(db, run_id, "literature", StageStatus.OUTPUT_READY, 2)
    await add_output(db, second, literature([paper("arxiv:1", "Kept"), paper("arxiv:3", "New")]))
    # Outputs from before the search existed hold only a plan; other stages never count.
    plan_only = await start_run(client, project)
    await add_stage_output(db, plan_only, "literature", {"topic": "Depth", "queries": ["a"]})
    await add_stage_output(db, plan_only, "method", {"papers": [paper("arxiv:9", "Wrong stage")]})

    page = await _library(client)
    assert sorted(_ids(page)) == ["arxiv:1", "arxiv:3"]
    assert [item["run_count"] for item in page["items"]] == [1, 1]


async def test_search_and_filters(client: httpx.AsyncClient, db: Factory) -> None:
    depth = await team_project(client)
    second = await _project(client, "Second", "bob")
    papers = [
        paper(
            "arxiv:1",
            "Monocular Depth with Transformers",
            authors=["Ana Silva"],
            year=2021,
            venue="CVPR",
            abstract="A study of attention for indoor scenes.",
            relevance=0.9,
        ),
        paper(
            PRISM,
            "Segmentation at Scale",
            authors=["Ji-woo Kim", "Bo Li"],
            year=2023,
            venue="ICCV",
            abstract="Uses 100% synthetic_data labels.",
            source="crossref",
            relevance=0.7,
            decision="maybe",
        ),
        paper(
            "openalex:W3",
            "Edge Devices",
            authors=["Carla Gomez"],
            year=2025,
            venue="IEEE TPAMI",
            abstract="Runs on phones.",
            source="openalex",
            relevance=0.4,
            decision="exclude",
        ),
    ]
    await add_stage_output(db, await start_run(client, depth), "literature", literature(papers))
    await add_stage_output(
        db,
        await start_run(client, second),
        "literature",
        literature([paper("arxiv:9", "Older Work", year=2020, relevance=0.6)]),
    )

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


async def test_papers_from_generated_outputs_are_marked_demo(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project = await team_project(client)
    generated = await start_run(client, project)
    real = await start_run(client, project)
    pending = await start_run(client, project)
    await add_stage_output(
        db,
        generated,
        "literature",
        literature([paper("arxiv:1", "Both"), paper("arxiv:2", "Generated only")]),
        degraded=True,
        degraded_reason="literature.demo_search",
    )
    await add_stage_output(db, real, "literature", literature([paper("arxiv:1", "Both")]))
    await add_stage_output(
        db,
        pending,
        "literature",
        literature([paper("arxiv:3", "Real but degraded")]),
        degraded=True,
        degraded_reason="literature.search_pending",
    )
    page = await _library(client)
    assert page["demo"] is True
    assert {item["paper"]["paper_id"]: item["demo"] for item in page["items"]} == {
        "arxiv:1": True,  # one of its records is generated
        "arxiv:2": True,
        "arxiv:3": False,  # degraded, but not generated
    }
    real_only = await _library(client, q="Real but")
    assert real_only["demo"] is False


async def _prism_runs(client: httpx.AsyncClient, db: Factory) -> tuple[str, str, str]:
    """PRISM found by bob's run (with an analysis; generated) and later by alice's run."""
    project = await team_project(client)
    first = await start_run(client, project, user="bob")
    second = await start_run(client, project, user="alice")
    notes = analysis(
        PRISM,
        ("We train for 30 epochs with AdamW (Table 2).", 4),
        (f"On NYU Depth V2, PRISM achieves {DELTA}1 of 0.871.", 6),
        ("Removing the decoder increases the error by 9.8%.", 9),
    )
    output_id = await add_stage_output(
        db,
        first,
        "literature",
        literature([paper(PRISM, "PRISM", relevance=0.9, decision_reason="Strong.")], [notes]),
        degraded=True,
        degraded_reason="literature.demo_search",
        created_at=NOW - timedelta(hours=2),
    )
    later = paper(
        PRISM,
        "PRISM: Scale-Aware Depth",
        authors=["Ji-woo Kim", f"J{UMLAUT}rgen M{UMLAUT}ller"],
        doi="10.5555/cvpr.2024.91234",
        venue="CVPR",
        relevance=0.7,
        decision="maybe",
        decision_reason="Unclear protocol.",
    )
    repeated = analysis(PRISM, ("We train for 30 epochs with AdamW (Table 2).", 4))
    await add_stage_output(
        db,
        second,
        "literature",
        literature([later], [repeated]),
        created_at=NOW - timedelta(hours=1),
    )
    return first, second, output_id


async def test_paper_detail_has_every_run_and_analysis(
    client: httpx.AsyncClient, db: Factory
) -> None:
    first, second, output_id = await _prism_runs(client, db)
    response = await client.get(f"{URL}/{PRISM}", headers=as_user("vera"))
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["paper"]["title"] == "PRISM: Scale-Aware Depth"  # the newest record
    assert detail["paper"]["doi"] == "10.5555/cvpr.2024.91234"
    assert (detail["best_relevance"], detail["demo"]) == (0.9, True)
    assert [
        (run["id"], run["decision"], run["relevance"], run["decision_reason"], run["demo"])
        for run in detail["runs"]
    ] == [
        (second, "maybe", 0.7, "Unclear protocol.", False),
        (first, "include", 0.9, "Strong.", True),
    ]
    assert (detail["runs"][0]["topic"], detail["runs"][0]["project_name"]) == (
        "Monocular depth",
        "Depth",
    )
    assert detail["runs"][0]["status"] == "queued"
    newest, oldest = detail["analyses"]
    assert (newest["run_id"], newest["demo"], len(newest["evidence"])) == (second, False, 1)
    assert (oldest["run_id"], oldest["stage_output_id"], oldest["attempt"]) == (first, output_id, 1)
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


async def test_paper_file_is_a_pdf_with_each_quote_on_its_page(
    client: httpx.AsyncClient, db: Factory
) -> None:
    await _prism_runs(client, db)
    response = await client.get(f"{URL}/{PRISM}/file", headers=as_user("vera"))
    assert response.status_code == 200, response.text
    body = response.content
    assert body.startswith(b"%PDF-1.4\n") and body.endswith(b"%%EOF\n")
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        'inline; filename="doi-10.5555-cvpr.2024.91234.pdf"'
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
    assert "Generated preview, not the published paper." in pages[0]
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


async def test_a_paper_without_analyses_still_gets_a_preview(
    client: httpx.AsyncClient, db: Factory
) -> None:
    project = await team_project(client)
    run_id = await start_run(client, project)
    await add_stage_output(
        db, run_id, "literature", literature([paper("arxiv:cs/0701234", "Old Paper", year=2007)])
    )
    response = await client.get(f"{URL}/arxiv:cs/0701234/file", headers=as_user("bob"))
    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"] == 'inline; filename="arxiv-cs-0701234.pdf"'
    assert assert_pdf_structure(response.content) == 4
    detail = await client.get(f"{URL}/arxiv:cs/0701234", headers=as_user("bob"))
    assert (detail.json()["analyses"], detail.json()["demo"]) == ([], False)

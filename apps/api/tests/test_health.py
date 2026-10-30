import re
from collections.abc import Mapping

from fastapi.testclient import TestClient

from agentic_api.headers import API_POLICY, DOCS_POLICY
from agentic_api.main import create_app
from agentic_api.settings import Settings


def make_client() -> TestClient:
    return TestClient(create_app(Settings(environment="test")))


def test_health_reports_ok() -> None:
    response = make_client().get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0", "environment": "test"}


def test_stages_are_listed_in_pipeline_order() -> None:
    stages = make_client().get("/api/v1/stages").json()
    assert [s["id"] for s in stages] == ["literature", "method", "coding", "experiment", "writing"]
    assert next(s for s in stages if s["id"] == "coding")["auto_approvable"] is False


def test_openapi_is_served_under_api_prefix() -> None:
    schema = make_client().get("/api/v1/openapi.json").json()
    assert "/api/v1/health" in schema["paths"]


def test_openapi_lists_every_stage_output_model() -> None:
    # No endpoint references them (outputs are plain JSON), but the TypeScript client needs them.
    components = make_client().get("/api/v1/openapi.json").json()["components"]["schemas"]
    for name in (
        "LiteratureOutput",
        "MethodOutput",
        "CodingOutput",
        "ExperimentOutput",
        "WritingOutput",
    ):
        assert name in components, name
    assert components["LiteratureOutput"]["properties"]["papers"]["items"] == {
        "$ref": "#/components/schemas/PaperRef"
    }


def test_production_hides_docs_and_schema() -> None:
    client = TestClient(create_app(Settings(environment="production")))
    assert client.get("/api/v1/docs").status_code == 404
    assert client.get("/api/v1/openapi.json").status_code == 404
    assert client.get("/api/v1/health").status_code == 200


def _hardening(headers: Mapping[str, str]) -> tuple[str | None, str | None, str | None]:
    return (
        headers.get("x-content-type-options"),
        headers.get("x-frame-options"),
        headers.get("content-security-policy"),
    )


def test_every_response_is_hardened() -> None:
    """API responses are data, never pages: nothing in them may run, load or be framed."""
    for environment in ("production", "development"):
        client = TestClient(create_app(Settings(environment=environment)))
        for response in (
            client.get("/api/v1/health"),
            client.get("/api/v1/docs" if environment == "production" else "/api/v1/nowhere"),
            client.post(
                "/api/v1/projects", json={"name": "x"}, headers={"origin": "https://evil.example"}
            ),
        ):
            assert _hardening(response.headers) == ("nosniff", "DENY", API_POLICY), (
                environment,
                response.request.url,
            )


def test_development_docs_may_load_swagger_ui() -> None:
    client = TestClient(create_app(Settings(environment="development")))
    docs = client.get("/api/v1/docs")
    assert docs.status_code == 200
    assert _hardening(docs.headers) == ("nosniff", "DENY", DOCS_POLICY)
    # The page loads its script and stylesheet from the CDN the policy allows, its icon from
    # FastAPI's site.
    sources = re.findall(r'(?:src|href)="(https://[^"/]+)/', docs.text)
    assert set(sources) == {"https://cdn.jsdelivr.net", "https://fastapi.tiangolo.com"}
    assert _hardening(client.get("/api/v1/openapi.json").headers)[2] == API_POLICY


def test_public_origin_may_list_several_origins() -> None:
    client = TestClient(
        create_app(
            Settings(
                environment="test", public_origin="https://demo.example, http://localhost:8080"
            )
        )
    )
    # CSRF passes for both listed origins (the request then fails auth, which is checked later).
    for origin in ("https://demo.example", "http://localhost:8080"):
        response = client.post("/api/v1/projects", json={"name": "x"}, headers={"origin": origin})
        assert response.status_code == 401, origin
    blocked = client.post(
        "/api/v1/projects", json={"name": "x"}, headers={"origin": "https://evil.example"}
    )
    assert blocked.json() == {"detail": "csrf.origin_mismatch"}

from fastapi.testclient import TestClient

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

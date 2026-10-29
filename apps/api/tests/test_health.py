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

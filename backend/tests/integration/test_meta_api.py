from app.core.config import get_settings


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_info_reports_mock_mode_and_no_bedrock_by_default(client, settings):
    client.app.dependency_overrides[get_settings] = lambda: settings
    r = client.get("/api/v1/info")
    assert r.status_code == 200
    body = r.json()
    assert body["aws_mode"] == "mock"
    assert body["bedrock_configured"] is False
    assert body["environment"] == "test"


def test_openapi_is_versioned(client):
    r = client.get("/api/v1/openapi.json")
    assert r.status_code == 200
    assert "/api/v1/health" in r.json()["paths"]


def test_cors_allows_configured_origin(client):
    r = client.options(
        "/api/v1/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"

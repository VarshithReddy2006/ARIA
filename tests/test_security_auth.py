"""Security tests for deny-by-default API key authentication (Task 3 / R-015)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.security_middleware import APIKeyMiddleware


def create_test_app(api_key: str = "secret-key-123", app_env: str = "test"):
    app = FastAPI(title="Test App")

    app.add_middleware(APIKeyMiddleware, api_key=api_key, app_env=app_env)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/v1/health")
    def v1_health():
        return {"status": "ok"}

    @app.get("/metrics")
    def metrics():
        return {"metrics": "ok"}

    @app.get("/api/v1/repositories")
    def list_repos():
        return {"repos": []}

    @app.get("/api/v1/chat")
    def chat():
        return {"message": "chat"}

    @app.get("/api/v1/graph")
    def graph():
        return {"nodes": []}

    return app


def test_public_endpoints_allow_anonymous_access():
    app = create_test_app(api_key="my-secret-key")
    client = TestClient(app)

    res_health = client.get("/health")
    assert res_health.status_code == 200

    res_v1_health = client.get("/api/v1/health")
    assert res_v1_health.status_code == 200

    res_metrics = client.get("/metrics")
    assert res_metrics.status_code == 200


def test_protected_endpoints_deny_unauthenticated_requests():
    app = create_test_app(api_key="my-secret-key")
    client = TestClient(app)

    res_repos = client.get("/api/v1/repositories")
    assert res_repos.status_code == 401
    assert res_repos.json() == {"detail": "Unauthorized. Invalid or missing API key."}

    res_chat = client.get("/api/v1/chat")
    assert res_chat.status_code == 401

    res_graph = client.get("/api/v1/graph")
    assert res_graph.status_code == 401


def test_protected_endpoints_deny_invalid_api_key():
    app = create_test_app(api_key="my-secret-key")
    client = TestClient(app)

    res = client.get("/api/v1/repositories", headers={"X-API-Key": "wrong-key"})
    assert res.status_code == 401


def test_protected_endpoints_allow_valid_x_api_key():
    app = create_test_app(api_key="my-secret-key")
    client = TestClient(app)

    res = client.get("/api/v1/repositories", headers={"X-API-Key": "my-secret-key"})
    assert res.status_code == 200
    assert res.json() == {"repos": []}


def test_protected_endpoints_allow_valid_bearer_token():
    app = create_test_app(api_key="my-secret-key")
    client = TestClient(app)

    res = client.get(
        "/api/v1/repositories",
        headers={"Authorization": "Bearer my-secret-key"},
    )
    assert res.status_code == 200


def test_options_preflight_bypasses_auth():
    app = create_test_app(api_key="my-secret-key")
    client = TestClient(app)

    res = client.options("/api/v1/chat")
    # The fixture intentionally has no CORSMiddleware, so routing returns 405
    # after API-key authentication is bypassed. The production application adds
    # CORSMiddleware and returns 200 for a real CORS preflight.
    assert res.status_code != 401


def test_production_mode_fails_startup_without_api_key():
    app = FastAPI()
    with pytest.raises(
        RuntimeError, match="API_KEY must be configured when running in production mode"
    ):
        APIKeyMiddleware(app, api_key="", app_env="production")

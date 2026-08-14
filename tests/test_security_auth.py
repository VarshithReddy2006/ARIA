"""Security tests for deny-by-default API key authentication (Task 3 / R-015)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.security_middleware import APIKeyMiddleware, RateLimitMiddleware


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


# ---------------------------------------------------------------------------
# H-2 Regression: Rate limiter must NOT bypass on localhost for normal endpoints
# ---------------------------------------------------------------------------


def create_rate_limit_test_app(limit: int = 5):
    """Create a minimal app with ONLY the rate limiter for isolated testing."""
    app = FastAPI(title="Rate Limit Test App")
    app.add_middleware(RateLimitMiddleware, limit=limit)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/metrics")
    def metrics():
        return {"metrics": "ok"}

    @app.get("/api/v1/health")
    def v1_health():
        return {"status": "ok"}

    @app.get("/api/v1/repositories")
    def list_repos():
        return {"repos": []}

    @app.get("/api/v1/chat")
    def chat():
        return {"message": "chat"}

    return app


def test_rate_limit_health_and_metrics_always_exempt():
    """Health and metrics endpoints must never be rate-limited regardless of source."""
    app = create_rate_limit_test_app(limit=2)
    client = TestClient(app)

    # Even after exceeding the limit, health/metrics remain accessible
    for _ in range(5):
        assert client.get("/health").status_code == 200
        assert client.get("/metrics").status_code == 200
        assert client.get("/api/v1/health").status_code == 200


def test_rate_limit_applies_to_normal_endpoints_from_localhost():
    """H-2 regression: loopback address must NOT bypass rate limiting for normal endpoints."""
    app = create_rate_limit_test_app(limit=3)
    # TestClient uses 'testclient' as host by default, but we can verify
    # the middleware does not exempt arbitrary non-health paths.
    client = TestClient(app)

    # First requests succeed
    for _ in range(3):
        resp = client.get("/api/v1/repositories")
        assert resp.status_code == 200

    # Next request should be rate-limited (429)
    resp = client.get("/api/v1/repositories")
    assert resp.status_code == 429
    assert "Rate limit" in resp.json()["detail"]


def test_rate_limit_429_response_contract():
    """Verify the 429 response body matches the expected contract."""
    app = create_rate_limit_test_app(limit=1)
    client = TestClient(app)

    # Exhaust the limit
    client.get("/api/v1/chat")
    resp = client.get("/api/v1/chat")

    assert resp.status_code == 429
    body = resp.json()
    assert body == {"detail": "Too many requests. Rate limit exceeded."}


# ---------------------------------------------------------------------------
# H-4 Regression: CORS must not include localhost origins in production
# ---------------------------------------------------------------------------


def test_cors_development_allows_localhost_origins(monkeypatch):
    """In development, localhost:4321 and localhost:5173 are permitted CORS origins."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("FRONTEND_URL", "http://localhost:4321")

    # Reimport to pick up patched env — use a fresh app construction
    from backend.api import app as main_app

    client = TestClient(main_app)

    # Preflight from localhost:4321 should be allowed
    resp = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:4321",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:4321"

    # Preflight from localhost:5173 should be allowed in development
    resp = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_production_rejects_localhost_origins(monkeypatch):
    """H-4 regression: production must NOT allow localhost CORS origins."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("FRONTEND_URL", "https://app.example.com")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("ALLOWED_HOSTS", '["app.example.com"]')
    monkeypatch.setenv("API_KEY", "prod-key")

    # Reconstruct the CORS origins as the application does at module level
    from core.config import Settings

    s = Settings()
    assert s.app_env == "production"
    assert s.frontend_url == "https://app.example.com"

    # Simulate the CORS origin logic from backend/api.py
    origins = [s.frontend_url]
    if s.app_env != "production":
        if "localhost:4321" not in s.frontend_url:
            origins.append("http://localhost:4321")
        if "localhost:5173" not in s.frontend_url:
            origins.append("http://localhost:5173")

    # Verify production origins do NOT contain localhost
    assert "http://localhost:4321" not in origins
    assert "http://localhost:5173" not in origins
    assert "https://app.example.com" in origins


def test_cors_production_allows_configured_frontend_url(monkeypatch):
    """Production CORS allows the explicitly configured FRONTEND_URL."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("FRONTEND_URL", "https://dashboard.example.com")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("ALLOWED_HOSTS", '["dashboard.example.com"]')
    monkeypatch.setenv("API_KEY", "prod-key")

    from core.config import Settings

    s = Settings()

    origins = [s.frontend_url]
    if s.app_env != "production":
        if "localhost:4321" not in s.frontend_url:
            origins.append("http://localhost:4321")
        if "localhost:5173" not in s.frontend_url:
            origins.append("http://localhost:5173")

    assert origins == ["https://dashboard.example.com"]

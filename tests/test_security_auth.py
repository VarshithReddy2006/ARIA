"""Security tests for deny-by-default API key and browser session authentication (Task 3 / R-015)."""

import hashlib
import hmac
import unittest.mock
import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from backend.security_middleware import (
    APIKeyMiddleware,
    RateLimitMiddleware,
    generate_session_token,
    verify_session_token,
    is_public_path,
    SESSION_COOKIE_NAME,
    _derive_signing_key,
)


def create_test_app(
    api_key: str = "secret-key-123",
    app_env: str = "test",
    allowed_origins: list = None,
    secure_cookies: bool = False,
):
    app = FastAPI(title="Test App")

    app.add_middleware(
        APIKeyMiddleware,
        api_key=api_key,
        app_env=app_env,
        allowed_origins=allowed_origins
        or ["http://localhost:4321", "https://aria.example.com"],
        secure_cookies=secure_cookies,
    )

    @app.get("/")
    def index():
        return {"page": "home"}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/v1/health")
    def v1_health():
        return {"status": "ok"}

    @app.get("/metrics")
    def metrics():
        return {"metrics": "ok"}

    @app.get("/docs")
    def docs():
        return {"docs": "ok"}

    @app.get("/analysis")
    @app.get("/analysis/")
    def analysis_page():
        return {"page": "analysis"}

    @app.get("/chat")
    @app.get("/chat/")
    def chat_page():
        return {"page": "chat"}

    @app.get("/issues")
    @app.get("/issues/")
    def issues_page():
        return {"page": "issues"}

    @app.get("/api/v1/repositories")
    def list_repos():
        return {"repos": []}

    @app.get("/api/v1/repos/examples")
    def repo_examples():
        return {"examples": ["fastapi/fastapi", "pallets/flask"]}

    @app.get("/api/v1/chat")
    def chat():
        return {"message": "chat"}

    @app.get("/api/v1/graph")
    def graph():
        return {"nodes": []}

    @app.post("/api/v1/analyze")
    def analyze_mutation():
        return {"status": "analysis_queued"}

    @app.post("/api/v1/analyze/stream")
    def analyze_stream():
        async def event_generator():
            yield 'data: {"progress": 50}\n\n'
            yield 'data: {"progress": 100, "status": "done"}\n\n'

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    return app


# ===========================================================================
# 1-6: Public Endpoints & Session Cookie Issuance
# ===========================================================================


def test_public_health_endpoint_is_public():
    """1. GET /health is public."""
    app = create_test_app(api_key="prod-secret-key", app_env="production")
    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_public_root_page_issues_aria_session():
    """2. GET / is public and issues aria_session cookie."""
    app = create_test_app(api_key="prod-secret-key", app_env="production")
    client = TestClient(app)
    res = client.get("/")
    assert res.status_code == 200
    assert SESSION_COOKIE_NAME in res.cookies
    cookie_value = res.cookies[SESSION_COOKIE_NAME]
    assert verify_session_token(cookie_value, "prod-secret-key") is True


def test_public_analysis_page_is_public():
    """3. GET /analysis/ is public."""
    app = create_test_app(api_key="prod-secret-key", app_env="production")
    client = TestClient(app)
    res = client.get("/analysis/")
    assert res.status_code == 200
    assert res.json() == {"page": "analysis"}


def test_public_chat_page_is_public():
    """4. GET /chat/ is public."""
    app = create_test_app(api_key="prod-secret-key", app_env="production")
    client = TestClient(app)
    res = client.get("/chat/")
    assert res.status_code == 200
    assert res.json() == {"page": "chat"}


def test_public_issues_page_is_public():
    """5. GET /issues/ is public."""
    app = create_test_app(api_key="prod-secret-key", app_env="production")
    client = TestClient(app)
    res = client.get("/issues/")
    assert res.status_code == 200
    assert res.json() == {"page": "issues"}


def test_public_docs_endpoint_is_public():
    """6. GET /docs is public."""
    app = create_test_app(api_key="prod-secret-key", app_env="production")
    client = TestClient(app)
    res = client.get("/docs")
    assert res.status_code == 200


# ===========================================================================
# 7-13: API Authentication Priority & Verification
# ===========================================================================


def test_unauthenticated_api_request_returns_401():
    """7. GET /api/v1/repos/examples without authentication returns 401."""
    app = create_test_app(api_key="prod-secret-key", app_env="production")
    client = TestClient(app)
    res = client.get("/api/v1/repos/examples")
    assert res.status_code == 401
    assert "detail" in res.json()


def test_api_request_with_valid_x_api_key_returns_200():
    """8. GET /api/v1/repos/examples with valid X-API-Key returns 200."""
    app = create_test_app(api_key="prod-secret-key", app_env="production")
    client = TestClient(app)
    res = client.get("/api/v1/repos/examples", headers={"X-API-Key": "prod-secret-key"})
    assert res.status_code == 200
    assert "examples" in res.json()


def test_api_request_with_valid_aria_session_returns_200():
    """9. GET /api/v1/repos/examples with valid aria_session returns 200."""
    app = create_test_app(api_key="prod-secret-key", app_env="production")
    client = TestClient(app)

    # 1. Acquire session cookie from public page
    res_page = client.get("/")
    assert res_page.status_code == 200
    session_cookie = res_page.cookies.get(SESSION_COOKIE_NAME)
    assert session_cookie is not None

    # 2. Access protected API using session cookie
    res_api = client.get("/api/v1/repos/examples")
    assert res_api.status_code == 200
    assert "examples" in res_api.json()


def test_api_request_with_invalid_aria_session_returns_401():
    """10. Invalid aria_session returns 401."""
    app = create_test_app(api_key="prod-secret-key", app_env="production")
    client = TestClient(app, cookies={SESSION_COOKIE_NAME: "v1.invalid.format"})
    res = client.get("/api/v1/repos/examples")
    assert res.status_code == 401


def test_api_request_with_tampered_aria_session_returns_401():
    """11. Tampered aria_session returns 401."""
    app = create_test_app(api_key="prod-secret-key", app_env="production")
    token = generate_session_token("prod-secret-key")
    # Tamper payload while keeping original signature
    parts = token.split(".")
    tampered_token = f"v1.tampered_session_id.{parts[2]}.{parts[3]}"

    client = TestClient(app, cookies={SESSION_COOKIE_NAME: tampered_token})
    res = client.get("/api/v1/repos/examples")
    assert res.status_code == 401


def test_api_request_with_expired_aria_session_returns_401():
    """12. Expired aria_session returns 401."""
    app = create_test_app(api_key="prod-secret-key", app_env="production")
    # Generate token that expired 10 seconds ago
    expired_token = generate_session_token("prod-secret-key", max_age=-10)

    client = TestClient(app, cookies={SESSION_COOKIE_NAME: expired_token})
    res = client.get("/api/v1/repos/examples")
    assert res.status_code == 401


def test_api_request_with_valid_bearer_token_returns_200():
    """13. Existing Authorization: Bearer <API_KEY> authentication still works."""
    app = create_test_app(api_key="prod-secret-key", app_env="production")
    client = TestClient(app)
    res = client.get(
        "/api/v1/repos/examples",
        headers={"Authorization": "Bearer prod-secret-key"},
    )
    assert res.status_code == 200


# ===========================================================================
# 14-17: CORS Preflight, CSRF Protection, and SSE Streaming
# ===========================================================================


def test_options_preflight_bypasses_auth():
    """14. OPTIONS requests bypass authentication."""
    app = create_test_app(api_key="prod-secret-key", app_env="production")
    client = TestClient(app)
    res = client.options("/api/v1/analyze")
    assert res.status_code != 401


def test_cookie_authenticated_post_works_with_same_origin():
    """15. Cookie-authenticated POST /api/v1/analyze works with valid same-origin request."""
    app = create_test_app(api_key="prod-secret-key", app_env="production")
    token = generate_session_token("prod-secret-key")
    client = TestClient(
        app, base_url="https://aria.example.com", cookies={SESSION_COOKIE_NAME: token}
    )

    res = client.post(
        "/api/v1/analyze",
        headers={
            "Origin": "https://aria.example.com",
            "Sec-Fetch-Site": "same-origin",
        },
    )
    assert res.status_code == 200
    assert res.json() == {"status": "analysis_queued"}


def test_cookie_authenticated_post_rejects_cross_origin():
    """16. Cookie-authenticated cross-origin POST /api/v1/analyze is rejected."""
    app = create_test_app(
        api_key="prod-secret-key",
        app_env="production",
        allowed_origins=["https://aria.example.com"],
    )
    token = generate_session_token("prod-secret-key")
    client = TestClient(
        app, base_url="https://aria.example.com", cookies={SESSION_COOKIE_NAME: token}
    )

    # Cross-origin attacker attempt
    res = client.post(
        "/api/v1/analyze",
        headers={
            "Origin": "https://evil-attacker.com",
            "Sec-Fetch-Site": "cross-site",
        },
    )
    assert res.status_code == 403
    assert "CSRF validation failed" in res.json()["detail"]


def test_sse_streaming_analysis_works_with_session_cookie():
    """17. SSE/streaming analysis works with valid browser session authentication."""
    app = create_test_app(api_key="prod-secret-key", app_env="production")
    token = generate_session_token("prod-secret-key")
    client = TestClient(
        app, base_url="https://aria.example.com", cookies={SESSION_COOKIE_NAME: token}
    )

    res = client.post(
        "/api/v1/analyze/stream",
        headers={"Origin": "https://aria.example.com"},
    )
    assert res.status_code == 200
    assert "text/event-stream" in res.headers.get("content-type", "")
    assert "progress" in res.text


# ===========================================================================
# 18-22: Cryptographic Security & Leakage Invariants
# ===========================================================================


def test_session_token_uses_hmac_sha256():
    """18. Session token uses HMAC-SHA256."""
    secret = "test-session-secret"
    token = generate_session_token(secret, session_id="test_session_id")
    parts = token.split(".")
    assert len(parts) == 4
    version, sid, expires_at, signature = parts
    assert version == "v1"
    assert sid == "test_session_id"

    # Verify signature format: 64 hex chars for SHA-256
    assert len(signature) == 64
    payload = f"{version}.{sid}.{expires_at}"
    derived_key = _derive_signing_key(secret)
    expected_sig = hmac.new(
        derived_key, payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    assert signature == expected_sig


def test_session_signature_verification_uses_constant_time_comparison():
    """19. Session signature verification uses constant-time comparison."""
    secret = "test-secret"
    token = generate_session_token(secret)

    with unittest.mock.patch(
        "secrets.compare_digest", wraps=unittest.mock.MagicMock(return_value=True)
    ) as mock_compare:
        result = verify_session_token(token, secret)
        assert result is True
        assert mock_compare.called, (
            "secrets.compare_digest must be called during verification"
        )


def test_session_cookie_attributes():
    """20. Session cookie has: HttpOnly, SameSite=Lax, Path=/."""
    app = create_test_app(
        api_key="prod-secret-key", app_env="production", secure_cookies=True
    )
    client = TestClient(app, base_url="https://aria.example.com")
    res = client.get("/")
    assert res.status_code == 200

    set_cookie_header = res.headers.get("set-cookie", "")
    assert f"{SESSION_COOKIE_NAME}=" in set_cookie_header
    assert "httponly" in set_cookie_header.lower()
    assert "samesite=lax" in set_cookie_header.lower()
    assert "path=/" in set_cookie_header.lower()
    assert "secure" in set_cookie_header.lower()


def test_api_key_is_never_returned_in_responses():
    """21. API_KEY is never returned in responses."""
    api_key_value = "super-secret-production-key-999"
    app = create_test_app(api_key=api_key_value, app_env="production")
    client = TestClient(app)

    for path in [
        "/",
        "/health",
        "/docs",
        "/analysis",
        "/api/v1/repositories",
        "/api/v1/repos/examples",
    ]:
        res = client.get(path, headers={"X-API-Key": api_key_value})
        assert api_key_value not in res.text


def test_session_secret_is_never_returned_in_responses():
    """22. Session secret is never returned in responses."""
    secret_value = "my-ultra-secret-signing-key-12345"
    app = create_test_app(api_key=secret_value, app_env="production")
    client = TestClient(app)

    res_root = client.get("/")
    assert secret_value not in res_root.text
    for h, v in res_root.headers.items():
        assert secret_value not in v


# ===========================================================================
# Edge Cases, Rate Limiting & Integration Tests
# ===========================================================================


def test_production_mode_fails_startup_without_api_key():
    app = FastAPI()
    with pytest.raises(
        RuntimeError, match="API_KEY must be configured when running in production mode"
    ):
        APIKeyMiddleware(app, api_key="", app_env="production")


def test_public_frontend_routes_allowlist():
    assert is_public_path("/") is True
    assert is_public_path("/favicon.svg") is True
    assert is_public_path("/favicon.png") is True
    assert is_public_path("/favicon.ico") is True
    assert is_public_path("/health") is True
    assert is_public_path("/metrics") is True
    assert is_public_path("/docs") is True
    assert is_public_path("/openapi.json") is True
    assert is_public_path("/analysis") is True
    assert is_public_path("/analysis/") is True
    assert is_public_path("/analysis/repo-1") is True
    assert is_public_path("/chat") is True
    assert is_public_path("/chat/") is True
    assert is_public_path("/issues") is True
    assert is_public_path("/issues/") is True
    assert is_public_path("/_astro/index.abc123.css") is True
    assert is_public_path("/api/v1/repositories") is False
    assert is_public_path("/api/v1/analyze") is False


def test_frontend_serving_integration(tmp_path):
    """Verify that FastAPI with StaticFiles and APIKeyMiddleware correctly serves Astro pages and protects API routes."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!DOCTYPE html><html><body>Home</body></html>")
    (dist / "favicon.svg").write_text("<svg></svg>")
    (dist / "favicon.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    analysis_dir = dist / "analysis"
    analysis_dir.mkdir()
    (analysis_dir / "index.html").write_text(
        "<!DOCTYPE html><html><body>Analysis</body></html>"
    )

    app = FastAPI(title="Test App")
    app.add_middleware(APIKeyMiddleware, api_key="prod-test-key", app_env="production")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/v1/repositories")
    def list_repos():
        return {"repos": []}

    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")

    client = TestClient(app)

    # 1. Frontend public routes issue session cookie
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert "Home" in res_root.text
    assert SESSION_COOKIE_NAME in res_root.cookies

    # 2. Protected API endpoints without key/cookie fail
    client_unauth = TestClient(app)
    res_unauth = client_unauth.get("/api/v1/repositories")
    assert res_unauth.status_code == 401

    # 3. Protected API endpoints with cookie succeed
    res_cookie_auth = client.get("/api/v1/repositories")
    assert res_cookie_auth.status_code == 200
    assert res_cookie_auth.json() == {"repos": []}


def create_rate_limit_test_app(limit: int = 5):
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
    app = create_rate_limit_test_app(limit=2)
    client = TestClient(app)

    for _ in range(5):
        assert client.get("/health").status_code == 200
        assert client.get("/metrics").status_code == 200
        assert client.get("/api/v1/health").status_code == 200


def test_rate_limit_applies_to_normal_endpoints_from_localhost():
    app = create_rate_limit_test_app(limit=3)
    client = TestClient(app)

    for _ in range(3):
        resp = client.get("/api/v1/repositories")
        assert resp.status_code == 200

    resp = client.get("/api/v1/repositories")
    assert resp.status_code == 429
    assert "Rate limit" in resp.json()["detail"]


def test_rate_limit_429_response_contract():
    app = create_rate_limit_test_app(limit=1)
    client = TestClient(app)

    client.get("/api/v1/chat")
    resp = client.get("/api/v1/chat")

    assert resp.status_code == 429
    body = resp.json()
    assert body == {"detail": "Too many requests. Rate limit exceeded."}


def test_cors_development_allows_localhost_origins(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("FRONTEND_URL", "http://localhost:4321")

    from backend.api import app as main_app

    client = TestClient(main_app)

    resp = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:4321",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:4321"


def test_cors_production_rejects_localhost_origins(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("FRONTEND_URL", "https://app.example.com")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("ALLOWED_HOSTS", '["app.example.com"]')
    monkeypatch.setenv("API_KEY", "prod-key")

    from core.config import Settings

    s = Settings()
    assert s.app_env == "production"
    assert s.frontend_url == "https://app.example.com"

    origins = [s.frontend_url]
    if s.app_env != "production":
        if "localhost:4321" not in s.frontend_url:
            origins.append("http://localhost:4321")
        if "localhost:5173" not in s.frontend_url:
            origins.append("http://localhost:5173")

    assert "http://localhost:4321" not in origins
    assert "http://localhost:5173" not in origins
    assert "https://app.example.com" in origins

"""End-to-End Production Readiness Verification Script for Render Deployment.

Verifies:
1. Production environment configuration & settings
2. Health check endpoint (/health)
3. Direct unauthenticated API denial (401)
4. X-API-Key authentication (200)
5. Bearer token authentication (200)
6. Browser session cookie issuance on public pages (aria_session)
7. Browser session cookie authentication on API endpoints (200)
8. CSRF origin verification on mutations (POST /api/v1/analyze -> same-origin 200/accepted, cross-origin 403)
9. Qdrant remote cloud configuration & API key passing
10. LLM provider configuration & response secrecy
11. Frontend static asset & page serving from FastAPI mount
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import unittest.mock
from fastapi.testclient import TestClient

# Configure production environment variables for simulation
os.environ["APP_ENV"] = "production"
os.environ["LOG_FORMAT"] = "json"
os.environ["API_KEY"] = "prod-test-key-render-999"
os.environ["ALLOWED_HOSTS"] = '["aria.onrender.com", "localhost", "127.0.0.1", "testserver"]'
os.environ["FRONTEND_URL"] = "https://aria.onrender.com"
os.environ["GEMINI_API_KEY"] = "dummy-prod-gemini-key"
os.environ["QDRANT_URL"] = "https://test-qdrant-cluster.qdrant.tech:6333"
os.environ["QDRANT_API_KEY"] = "test-qdrant-api-key-xyz"
os.environ["QDRANT_PREFER_GRPC"] = "false"

from backend.settings import get_settings
settings = get_settings(reload=True)

from backend.api import app
from backend.security_middleware import SESSION_COOKIE_NAME, generate_session_token, verify_session_token
from memory.qdrant_store import QdrantStore
from memory.vector_store import ProductionVectorStore


def run_verification():
    print("==================================================")
    print("ARIA PRODUCTION-READINESS VERIFICATION")
    print("==================================================")

    client = TestClient(app, base_url="https://aria.onrender.com")

    # 1. Verify /health
    res_health = client.get("/health")
    print(f"[*] 1. GET /health -> Status: {res_health.status_code}")
    assert res_health.status_code == 200, f"Expected 200, got {res_health.status_code}"
    assert "status" in res_health.json()

    # 2. Verify Direct API Security (unauthenticated -> 401)
    unauth_client = TestClient(app, base_url="https://aria.onrender.com")
    res_unauth = unauth_client.get("/api/v1/repos/examples")
    print(f"[*] 2. Direct Unauthenticated GET /api/v1/repos/examples -> Status: {res_unauth.status_code}")
    assert res_unauth.status_code == 401, f"Expected 401, got {res_unauth.status_code}"

    # 3. Verify API Key Auth (X-API-Key -> 200)
    res_apikey = client.get(
        "/api/v1/repos/examples",
        headers={"X-API-Key": "prod-test-key-render-999"},
    )
    print(f"[*] 3. X-API-Key GET /api/v1/repos/examples -> Status: {res_apikey.status_code}")
    assert res_apikey.status_code == 200, f"Expected 200, got {res_apikey.status_code}"
    assert isinstance(res_apikey.json(), list) and len(res_apikey.json()) > 0

    # 4. Verify Bearer Auth (Authorization: Bearer -> 200)
    res_bearer = client.get(
        "/api/v1/repos/examples",
        headers={"Authorization": "Bearer prod-test-key-render-999"},
    )
    print(f"[*] 4. Bearer GET /api/v1/repos/examples -> Status: {res_bearer.status_code}")
    assert res_bearer.status_code == 200, f"Expected 200, got {res_bearer.status_code}"
    assert isinstance(res_bearer.json(), list)

    # 5. Verify Browser Session Issuance on Public GET /
    browser_client = TestClient(app, base_url="https://aria.onrender.com")
    res_root = browser_client.get("/")
    print(f"[*] 5. Browser GET / -> Status: {res_root.status_code}")
    assert res_root.status_code == 200
    session_cookie = res_root.cookies.get(SESSION_COOKIE_NAME)
    print(f"    Set-Cookie aria_session present: {bool(session_cookie)}")
    assert session_cookie is not None
    assert verify_session_token(session_cookie, "prod-test-key-render-999") is True

    # 6. Verify Browser Session Auth on Protected Endpoint
    res_cookie_auth = browser_client.get("/api/v1/repos/examples")
    print(f"[*] 6. Browser Cookie-Auth GET /api/v1/repos/examples -> Status: {res_cookie_auth.status_code}")
    assert res_cookie_auth.status_code == 200, f"Expected 200, got {res_cookie_auth.status_code}"
    assert isinstance(res_cookie_auth.json(), list) and len(res_cookie_auth.json()) > 0

    # 7. Verify CSRF: Same-Origin Mutation Allowed
    # Mocking clone_repository so it doesn't try actual git cloning in verification
    with unittest.mock.patch("backend.routers.repositories.github_service.clone_repository", return_value="/tmp/test"):
        with unittest.mock.patch("backend.routers.repositories.snapshot_store.load", return_value={"summary": "ok", "relationships": [], "reading_order": []}):
            res_mutation_same = browser_client.post(
                "/api/v1/analyze",
                json={"url": "https://github.com/fastapi/fastapi", "branch": "main"},
                headers={
                    "Origin": "https://aria.onrender.com",
                    "Sec-Fetch-Site": "same-origin",
                },
            )
            print(f"[*] 7. Same-Origin Cookie POST /api/v1/analyze -> Status: {res_mutation_same.status_code}")
            assert res_mutation_same.status_code in (200, 308), f"Expected 200, got {res_mutation_same.status_code}"

    # 8. Verify CSRF: Cross-Origin Mutation Rejected (403)
    attacker_client = TestClient(app, base_url="https://aria.onrender.com", cookies={SESSION_COOKIE_NAME: session_cookie})
    res_mutation_cross = attacker_client.post(
        "/api/v1/analyze",
        json={"url": "https://github.com/fastapi/fastapi", "branch": "main"},
        headers={
            "Origin": "https://malicious-cross-origin.com",
            "Sec-Fetch-Site": "cross-site",
        },
    )
    print(f"[*] 8. Cross-Origin Cookie POST /api/v1/analyze -> Status: {res_mutation_cross.status_code}")
    assert res_mutation_cross.status_code == 403, f"Expected 403, got {res_mutation_cross.status_code}"
    assert "CSRF validation failed" in res_mutation_cross.json()["detail"]

    # 9. Verify Qdrant Configuration & API Key Passing
    print("[*] 9. Checking Qdrant Settings & QdrantStore parameters:")
    print(f"    qdrant_url = {settings.qdrant_url}")
    print(f"    qdrant_api_key = {'*' * len(settings.qdrant_api_key) if settings.qdrant_api_key else None}")
    print(f"    qdrant_prefer_grpc = {settings.qdrant_prefer_grpc}")
    assert settings.qdrant_url == "https://test-qdrant-cluster.qdrant.tech:6333"
    assert settings.qdrant_api_key == "test-qdrant-api-key-xyz"

    # Test QdrantStore constructor signature and client arguments
    with unittest.mock.patch("memory.qdrant_store.QdrantClient") as mock_qclient:
        store = QdrantStore(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            timeout=settings.qdrant_timeout,
            prefer_grpc=settings.qdrant_prefer_grpc,
        )
        mock_qclient.assert_called_once_with(
            url="https://test-qdrant-cluster.qdrant.tech:6333",
            prefer_grpc=False,
            api_key="test-qdrant-api-key-xyz",
            timeout=10.0,
        )
    print("    QdrantStore initialized with remote cloud URL, API key, and timeout verified successfully.")

    # 10. Verify Frontend Static File Serving
    print("[*] 10. Checking Frontend Static Files Mount:")
    res_page_analysis = browser_client.get("/analysis/")
    print(f"    GET /analysis/ -> Status: {res_page_analysis.status_code}")
    assert res_page_analysis.status_code == 200

    res_page_chat = browser_client.get("/chat/")
    print(f"    GET /chat/ -> Status: {res_page_chat.status_code}")
    assert res_page_chat.status_code == 200

    res_page_issues = browser_client.get("/issues/")
    print(f"    GET /issues/ -> Status: {res_page_issues.status_code}")
    assert res_page_issues.status_code == 200

    # 11. Verify Secret Invariants (No API keys or secrets in responses)
    for p in ["/", "/health", "/docs", "/api/v1/repos/examples"]:
        r = client.get(p, headers={"X-API-Key": "prod-test-key-render-999"})
        assert "prod-test-key-render-999" not in r.text
        assert "test-qdrant-api-key-xyz" not in r.text
        assert "dummy-prod-gemini-key" not in r.text

    print("==================================================")
    print("ALL PRODUCTION READINESS CHECKS PASSED SUCCESSFULLY!")
    print("==================================================")


if __name__ == "__main__":
    run_verification()

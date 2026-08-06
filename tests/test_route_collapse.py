"""Regression tests for canonical API routing.

The application exposes its API only under ``/api/v1``. Legacy ``/api/*``
requests are handled by redirect middleware and must not be mounted as routes.
Operational health/readiness endpoints remain top-level for deployment probes.
"""

from fastapi.testclient import TestClient
from backend.api import app

client = TestClient(app, follow_redirects=False)


def test_canonical_route_registration():
    """Ensure the API is not accidentally mounted again under legacy prefixes."""
    route_paths = [route.path for route in app.routes if hasattr(route, "path")]
    legacy_routes = [
        path
        for path in route_paths
        if path.startswith("/api/") and not path.startswith("/api/v1/")
    ]
    assert legacy_routes == []
    # The current API has 121 canonical and framework routes. This budget still
    # catches accidental duplicate router mounts without prohibiting endpoints.
    assert len(route_paths) <= 125


def test_all_route_paths_use_canonical_or_operational_prefixes():
    """Allow canonical API, documented framework, and deployment probe routes."""
    allowed_prefixes = (
        "/api/v1",
        "/health",
        "/ready",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/redoc",
    )
    for route in app.routes:
        if hasattr(route, "path"):
            assert route.path.startswith(allowed_prefixes)


def test_legacy_api_prefix_308_redirect():
    """Verify that legacy /api/ endpoints redirect to /api/v1/ with 308 status code and Deprecation header."""
    response = client.get(
        "/api/repositories/test-owner/test-repo/summary", follow_redirects=False
    )
    assert response.status_code == 308
    assert (
        response.headers.get("location")
        == "/api/v1/repositories/test-owner/test-repo/summary"
    )
    assert response.headers.get("deprecation") == "true"

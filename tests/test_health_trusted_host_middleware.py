"""Tests for HealthExemptTrustedHostMiddleware and Host header enforcement.

Verifies:
1. /health and /ready with public Azure hostname -> 200
2. /health and /ready with localhost -> 200
3. /health and /ready with dynamic pod IP (100.100.0.25:8001) -> 200
4. Normal application routes with untrusted Host header -> 400 Bad Request
5. Normal application routes with trusted Host header (Azure / Vercel) -> not rejected by host validation
6. ALLOWED_HOSTS contains NO wildcard.
"""

import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from backend.security_middleware import HealthExemptTrustedHostMiddleware
from core.config import Settings


def dummy_health(request):
    return JSONResponse({"status": "healthy"})


def dummy_ready(request):
    return JSONResponse({"status": "ready"})


def dummy_api(request):
    return JSONResponse({"data": "ok"})


@pytest.fixture
def probe_app():
    """Create a minimal Starlette test app mirroring production middleware configuration."""
    routes = [
        Route("/health", dummy_health),
        Route("/ready", dummy_ready),
        Route("/api/v1/health", dummy_health),
        Route("/api/v1/ready", dummy_ready),
        Route("/api/repos/examples", dummy_api),
        Route("/api/analyze", dummy_api),
    ]
    app = Starlette(routes=routes)
    allowed_hosts = [
        "aria-api.lemonriver-308dc42a.eastasia.azurecontainerapps.io",
        "aria-orpin-five.vercel.app",
        "localhost",
        "127.0.0.1",
    ]
    app.add_middleware(HealthExemptTrustedHostMiddleware, allowed_hosts=allowed_hosts)
    return app


class TestHealthTrustedHostMiddleware:
    def test_health_with_public_azure_hostname(self, probe_app):
        client = TestClient(probe_app)
        res = client.get(
            "/health",
            headers={
                "Host": "aria-api.lemonriver-308dc42a.eastasia.azurecontainerapps.io"
            },
        )
        assert res.status_code == 200
        assert res.json() == {"status": "healthy"}

    def test_ready_with_public_azure_hostname(self, probe_app):
        client = TestClient(probe_app)
        res = client.get(
            "/ready",
            headers={
                "Host": "aria-api.lemonriver-308dc42a.eastasia.azurecontainerapps.io"
            },
        )
        assert res.status_code == 200
        assert res.json() == {"status": "ready"}

    def test_health_with_localhost(self, probe_app):
        client = TestClient(probe_app)
        res = client.get("/health", headers={"Host": "localhost:8001"})
        assert res.status_code == 200

    def test_ready_with_localhost(self, probe_app):
        client = TestClient(probe_app)
        res = client.get("/ready", headers={"Host": "127.0.0.1:8001"})
        assert res.status_code == 200

    def test_health_with_dynamic_pod_ip(self, probe_app):
        """Dynamic pod IP (100.100.0.25:8001) used by Azure Container Apps probe is allowed on /health."""
        client = TestClient(probe_app)
        res = client.get("/health", headers={"Host": "100.100.0.25:8001"})
        assert res.status_code == 200
        assert res.json() == {"status": "healthy"}

    def test_ready_with_dynamic_pod_ip(self, probe_app):
        """Dynamic pod IP used by Azure Container Apps probe is allowed on /ready."""
        client = TestClient(probe_app)
        res = client.get("/ready", headers={"Host": "100.100.0.25:8001"})
        assert res.status_code == 200
        assert res.json() == {"status": "ready"}

    def test_normal_route_with_untrusted_host_rejected_400(self, probe_app):
        """Normal application endpoints reject untrusted/dynamic pod IP Host headers with 400."""
        client = TestClient(probe_app)
        res = client.get("/api/repos/examples", headers={"Host": "100.100.0.25:8001"})
        assert res.status_code == 400
        assert "Invalid host header" in res.text

    def test_normal_route_with_evil_host_rejected_400(self, probe_app):
        """Attacker host header is strictly rejected with 400."""
        client = TestClient(probe_app)
        res = client.get("/api/repos/examples", headers={"Host": "evil-attacker.com"})
        assert res.status_code == 400
        assert "Invalid host header" in res.text

    def test_normal_route_with_trusted_azure_host_allowed(self, probe_app):
        """Trusted production Azure hostname passes host header validation."""
        client = TestClient(probe_app)
        res = client.get(
            "/api/repos/examples",
            headers={
                "Host": "aria-api.lemonriver-308dc42a.eastasia.azurecontainerapps.io"
            },
        )
        assert res.status_code == 200

    def test_normal_route_with_trusted_vercel_host_allowed(self, probe_app):
        """Trusted production Vercel hostname passes host header validation."""
        client = TestClient(probe_app)
        res = client.get(
            "/api/repos/examples", headers={"Host": "aria-orpin-five.vercel.app"}
        )
        assert res.status_code == 200

    def test_allowed_hosts_config_contains_no_global_wildcard(self):
        """Production config forbids unrestricted wildcard hosts [*]."""
        with pytest.raises(
            ValueError,
            match="ALLOWED_HOSTS must be explicitly configured in production",
        ):
            Settings(
                APP_ENV="production",
                ALLOWED_HOSTS='["*"]',
                GEMINI_API_KEY="dummy-key",
            )

    def test_revision_staging_host_allowed_via_domain_wildcard(self):
        """Revision-specific staging hostname is allowed when domain wildcard is configured."""
        routes = [Route("/api/repos/examples", dummy_api)]
        app = Starlette(routes=routes)
        allowed_hosts = [
            "aria-api.lemonriver-308dc42a.eastasia.azurecontainerapps.io",
            "*.lemonriver-308dc42a.eastasia.azurecontainerapps.io",
            "localhost",
            "127.0.0.1",
        ]
        app.add_middleware(
            HealthExemptTrustedHostMiddleware, allowed_hosts=allowed_hosts
        )
        client = TestClient(app)

        res = client.get(
            "/api/repos/examples",
            headers={
                "Host": "aria-api--p2-194205.lemonriver-308dc42a.eastasia.azurecontainerapps.io"
            },
        )
        assert res.status_code == 200

    def test_parse_allowed_hosts_robust_against_unquoted_brackets(self):
        """Verifies unquoted bracketed strings are correctly parsed without stray brackets."""
        s = Settings(
            APP_ENV="production",
            ALLOWED_HOSTS="[aria-api.lemonriver-308dc42a.eastasia.azurecontainerapps.io, *.lemonriver-308dc42a.eastasia.azurecontainerapps.io, localhost, 127.0.0.1]",
            GEMINI_API_KEY="dummy-key",
        )
        assert s.allowed_hosts == [
            "aria-api.lemonriver-308dc42a.eastasia.azurecontainerapps.io",
            "*.lemonriver-308dc42a.eastasia.azurecontainerapps.io",
            "localhost",
            "127.0.0.1",
        ]
        assert not any(h.startswith("[") or h.endswith("]") for h in s.allowed_hosts)

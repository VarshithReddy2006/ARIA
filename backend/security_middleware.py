import logging
import secrets
import time
import threading
from typing import Dict, List, Optional, Set
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

logger = logging.getLogger(__name__)

# Explicit public endpoint path allowlist
PUBLIC_PATHS: Set[str] = {
    "/health",
    "/metrics",
    "/api/v1/health",
    "/api/v1/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
}


class RateLimiter:
    """Thread-safe sliding-window rate limiter for clients."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.requests: Dict[str, List[float]] = {}
        self.last_cleanup = time.time()
        self.lock = threading.Lock()

    def is_allowed(self, client_ip: str) -> bool:
        if self.limit <= 0:
            return True

        now = time.time()
        with self.lock:
            # Periodic pruning of all IPs to prevent memory leaks from inactive IPs
            if now - self.last_cleanup > 300:
                dead_ips = []
                for ip, ts_list in list(self.requests.items()):
                    pruned = [t for t in ts_list if now - t < 60]
                    if not pruned:
                        dead_ips.append(ip)
                    else:
                        self.requests[ip] = pruned
                for ip in dead_ips:
                    self.requests.pop(ip, None)
                self.last_cleanup = now

            # Fetch or initialize list for current client
            client_requests = self.requests.get(client_ip, [])
            # Prune requests older than 60 seconds
            client_requests = [t for t in client_requests if now - t < 60]

            if len(client_requests) < self.limit:
                client_requests.append(now)
                self.requests[client_ip] = client_requests
                return True
            else:
                if client_requests:
                    self.requests[client_ip] = client_requests
                else:
                    self.requests.pop(client_ip, None)
                return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware enforcing request rate limiting per IP address."""

    def __init__(self, app, limit: int = 60) -> None:
        super().__init__(app)
        self.limiter = RateLimiter(limit)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Bypass rate limit on health/metrics routes
        if request.url.path in [
            "/health",
            "/metrics",
            "/api/v1/health",
            "/api/v1/metrics",
        ]:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        # Bypass rate limit during tests only. Production loopback requests are
        # rate-limited like any other client. Health/metrics endpoints (the only
        # paths that Docker HEALTHCHECK and Prometheus scrapers hit) are already
        # exempted by path above.
        import sys
        from backend.settings import settings

        is_main_app = getattr(request.app, "title", "") in (
            "ARIA — AI-Powered Repository Intelligence Agent",
            "Aria — AI-Powered Repository Intelligence Agent",
        )
        if ("pytest" in sys.modules and is_main_app) or settings.app_env == "test":
            return await call_next(request)

        if not self.limiter.is_allowed(client_ip):
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Rate limit exceeded."},
            )

        return await call_next(request)


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Deny-by-default API Key authentication middleware."""

    def __init__(
        self, app, api_key: Optional[str] = None, app_env: str = "development"
    ) -> None:
        super().__init__(app)
        self.api_key = api_key
        self.app_env = app_env

        if self.app_env == "production" and not self.api_key:
            raise RuntimeError(
                "API_KEY must be configured when running in production mode (APP_ENV=production)"
            )

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # If API key is not configured in non-production environments, bypass auth
        if not self.api_key:
            return await call_next(request)

        # Allow OPTIONS (CORS preflight) and explicit public routes
        path = request.url.path
        if (
            request.method == "OPTIONS"
            or path in PUBLIC_PATHS
            or path.startswith("/docs")
            or path.startswith("/redoc")
        ):
            return await call_next(request)

        # Deny-by-default: all other endpoints require valid API key
        provided_key = request.headers.get("X-API-Key")

        # Fallback to Authorization header
        if not provided_key:
            auth_header = request.headers.get("Authorization")
            if auth_header:
                if auth_header.lower().startswith("bearer "):
                    provided_key = auth_header[7:]
                else:
                    provided_key = auth_header

        if not provided_key or not secrets.compare_digest(provided_key, self.api_key):
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized. Invalid or missing API key."},
            )

        return await call_next(request)

import hashlib
import hmac
import logging
import secrets
import time
import threading
import urllib.parse
from typing import Dict, List, Optional, Set
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from starlette.types import Receive, Scope, Send

logger = logging.getLogger(__name__)


class HealthExemptTrustedHostMiddleware(TrustedHostMiddleware):
    """TrustedHostMiddleware that exempts platform health and readiness probes.

    Allows internal orchestrators (Azure Container Apps, Kubernetes) querying
    via dynamic pod IP or localhost to perform health checks without weakening
    ALLOWED_HOSTS validation for normal application routes.
    """

    EXEMPT_PATHS: Set[str] = {
        "/health",
        "/health/",
        "/ready",
        "/ready/",
        "/api/v1/health",
        "/api/v1/health/",
        "/api/v1/ready",
        "/api/v1/ready/",
    }

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path in self.EXEMPT_PATHS:
                await self.app(scope, receive, send)
                return
        await super().__call__(scope, receive, send)


# Session configuration constants
SESSION_COOKIE_NAME: str = "aria_session"
SESSION_VERSION: str = "v1"
DEFAULT_SESSION_MAX_AGE: int = 604800  # 7 days in seconds


def _derive_signing_key(secret: str) -> bytes:
    """Derive a dedicated HMAC signing key from the server secret."""
    return hmac.new(
        b"aria-session-signature-v1",
        secret.encode("utf-8"),
        hashlib.sha256,
    ).digest()


def generate_session_token(
    secret: str,
    max_age: int = DEFAULT_SESSION_MAX_AGE,
    session_id: Optional[str] = None,
) -> str:
    """Generate a cryptographically signed browser session token.

    Format: v1.<session_id>.<expires_at>.<hmac_signature>
    """
    if not secret:
        raise ValueError("Cannot generate session token without a signing secret")

    sid = session_id or secrets.token_hex(16)
    expires_at = int(time.time()) + max_age
    payload = f"{SESSION_VERSION}.{sid}.{expires_at}"
    signature = hmac.new(
        _derive_signing_key(secret),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{signature}"


def verify_session_token(token: Optional[str], secret: Optional[str]) -> bool:
    """Verify an HMAC-SHA256 signed browser session token using constant-time comparison."""
    if not token or not secret or not isinstance(token, str):
        return False

    try:
        parts = token.strip().split(".")
        if len(parts) != 4:
            return False

        version, session_id, expires_at_str, signature = parts

        if version != SESSION_VERSION:
            return False

        if not session_id or not expires_at_str or not signature:
            return False

        expires_at = int(expires_at_str)
        now = int(time.time())
        if now > expires_at:
            return False

        payload = f"{version}.{session_id}.{expires_at_str}"
        expected_signature = hmac.new(
            _derive_signing_key(secret),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return secrets.compare_digest(signature, expected_signature)
    except Exception as exc:
        logger.debug("Session verification failed: %s", exc)
        return False


def is_valid_origin(
    request: Request, allowed_origins: Optional[List[str]] = None
) -> bool:
    """Validate request origin and headers for CSRF protection on cookie-authenticated requests."""
    # 1. Inspect Sec-Fetch-Site if provided by modern browsers
    sec_fetch_site = request.headers.get("sec-fetch-site", "").lower()
    if sec_fetch_site == "cross-site":
        return False

    # 2. Extract origin from Origin header or Referer header
    origin_header = request.headers.get("origin")
    if not origin_header:
        referer = request.headers.get("referer")
        if referer:
            try:
                parsed = urllib.parse.urlparse(referer)
                if parsed.scheme and parsed.netloc:
                    origin_header = f"{parsed.scheme}://{parsed.netloc}"
            except Exception:
                pass

    if not origin_header:
        # If neither Origin nor Referer is present on a mutation, only allow if browser confirms same-origin
        if sec_fetch_site in ("same-origin", "same-site"):
            return True
        return False

    origin_norm = origin_header.rstrip("/").lower()
    origin_netloc = urllib.parse.urlparse(origin_header).netloc.lower()

    # 3. Determine host / scheme of current request
    proto = request.headers.get("x-forwarded-proto", request.url.scheme).lower()
    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.netloc
    )
    host_lower = host.lower()

    # Build acceptable origins
    acceptable: Set[str] = {
        f"{proto}://{host_lower}".rstrip("/"),
        f"{request.url.scheme}://{request.url.netloc}".rstrip("/").lower(),
        f"http://{host_lower}".rstrip("/"),
        f"https://{host_lower}".rstrip("/"),
    }

    if allowed_origins:
        for orig in allowed_origins:
            if orig:
                acceptable.add(orig.rstrip("/").lower())

    # Try matching frontend_url from core config if available
    try:
        from core.config import settings

        if settings.frontend_url:
            acceptable.add(settings.frontend_url.rstrip("/").lower())
    except Exception:
        pass

    if origin_norm in acceptable:
        return True

    # Netloc match (host + port)
    if origin_netloc and origin_netloc == host_lower:
        return True

    return False


# Explicit public endpoint path allowlist
PUBLIC_PATHS: Set[str] = {
    "/",
    "/health",
    "/ready",
    "/metrics",
    "/api/v1/health",
    "/api/v1/ready",
    "/api/v1/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.svg",
    "/favicon.png",
    "/favicon.ico",
    "/robots.txt",
}

PUBLIC_PAGE_ROUTES: Set[str] = {
    "/analysis",
    "/chat",
    "/issues",
}

PUBLIC_PREFIXES: tuple[str, ...] = (
    "/_astro/",
    "/docs",
    "/redoc",
)


def is_public_path(path: str) -> bool:
    """Check whether an incoming request path is accessible without an API key."""
    if path in PUBLIC_PATHS or path in PUBLIC_PAGE_ROUTES:
        return True
    if any(path.startswith(prefix + "/") for prefix in PUBLIC_PAGE_ROUTES):
        return True
    if any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES):
        return True
    return False


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
            "/ready",
            "/metrics",
            "/api/v1/health",
            "/api/v1/ready",
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
    """Deny-by-default API Key and HMAC Session authentication middleware."""

    def __init__(
        self,
        app,
        api_key: Optional[str] = None,
        app_env: str = "development",
        allowed_origins: Optional[List[str]] = None,
        session_secret: Optional[str] = None,
        secure_cookies: Optional[bool] = None,
    ) -> None:
        super().__init__(app)
        self.api_key = api_key
        self.app_env = app_env
        self.session_secret = session_secret or api_key
        self.allowed_origins = allowed_origins or []
        self.secure_cookies = secure_cookies

        if self.app_env == "production" and not self.api_key:
            raise RuntimeError(
                "API_KEY must be configured when running in production mode (APP_ENV=production)"
            )

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # 1. OPTIONS preflight requests bypass authentication and CSRF checks
        if request.method == "OPTIONS":
            return await call_next(request)

        # 2. Check if request path is public
        if is_public_path(path):
            response = await call_next(request)

            # Issue or refresh session cookie on public GET page requests if session secret is present
            effective_secret = self.session_secret or self.api_key
            if request.method == "GET" and effective_secret:
                existing_cookie = request.cookies.get(SESSION_COOKIE_NAME)
                if not existing_cookie or not verify_session_token(
                    existing_cookie, effective_secret
                ):
                    new_token = generate_session_token(effective_secret)
                    is_secure = (
                        self.secure_cookies
                        if self.secure_cookies is not None
                        else (
                            self.app_env == "production"
                            and (
                                request.url.scheme == "https"
                                or request.headers.get("x-forwarded-proto") == "https"
                            )
                        )
                    )
                    response.set_cookie(
                        key=SESSION_COOKIE_NAME,
                        value=new_token,
                        max_age=DEFAULT_SESSION_MAX_AGE,
                        httponly=True,
                        samesite="lax",
                        path="/",
                        secure=is_secure,
                    )
            return response

        # If API key is not configured in non-production environments, bypass auth
        if not self.api_key and self.app_env != "production":
            return await call_next(request)

        # 3. Protected endpoint authentication priority:
        # Priority 1: X-API-Key header
        provided_key = request.headers.get("X-API-Key")

        # Priority 2: Authorization header (Bearer or raw key)
        if not provided_key:
            auth_header = request.headers.get("Authorization")
            if auth_header:
                if auth_header.lower().startswith("bearer "):
                    provided_key = auth_header[7:].strip()
                else:
                    provided_key = auth_header.strip()

        # Validate API Key if provided
        if (
            provided_key
            and self.api_key
            and secrets.compare_digest(provided_key, self.api_key)
        ):
            return await call_next(request)

        # Priority 3: HttpOnly aria_session cookie
        effective_secret = self.session_secret or self.api_key
        session_token = request.cookies.get(SESSION_COOKIE_NAME)
        if (
            session_token
            and effective_secret
            and verify_session_token(session_token, effective_secret)
        ):
            # Enforce CSRF / origin validation on state-changing methods for cookie auth
            if request.method in ("POST", "PUT", "PATCH", "DELETE"):
                if not is_valid_origin(request, self.allowed_origins):
                    return JSONResponse(
                        status_code=403,
                        content={
                            "detail": "CSRF validation failed: cross-origin mutation not allowed."
                        },
                    )
            return await call_next(request)

        # 4. Deny unauthenticated requests with 401
        return JSONResponse(
            status_code=401,
            content={"detail": "Unauthorized. Invalid or missing API key."},
        )

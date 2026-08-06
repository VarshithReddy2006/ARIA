"""FastAPI middleware to capture HTTP request statistics and log slow requests."""

import logging
import time
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from backend.settings import settings
from core.observability.context import get_current_request_id
from core.observability.metrics import metrics_collector

logger = logging.getLogger("backend.performance")


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware collecting HTTP request telemetry and warning on slow requests."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Exclude metrics scraping itself from metrics collection to avoid noise
        if request.url.path in ["/metrics", "/ready", "/health", "/api/v1/metrics", "/api/v1/ready", "/api/v1/health"]:
            return await call_next(request)

        metrics_collector.increment_active_requests()
        start_time = time.time()

        try:
            response = await call_next(request)
            elapsed = time.time() - start_time
            # Increment request counter labeled by method, path, and status code
            metrics_collector.increment_request(
                request.method, request.url.path, response.status_code
            )
            metrics_collector.record_request_duration(
                request.method, request.url.path, response.status_code, elapsed
            )

            # Log SLOW_REQUEST warning if threshold exceeded
            threshold = getattr(settings, "slow_request_threshold_seconds", 2.0)
            if elapsed > threshold:
                req_id = getattr(request.state, "request_id", None) or get_current_request_id() or ""
                logger.warning(
                    "SLOW_REQUEST method=%s path=%s duration_ms=%.2f status=%d request_id=%s threshold_seconds=%.2f",
                    request.method,
                    request.url.path,
                    elapsed * 1000.0,
                    response.status_code,
                    req_id,
                    threshold,
                )

            return response
        finally:
            metrics_collector.decrement_active_requests()

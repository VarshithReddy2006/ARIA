"""FastAPI middleware to extract or generate Request IDs and bind them to request state and context variables."""

import uuid
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from core.observability.context import request_id_var


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware that injects, stores in state, and propagates X-Request-ID across the HTTP request lifecycle."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Get request ID from header or generate a new UUID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Store in request.state.request_id (CHANGE 2 requirement)
        request.state.request_id = request_id

        # Set contextvar token for structured loggers
        token = request_id_var.set(request_id)

        try:
            response = await call_next(request)
            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            # Clean up token
            request_id_var.reset(token)

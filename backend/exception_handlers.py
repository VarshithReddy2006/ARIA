"""Standardized Exception Handlers for FastAPI Application.

Ensures all errors (HTTPException, RequestValidationError, RESTAPIException,
and unexpected exceptions) produce a consistent JSON envelope with request_id
correlation and zero internal stack trace exposure.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import FastAPI, Request, status
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse

from core.observability.context import get_current_request_id
from core.observability.redaction import sanitize_sensitive_data
from ria.interfaces.rest.exceptions import RESTAPIException

logger = logging.getLogger(__name__)


def _get_request_id(request: Request) -> str:
    """Retrieve request_id from request.state or active contextvar."""
    return getattr(request.state, "request_id", None) or get_current_request_id() or ""


def create_error_response(
    request_id: str,
    code: int,
    message: str,
    details: Any = None,
) -> JSONResponse:
    """Construct a standardized JSON error response envelope."""
    safe_message = sanitize_sensitive_data(message)
    payload: Dict[str, Any] = {
        "request_id": request_id,
        "status": "error",
        "code": code,
        "message": safe_message,
        "detail": safe_message,
        "details": sanitize_sensitive_data(details) if details is not None else None,
    }
    return JSONResponse(status_code=code, content=payload)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    req_id = _get_request_id(request)
    detail_msg = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return create_error_response(
        request_id=req_id,
        code=exc.status_code,
        message=detail_msg,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    req_id = _get_request_id(request)
    return create_error_response(
        request_id=req_id,
        code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        message="Request validation error",
        details=exc.errors(),
    )


async def rest_api_exception_handler(
    request: Request, exc: RESTAPIException
) -> JSONResponse:
    req_id = _get_request_id(request)
    return create_error_response(
        request_id=req_id,
        code=getattr(exc, "status_code", 400),
        message=getattr(exc, "message", str(exc)),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    req_id = _get_request_id(request)
    logger.error(
        "UNHANDLED_EXCEPTION path=%s request_id=%s error=%s",
        request.url.path,
        req_id,
        exc,
        exc_info=True,
    )
    return create_error_response(
        request_id=req_id,
        code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message="An internal server error occurred.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all global exception handlers on the FastAPI app instance."""
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(RESTAPIException, rest_api_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

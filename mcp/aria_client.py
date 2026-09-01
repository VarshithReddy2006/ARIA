"""ARIA HTTP API Client for MCP Adapters.

Provides a thin, resilient HTTP client that bridges MCP tool and resource
invocations to the canonical ARIA REST and streaming API.

MCP adapters must remain strictly stateless protocol translators; no business
logic, direct vector DB access, SQLite access, or direct LLM calls live here.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional
import httpx


from mcp.errors import ToolFailure, ToolInputError

logger = logging.getLogger("mcp.aria_client")

DEFAULT_API_URL = "http://127.0.0.1:8001"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 2


class AriaAPIClient:
    """HTTP Client for communicating with the ARIA backend API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        raw_url = (
            base_url
            or os.environ.get("ARIA_API_URL")
            or os.environ.get("BACKEND_API_URL")
            or DEFAULT_API_URL
        )
        self.base_url = raw_url.rstrip("/")
        self.api_key = (
            api_key
            if api_key is not None
            else os.environ.get("ARIA_API_KEY", os.environ.get("API_KEY", ""))
        )
        self.timeout = (
            timeout
            if timeout is not None
            else float(os.environ.get("ARIA_API_TIMEOUT", DEFAULT_TIMEOUT_SECONDS))
        )
        self.max_retries = max_retries

    def _get_headers(
        self, custom_headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "ARIA-MCP-Adapter/1.5.0",
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
            headers["Authorization"] = f"Bearer {self.api_key}"
        if custom_headers:
            headers.update(custom_headers)
        return headers

    def _normalize_path(self, path: str) -> str:
        """Ensure canonical versioned /api/v1 prefix."""
        normalized = path.strip()
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"

        # Root, health, ready, metrics shortcuts
        if normalized in (
            "/health",
            "/ready",
            "/metrics",
            "/api/v1/health",
            "/api/v1/ready",
            "/api/v1/metrics",
        ):
            return normalized

        if normalized.startswith("/api/v1/"):
            return normalized
        elif normalized == "/api/v1":
            return "/api/v1"
        elif normalized.startswith("/v1/"):
            return f"/api{normalized}"
        elif normalized.startswith("/api/"):
            return f"/api/v1{normalized[4:]}"
        else:
            return f"/api/v1{normalized}"

    def _build_url(self, path: str) -> str:
        canonical_path = self._normalize_path(path)
        return f"{self.base_url}{canonical_path}"

    def _extract_error_detail(self, response: httpx.Response) -> str:
        """Extract a clean, user-safe error message from API response body."""
        try:
            body = response.json()
            if isinstance(body, dict):
                detail = body.get("detail")
                if detail:
                    if isinstance(detail, list):
                        parts = []
                        for item in detail:
                            if isinstance(item, dict):
                                loc = ".".join(str(x) for x in item.get("loc", []))
                                msg = item.get("msg", str(item))
                                parts.append(f"{loc}: {msg}" if loc else msg)
                            else:
                                parts.append(str(item))
                        return "; ".join(parts)
                    return str(detail)
                if body.get("error"):
                    return str(body["error"])
                if body.get("message"):
                    return str(body["message"])
        except Exception:
            pass
        return response.text.strip() or f"HTTP {response.status_code}"

    def _handle_response_error(self, response: httpx.Response, path: str) -> None:
        """Convert HTTP error codes into normalized ToolInputError or ToolFailure."""
        status = response.status_code
        detail = self._extract_error_detail(response)

        logger.error(
            "[MCP_ERROR] status=%d path=%s detail=%s",
            status,
            path,
            detail,
        )

        if status in (400, 422):
            raise ToolInputError(f"Invalid params: {detail}")
        elif status == 401:
            raise ToolFailure(
                "Authentication failed with ARIA API. Please configure a valid ARIA_API_KEY."
            )
        elif status == 403:
            raise ToolFailure(
                "Access denied by ARIA API. Ensure the API key has permission for this resource."
            )
        elif status == 404:
            raise ToolFailure(detail or "Requested repository or resource not found.")
        elif status == 409:
            raise ToolFailure(f"Conflict: {detail}")
        elif status == 429:
            raise ToolFailure(
                "ARIA AI provider or API rate limit exceeded. Please wait a moment and try again."
            )
        elif status in (502, 503, 504):
            raise ToolFailure(
                "ARIA backend service or AI provider is temporarily unavailable."
            )
        else:
            raise ToolFailure(f"ARIA API error ({status}): {detail}")

    def get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        allow_retries: bool = True,
    ) -> Any:
        """Execute a synchronous GET request with bounded retries for idempotent reads."""
        url = self._build_url(path)
        headers = self._get_headers()
        effective_timeout = timeout if timeout is not None else self.timeout
        max_attempts = (self.max_retries + 1) if allow_retries else 1

        logger.info("[MCP_REQUEST] method=GET url=%s params=%s", url, params)
        start_time = time.perf_counter()

        last_exc: Optional[Exception] = None
        for attempt in range(max_attempts):
            try:
                with httpx.Client(timeout=effective_timeout) as client:
                    resp = client.get(url, params=params, headers=headers)
                    duration_ms = (time.perf_counter() - start_time) * 1000.0
                    logger.info(
                        "[MCP_API] method=GET path=%s status=%d latency_ms=%.1f",
                        path,
                        resp.status_code,
                        duration_ms,
                    )

                    if resp.is_success:
                        content_type = resp.headers.get("content-type", "")
                        if "application/json" in content_type:
                            return resp.json()
                        return resp.text

                    self._handle_response_error(resp, path)

            except (ToolFailure, ToolInputError):
                raise
            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt < max_attempts - 1 and allow_retries:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise ToolFailure(
                    f"ARIA API request timed out after {effective_timeout}s."
                ) from exc
            except httpx.NetworkError as exc:
                last_exc = exc
                if attempt < max_attempts - 1 and allow_retries:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise ToolFailure(
                    f"Unable to connect to ARIA API at {self.base_url}. "
                    "Please ensure the ARIA backend is running."
                ) from exc
            except Exception as exc:
                raise ToolFailure(f"API request failed: {exc}") from exc

        raise ToolFailure(f"API request failed after retries: {last_exc}")

    def post(
        self,
        path: str,
        json: Optional[Any] = None,
        data: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        """Execute a synchronous POST request (non-retried for state mutations)."""
        url = self._build_url(path)
        headers = self._get_headers()
        effective_timeout = timeout if timeout is not None else self.timeout

        logger.info("[MCP_REQUEST] method=POST url=%s", url)
        start_time = time.perf_counter()

        try:
            with httpx.Client(timeout=effective_timeout) as client:
                resp = client.post(
                    url, json=json, data=data, params=params, headers=headers
                )
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                logger.info(
                    "[MCP_API] method=POST path=%s status=%d latency_ms=%.1f",
                    path,
                    resp.status_code,
                    duration_ms,
                )

                if resp.is_success:
                    content_type = resp.headers.get("content-type", "")
                    if "application/json" in content_type:
                        return resp.json()
                    return resp.text

                self._handle_response_error(resp, path)

        except (ToolFailure, ToolInputError):
            raise
        except httpx.TimeoutException as exc:
            raise ToolFailure(
                f"ARIA API request timed out after {effective_timeout}s."
            ) from exc
        except httpx.NetworkError as exc:
            raise ToolFailure(
                f"Unable to connect to ARIA API at {self.base_url}. "
                "Please ensure the ARIA backend is running."
            ) from exc
        except Exception as exc:
            raise ToolFailure(f"API request failed: {exc}") from exc

    def delete(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        """Execute a synchronous DELETE request."""
        url = self._build_url(path)
        headers = self._get_headers()
        effective_timeout = timeout if timeout is not None else self.timeout

        logger.info("[MCP_REQUEST] method=DELETE url=%s", url)
        try:
            with httpx.Client(timeout=effective_timeout) as client:
                resp = client.delete(url, params=params, headers=headers)
                if resp.is_success:
                    return (
                        resp.json()
                        if "application/json" in resp.headers.get("content-type", "")
                        else resp.text
                    )
                self._handle_response_error(resp, path)
        except (ToolFailure, ToolInputError):
            raise
        except Exception as exc:
            raise ToolFailure(f"API delete request failed: {exc}") from exc

    def get_health(self) -> Dict[str, Any]:
        """Probe the backend health endpoint."""
        try:
            return self.get("/health", allow_retries=False, timeout=5.0)
        except Exception:
            return {"status": "offline", "backend": "offline"}


# Global singleton client instance
_global_client: Optional[AriaAPIClient] = None


def get_aria_client() -> AriaAPIClient:
    """Return the global AriaAPIClient singleton."""
    global _global_client
    if _global_client is None:
        _global_client = AriaAPIClient()
    return _global_client


def set_aria_client(client: AriaAPIClient) -> None:
    """Set the global AriaAPIClient singleton (useful for testing)."""
    global _global_client
    _global_client = client

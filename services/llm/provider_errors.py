"""Provider error classification system.

Maps raw SDK exceptions from Gemini and DeepSeek into a deterministic set of
error categories so the rest of the application never consumes raw SDK errors.

Usage::

    from services.llm.provider_errors import classify_gemini_error, ProviderErrorType

    try:
        await provider.health_check()
    except Exception as exc:
        error = classify_gemini_error(exc, "gemini")
        if error.error_type == ProviderErrorType.INVALID_CREDENTIAL_TYPE:
            ...

Error categories align with the requirements:
  - MISSING_CREDENTIAL
  - AUTHENTICATION_ERROR
  - INVALID_CREDENTIAL_TYPE
  - RATE_LIMIT_ERROR
  - QUOTA_EXCEEDED
  - TIMEOUT
  - NETWORK_ERROR
  - CONFIGURATION_ERROR
  - UNKNOWN_PROVIDER_ERROR
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error type enumeration
# ---------------------------------------------------------------------------


class ProviderErrorType(str, Enum):
    """Deterministic categories for LLM provider errors."""

    MISSING_CREDENTIAL = "missing_credential"
    AUTHENTICATION_ERROR = "authentication_error"
    INVALID_CREDENTIAL_TYPE = "invalid_credential_type"
    RATE_LIMIT_ERROR = "rate_limit_error"
    QUOTA_EXCEEDED = "quota_exceeded"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    CONFIGURATION_ERROR = "configuration_error"
    UNKNOWN_PROVIDER_ERROR = "unknown_provider_error"


# ---------------------------------------------------------------------------
# Structured error model
# ---------------------------------------------------------------------------


class EmptyCompletionError(Exception):
    """Raised when an LLM provider returns an empty or whitespace-only completion."""

    def __init__(self, message: str = "Provider returned an empty completion."):
        super().__init__(message)
        self.message = message


@dataclass
class ProviderError:
    """Classified provider error with actionable diagnostics."""

    error_type: ProviderErrorType
    provider_name: str
    message: str
    recommendation: str = ""
    original_exception: Optional[Exception] = field(default=None, repr=False)

    def __str__(self) -> str:
        return f"[{self.provider_name}:{self.error_type.value}] {self.message}"


# ---------------------------------------------------------------------------
# Actionable user messages
# ---------------------------------------------------------------------------

_GEMINI_MESSAGES = {
    ProviderErrorType.MISSING_CREDENTIAL: (
        "GEMINI_API_KEY is not set.",
        "Set GEMINI_API_KEY in your .env file. "
        "Get a key at https://aistudio.google.com/app/apikey",
    ),
    ProviderErrorType.INVALID_CREDENTIAL_TYPE: (
        "Gemini authentication failed. The configured credential is not accepted "
        "by the Gemini Developer API.",
        "Verify that GEMINI_API_KEY is a valid Google AI Studio Developer API key "
        "(not an OAuth access token, service account JSON, or Vertex AI credential). "
        "Generate a new key at https://aistudio.google.com/app/apikey",
    ),
    ProviderErrorType.AUTHENTICATION_ERROR: (
        "Gemini authentication failed. The API key is invalid or has been revoked.",
        "Verify GEMINI_API_KEY is correct and active. "
        "Generate a new key at https://aistudio.google.com/app/apikey",
    ),
    ProviderErrorType.RATE_LIMIT_ERROR: (
        "Gemini rate limit exceeded.",
        "Wait 60 seconds and retry. Consider adding GEMINI_API_KEY quotas at "
        "https://aistudio.google.com/app/apikey",
    ),
    ProviderErrorType.QUOTA_EXCEEDED: (
        "Gemini quota exceeded.",
        "Check your Gemini API quota and billing at "
        "https://console.cloud.google.com/apis/api/generativelanguage.googleapis.com",
    ),
    ProviderErrorType.TIMEOUT: (
        "Gemini request timed out.",
        "This may be a transient issue. Retry the request.",
    ),
    ProviderErrorType.NETWORK_ERROR: (
        "Could not connect to the Gemini API.",
        "Check network connectivity to generativelanguage.googleapis.com",
    ),
}

_DEEPSEEK_MESSAGES = {
    ProviderErrorType.MISSING_CREDENTIAL: (
        "DEEPSEEK_API_KEY is not set.",
        "Set DEEPSEEK_API_KEY in your .env file with your NVIDIA NIM API key.",
    ),
    ProviderErrorType.AUTHENTICATION_ERROR: (
        "DeepSeek/NVIDIA NIM authentication failed. The API key is invalid or expired.",
        "Verify DEEPSEEK_API_KEY is correct. Get a key at https://build.nvidia.com",
    ),
    ProviderErrorType.RATE_LIMIT_ERROR: (
        "DeepSeek/NVIDIA NIM rate limit exceeded.",
        "Wait 60 seconds and retry.",
    ),
    ProviderErrorType.TIMEOUT: (
        "DeepSeek/NVIDIA NIM request timed out.",
        "This may be a transient issue. Retry the request.",
    ),
    ProviderErrorType.NETWORK_ERROR: (
        "Could not connect to DeepSeek/NVIDIA NIM endpoint.",
        "Check network connectivity to integrate.api.nvidia.com "
        "and verify DEEPSEEK_BASE_URL in .env",
    ),
}


# ---------------------------------------------------------------------------
# Classifier: Gemini
# ---------------------------------------------------------------------------


def classify_gemini_error(
    exc: Exception, provider_name: str = "gemini"
) -> ProviderError:
    """Classify a Google GenAI SDK exception into a ProviderError.

    This is the authoritative mapping for Gemini errors. Any exception that
    reaches this function is classified — nothing falls through to bare SDK types.

    Args:
        exc:           The caught exception.
        provider_name: Provider label (default "gemini").

    Returns:
        ProviderError with a deterministic error_type and actionable message.
    """
    exc_type = type(exc).__name__
    exc_str = str(exc).lower()

    # Missing credential — short-circuit before any API call attempt
    if _is_missing_credential(exc_str):
        return _make(
            ProviderErrorType.MISSING_CREDENTIAL, provider_name, exc, _GEMINI_MESSAGES
        )

    # google.genai.errors.ClientError covers all HTTP-level errors
    # The message always contains the HTTP status and detail string
    if "clienterror" in exc_type.lower() or "apierror" in exc_type.lower():
        # Access token type unsupported — most specific check first
        if "access_token_type_unsupported" in exc_str:
            return _make(
                ProviderErrorType.INVALID_CREDENTIAL_TYPE,
                provider_name,
                exc,
                _GEMINI_MESSAGES,
            )

        # Generic 401 / unauthenticated
        if "401" in exc_str or "unauthenticated" in exc_str:
            return _make(
                ProviderErrorType.AUTHENTICATION_ERROR,
                provider_name,
                exc,
                _GEMINI_MESSAGES,
            )

        # 403 permission denied
        if "403" in exc_str or "permission_denied" in exc_str or "forbidden" in exc_str:
            return _make(
                ProviderErrorType.AUTHENTICATION_ERROR,
                provider_name,
                exc,
                _GEMINI_MESSAGES,
            )

        # 429 rate limit
        if "429" in exc_str or "resource_exhausted" in exc_str or "rate" in exc_str:
            if "quota" in exc_str:
                return _make(
                    ProviderErrorType.QUOTA_EXCEEDED,
                    provider_name,
                    exc,
                    _GEMINI_MESSAGES,
                )
            return _make(
                ProviderErrorType.RATE_LIMIT_ERROR, provider_name, exc, _GEMINI_MESSAGES
            )

        # 503 / 502 service unavailable
        if "503" in exc_str or "502" in exc_str or "unavailable" in exc_str:
            return _make(
                ProviderErrorType.NETWORK_ERROR, provider_name, exc, _GEMINI_MESSAGES
            )

    # Timeout exceptions
    if _is_timeout(exc_type, exc_str):
        return _make(ProviderErrorType.TIMEOUT, provider_name, exc, _GEMINI_MESSAGES)

    # Network/connection errors
    if _is_network_error(exc_type, exc_str):
        return _make(
            ProviderErrorType.NETWORK_ERROR, provider_name, exc, _GEMINI_MESSAGES
        )

    # API key format issues (wrong key format detected locally)
    if "api_key" in exc_str and ("invalid" in exc_str or "malformed" in exc_str):
        return _make(
            ProviderErrorType.AUTHENTICATION_ERROR, provider_name, exc, _GEMINI_MESSAGES
        )

    # Unknown — log full type for future classification
    logger.warning(
        "classify_gemini_error: unrecognized exception exc_type=%s exc_str_prefix=%s",
        exc_type,
        exc_str[:120],
    )
    return ProviderError(
        error_type=ProviderErrorType.UNKNOWN_PROVIDER_ERROR,
        provider_name=provider_name,
        message=f"Unexpected Gemini error: {exc_type}: {str(exc)[:200]}",
        recommendation="Check backend logs for full stack trace.",
        original_exception=exc,
    )


# ---------------------------------------------------------------------------
# Classifier: DeepSeek / NVIDIA NIM
# ---------------------------------------------------------------------------


def classify_deepseek_error(
    exc: Exception, provider_name: str = "deepseek"
) -> ProviderError:
    """Classify a DeepSeek/NVIDIA NIM exception into a ProviderError.

    Args:
        exc:           The caught exception.
        provider_name: Provider label (default "deepseek").

    Returns:
        ProviderError with a deterministic error_type and actionable message.
    """
    exc_type = type(exc).__name__
    exc_str = str(exc).lower()

    # Missing credential
    if _is_missing_credential(exc_str):
        return _make(
            ProviderErrorType.MISSING_CREDENTIAL, provider_name, exc, _DEEPSEEK_MESSAGES
        )

    # httpx.HTTPStatusError — has .response.status_code
    if hasattr(exc, "response"):
        try:
            status = exc.response.status_code  # type: ignore[attr-defined]
        except Exception:
            status = None

        if status == 401:
            return _make(
                ProviderErrorType.AUTHENTICATION_ERROR,
                provider_name,
                exc,
                _DEEPSEEK_MESSAGES,
            )
        if status == 403:
            return _make(
                ProviderErrorType.AUTHENTICATION_ERROR,
                provider_name,
                exc,
                _DEEPSEEK_MESSAGES,
            )
        if status == 429:
            return _make(
                ProviderErrorType.RATE_LIMIT_ERROR,
                provider_name,
                exc,
                _DEEPSEEK_MESSAGES,
            )

    # String-based fallback for httpx errors without response attribute
    if "401" in exc_str or "unauthorized" in exc_str:
        return _make(
            ProviderErrorType.AUTHENTICATION_ERROR,
            provider_name,
            exc,
            _DEEPSEEK_MESSAGES,
        )
    if "403" in exc_str or "forbidden" in exc_str:
        return _make(
            ProviderErrorType.AUTHENTICATION_ERROR,
            provider_name,
            exc,
            _DEEPSEEK_MESSAGES,
        )
    if "429" in exc_str or "rate limit" in exc_str or "too many requests" in exc_str:
        return _make(
            ProviderErrorType.RATE_LIMIT_ERROR, provider_name, exc, _DEEPSEEK_MESSAGES
        )

    # Timeout
    if _is_timeout(exc_type, exc_str):
        return _make(ProviderErrorType.TIMEOUT, provider_name, exc, _DEEPSEEK_MESSAGES)

    # Network / connection
    if _is_network_error(exc_type, exc_str):
        return _make(
            ProviderErrorType.NETWORK_ERROR, provider_name, exc, _DEEPSEEK_MESSAGES
        )

    logger.warning(
        "classify_deepseek_error: unrecognized exception exc_type=%s exc_str_prefix=%s",
        exc_type,
        exc_str[:120],
    )
    return ProviderError(
        error_type=ProviderErrorType.UNKNOWN_PROVIDER_ERROR,
        provider_name=provider_name,
        message=f"Unexpected DeepSeek error: {exc_type}: {str(exc)[:200]}",
        recommendation="Check backend logs for full stack trace.",
        original_exception=exc,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _make(
    error_type: ProviderErrorType,
    provider_name: str,
    exc: Exception,
    messages_map: dict,
) -> ProviderError:
    """Build a ProviderError from the messages map."""
    msg, rec = messages_map.get(
        error_type, (str(exc), "Check your provider configuration.")
    )
    return ProviderError(
        error_type=error_type,
        provider_name=provider_name,
        message=msg,
        recommendation=rec,
        original_exception=exc,
    )


def _is_missing_credential(exc_str: str) -> bool:
    return any(
        phrase in exc_str
        for phrase in (
            "api_key is not set",
            "api key is not set",
            "api key missing",
            "no api key",
            "empty api key",
            "key is none",
            "key is empty",
        )
    )


def _is_timeout(exc_type: str, exc_str: str) -> bool:
    timeout_types = (
        "timeouterror",
        "timeoutexception",
        "readtimeout",
        "connecttimeout",
        "asynciotimeouterror",
        "asyncio.timeouterror",
    )
    return (
        any(t in exc_type.lower() for t in timeout_types)
        or "timeout" in exc_str
        or "timed out" in exc_str
    )


def _is_network_error(exc_type: str, exc_str: str) -> bool:
    network_types = (
        "connecterror",
        "connectionerror",
        "networkerror",
        "connectionrefused",
        "gaierror",
        "httperror",
        "transporterror",
    )
    network_phrases = (
        "connection refused",
        "network error",
        "name resolution",
        "failed to connect",
        "socket",
        "unreachable",
    )
    return any(t in exc_type.lower() for t in network_types) or any(
        p in exc_str for p in network_phrases
    )

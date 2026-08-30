"""Provider Manager — Phase 8.

Multi-provider orchestration with:
  - Configuration-driven priority order
  - Per-provider circuit breaker (open/half-open/closed states)
  - Retry policy with exponential backoff
  - Timeout enforcement
  - Automatic fallback to secondary provider
  - Streaming retry safeguards (Phase 9)

The ProviderManager wraps existing BaseLLMProvider implementations.
It does NOT replace them — it adds an orchestration layer above them.

Circuit Breaker States:
  CLOSED     → normal operation, requests go through
  OPEN       → provider failed recently, skip to next provider
  HALF_OPEN  → test period, allow one request through to check recovery

Configuration is read from settings but providers can be overridden at
construction time for testing.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_SECRET_RE = re.compile(
    r"(?:AIza[0-9A-Za-z-_]{35}|sk-[a-zA-Z0-9_-]{20,}|ghp_[a-zA-Z0-9]{30,}|Bearer\s+[a-zA-Z0-9._-]{25,}|AKIA[0-9A-Z]{16})",
    re.I,
)


def redact_secrets(text: str) -> str:
    """Redact known API keys, tokens, and credentials from string text."""
    if not text:
        return ""
    return _SECRET_RE.sub("[REDACTED_CREDENTIAL]", str(text))


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class CircuitState(Enum):
    CLOSED = "closed"  # Normal — requests allowed
    OPEN = "open"  # Failed — requests blocked
    HALF_OPEN = "half_open"  # Testing recovery — one request allowed


@dataclass
class CircuitBreaker:
    """Per-provider circuit breaker.

    Attributes:
        failure_threshold:  Consecutive failures before opening.
        recovery_timeout:   Seconds before trying again (OPEN → HALF_OPEN).
        half_open_timeout:  Seconds to stay in HALF_OPEN before deciding.
    """

    provider_name: str
    failure_threshold: int = 3
    recovery_timeout: float = 60.0
    half_open_timeout: float = 15.0

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)
    _half_open_time: float = field(default=0.0, init=False)

    @property
    def state(self) -> CircuitState:
        now = time.time()
        if self._state == CircuitState.OPEN:
            if now - self._last_failure_time >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_time = now
                logger.info(
                    "[LLM_CIRCUIT] provider=%s transition=OPEN->HALF_OPEN cooldown_elapsed=%.1fs",
                    self.provider_name,
                    now - self._last_failure_time,
                )
        elif self._state == CircuitState.HALF_OPEN:
            if now - self._half_open_time >= self.half_open_timeout:
                # Stayed HALF_OPEN too long without resolution — re-open
                self._state = CircuitState.OPEN
                self._last_failure_time = now
                logger.warning(
                    "[LLM_CIRCUIT] provider=%s transition=HALF_OPEN->OPEN timeout_elapsed=%.1fs",
                    self.provider_name,
                    now - self._half_open_time,
                )
        return self._state

    def is_allowed(self) -> bool:
        return self.state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def record_success(self) -> None:
        if self._state != CircuitState.CLOSED:
            logger.info(
                "[LLM_CIRCUIT] provider=%s transition=%s->CLOSED (recovered)",
                self.provider_name,
                self._state.value.upper(),
            )
        self._state = CircuitState.CLOSED
        self._failure_count = 0

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold:
            if self._state != CircuitState.OPEN:
                logger.warning(
                    "[LLM_CIRCUIT] provider=%s transition=CLOSED->OPEN (failure_threshold=%d reached)",
                    self.provider_name,
                    self._failure_count,
                )
            self._state = CircuitState.OPEN

    def reset(self) -> None:
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0


# ---------------------------------------------------------------------------
# Provider entry
# ---------------------------------------------------------------------------


@dataclass
class ProviderEntry:
    name: str
    provider: object  # BaseLLMProvider
    priority: int  # lower = tried first
    circuit_breaker: CircuitBreaker = field(init=False)
    timeout: float = 60.0

    def __post_init__(self):
        self.circuit_breaker = CircuitBreaker(provider_name=self.name)


# ---------------------------------------------------------------------------
# ProviderManager
# ---------------------------------------------------------------------------


class ProviderManager:
    """Manages multiple LLM providers with automatic fallback and circuit breaking.

    Usage::

        manager = ProviderManager()
        answer = await manager.generate(prompt, system_instruction=...)
        async for token in manager.stream(prompt, system_instruction=...):
            yield token
    """

    def __init__(
        self,
        providers: Optional[List[ProviderEntry]] = None,
        settings: Optional[Any] = None,
    ) -> None:
        """Initialise the ProviderManager.

        Args:
            providers: Ordered list of ProviderEntry objects.
                       If None, loads from ProviderFactory settings.
            settings:  Optional Settings instance to configure providers.
        """
        if providers is not None:
            self._providers = sorted(providers, key=lambda p: p.priority)
        else:
            self._providers = self._load_from_settings(settings=settings)
        self._last_telemetry: Dict[str, Any] = {}

    def _load_from_settings(
        self, settings: Optional[Any] = None
    ) -> List[ProviderEntry]:
        """Build providers from application settings."""
        from services.llm import ProviderFactory
        from core.config import Settings, get_settings

        current_settings: Settings = (
            settings if isinstance(settings, Settings) else get_settings()
        )

        entries: List[ProviderEntry] = []
        primary_name = (
            (
                getattr(current_settings, "llm_primary_provider", None)
                or current_settings.llm_provider
            )
            .lower()
            .strip()
        )

        failover_enabled = getattr(current_settings, "llm_failover_enabled", True)
        total_timeout = getattr(current_settings, "llm_total_timeout", 60.0)
        cooldown = getattr(
            current_settings, "llm_circuit_breaker_cooldown_seconds", 60.0
        )
        failure_thresh = getattr(
            current_settings, "llm_circuit_breaker_failure_threshold", 3
        )

        # Primary provider (from config)
        try:
            primary = ProviderFactory.get_provider(settings=current_settings)
            primary_entry = ProviderEntry(
                name=primary_name,
                provider=primary,
                priority=1,
                timeout=total_timeout,
            )
            primary_entry.circuit_breaker.recovery_timeout = cooldown
            primary_entry.circuit_breaker.failure_threshold = failure_thresh
            entries.append(primary_entry)
            logger.info(
                "[LLM_ROUTER] registered primary_provider=%s model=%s timeout=%.1fs",
                primary_name,
                getattr(primary, "model", "unknown"),
                total_timeout,
            )
        except Exception as exc:
            logger.error("ProviderManager: failed to load primary provider: %s", exc)

        # Secondary provider (if failover is enabled and key exists)
        if failover_enabled:
            if primary_name == "gemini" and current_settings.deepseek_api_key:
                try:
                    from services.llm.deepseek_provider import DeepSeekProvider

                    secondary_deepseek = DeepSeekProvider(
                        api_key=current_settings.deepseek_api_key,
                        base_url=current_settings.deepseek_base_url,
                        model=current_settings.deepseek_model,
                    )
                    secondary_entry = ProviderEntry(
                        name="deepseek",
                        provider=secondary_deepseek,
                        priority=2,
                        timeout=total_timeout,
                    )
                    secondary_entry.circuit_breaker.recovery_timeout = cooldown
                    secondary_entry.circuit_breaker.failure_threshold = failure_thresh
                    entries.append(secondary_entry)
                    logger.info(
                        "[LLM_ROUTER] registered secondary_provider=deepseek model=%s",
                        secondary_deepseek.model,
                    )
                except Exception as exc:
                    logger.debug(
                        "ProviderManager: DeepSeek secondary unavailable: %s", exc
                    )

            elif primary_name == "deepseek" and current_settings.gemini_api_key:
                try:
                    from services.llm.gemini_provider import GeminiProvider

                    secondary_gemini = GeminiProvider(
                        api_key=current_settings.gemini_api_key,
                        model=current_settings.gemini_model,
                    )
                    secondary_entry = ProviderEntry(
                        name="gemini",
                        provider=secondary_gemini,
                        priority=2,
                        timeout=total_timeout,
                    )
                    secondary_entry.circuit_breaker.recovery_timeout = cooldown
                    secondary_entry.circuit_breaker.failure_threshold = failure_thresh
                    entries.append(secondary_entry)
                    logger.info(
                        "[LLM_ROUTER] registered secondary_provider=gemini model=%s",
                        secondary_gemini.model,
                    )
                except Exception as exc:
                    logger.debug(
                        "ProviderManager: Gemini secondary unavailable: %s", exc
                    )

        if not entries:
            raise RuntimeError(
                "ProviderManager: no LLM providers available. "
                "Check LLM_PROVIDER and API key configuration."
            )

        return sorted(entries, key=lambda p: p.priority)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        history: Optional[List[Dict]] = None,
    ) -> Tuple[str, str]:
        """Generate a complete response, trying providers in priority order.

        Returns:
            Tuple of (response_text, provider_name_used).

        Raises:
            RuntimeError if all providers fail.
        """
        from services.llm.provider_errors import (
            classify_gemini_error,
            classify_deepseek_error,
            ProviderErrorType,
        )

        last_exc: Optional[Exception] = None
        tried: List[str] = []
        prev_provider: Optional[str] = None
        failures: List[Dict[str, Any]] = []
        overall_t0 = time.perf_counter()

        logger.info(
            "[LLM_ROUTER] request_start preferred_provider=%s model=%s providers_count=%d",
            self._providers[0].name if self._providers else "none",
            getattr(self._providers[0].provider, "model", "unknown")
            if self._providers
            else "none",
            len(self._providers),
        )

        for attempt_idx, entry in enumerate(self._providers, 1):
            cb_state = entry.circuit_breaker.state.value
            if not entry.circuit_breaker.is_allowed():
                logger.info(
                    "[LLM_ROUTER] skipping provider=%s (circuit=%s)",
                    entry.name,
                    cb_state,
                )
                continue

            logger.info(
                "[LLM_PROVIDER] provider=%s model=%s status=selected circuit_state=%s",
                entry.name,
                entry.provider.model,
                cb_state,
            )

            if prev_provider is not None:
                logger.info(
                    "[LLM_FAILOVER] from=%s to=%s reason=%s",
                    prev_provider,
                    entry.name,
                    failures[-1]["reason"] if failures else "fallback",
                )

            prev_provider = entry.name
            tried.append(entry.name)
            t0 = time.perf_counter()
            try:
                result = await asyncio.wait_for(
                    entry.provider.generate(
                        prompt=prompt,
                        system_instruction=system_instruction,
                        history=history,
                    ),
                    timeout=entry.timeout,
                )

                latency = (time.perf_counter() - t0) * 1000
                logger.info(
                    "[LLM_PROVIDER] provider=%s model=%s status=success total_latency_ms=%.1f",
                    entry.name,
                    entry.provider.model,
                    latency,
                )
                entry.circuit_breaker.record_success()
                self._last_telemetry = {
                    "selected_provider": entry.name,
                    "fallback_used": len(failures) > 0,
                    "provider_failures": list(failures),
                    "failure_reason": failures[0]["reason"] if failures else None,
                    "latency_ms": round(latency, 2),
                    "total_latency_ms": round(
                        (time.perf_counter() - overall_t0) * 1000, 2
                    ),
                }
                return result, entry.name

            except Exception as exc:
                latency = (time.perf_counter() - t0) * 1000
                last_exc = exc

                # Check for quota exhausted
                is_quota = False
                fallback_reason = "exception"
                error_type_val = "unknown"
                if entry.name == "gemini":
                    err = classify_gemini_error(exc, "gemini")
                    fallback_reason = err.error_type.value
                    error_type_val = err.error_type.value
                    if err.error_type in (
                        ProviderErrorType.QUOTA_EXCEEDED,
                        ProviderErrorType.RATE_LIMIT_ERROR,
                    ):
                        is_quota = True
                elif entry.name == "deepseek":
                    err = classify_deepseek_error(exc, "deepseek")
                    fallback_reason = err.error_type.value
                    error_type_val = err.error_type.value
                    if err.error_type in (
                        ProviderErrorType.QUOTA_EXCEEDED,
                        ProviderErrorType.RATE_LIMIT_ERROR,
                    ):
                        is_quota = True

                failures.append(
                    {
                        "provider": entry.name,
                        "reason": fallback_reason,
                        "error_type": error_type_val,
                        "latency_ms": round(latency, 2),
                    }
                )

                if is_quota:
                    logger.warning(
                        "[LLM_PROVIDER] provider=%s status=quota_exhausted error=%s",
                        entry.name,
                        str(exc),
                    )
                    entry.circuit_breaker._state = CircuitState.OPEN
                    entry.circuit_breaker._last_failure_time = time.time()
                    entry.circuit_breaker._failure_count = max(
                        entry.circuit_breaker._failure_count,
                        entry.circuit_breaker.failure_threshold,
                    )
                    fallback_reason = "quota_exhausted"
                else:
                    entry.circuit_breaker.record_failure()

                logger.error(
                    "[LLM_PROVIDER] provider=%s model=%s status=failed fallback_reason=%s latency_ms=%.1f circuit_state=%s",
                    entry.name,
                    entry.provider.model,
                    fallback_reason,
                    latency,
                    entry.circuit_breaker.state.value,
                    exc_info=True,
                )

        self._last_telemetry = {
            "selected_provider": None,
            "fallback_used": len(failures) > 1,
            "provider_failures": list(failures),
            "failure_reason": failures[0]["reason"] if failures else "all_failed",
            "total_latency_ms": round((time.perf_counter() - overall_t0) * 1000, 2),
        }
        raise RuntimeError(f"All LLM providers failed after trying {tried}: {last_exc}")

    async def stream(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        history: Optional[List[Dict]] = None,
    ) -> AsyncIterator[Tuple[str, str]]:
        """Stream tokens, trying providers in priority order.

        Yields:
            Tuples of (token_text, provider_name).

        Phase 9 contract:
          - If 0 tokens have been yielded, retry with next provider on error.
          - If tokens already yielded, NEVER retry — terminate gracefully.
        """
        from services.llm.provider_errors import (
            classify_gemini_error,
            classify_deepseek_error,
            ProviderErrorType,
            EmptyCompletionError,
        )

        last_exc: Optional[Exception] = None
        tried: List[str] = []
        prev_provider: Optional[str] = None
        failures: List[Dict[str, Any]] = []
        overall_t0 = time.perf_counter()

        logger.info(
            "[LLM_ROUTER] stream_start preferred_provider=%s model=%s providers_count=%d",
            self._providers[0].name if self._providers else "none",
            getattr(self._providers[0].provider, "model", "unknown")
            if self._providers
            else "none",
            len(self._providers),
        )

        for attempt_idx, entry in enumerate(self._providers, 1):
            cb_state = entry.circuit_breaker.state.value
            if not entry.circuit_breaker.is_allowed():
                logger.info(
                    "[LLM_ROUTER] skipping provider=%s (circuit=%s)",
                    entry.name,
                    cb_state,
                )
                continue

            logger.info(
                "[LLM_PROVIDER] provider=%s model=%s status=selected circuit_state=%s",
                entry.name,
                entry.provider.model,
                cb_state,
            )

            if prev_provider is not None:
                logger.info(
                    "[LLM_FAILOVER] from=%s to=%s reason=%s",
                    prev_provider,
                    entry.name,
                    failures[-1]["reason"] if failures else "fallback",
                )

            prev_provider = entry.name
            tried.append(entry.name)
            tokens_yielded = 0
            completion_text = ""
            buffered_whitespace: List[str] = []
            has_non_ws = False
            t0 = time.perf_counter()
            first_token_time: Optional[float] = None

            try:
                async for token in entry.provider.stream(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    history=history,
                ):
                    completion_text += token

                    if not has_non_ws:
                        if token.strip() == "":
                            buffered_whitespace.append(token)
                            continue
                        else:
                            has_non_ws = True
                            for ws in buffered_whitespace:
                                if tokens_yielded == 0:
                                    first_token_time = time.perf_counter()
                                    first_token_latency = (first_token_time - t0) * 1000
                                    logger.info(
                                        "[LLM_PROVIDER] provider=%s status=first_token first_token_latency_ms=%.1f",
                                        entry.name,
                                        first_token_latency,
                                    )
                                tokens_yielded += 1
                                yield ws, entry.name
                            buffered_whitespace.clear()

                    if tokens_yielded == 0:
                        first_token_time = time.perf_counter()
                        first_token_latency = (first_token_time - t0) * 1000
                        logger.info(
                            "[LLM_PROVIDER] provider=%s status=first_token first_token_latency_ms=%.1f",
                            entry.name,
                            first_token_latency,
                        )
                    tokens_yielded += 1
                    yield token, entry.name

                # Validate completion text non-emptiness (meaningful text required for success)
                if completion_text.strip() == "":
                    raise EmptyCompletionError(
                        f"Provider '{entry.name}' completed HTTP stream but returned an empty completion."
                    )

                # Stream completed with non-empty completion text -> genuine success
                latency = (time.perf_counter() - t0) * 1000
                logger.info(
                    "[LLM_PROVIDER] provider=%s model=%s status=success latency_ms=%.1f tokens=%d completion_length=%d",
                    entry.name,
                    entry.provider.model,
                    latency,
                    tokens_yielded,
                    len(completion_text),
                )
                entry.circuit_breaker.record_success()
                self._last_telemetry = {
                    "selected_provider": entry.name,
                    "fallback_used": len(failures) > 0,
                    "provider_failures": list(failures),
                    "failure_reason": failures[0]["reason"] if failures else None,
                    "tokens_yielded": tokens_yielded,
                    "latency_ms": round(latency, 2),
                    "total_latency_ms": round(
                        (time.perf_counter() - overall_t0) * 1000, 2
                    ),
                }
                return  # success — do not try other providers

            except asyncio.CancelledError:
                # Client disconnected — never retry, just stop
                latency = (time.perf_counter() - t0) * 1000
                logger.info(
                    "[LLM_STREAM] client disconnected provider=%s tokens_yielded=%d latency_ms=%.1f",
                    entry.name,
                    tokens_yielded,
                    latency,
                )
                return

            except Exception as exc:
                latency = (time.perf_counter() - t0) * 1000
                last_exc = exc

                # Check for quota exhausted
                is_quota = False
                fallback_reason = "exception"
                error_type_val = "unknown"
                if isinstance(exc, EmptyCompletionError):
                    fallback_reason = "empty_completion"
                    error_type_val = "empty_completion"
                elif entry.name == "gemini":
                    err = classify_gemini_error(exc, "gemini")
                    fallback_reason = err.error_type.value
                    error_type_val = err.error_type.value
                    if err.error_type in (
                        ProviderErrorType.QUOTA_EXCEEDED,
                        ProviderErrorType.RATE_LIMIT_ERROR,
                    ):
                        is_quota = True
                elif entry.name == "deepseek":
                    err = classify_deepseek_error(exc, "deepseek")
                    fallback_reason = err.error_type.value
                    error_type_val = err.error_type.value
                    if err.error_type in (
                        ProviderErrorType.QUOTA_EXCEEDED,
                        ProviderErrorType.RATE_LIMIT_ERROR,
                    ):
                        is_quota = True

                failures.append(
                    {
                        "provider": entry.name,
                        "reason": fallback_reason,
                        "error_type": error_type_val,
                        "latency_ms": round(latency, 2),
                    }
                )

                if is_quota:
                    logger.warning(
                        "[LLM_PROVIDER] provider=%s status=quota_exhausted error=%s",
                        entry.name,
                        str(exc),
                    )
                    entry.circuit_breaker._state = CircuitState.OPEN
                    entry.circuit_breaker._last_failure_time = time.time()
                    entry.circuit_breaker._failure_count = max(
                        entry.circuit_breaker._failure_count,
                        entry.circuit_breaker.failure_threshold,
                    )
                    fallback_reason = "quota_exhausted"
                else:
                    entry.circuit_breaker.record_failure()

                first_token_lat_str = (
                    f"{((first_token_time - t0) * 1000):.1f} ms"
                    if first_token_time
                    else "N/A"
                )

                logger.error(
                    "[LLM_PROVIDER] provider=%s model=%s status=failed fallback_reason=%s tokens_yielded=%d first_token_latency=%s total_latency_ms=%.1f circuit_state=%s",
                    entry.name,
                    entry.provider.model,
                    fallback_reason,
                    tokens_yielded,
                    first_token_lat_str,
                    latency,
                    entry.circuit_breaker.state.value,
                    exc_info=True,
                )

                if len(completion_text.strip()) > 0:
                    # Meaningful content was already delivered to user — NEVER retry to prevent duplicate text
                    logger.warning(
                        "[LLM_STREAM_ERROR] provider=%s failed mid-stream after %d tokens. Aborting to avoid duplication.",
                        entry.name,
                        tokens_yielded,
                    )
                    raise exc

                # 0 meaningful content delivered — safe to try next provider
                continue

        # All providers exhausted (with 0 tokens)
        self._last_telemetry = {
            "selected_provider": None,
            "fallback_used": len(failures) > 1,
            "provider_failures": list(failures),
            "failure_reason": failures[0]["reason"] if failures else "all_failed",
            "total_latency_ms": round((time.perf_counter() - overall_t0) * 1000, 2),
        }
        raise RuntimeError(
            f"All LLM providers failed streaming after trying {tried}: {last_exc}"
        )

    def get_last_telemetry(self) -> Dict[str, Any]:
        """Return telemetry data from the most recent request execution."""
        return dict(self._last_telemetry)

    def provider_status(self) -> List[Dict]:
        """Return circuit breaker status for all providers (for observability)."""
        return [
            {
                "name": e.name,
                "model": getattr(e.provider, "model", "unknown"),
                "priority": e.priority,
                "circuit_state": e.circuit_breaker.state.value,
                "failure_count": e.circuit_breaker._failure_count,
                "configured": True,
            }
            for e in self._providers
        ]

    def reset_all_circuits(self) -> None:
        """Reset all circuit breakers (useful for tests)."""
        for entry in self._providers:
            entry.circuit_breaker.reset()

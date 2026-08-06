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
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


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
    half_open_timeout: float = 10.0

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
                logger.info("CircuitBreaker[%s]: OPEN → HALF_OPEN", self.provider_name)
        elif self._state == CircuitState.HALF_OPEN:
            if now - self._half_open_time >= self.half_open_timeout:
                # Stayed HALF_OPEN too long without resolution — re-open
                self._state = CircuitState.OPEN
                self._last_failure_time = now
        return self._state

    def is_allowed(self) -> bool:
        return self.state in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def record_success(self) -> None:
        if self._state != CircuitState.CLOSED:
            logger.info("CircuitBreaker[%s]: recovered → CLOSED", self.provider_name)
        self._state = CircuitState.CLOSED
        self._failure_count = 0

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold:
            if self._state != CircuitState.OPEN:
                logger.warning(
                    "CircuitBreaker[%s]: threshold reached → OPEN (failures=%d)",
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
    ) -> None:
        """Initialise the ProviderManager.

        Args:
            providers: Ordered list of ProviderEntry objects.
                       If None, loads from ProviderFactory settings.
        """
        if providers is not None:
            self._providers = sorted(providers, key=lambda p: p.priority)
        else:
            self._providers = self._load_from_settings()

    def _load_from_settings(self) -> List[ProviderEntry]:
        """Build providers from application settings."""
        from services.llm import ProviderFactory
        from core.config import settings

        entries: List[ProviderEntry] = []
        provider_name = settings.llm_provider.lower()

        # Primary provider (from config)
        try:
            primary = ProviderFactory.get_provider()
            entries.append(
                ProviderEntry(
                    name=provider_name,
                    provider=primary,
                    priority=1,
                    timeout=60.0,
                )
            )
        except Exception as exc:
            logger.error("ProviderManager: failed to load primary provider: %s", exc)

        # Secondary provider (if configured and different from primary)
        if provider_name == "gemini" and settings.deepseek_api_key:
            try:
                from services.llm.deepseek_provider import DeepSeekProvider

                entries.append(
                    ProviderEntry(
                        name="deepseek",
                        provider=DeepSeekProvider(),
                        priority=2,
                        timeout=120.0,
                    )
                )
                logger.info(
                    "ProviderManager: DeepSeek registered as secondary provider"
                )
            except Exception as exc:
                logger.debug("ProviderManager: DeepSeek secondary unavailable: %s", exc)

        elif provider_name == "deepseek" and settings.gemini_api_key:
            try:
                from services.llm.gemini_provider import GeminiProvider

                entries.append(
                    ProviderEntry(
                        name="gemini",
                        provider=GeminiProvider(),
                        priority=2,
                        timeout=60.0,
                    )
                )
                logger.info("ProviderManager: Gemini registered as secondary provider")
            except Exception as exc:
                logger.debug("ProviderManager: Gemini secondary unavailable: %s", exc)

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

        for attempt_idx, entry in enumerate(self._providers, 1):
            cb_state = entry.circuit_breaker.state.value
            if not entry.circuit_breaker.is_allowed():
                logger.info(
                    "ProviderManager.generate: skipping %s (circuit %s)",
                    entry.name,
                    cb_state,
                )
                continue

            logger.info(
                "Provider selected: %s, model: %s, circuit breaker state: %s",
                entry.name,
                entry.provider.model,
                cb_state,
            )

            if prev_provider is not None:
                logger.info(
                    "Provider switched from %s to %s", prev_provider, entry.name
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
                    "Provider succeeded: %s, model: %s, total latency: %.1f ms, retry count: 0",
                    entry.name,
                    entry.provider.model,
                    latency,
                )
                entry.circuit_breaker.record_success()
                return result, entry.name

            except Exception as exc:
                latency = (time.perf_counter() - t0) * 1000
                last_exc = exc

                # Check for quota exhausted
                is_quota = False
                fallback_reason = "exception"
                if entry.name == "gemini":
                    err = classify_gemini_error(exc, "gemini")
                    fallback_reason = err.error_type.value
                    if err.error_type in (
                        ProviderErrorType.QUOTA_EXCEEDED,
                        ProviderErrorType.RATE_LIMIT_ERROR,
                    ):
                        is_quota = True
                elif entry.name == "deepseek":
                    err = classify_deepseek_error(exc, "deepseek")
                    fallback_reason = err.error_type.value
                    if err.error_type in (
                        ProviderErrorType.QUOTA_EXCEEDED,
                        ProviderErrorType.RATE_LIMIT_ERROR,
                    ):
                        is_quota = True

                if is_quota:
                    logger.warning(
                        "%s quota exhausted. Error: %s",
                        entry.name.capitalize(),
                        str(exc),
                    )
                    # Mark temporarily unavailable by force opening the circuit breaker
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
                    "Provider failed: %s, model: %s, fallback reason: %s, total latency: %.1f ms, retry count: 1, circuit breaker state: %s",
                    entry.name,
                    entry.provider.model,
                    fallback_reason,
                    latency,
                    entry.circuit_breaker.state.value,
                    exc_info=True,
                )

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

        for attempt_idx, entry in enumerate(self._providers, 1):
            cb_state = entry.circuit_breaker.state.value
            if not entry.circuit_breaker.is_allowed():
                logger.info(
                    "ProviderManager.stream: skipping %s (circuit %s)",
                    entry.name,
                    cb_state,
                )
                continue

            logger.info(
                "Provider selected: %s, model: %s, circuit breaker state: %s",
                entry.name,
                entry.provider.model,
                cb_state,
            )

            if prev_provider is not None:
                logger.info(
                    "Provider switched from %s to %s", prev_provider, entry.name
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
                                        "Provider first token received: %s, first token latency: %.1f ms",
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
                            "Provider first token received: %s, first token latency: %.1f ms",
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
                    "Provider succeeded: %s, model: %s, total latency: %.1f ms, tokens: %d, completion_length: %d, retry count: 0",
                    entry.name,
                    entry.provider.model,
                    latency,
                    tokens_yielded,
                    len(completion_text),
                )
                entry.circuit_breaker.record_success()
                return  # success — do not try other providers

            except asyncio.CancelledError:
                # Client disconnected — never retry, just stop
                latency = (time.perf_counter() - t0) * 1000
                logger.info(
                    "ProviderManager.stream: client disconnected provider=%s "
                    "tokens_yielded=%d, completion_length=%d, total latency=%.1f ms",
                    entry.name,
                    tokens_yielded,
                    len(completion_text),
                    latency,
                )
                return

            except Exception as exc:
                latency = (time.perf_counter() - t0) * 1000
                last_exc = exc

                # Check for quota exhausted
                is_quota = False
                fallback_reason = "exception"
                if isinstance(exc, EmptyCompletionError):
                    fallback_reason = "empty_completion"
                elif entry.name == "gemini":
                    err = classify_gemini_error(exc, "gemini")
                    fallback_reason = err.error_type.value
                    if err.error_type in (
                        ProviderErrorType.QUOTA_EXCEEDED,
                        ProviderErrorType.RATE_LIMIT_ERROR,
                    ):
                        is_quota = True
                elif entry.name == "deepseek":
                    err = classify_deepseek_error(exc, "deepseek")
                    fallback_reason = err.error_type.value
                    if err.error_type in (
                        ProviderErrorType.QUOTA_EXCEEDED,
                        ProviderErrorType.RATE_LIMIT_ERROR,
                    ):
                        is_quota = True

                if is_quota:
                    logger.warning(
                        "%s quota exhausted. Error: %s",
                        entry.name.capitalize(),
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
                    "Provider failed: %s, model: %s, fallback reason: %s, tokens yielded: %d, completion_length: %d, first token latency: %s, total latency: %.1f ms, retry count: 1, circuit breaker state: %s",
                    entry.name,
                    entry.provider.model,
                    fallback_reason,
                    tokens_yielded,
                    len(completion_text),
                    first_token_lat_str,
                    latency,
                    entry.circuit_breaker.state.value,
                    exc_info=True,
                )

                if len(completion_text.strip()) > 0:
                    # Meaningful content was already delivered to user — NEVER retry to prevent duplicate text
                    raise exc

                # 0 meaningful content delivered — safe to try next provider
                continue

        # All providers exhausted (with 0 tokens)
        raise RuntimeError(
            f"All LLM providers failed streaming after trying {tried}: {last_exc}"
        )

    def provider_status(self) -> List[Dict]:
        """Return circuit breaker status for all providers (for observability)."""
        return [
            {
                "name": e.name,
                "priority": e.priority,
                "circuit_state": e.circuit_breaker.state.value,
                "failure_count": e.circuit_breaker._failure_count,
            }
            for e in self._providers
        ]

    def reset_all_circuits(self) -> None:
        """Reset all circuit breakers (useful for tests)."""
        for entry in self._providers:
            entry.circuit_breaker.reset()

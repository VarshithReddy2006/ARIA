"""Google Gemini provider via modern google-genai SDK.

Implements the BaseLLMProvider interface so it integrates seamlessly with the rest
of the codebase.
"""

import asyncio
import logging
import time
from typing import AsyncIterator, List, Dict, Any, Optional

from google import genai
from google.genai import types
from .base_provider import BaseLLMProvider, ProviderHealth
from .provider_errors import classify_gemini_error, ProviderErrorType

logger = logging.getLogger(__name__)


class _GeminiClientProxy:
    """Non-SDK proxy used before lazy Client initialization.

    - CI/pytest imports must not create any google-genai SDK client.
    - Unit tests patch `provider.client.aio.models.*` directly.
    """

    _is_proxy = True

    class aio:
        class models:
            # Placeholders exist only so `provider.client.aio.models.X` can be assigned.
            pass


_HEALTH_CHECK_TIMEOUT = 10.0  # seconds — list models is cheap, 10s is generous
_HEALTH_CHECK_PROMPT = "Reply with the single word: ready"


class GeminiProvider(BaseLLMProvider):
    """LLM provider backed by Google Gemini using the google-genai SDK."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        from core.config import settings

        self.api_key = api_key or settings.gemini_api_key or ""
        self.model = model or settings.gemini_model or "gemini-2.5-flash"

        if not self.api_key:
            logger.warning("GEMINI_API_KEY is not set — requests to Gemini will fail.")
            # Do not eagerly initialize the google-genai client during construction/import.
            # The SDK validates the API key during client creation, which breaks CI/pytest
            # during provider discovery/collection when no secrets are available.

        # IMPORTANT: Do not create the google-genai SDK client during construction.
        # CI/pytest imports must succeed without any GEMINI API key.
        self.client: Any = _GeminiClientProxy()
        self._client_lock = asyncio.Lock()
        self._sdk_client_created = False

    async def _get_client(self) -> genai.Client:
        """Return cached google-genai client or lazily create it.

        - Never create the SDK client during __init__.
        - Thread-safe: SDK client is created at most once.
        - If tests have patched proxy methods (generate/list/stream paths),
          keep using the patched proxy (do not overwrite it).
        """
        if getattr(self, "_sdk_client_created", False):
            return self.client  # type: ignore[return-value]

        # If we're still on the proxy and tests already patched the required methods,
        # keep using the proxy so their AsyncMock expectations are honored.
        if getattr(self.client, "_is_proxy", False):
            proxy_models = getattr(getattr(self.client, "aio", None), "models", None)
            if proxy_models is not None and (
                hasattr(proxy_models, "generate_content")
                or hasattr(proxy_models, "generate_content_stream")
                or hasattr(proxy_models, "list")
            ):
                return self.client  # type: ignore[return-value]

        async with self._client_lock:
            if getattr(self, "_sdk_client_created", False):
                return self.client  # type: ignore[return-value]

            if getattr(self.client, "_is_proxy", False):
                proxy_models = getattr(
                    getattr(self.client, "aio", None), "models", None
                )
                if proxy_models is not None and (
                    hasattr(proxy_models, "generate_content")
                    or hasattr(proxy_models, "generate_content_stream")
                    or hasattr(proxy_models, "list")
                ):
                    return self.client  # type: ignore[return-value]

            if not self.api_key:
                raise ValueError("Gemini API key is not configured.")

            self.client = genai.Client(api_key=self.api_key)
            self._sdk_client_created = True
            return self.client

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health_check(self) -> ProviderHealth:
        """Validate Gemini credentials by listing available models.

        ``models.list`` is an inexpensive read-only call that exercises the
        authentication path without generating any content.  It will raise
        a ``ClientError`` with 401/UNAUTHENTICATED if the credential is wrong
        or the wrong credential type is supplied.

        Returns:
            ProviderHealth — never raises.
        """
        # Fast-path: missing credential — no need to make a network call
        if not self.api_key:
            from .provider_errors import _GEMINI_MESSAGES

            msg, rec = _GEMINI_MESSAGES[ProviderErrorType.MISSING_CREDENTIAL]
            logger.error(
                "PROVIDER_HEALTH provider=gemini model=%s authenticated=false "
                "error_type=%s message=%s",
                self.model,
                ProviderErrorType.MISSING_CREDENTIAL.value,
                msg,
            )
            return ProviderHealth(
                healthy=False,
                provider="gemini",
                model=self.model,
                authenticated=False,
                latency_ms=0.0,
                error_message=msg,
                error_type=ProviderErrorType.MISSING_CREDENTIAL.value,
                recommendation=rec,
            )

        client = await self._get_client()
        t0 = time.perf_counter()
        try:
            # google-genai SDK: list models is a lightweight auth validation call
            await asyncio.wait_for(
                client.aio.models.list(),
                timeout=_HEALTH_CHECK_TIMEOUT,
            )
            latency_ms = (time.perf_counter() - t0) * 1000

            logger.info(
                "PROVIDER_HEALTH provider=gemini model=%s healthy=true "
                "authenticated=true latency_ms=%.0f",
                self.model,
                latency_ms,
            )
            return ProviderHealth(
                healthy=True,
                provider="gemini",
                model=self.model,
                authenticated=True,
                latency_ms=latency_ms,
            )

        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000
            error = classify_gemini_error(exc, "gemini")
            is_auth = error.error_type in (
                ProviderErrorType.AUTHENTICATION_ERROR,
                ProviderErrorType.INVALID_CREDENTIAL_TYPE,
                ProviderErrorType.MISSING_CREDENTIAL,
            )

            logger.error(
                "PROVIDER_HEALTH provider=gemini model=%s healthy=false "
                "authenticated=%s error_type=%s latency_ms=%.0f "
                "exc_type=%s recommendation=%s",
                self.model,
                not is_auth,
                error.error_type.value,
                latency_ms,
                type(exc).__name__,
                error.recommendation,
            )
            return ProviderHealth(
                healthy=False,
                provider="gemini",
                model=self.model,
                authenticated=not is_auth,
                latency_ms=latency_ms,
                error_message=error.message,
                error_type=error.error_type.value,
                recommendation=error.recommendation,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_contents(
        self,
        prompt: str,
        history: Optional[List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        """Assembles the list of history turns plus current prompt for google-genai SDK."""
        contents: List[Dict[str, Any]] = []

        if history:
            for turn in history:
                role = turn.get("role", "user")
                # Normalize Gemini/OpenAI roles
                if role == "assistant":
                    role = "model"

                content = turn.get("content", "")
                contents.append({"role": role, "parts": [{"text": str(content)}]})

        contents.append({"role": "user", "parts": [{"text": prompt}]})
        return contents

    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        history: Optional[List[Dict[str, Any]]] = None,
        response_mime_type: Optional[str] = None,
    ) -> str:
        """Generate a complete text response from Gemini with retry policy and timeout."""
        import random

        contents = self._build_contents(prompt, history)
        client = await self._get_client()

        config = types.GenerateContentConfig()
        if system_instruction:
            config.system_instruction = system_instruction
        if response_mime_type == "application/json":
            config.response_mime_type = response_mime_type

        base_delay = 1.0
        timeout_seconds = 30.0
        attempt = 0

        while True:
            try:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=self.model,
                        contents=contents,
                        config=config,
                    ),
                    timeout=timeout_seconds,
                )
                return response.text or ""
            except asyncio.CancelledError:
                logger.info("Gemini generate call cancelled by client/system.")
                raise
            except Exception as e:
                error = classify_gemini_error(e, "gemini")

                is_auth = error.error_type in (
                    ProviderErrorType.AUTHENTICATION_ERROR,
                    ProviderErrorType.INVALID_CREDENTIAL_TYPE,
                    ProviderErrorType.MISSING_CREDENTIAL,
                )
                is_quota = error.error_type in (
                    ProviderErrorType.QUOTA_EXCEEDED,
                    ProviderErrorType.RATE_LIMIT_ERROR,
                )
                should_retry = not is_auth and not is_quota

                if should_retry and attempt < 1:
                    attempt += 1
                    delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                    logger.warning(
                        "Gemini generate failed (transient error, retry %d/1): model=%s "
                        "error_type=%s exc_type=%s retrying_in=%.2fs",
                        attempt,
                        self.model,
                        error.error_type.value,
                        type(e).__name__,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                logger.error(
                    "Gemini generate failed permanently: model=%s error_type=%s exc_type=%s "
                    "attempts=%d",
                    self.model,
                    error.error_type.value,
                    type(e).__name__,
                    attempt + 1,
                    exc_info=True,
                )
                raise

    async def stream(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[str]:
        """Stream token-by-token text output from Gemini with retry policy and timeout."""
        import random

        contents = self._build_contents(prompt, history)
        client = await self._get_client()

        config = types.GenerateContentConfig()
        if system_instruction:
            config.system_instruction = system_instruction

        base_delay = 1.0
        timeout_seconds = 30.0
        attempt = 0

        while True:
            try:
                response_stream = await asyncio.wait_for(
                    client.aio.models.generate_content_stream(
                        model=self.model,
                        contents=contents,
                        config=config,
                    ),
                    timeout=timeout_seconds,
                )
                async for chunk in response_stream:
                    if chunk.text:
                        yield chunk.text
                return
            except asyncio.CancelledError:
                logger.info("Gemini stream call cancelled by client/system.")
                raise
            except Exception as e:
                error = classify_gemini_error(e, "gemini")

                is_auth = error.error_type in (
                    ProviderErrorType.AUTHENTICATION_ERROR,
                    ProviderErrorType.INVALID_CREDENTIAL_TYPE,
                    ProviderErrorType.MISSING_CREDENTIAL,
                )
                is_quota = error.error_type in (
                    ProviderErrorType.QUOTA_EXCEEDED,
                    ProviderErrorType.RATE_LIMIT_ERROR,
                )
                should_retry = not is_auth and not is_quota

                if should_retry and attempt < 1:
                    attempt += 1
                    delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                    logger.warning(
                        "Gemini stream failed (transient error, retry %d/1): model=%s "
                        "error_type=%s exc_type=%s retrying_in=%.2fs",
                        attempt,
                        self.model,
                        error.error_type.value,
                        type(e).__name__,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                logger.error(
                    "Gemini stream failed permanently: model=%s error_type=%s exc_type=%s "
                    "attempts=%d",
                    self.model,
                    error.error_type.value,
                    type(e).__name__,
                    attempt + 1,
                    exc_info=True,
                )
                raise

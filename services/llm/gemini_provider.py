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


class _ModelsProxy:
    pass


class _AioProxy:
    def __init__(self) -> None:
        self.models = _ModelsProxy()


class _GeminiClientProxy:
    """Non-SDK proxy used before lazy Client initialization.

    - CI/pytest imports must not create any google-genai SDK client.
    - Unit tests patch `provider.client.aio.models.*` directly per instance.
    """

    _is_proxy = True

    def __init__(self) -> None:
        self.aio = _AioProxy()


_HEALTH_CHECK_TIMEOUT = 10.0  # seconds — list models is cheap, 10s is generous
_HEALTH_CHECK_PROMPT = "Reply with the single word: ready"


_GEMINI_FALLBACK_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-flash-lite-latest",
    "gemini-2.5-flash",
]


class GeminiProvider(BaseLLMProvider):
    """LLM provider backed by Google Gemini using the google-genai SDK."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        from core.config import get_settings

        current_settings = get_settings()

        self.api_key = (
            api_key if api_key is not None else (current_settings.gemini_api_key or "")
        ).strip()
        self.model = (
            model or current_settings.gemini_model or "gemini-3.1-flash-lite"
        ).strip()

        if current_settings.gemini_fallback_models:
            self.fallback_models = [
                m.strip()
                for m in current_settings.gemini_fallback_models.split(",")
                if m.strip()
            ]
        else:
            self.fallback_models = list(_GEMINI_FALLBACK_MODELS)

        self.timeout = current_settings.llm_total_timeout or 30.0

        if not self.api_key:
            logger.warning("GEMINI_API_KEY is not set — requests to Gemini will fail.")

        self.client: Any = _GeminiClientProxy()
        self._client_lock = asyncio.Lock()
        self._sdk_client_created = False

    async def _get_client(self) -> genai.Client:
        """Return cached google-genai client or lazily create it."""
        if getattr(self, "_sdk_client_created", False):
            return self.client

        if self.client is not None and not getattr(self.client, "_is_proxy", False):
            return self.client

        if not hasattr(self, "_client_lock"):
            self._client_lock = asyncio.Lock()

        async with self._client_lock:
            if getattr(self, "_sdk_client_created", False):
                return self.client

            if getattr(self.client, "_is_proxy", False):
                proxy_models = getattr(
                    getattr(self.client, "aio", None), "models", None
                )
                if proxy_models is not None and (
                    hasattr(proxy_models, "generate_content")
                    or hasattr(proxy_models, "generate_content_stream")
                    or hasattr(proxy_models, "list")
                ):
                    return self.client

            if not self.api_key:
                raise ValueError("Gemini API key is not configured.")

            self.client = genai.Client(api_key=self.api_key)
            self._sdk_client_created = True
            return self.client

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health_check(self) -> ProviderHealth:
        """Validate Gemini credentials by listing available models."""
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
        """Generate a complete text response from Gemini with model fallback and retry policy."""
        contents = self._build_contents(prompt, history)
        client = await self._get_client()

        config = types.GenerateContentConfig()
        if system_instruction:
            config.system_instruction = system_instruction
        if response_mime_type == "application/json":
            config.response_mime_type = response_mime_type

        timeout_seconds = self.timeout
        models_to_try = [self.model] + [
            m for m in self.fallback_models if m != self.model
        ]
        last_error = None

        for idx, model_candidate in enumerate(models_to_try):
            try:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=model_candidate,
                        contents=contents,
                        config=config,
                    ),
                    timeout=timeout_seconds,
                )
                if model_candidate != self.model:
                    logger.info(
                        "[LLM_MODEL_FALLBACK] provider=gemini original_model=%s fallback_model=%s status=success",
                        self.model,
                        model_candidate,
                    )
                return response.text or ""
            except (StopIteration, StopAsyncIteration) as e:
                last_error = e
                break
            except Exception as e:
                last_error = e
                error = classify_gemini_error(e, "gemini")
                is_unrecoverable_model_error = error.error_type in (
                    ProviderErrorType.AUTHENTICATION_ERROR,
                    ProviderErrorType.INVALID_CREDENTIAL_TYPE,
                    ProviderErrorType.MISSING_CREDENTIAL,
                )
                if is_unrecoverable_model_error:
                    logger.error(
                        "[LLM_PROVIDER] provider=gemini model=%s status=error error_type=%s",
                        model_candidate,
                        error.error_type.value,
                    )
                    raise
                logger.warning(
                    "[LLM_MODEL_FALLBACK] provider=gemini model=%s failed (%s). Attempting next model candidate.",
                    model_candidate,
                    error.error_type.value,
                )
                if idx < len(models_to_try) - 1:
                    await asyncio.sleep(1.0)

        logger.error(
            "[LLM_PROVIDER] provider=gemini failed on all model candidates: %s",
            last_error,
        )
        raise last_error

    async def stream(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[str]:
        """Stream token-by-token text output from Gemini with model fallback and timeout."""
        contents = self._build_contents(prompt, history)
        client = await self._get_client()

        config = types.GenerateContentConfig()
        if system_instruction:
            config.system_instruction = system_instruction

        timeout_seconds = self.timeout
        models_to_try = [self.model] + [
            m for m in self.fallback_models if m != self.model
        ]
        last_error = None

        for model_candidate in models_to_try:
            tokens_yielded = 0
            try:
                response_stream = await asyncio.wait_for(
                    client.aio.models.generate_content_stream(
                        model=model_candidate,
                        contents=contents,
                        config=config,
                    ),
                    timeout=timeout_seconds,
                )
                async for chunk in response_stream:
                    if chunk.text:
                        tokens_yielded += 1
                        yield chunk.text

                if tokens_yielded > 0:
                    if model_candidate != self.model:
                        logger.info(
                            "[LLM_MODEL_FALLBACK] provider=gemini original_model=%s fallback_model=%s status=success tokens_yielded=%d",
                            self.model,
                            model_candidate,
                            tokens_yielded,
                        )
                    return
            except asyncio.CancelledError:
                logger.info("Gemini stream call cancelled by client/system.")
                raise
            except Exception as e:
                last_error = e
                # If we already yielded tokens to client, cannot switch model mid-stream
                if tokens_yielded > 0:
                    logger.error(
                        "[LLM_STREAM_ERROR] provider=gemini model=%s failed mid-stream after %d tokens: %s",
                        model_candidate,
                        tokens_yielded,
                        e,
                    )
                    raise

                error = classify_gemini_error(e, "gemini")
                is_auth = error.error_type in (
                    ProviderErrorType.AUTHENTICATION_ERROR,
                    ProviderErrorType.INVALID_CREDENTIAL_TYPE,
                    ProviderErrorType.MISSING_CREDENTIAL,
                )
                if is_auth:
                    logger.error(
                        "[LLM_PROVIDER] provider=gemini model=%s status=auth_error error_type=%s",
                        model_candidate,
                        error.error_type.value,
                    )
                    raise

                logger.warning(
                    "[LLM_MODEL_FALLBACK] provider=gemini model=%s failed (%s). Attempting next model candidate.",
                    model_candidate,
                    error.error_type.value,
                )

        logger.error(
            "[LLM_PROVIDER] provider=gemini stream failed on all model candidates: %s",
            last_error,
        )
        raise last_error

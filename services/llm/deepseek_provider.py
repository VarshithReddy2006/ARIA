"""DeepSeek V4 Flash provider via NVIDIA NIM (OpenAI-compatible API).

Uses the openai SDK pointed at NVIDIA's inference endpoint so no additional
SDK is required beyond what is already standard in the Python ecosystem.
"""

import asyncio
import logging
import time
from typing import AsyncIterator, List, Dict, Any, Optional

import httpx
from .base_provider import BaseLLMProvider, ProviderHealth
from .provider_errors import classify_deepseek_error, ProviderErrorType

logger = logging.getLogger(__name__)

_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
_DEFAULT_MAX_RETRIES = 2  # reduced for MVP — fail fast on sustained 429
_DEFAULT_INITIAL_DELAY = 5.0
_DEFAULT_BACKOFF_FACTOR = 2.0
_DEFAULT_TIMEOUT = 120.0
_HEALTH_CHECK_TIMEOUT = 10.0  # /models is cheap


class DeepSeekProvider(BaseLLMProvider):
    """LLM provider backed by DeepSeek V4 Flash on NVIDIA NIM."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        from core.config import settings

        self.api_key = api_key or settings.deepseek_api_key or ""
        self.base_url = (base_url or settings.deepseek_base_url).rstrip("/")
        self.model = model or settings.deepseek_model
        self.max_retries = max_retries
        self.timeout = timeout

        if not self.api_key:
            logger.warning(
                "DEEPSEEK_API_KEY is not set — requests to NVIDIA NIM will be rejected."
            )

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health_check(self) -> ProviderHealth:
        """Validate DeepSeek/NVIDIA NIM credentials via GET /models.

        ``GET /models`` is an inexpensive read-only call that exercises the
        authentication path without generating any content.

        Returns:
            ProviderHealth — never raises.
        """
        # Fast-path: missing credential
        if not self.api_key:
            from .provider_errors import _DEEPSEEK_MESSAGES

            msg, rec = _DEEPSEEK_MESSAGES[ProviderErrorType.MISSING_CREDENTIAL]
            logger.error(
                "PROVIDER_HEALTH provider=deepseek model=%s authenticated=false "
                "error_type=%s message=%s",
                self.model,
                ProviderErrorType.MISSING_CREDENTIAL.value,
                msg,
            )
            return ProviderHealth(
                healthy=False,
                provider="deepseek",
                model=self.model,
                authenticated=False,
                latency_ms=0.0,
                error_message=msg,
                error_type=ProviderErrorType.MISSING_CREDENTIAL.value,
                recommendation=rec,
            )

        t0 = time.perf_counter()
        url = f"{self.base_url}/models"
        try:
            async with httpx.AsyncClient(timeout=_HEALTH_CHECK_TIMEOUT) as client:
                response = await client.get(url, headers=self._headers())
                response.raise_for_status()

            latency_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                "PROVIDER_HEALTH provider=deepseek model=%s healthy=true "
                "authenticated=true latency_ms=%.0f",
                self.model,
                latency_ms,
            )
            return ProviderHealth(
                healthy=True,
                provider="deepseek",
                model=self.model,
                authenticated=True,
                latency_ms=latency_ms,
            )

        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000
            error = classify_deepseek_error(exc, "deepseek")
            is_auth = error.error_type in (
                ProviderErrorType.AUTHENTICATION_ERROR,
                ProviderErrorType.MISSING_CREDENTIAL,
            )

            logger.error(
                "PROVIDER_HEALTH provider=deepseek model=%s healthy=false "
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
                provider="deepseek",
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

    def _build_messages(
        self,
        prompt: str,
        system_instruction: Optional[str],
        history: Optional[List[Dict[str, Any]]],
    ) -> List[Dict[str, str]]:
        """Assemble the OpenAI-style messages list."""
        messages: List[Dict[str, str]] = []

        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})

        if history:
            for turn in history:
                role = turn.get("role", "user")
                # Normalise 'model' role (Gemini convention) → 'assistant'
                if role == "model":
                    role = "assistant"
                content = turn.get(
                    "content",
                    turn.get("parts", [""])[0]
                    if isinstance(turn.get("parts"), list)
                    else "",
                )
                if content:
                    messages.append({"role": role, "content": str(content)})

        messages.append({"role": "user", "content": prompt})
        return messages

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _post_with_retry(
        self, client: httpx.AsyncClient, payload: Dict[str, Any]
    ) -> httpx.Response:
        """POST /chat/completions with exponential backoff."""
        url = f"{self.base_url}/chat/completions"
        delay = _DEFAULT_INITIAL_DELAY
        last_exc: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                response = await client.post(
                    url,
                    json=payload,
                    headers=self._headers(),
                    timeout=self.timeout,
                )
                if (
                    response.status_code in _RETRY_STATUS_CODES
                    and attempt < self.max_retries - 1
                ):
                    logger.warning(
                        "DeepSeek NIM returned %s (attempt %d/%d). Retrying in %.1fs…",
                        response.status_code,
                        attempt + 1,
                        self.max_retries,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    delay *= _DEFAULT_BACKOFF_FACTOR
                    continue
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                if attempt < self.max_retries - 1:
                    logger.warning(
                        "DeepSeek NIM connection error (attempt %d/%d): %s. Retrying in %.1fs…",
                        attempt + 1,
                        self.max_retries,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    delay *= _DEFAULT_BACKOFF_FACTOR
                    continue
                raise

        raise last_exc or RuntimeError("Max retries exceeded for DeepSeek NIM request.")

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        history: Optional[List[Dict[str, Any]]] = None,
        response_mime_type: Optional[str] = None,
    ) -> str:
        """Generate a complete response (non-streaming)."""
        messages = self._build_messages(prompt, system_instruction, history)

        # When JSON output is requested, ask the model to return valid JSON
        if response_mime_type == "application/json":
            if system_instruction:
                messages[0]["content"] += (
                    "\nYou MUST respond with valid JSON only. No markdown fences, no explanatory text outside the JSON object."
                )
            else:
                messages.insert(
                    0,
                    {
                        "role": "system",
                        "content": "You MUST respond with valid JSON only. No markdown fences, no explanatory text outside the JSON object.",
                    },
                )

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await self._post_with_retry(client, payload)
        except Exception as exc:
            error = classify_deepseek_error(exc, "deepseek")
            logger.error(
                "DeepSeek generate failed: model=%s error_type=%s exc_type=%s",
                self.model,
                error.error_type.value,
                type(exc).__name__,
                exc_info=True,
            )
            raise

        data = response.json()
        text = data["choices"][0]["message"]["content"]

        # Strip markdown code fences that some models add around JSON
        if response_mime_type == "application/json":
            text = _strip_json_fences(text)

        return text

    async def stream(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[str]:
        """Stream token-by-token output via SSE with full lifecycle logging."""
        from .provider_errors import EmptyCompletionError

        messages = self._build_messages(prompt, system_instruction, history)
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }

        url = f"{self.base_url}/chat/completions"
        delay = _DEFAULT_INITIAL_DELAY
        t0 = time.perf_counter()

        logger.info(
            "STREAM_START provider=deepseek model=%s prompt_size=%d",
            self.model,
            len(prompt),
        )

        for attempt in range(self.max_retries):
            tokens_yielded = 0
            completion_text = ""
            finish_reason = None
            first_token = True

            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    async with client.stream(
                        "POST", url, json=payload, headers=self._headers()
                    ) as response:
                        if (
                            response.status_code in _RETRY_STATUS_CODES
                            and attempt < self.max_retries - 1
                        ):
                            logger.warning(
                                "DeepSeek stream returned %s (attempt %d/%d). Retrying in %.1fs…",
                                response.status_code,
                                attempt + 1,
                                self.max_retries,
                                delay,
                            )
                            await asyncio.sleep(delay)
                            delay *= _DEFAULT_BACKOFF_FACTOR
                            continue
                        response.raise_for_status()

                        async for line in response.aiter_lines():
                            if not line or not line.startswith("data:"):
                                continue
                            raw = line[len("data:") :].strip()
                            if not raw or raw == "[DONE]":
                                break
                            try:
                                import json

                                chunk = json.loads(raw)
                                choices = chunk.get("choices", [])
                                if not choices:
                                    continue

                                choice = choices[0]
                                finish_reason = choice.get("finish_reason") or finish_reason
                                delta = choice.get("delta", {})
                                message = choice.get("message", {})

                                # Extract text across all supported payload formats
                                text = ""
                                source = ""

                                if isinstance(delta, dict) and delta.get("content"):
                                    text = delta["content"]
                                    source = "delta.content"
                                elif isinstance(delta, dict) and delta.get("reasoning_content"):
                                    text = delta["reasoning_content"]
                                    source = "delta.reasoning_content"
                                elif isinstance(delta, dict) and delta.get("reasoning"):
                                    text = delta["reasoning"]
                                    source = "delta.reasoning"
                                elif choice.get("text"):
                                    text = choice["text"]
                                    source = "choices[].text"
                                elif isinstance(message, dict) and message.get("content"):
                                    text = message["content"]
                                    source = "message.content"

                                if text:
                                    if first_token:
                                        first_token = False
                                        elapsed_ms = (time.perf_counter() - t0) * 1000
                                        logger.info(
                                            "FIRST_TOKEN provider=deepseek model=%s latency_ms=%.1f source=%s",
                                            self.model,
                                            elapsed_ms,
                                            source,
                                        )

                                    tokens_yielded += 1
                                    completion_text += text
                                    logger.debug(
                                        "STREAM_CHUNK provider=deepseek source=%s text_len=%d",
                                        source,
                                        len(text),
                                    )
                                    yield text

                            except Exception as parse_exc:
                                logger.debug("DeepSeek stream parse error on chunk '%s': %s", raw[:50], parse_exc)
                                continue

                # Stream completed HTTP iteration — validate non-empty completion text
                if completion_text.strip() == "":
                    logger.warning(
                        "DeepSeek returned empty or whitespace-only completion (tokens=%d, len=%d)",
                        tokens_yielded,
                        len(completion_text),
                    )
                    raise EmptyCompletionError("DeepSeek returned an empty completion.")

                elapsed_ms = (time.perf_counter() - t0) * 1000
                logger.info(
                    "STREAM_FINISHED provider=deepseek model=%s tokens=%d completion_len=%d finish_reason=%s elapsed_ms=%.1f",
                    self.model,
                    tokens_yielded,
                    len(completion_text),
                    finish_reason,
                    elapsed_ms,
                )
                return  # success — exit retry loop

            except EmptyCompletionError:
                # Do not retry empty completion on same provider — re-raise for failover
                raise
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                if attempt < self.max_retries - 1:
                    logger.warning("DeepSeek stream error: %s. Retrying…", exc)
                    await asyncio.sleep(delay)
                    delay *= _DEFAULT_BACKOFF_FACTOR
                    continue
                error = classify_deepseek_error(exc, "deepseek")
                logger.error(
                    "DeepSeek stream failed: model=%s error_type=%s exc_type=%s",
                    self.model,
                    error.error_type.value,
                    type(exc).__name__,
                    exc_info=True,
                )
                raise
            finally:
                logger.info("STREAM_CLOSED provider=deepseek model=%s", self.model)


def _strip_json_fences(text: str) -> str:
    """Remove ```json ... ``` fences that models sometimes wrap around JSON."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Drop first line (```json or ```) and last line (```)
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        elif lines[0].strip().startswith("```"):
            lines = lines[1:]
        text = "\n".join(lines).strip()
    return text

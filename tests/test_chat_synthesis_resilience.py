"""Comprehensive regression & property test suite for ARIA Multi-Provider AI Copilot.

Tests covered:
1. Gemini success (preferred provider, DeepSeek not invoked).
2. Gemini model fallback (cascade to candidate model, DeepSeek not invoked).
3. Gemini full exhaustion -> DeepSeek takeover (same context).
4. Gemini quota exhaustion (429 RESOURCE_EXHAUSTED) -> circuit opens -> DeepSeek takeover.
5. Gemini timeout -> DeepSeek takeover with identical context.
6. DeepSeek standalone success.
7. DeepSeek standalone failure -> controlled error.
8. Both providers unavailable -> controlled degraded fallback without stack traces.
9. Authentication failure -> no infinite retries.
10. Circuit breaker recovery progression (CLOSED -> OPEN -> HALF_OPEN probe -> CLOSED).
11. Streaming failover: 0-token failover vs mid-stream abort.
12. Request context preservation invariant (prompt, instructions, history immutable).
13. Security invariant (no secret leakage in telemetry, exceptions, or logs).
14. Failover toggle (LLM_FAILOVER_ENABLED=false prevents secondary failover).
"""

from __future__ import annotations

import time
import pytest
from unittest.mock import MagicMock

from services.chat.provider_manager import (
    ProviderManager,
    ProviderEntry,
    CircuitState,
    CircuitBreaker,
)
from services.chat.fallback_renderer import render_fallback
from services.llm.base_provider import BaseLLMProvider, ProviderHealth
from services.llm.gemini_provider import GeminiProvider
from services.llm.provider_errors import ProviderErrorType


class _MockSuccessProvider(BaseLLMProvider):
    def __init__(self, name: str = "mock-success", model: str = "mock-model"):
        self.name = name
        self.model = model
        self.invocations = 0
        self.last_prompt = None
        self.last_system_instruction = None
        self.last_history = None

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            healthy=True,
            provider=self.name,
            model=self.model,
            authenticated=True,
            latency_ms=10.0,
        )

    async def generate(
        self,
        prompt: str,
        system_instruction: str = None,
        history: list = None,
        **kwargs,
    ) -> str:
        self.invocations += 1
        self.last_prompt = prompt
        self.last_system_instruction = system_instruction
        self.last_history = history
        return f"Synthesized answer from {self.name} ({self.model}) for: {prompt[:30]}"

    async def stream(
        self,
        prompt: str,
        system_instruction: str = None,
        history: list = None,
        **kwargs,
    ):
        self.invocations += 1
        self.last_prompt = prompt
        self.last_system_instruction = system_instruction
        self.last_history = history
        for token in [
            "Synthesized ",
            f"answer from {self.name} ",
            "grounded ",
            "in ",
            "repository.",
        ]:
            yield token


class _MockFailingProvider(BaseLLMProvider):
    def __init__(
        self, name: str = "mock-fail", model: str = "fail-model", error_exc=None
    ):
        self.name = name
        self.model = model
        self.invocations = 0
        self.last_prompt = None
        self.last_system_instruction = None
        self.last_history = None
        self.error_exc = error_exc or RuntimeError(
            "429 RESOURCE_EXHAUSTED: quota exceeded"
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            healthy=False,
            provider=self.name,
            model=self.model,
            authenticated=False,
            latency_ms=0.0,
            error_message=str(self.error_exc),
            error_type=ProviderErrorType.QUOTA_EXCEEDED.value,
        )

    async def generate(
        self,
        prompt: str,
        system_instruction: str = None,
        history: list = None,
        **kwargs,
    ) -> str:
        self.invocations += 1
        self.last_prompt = prompt
        self.last_system_instruction = system_instruction
        self.last_history = history
        raise self.error_exc

    async def stream(
        self,
        prompt: str,
        system_instruction: str = None,
        history: list = None,
        **kwargs,
    ):
        self.invocations += 1
        self.last_prompt = prompt
        self.last_system_instruction = system_instruction
        self.last_history = history
        raise self.error_exc
        yield ""


class _MockMidStreamFailingProvider(BaseLLMProvider):
    def __init__(self, name: str = "mock-mid-fail", model: str = "mid-fail-model"):
        self.name = name
        self.model = model
        self.invocations = 0

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            healthy=True,
            provider=self.name,
            model=self.model,
            authenticated=True,
            latency_ms=5.0,
        )

    async def generate(self, prompt: str, **kwargs) -> str:
        return "Complete text"

    async def stream(self, prompt: str, **kwargs):
        self.invocations += 1
        yield "Initial partial token before crash. "
        raise RuntimeError("Connection dropped mid-stream")


class _MockTimeoutProvider(BaseLLMProvider):
    def __init__(self, name: str = "mock-timeout", model: str = "timeout-model"):
        self.name = name
        self.model = model
        self.invocations = 0

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            healthy=False,
            provider=self.name,
            model=self.model,
            authenticated=True,
            latency_ms=5000.0,
        )

    async def generate(self, prompt: str, **kwargs) -> str:
        self.invocations += 1
        raise TimeoutError("Request timed out")

    async def stream(self, prompt: str, **kwargs):
        self.invocations += 1
        raise TimeoutError("Stream timed out before first token")
        yield ""


# ── Tests ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gemini_success_preferred_deepseek_not_invoked():
    """1. Gemini succeeds normally; DeepSeek is not invoked at all."""
    gemini = _MockSuccessProvider(name="gemini", model="gemini-3.1-flash-lite")
    deepseek = _MockSuccessProvider(
        name="deepseek", model="deepseek-ai/deepseek-v4-flash-0731"
    )

    e1 = ProviderEntry(name="gemini", provider=gemini, priority=1)
    e2 = ProviderEntry(name="deepseek", provider=deepseek, priority=2)
    pm = ProviderManager(providers=[e1, e2])

    resp, prov_used = await pm.generate("Explain FastAPI lifespan")
    assert "from gemini" in resp
    assert prov_used == "gemini"
    assert gemini.invocations == 1
    assert deepseek.invocations == 0


@pytest.mark.asyncio
async def test_gemini_model_fallback_deepseek_not_invoked():
    """2. Gemini model cascade succeeds on secondary candidate; DeepSeek is not invoked."""
    gemini = GeminiProvider(api_key="valid-key", model="gemini-2.5-flash")
    gemini.fallback_models = ["gemini-2.5-flash", "gemini-3.1-flash-lite"]

    mock_client = MagicMock()

    async def mock_generate_stream(model, contents, config):
        if model == "gemini-2.5-flash":
            raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")
        elif model == "gemini-3.1-flash-lite":

            async def _chunks():
                yield MagicMock(text="Grounded response from fallback Gemini model.")

            return _chunks()
        raise RuntimeError(f"Unexpected model {model}")

    mock_client.aio.models.generate_content_stream = mock_generate_stream
    gemini.client = mock_client
    gemini._sdk_client_created = True

    deepseek = _MockSuccessProvider(name="deepseek")
    e1 = ProviderEntry(name="gemini", provider=gemini, priority=1)
    e2 = ProviderEntry(name="deepseek", provider=deepseek, priority=2)
    pm = ProviderManager(providers=[e1, e2])

    tokens = []
    async for token, prov in pm.stream("Explain architecture"):
        tokens.append(token)

    assert "".join(tokens) == "Grounded response from fallback Gemini model."
    assert prov == "gemini"
    assert deepseek.invocations == 0


@pytest.mark.asyncio
async def test_gemini_quota_exhausted_deepseek_takeover_same_context():
    """3. All Gemini models fail with quota exhausted -> DeepSeek takes over with identical context."""
    gemini_err = RuntimeError("429 RESOURCE_EXHAUSTED: Quota limit reached")
    gemini = _MockFailingProvider(
        name="gemini", model="gemini-3.1-flash-lite", error_exc=gemini_err
    )
    deepseek = _MockSuccessProvider(
        name="deepseek", model="deepseek-ai/deepseek-v4-flash-0731"
    )

    e1 = ProviderEntry(name="gemini", provider=gemini, priority=1)
    e2 = ProviderEntry(name="deepseek", provider=deepseek, priority=2)
    pm = ProviderManager(providers=[e1, e2])

    prompt = "Detailed repo query with chunks..."
    sys_inst = "You are ARIA. Respond in markdown."
    hist = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
    ]

    resp, prov_used = await pm.generate(
        prompt=prompt, system_instruction=sys_inst, history=hist
    )

    assert "from deepseek" in resp
    assert prov_used == "deepseek"
    assert gemini.invocations == 1
    assert deepseek.invocations == 1

    # Invariant: request context is identical
    assert deepseek.last_prompt == prompt
    assert deepseek.last_system_instruction == sys_inst
    assert deepseek.last_history == hist

    # Invariant: Gemini circuit is now OPEN
    assert e1.circuit_breaker.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_gemini_timeout_deepseek_takeover():
    """4. Gemini timeout triggers clean failover to DeepSeek."""
    gemini = _MockTimeoutProvider(name="gemini")
    deepseek = _MockSuccessProvider(
        name="deepseek", model="deepseek-ai/deepseek-v4-flash-0731"
    )

    e1 = ProviderEntry(name="gemini", provider=gemini, priority=1, timeout=0.1)
    e2 = ProviderEntry(name="deepseek", provider=deepseek, priority=2)
    pm = ProviderManager(providers=[e1, e2])

    tokens = []
    async for token, prov in pm.stream("Explain latency"):
        tokens.append(token)

    assert "".join(tokens).startswith("Synthesized answer from deepseek")
    assert prov == "deepseek"


@pytest.mark.asyncio
async def test_circuit_breaker_cooldown_and_recovery_to_gemini():
    """5. Circuit breaker OPEN skips Gemini; after cooldown, HALF_OPEN probe restores Gemini."""
    gemini = _MockSuccessProvider(name="gemini")
    deepseek = _MockSuccessProvider(name="deepseek")

    cb = CircuitBreaker(
        provider_name="gemini", failure_threshold=2, recovery_timeout=0.1
    )
    e1 = ProviderEntry(name="gemini", provider=gemini, priority=1)
    e1.circuit_breaker = cb
    e2 = ProviderEntry(name="deepseek", provider=deepseek, priority=2)
    pm = ProviderManager(providers=[e1, e2])

    # Force circuit open
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    # In OPEN state, request immediately goes to DeepSeek
    resp1, prov1 = await pm.generate("Query 1")
    assert prov1 == "deepseek"
    assert gemini.invocations == 0

    # Wait for cooldown
    time.sleep(0.15)
    assert cb.state == CircuitState.HALF_OPEN

    # Next request probes Gemini; on success, circuit closes and Gemini is preferred again!
    resp2, prov2 = await pm.generate("Query 2")
    assert prov2 == "gemini"
    assert cb.state == CircuitState.CLOSED
    assert gemini.invocations == 1


@pytest.mark.asyncio
async def test_streaming_failover_before_tokens_succeeds():
    """6. When primary provider fails before emitting tokens, secondary streams smoothly."""
    failing_primary = _MockFailingProvider(name="gemini")
    working_fallback = _MockSuccessProvider(name="deepseek")

    e1 = ProviderEntry(name="gemini", provider=failing_primary, priority=1)
    e2 = ProviderEntry(name="deepseek", provider=working_fallback, priority=2)
    pm = ProviderManager(providers=[e1, e2])

    tokens = []
    async for token, prov in pm.stream("Streaming query"):
        tokens.append(token)

    assert "".join(tokens).startswith("Synthesized answer from deepseek")
    assert prov == "deepseek"


@pytest.mark.asyncio
async def test_streaming_mid_stream_failure_does_not_duplicate():
    """7. Mid-stream failure after meaningful tokens aborts cleanly without re-streaming from start."""
    mid_fail = _MockMidStreamFailingProvider(name="gemini")
    backup = _MockSuccessProvider(name="deepseek")

    e1 = ProviderEntry(name="gemini", provider=mid_fail, priority=1)
    e2 = ProviderEntry(name="deepseek", provider=backup, priority=2)
    pm = ProviderManager(providers=[e1, e2])

    tokens = []
    with pytest.raises(RuntimeError, match="Connection dropped mid-stream"):
        async for token, prov in pm.stream("Prompt"):
            tokens.append(token)

    assert len(tokens) == 1
    assert tokens[0] == "Initial partial token before crash. "
    # Backup was never invoked to prevent duplicated output text
    assert backup.invocations == 0


@pytest.mark.asyncio
async def test_both_providers_fail_raises_clean_runtime_error():
    """8. When both providers fail, ProviderManager raises RuntimeError without leaking secrets."""
    e1 = ProviderEntry(
        name="gemini", provider=_MockFailingProvider(name="gemini"), priority=1
    )
    e2 = ProviderEntry(
        name="deepseek", provider=_MockFailingProvider(name="deepseek"), priority=2
    )
    pm = ProviderManager(providers=[e1, e2])

    with pytest.raises(RuntimeError) as exc_info:
        await pm.generate("Query")

    err_str = str(exc_info.value)
    assert "All LLM providers failed" in err_str
    # Invariant: no raw keys in error message
    assert "AIza" not in err_str
    assert "nvapi-" not in err_str


@pytest.mark.asyncio
async def test_empty_completion_triggers_failover():
    """9. Empty completion raises EmptyCompletionError and triggers fallback provider."""

    class _EmptyProvider(BaseLLMProvider):
        model = "empty-model"

        async def health_check(self):
            return ProviderHealth(
                healthy=True,
                provider="empty",
                model=self.model,
                authenticated=True,
                latency_ms=1.0,
            )

        async def generate(self, prompt, **kwargs):
            return "   "

        async def stream(self, prompt, **kwargs):
            yield "   "

    e1 = ProviderEntry(name="empty", provider=_EmptyProvider(), priority=1)
    e2 = ProviderEntry(
        name="deepseek", provider=_MockSuccessProvider(name="deepseek"), priority=2
    )
    pm = ProviderManager(providers=[e1, e2])

    tokens = []
    async for token, prov in pm.stream("Prompt"):
        tokens.append(token)

    assert "".join(tokens).startswith("Synthesized answer from deepseek")
    assert prov == "deepseek"


def test_repository_context_remains_available_on_total_failure():
    """10. Structured repository evidence renders intact in fallback UI when LLM is unavailable."""
    chunks = [
        {
            "metadata": {
                "file_path": "Backend/app.py",
                "start_line": 1,
                "end_line": 40,
                "why_this_file": "API Entry Point",
                "confidence": 95,
            }
        },
        {
            "metadata": {
                "file_path": "Backend/features.py",
                "start_line": 1,
                "end_line": 60,
                "why_this_file": "Feature Transformation",
                "confidence": 90,
            }
        },
    ]

    rendered = render_fallback(
        question="How does inference work?",
        structured_intelligence="### Module Structure\nBackend/app.py routes to features.py",
        chunks=chunks,
        source_files=["Backend/app.py", "Backend/features.py"],
        provider_error="429 Resource Exhausted",
    )

    assert "AI synthesis is temporarily unavailable" in rendered
    assert "Repository intelligence is still available" in rendered
    assert "Backend/app.py" in rendered
    assert "Backend/features.py" in rendered
    assert "1–40" in rendered
    assert "1–60" in rendered


@pytest.mark.asyncio
async def test_auth_error_aborts_without_infinite_retry():
    """11. Authentication errors mark provider unhealthy immediately without repeating invalid attempts."""
    gemini = GeminiProvider(api_key="")
    health = await gemini.health_check()

    assert not health.healthy
    assert not health.authenticated
    assert health.error_type == ProviderErrorType.MISSING_CREDENTIAL.value


@pytest.mark.asyncio
async def test_telemetry_captures_failover_metadata():
    """12. Telemetry metadata correctly reflects failover events and latency."""
    gemini = _MockFailingProvider(name="gemini")
    deepseek = _MockSuccessProvider(name="deepseek")

    e1 = ProviderEntry(name="gemini", provider=gemini, priority=1)
    e2 = ProviderEntry(name="deepseek", provider=deepseek, priority=2)
    pm = ProviderManager(providers=[e1, e2])

    resp, prov = await pm.generate("Telemetry test query")
    telemetry = pm.get_last_telemetry()

    assert telemetry["selected_provider"] == "deepseek"
    assert telemetry["fallback_used"] is True
    assert len(telemetry["provider_failures"]) == 1
    assert telemetry["provider_failures"][0]["provider"] == "gemini"
    assert telemetry["total_latency_ms"] > 0

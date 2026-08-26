"""Comprehensive Provider Failover Matrix Test Suite.

Verifies the 12-case test matrix for LLM provider orchestration:
 1. Gemini success → Gemini used, DeepSeek not called
 2. Gemini 429 → DeepSeek called, request succeeds
 3. Gemini timeout → DeepSeek called
 4. Gemini 5xx → DeepSeek called
 5. Gemini capacity error → DeepSeek called
 6. Gemini invalid credentials → controlled error according to provider policy
 7. Gemini malformed request / empty output → handled safely
 8. Gemini fails + DeepSeek succeeds → final response from DeepSeek
 9. Gemini fails + DeepSeek fails → controlled final error
10. Provider telemetry is correct (selected_provider, fallback_used, provider_failures, latencies)
11. Concurrent requests do not corrupt provider state
12. Circuit breaker behavior (CLOSED → OPEN → HALF_OPEN → CLOSED) remains correct
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from services.chat.provider_manager import (
    CircuitBreaker,
    CircuitState,
    ProviderEntry,
    ProviderManager,
)


class MockGeminiClientError(Exception):
    pass


class MockTimeoutError(Exception):
    pass


class MockServerError(Exception):
    pass


@pytest.fixture
def mock_gemini_provider():
    p = MagicMock()
    p.model = "gemini-2.5-flash"
    p.generate = AsyncMock(return_value="Gemini response")
    return p


@pytest.fixture
def mock_deepseek_provider():
    p = MagicMock()
    p.model = "deepseek-chat"
    p.generate = AsyncMock(return_value="DeepSeek response")
    return p


@pytest.mark.anyio
class TestProviderFailoverMatrix:
    # 1. Gemini success → Gemini used, DeepSeek not called
    async def test_1_gemini_success_deepseek_not_called(
        self, mock_gemini_provider, mock_deepseek_provider
    ):
        e1 = ProviderEntry(name="gemini", provider=mock_gemini_provider, priority=1)
        e2 = ProviderEntry(name="deepseek", provider=mock_deepseek_provider, priority=2)
        pm = ProviderManager(providers=[e1, e2])

        res, provider_used = await pm.generate("What is ARIA?")
        assert res == "Gemini response"
        assert provider_used == "gemini"
        assert mock_gemini_provider.generate.call_count == 1
        assert mock_deepseek_provider.generate.call_count == 0

        telemetry = pm.get_last_telemetry()
        assert telemetry["selected_provider"] == "gemini"
        assert telemetry["fallback_used"] is False
        assert len(telemetry["provider_failures"]) == 0

    # 2. Gemini 429 → DeepSeek called, request succeeds
    async def test_2_gemini_429_deepseek_succeeds(
        self, mock_gemini_provider, mock_deepseek_provider
    ):
        mock_gemini_provider.generate = AsyncMock(
            side_effect=MockGeminiClientError(
                "ClientError: 429 RESOURCE_EXHAUSTED quota exceeded"
            )
        )
        e1 = ProviderEntry(name="gemini", provider=mock_gemini_provider, priority=1)
        e2 = ProviderEntry(name="deepseek", provider=mock_deepseek_provider, priority=2)
        pm = ProviderManager(providers=[e1, e2])

        res, provider_used = await pm.generate("Analyze repo")
        assert res == "DeepSeek response"
        assert provider_used == "deepseek"
        assert mock_gemini_provider.generate.call_count == 1
        assert mock_deepseek_provider.generate.call_count == 1
        assert e1.circuit_breaker.state == CircuitState.OPEN

        telemetry = pm.get_last_telemetry()
        assert telemetry["selected_provider"] == "deepseek"
        assert telemetry["fallback_used"] is True
        assert len(telemetry["provider_failures"]) == 1
        assert telemetry["provider_failures"][0]["provider"] == "gemini"

    # 3. Gemini timeout → DeepSeek called
    async def test_3_gemini_timeout_deepseek_called(
        self, mock_gemini_provider, mock_deepseek_provider
    ):
        mock_gemini_provider.generate = AsyncMock(
            side_effect=MockTimeoutError("Request timed out after 30s")
        )
        e1 = ProviderEntry(name="gemini", provider=mock_gemini_provider, priority=1)
        e2 = ProviderEntry(name="deepseek", provider=mock_deepseek_provider, priority=2)
        pm = ProviderManager(providers=[e1, e2])

        res, provider_used = await pm.generate("Summarize architecture")
        assert res == "DeepSeek response"
        assert provider_used == "deepseek"
        assert mock_deepseek_provider.generate.call_count == 1

        telemetry = pm.get_last_telemetry()
        assert telemetry["selected_provider"] == "deepseek"
        assert telemetry["fallback_used"] is True

    # 4. Gemini 5xx → DeepSeek called
    async def test_4_gemini_5xx_deepseek_called(
        self, mock_gemini_provider, mock_deepseek_provider
    ):
        mock_gemini_provider.generate = AsyncMock(
            side_effect=MockServerError("ServerError: 503 Service Unavailable")
        )
        e1 = ProviderEntry(name="gemini", provider=mock_gemini_provider, priority=1)
        e2 = ProviderEntry(name="deepseek", provider=mock_deepseek_provider, priority=2)
        pm = ProviderManager(providers=[e1, e2])

        res, provider_used = await pm.generate("List endpoints")
        assert res == "DeepSeek response"
        assert provider_used == "deepseek"

    # 5. Gemini capacity error → DeepSeek called
    async def test_5_gemini_capacity_error_deepseek_called(
        self, mock_gemini_provider, mock_deepseek_provider
    ):
        mock_gemini_provider.generate = AsyncMock(
            side_effect=MockGeminiClientError(
                "Server is experiencing high demand. Please try again later."
            )
        )
        e1 = ProviderEntry(name="gemini", provider=mock_gemini_provider, priority=1)
        e2 = ProviderEntry(name="deepseek", provider=mock_deepseek_provider, priority=2)
        pm = ProviderManager(providers=[e1, e2])

        res, provider_used = await pm.generate("Find vulnerabilities")
        assert res == "DeepSeek response"
        assert provider_used == "deepseek"

    # 6. Gemini invalid credentials → controlled fallback or error
    async def test_6_gemini_invalid_credentials_policy(
        self, mock_gemini_provider, mock_deepseek_provider
    ):
        mock_gemini_provider.generate = AsyncMock(
            side_effect=MockGeminiClientError(
                "ClientError 401 UNAUTHENTICATED: API key invalid"
            )
        )
        e1 = ProviderEntry(name="gemini", provider=mock_gemini_provider, priority=1)
        e2 = ProviderEntry(name="deepseek", provider=mock_deepseek_provider, priority=2)
        pm = ProviderManager(providers=[e1, e2])

        # ProviderManager allows configured secondary provider to rescue the request
        res, provider_used = await pm.generate("Explain authentication")
        assert res == "DeepSeek response"
        assert provider_used == "deepseek"

    # 7. Gemini streaming with empty completion triggers fallback
    async def test_7_gemini_empty_completion_stream_fallback(
        self, mock_deepseek_provider
    ):
        mock_gemini_stream = MagicMock()
        mock_gemini_stream.model = "gemini-2.5-flash"

        async def empty_stream(*args, **kwargs):
            if False:
                yield ""

        mock_gemini_stream.stream = empty_stream

        async def deepseek_stream(*args, **kwargs):
            yield "DeepSeek token 1"
            yield " token 2"

        mock_deepseek_provider.stream = deepseek_stream

        e1 = ProviderEntry(name="gemini", provider=mock_gemini_stream, priority=1)
        e2 = ProviderEntry(name="deepseek", provider=mock_deepseek_provider, priority=2)
        pm = ProviderManager(providers=[e1, e2])

        tokens = []
        async for tok, prov in pm.stream("Prompt"):
            tokens.append((tok, prov))

        assert len(tokens) == 2
        assert "".join(t[0] for t in tokens) == "DeepSeek token 1 token 2"
        assert all(t[1] == "deepseek" for t in tokens)

    # 8. Gemini fails + DeepSeek succeeds → final response from DeepSeek
    async def test_8_gemini_fails_deepseek_succeeds(
        self, mock_gemini_provider, mock_deepseek_provider
    ):
        mock_gemini_provider.generate = AsyncMock(
            side_effect=RuntimeError("Primary crashed")
        )
        e1 = ProviderEntry(name="gemini", provider=mock_gemini_provider, priority=1)
        e2 = ProviderEntry(name="deepseek", provider=mock_deepseek_provider, priority=2)
        pm = ProviderManager(providers=[e1, e2])

        res, prov = await pm.generate("Hello")
        assert res == "DeepSeek response"
        assert prov == "deepseek"

    # 9. Gemini fails + DeepSeek fails → controlled final error
    async def test_9_gemini_fails_deepseek_fails_raises_runtime_error(
        self, mock_gemini_provider, mock_deepseek_provider
    ):
        mock_gemini_provider.generate = AsyncMock(
            side_effect=MockGeminiClientError("429 rate limited")
        )
        mock_deepseek_provider.generate = AsyncMock(
            side_effect=MockServerError("500 internal server error")
        )
        e1 = ProviderEntry(name="gemini", provider=mock_gemini_provider, priority=1)
        e2 = ProviderEntry(name="deepseek", provider=mock_deepseek_provider, priority=2)
        pm = ProviderManager(providers=[e1, e2])

        with pytest.raises(RuntimeError) as exc_info:
            await pm.generate("Hello")

        assert "All LLM providers failed after trying" in str(exc_info.value)
        telemetry = pm.get_last_telemetry()
        assert telemetry["selected_provider"] is None
        assert len(telemetry["provider_failures"]) == 2

    # 10. Provider telemetry is correct
    async def test_10_provider_telemetry_correctness(
        self, mock_gemini_provider, mock_deepseek_provider
    ):
        mock_gemini_provider.generate = AsyncMock(
            side_effect=MockGeminiClientError("429 Quota Exceeded")
        )
        e1 = ProviderEntry(name="gemini", provider=mock_gemini_provider, priority=1)
        e2 = ProviderEntry(name="deepseek", provider=mock_deepseek_provider, priority=2)
        pm = ProviderManager(providers=[e1, e2])

        res, prov = await pm.generate("Test query")
        t = pm.get_last_telemetry()
        assert t["selected_provider"] == "deepseek"
        assert t["fallback_used"] is True
        assert t["failure_reason"] == "quota_exceeded"
        assert t["total_latency_ms"] >= 0.0
        assert len(t["provider_failures"]) == 1
        assert t["provider_failures"][0]["provider"] == "gemini"

    # 11. Concurrent requests do not corrupt provider state
    async def test_11_concurrent_requests_state_safety(
        self, mock_gemini_provider, mock_deepseek_provider
    ):
        e1 = ProviderEntry(name="gemini", provider=mock_gemini_provider, priority=1)
        e2 = ProviderEntry(name="deepseek", provider=mock_deepseek_provider, priority=2)
        pm = ProviderManager(providers=[e1, e2])

        tasks = [pm.generate(f"Query {i}") for i in range(10)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 10
        assert all(
            res[0] == "Gemini response" and res[1] == "gemini" for res in results
        )

    # 12. Circuit breaker state transitions remain correct
    async def test_12_circuit_breaker_state_transitions(self):
        cb = CircuitBreaker(
            provider_name="gemini", failure_threshold=2, recovery_timeout=0.1
        )
        assert cb.state == CircuitState.CLOSED
        assert cb.is_allowed() is True

        cb.record_failure()
        assert cb.state == CircuitState.CLOSED  # 1/2 failures

        cb.record_failure()
        assert cb.state == CircuitState.OPEN  # 2/2 failures -> OPEN
        assert cb.is_allowed() is False

        # Wait for recovery timeout
        await asyncio.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.is_allowed() is True

        # Successful request closes the circuit
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

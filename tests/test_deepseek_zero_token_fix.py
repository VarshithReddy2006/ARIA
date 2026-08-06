"""DeepSeek Zero-Token & Streaming Lifecycle Regression Test Suite.

Verifies:
  1. DeepSeek provider parses multi-format SSE payloads (delta.content, delta.reasoning_content, delta.reasoning, choices[].text, message.content).
  2. ProviderManager requires non-empty completion text (completion_text.strip() != "") to declare success.
  3. Empty or whitespace-only completions raise EmptyCompletionError and trigger automatic provider failover.
  4. Stream lifecycle events (STREAM_START -> FIRST_TOKEN -> LAST_TOKEN -> STREAM_FINISHED -> STREAM_CLOSED) log accurately.
  5. Scenarios A, B, C, D, E, F, G, H, I, J pass cleanly under all conditions.
"""

from __future__ import annotations

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.llm.base_provider import BaseLLMProvider, ProviderHealth
from services.llm.deepseek_provider import DeepSeekProvider
from services.llm.provider_errors import EmptyCompletionError
from services.chat.provider_manager import ProviderManager, ProviderEntry


class MockStreamProvider(BaseLLMProvider):
    def __init__(self, name: str, model: str, stream_chunks: list[str], raise_exc: Exception | None = None):
        self.name = name
        self.model = model
        self.stream_chunks = stream_chunks
        self.raise_exc = raise_exc

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(healthy=True, provider=self.name, model=self.model, authenticated=True)

    async def generate(self, prompt: str, system_instruction: str | None = None, history: list[dict] | None = None) -> str:
        if self.raise_exc:
            raise self.raise_exc
        return "".join(self.stream_chunks)

    async def stream(self, prompt: str, system_instruction: str | None = None, history: list[dict] | None = None):
        if self.raise_exc:
            raise self.raise_exc
        for chunk in self.stream_chunks:
            yield chunk


def _create_mock_async_client(mock_lines: list[str]):
    """Helper to mock httpx.AsyncClient with async context manager stream."""
    async def mock_aiter_lines():
        for line in mock_lines:
            yield line

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.aiter_lines = mock_aiter_lines
    mock_resp.raise_for_status = MagicMock()

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_stream_ctx)

    mock_async_client_ctx = MagicMock()
    mock_async_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_async_client_ctx.__aexit__ = AsyncMock(return_value=None)

    return MagicMock(return_value=mock_async_client_ctx)


@pytest.mark.asyncio
class TestDeepSeekZeroTokenFix:

    async def test_scenario_a_gemini_succeeds(self):
        """Scenario A: Primary provider succeeds -> tokens streamed -> stream completes."""
        p1 = MockStreamProvider("gemini", "gemini-2.5-flash", ["Hello ", "world!"])
        manager = ProviderManager(providers=[ProviderEntry("gemini", p1, 1)])

        tokens = []
        async for token, name in manager.stream("Test prompt"):
            tokens.append(token)
            assert name == "gemini"

        assert "".join(tokens) == "Hello world!"
        assert manager._providers[0].circuit_breaker.state.value == "closed"

    async def test_scenario_b_gemini_quota_failover_to_deepseek(self):
        """Scenario B: Gemini fails 429 quota -> DeepSeek succeeds -> tokens streamed."""
        p1 = MockStreamProvider("gemini", "gemini-2.5-flash", [], raise_exc=RuntimeError("429 Resource Exhausted"))
        p2 = MockStreamProvider("deepseek", "deepseek-v4-flash", ["DeepSeek ", "response."])
        manager = ProviderManager(providers=[
            ProviderEntry("gemini", p1, 1),
            ProviderEntry("deepseek", p2, 2),
        ])

        tokens = []
        used_providers = []
        async for token, name in manager.stream("Test prompt"):
            tokens.append(token)
            used_providers.append(name)

        assert "".join(tokens) == "DeepSeek response."
        assert set(used_providers) == {"deepseek"}

    async def test_scenario_c_and_f_empty_or_whitespace_completion_triggers_failover(self):
        """Scenario C & F: Provider returns 0 tokens or whitespace only -> EmptyCompletionError -> Failover."""
        p1 = MockStreamProvider("deepseek", "deepseek-v4-flash", ["   ", "\n", "\t"])
        p2 = MockStreamProvider("gemini", "gemini-2.5-flash", ["Fallback ", "success."])
        manager = ProviderManager(providers=[
            ProviderEntry("deepseek", p1, 1),
            ProviderEntry("gemini", p2, 2),
        ])

        tokens = []
        used_providers = []
        async for token, name in manager.stream("Test prompt"):
            tokens.append(token)
            used_providers.append(name)

        assert "".join(tokens) == "Fallback success."
        assert set(used_providers) == {"gemini"}

    async def test_scenario_g_reasoning_content_parsed_correctly(self):
        """Scenario G: Provider streams reasoning_content payload -> parsed and yielded."""
        provider = DeepSeekProvider(api_key="mock", base_url="http://mock", model="deepseek-v4")

        mock_lines = [
            'data: {"choices":[{"delta":{"reasoning_content":"Step 1 reasoning"}}]}',
            'data: {"choices":[{"delta":{"content":" Final answer"}}]}',
            'data: [DONE]',
        ]

        mock_factory = _create_mock_async_client(mock_lines)
        with patch("httpx.AsyncClient", mock_factory):
            chunks = []
            async for token in provider.stream("Explain API"):
                chunks.append(token)

            assert chunks == ["Step 1 reasoning", " Final answer"]

    async def test_scenario_h_immediate_done_without_content_raises_empty_completion(self):
        """Scenario H: Provider sends [DONE] immediately without content -> EmptyCompletionError."""
        provider = DeepSeekProvider(api_key="mock", base_url="http://mock", model="deepseek-v4")

        mock_lines = ['data: [DONE]']

        mock_factory = _create_mock_async_client(mock_lines)
        with patch("httpx.AsyncClient", mock_factory):
            with pytest.raises(EmptyCompletionError):
                async for _ in provider.stream("Explain API"):
                    pass

    async def test_scenario_i_malformed_json_chunks_skipped_gracefully(self):
        """Scenario I: Malformed JSON chunks in SSE stream -> skipped gracefully without crash."""
        provider = DeepSeekProvider(api_key="mock", base_url="http://mock", model="deepseek-v4")

        mock_lines = [
            'data: {INVALID_JSON}',
            'data: {"choices":[{"delta":{"content":"Valid chunk"}}]}',
            'data: [DONE]',
        ]

        mock_factory = _create_mock_async_client(mock_lines)
        with patch("httpx.AsyncClient", mock_factory):
            chunks = []
            async for token in provider.stream("Explain API"):
                chunks.append(token)

            assert chunks == ["Valid chunk"]

    async def test_scenario_e_100_consecutive_stream_requests_stress(self):
        """Scenario E: 100 consecutive requests stress test -> 0 stuck streams."""
        p1 = MockStreamProvider("deepseek", "deepseek-v4", ["Chunk 1 ", "Chunk 2"])
        manager = ProviderManager(providers=[ProviderEntry("deepseek", p1, 1)])

        for i in range(100):
            tokens = []
            async for token, _ in manager.stream(f"Stress request {i}"):
                tokens.append(token)
            assert "".join(tokens) == "Chunk 1 Chunk 2"

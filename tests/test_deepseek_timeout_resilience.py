"""Focused tests for DeepSeek timeout configuration, exception handling, and failover resilience."""

from __future__ import annotations

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.config import Settings
from services.llm.deepseek_provider import DeepSeekProvider
from services.llm.provider_errors import classify_deepseek_error, ProviderErrorType
from services.chat.provider_manager import ProviderManager, ProviderEntry, CircuitState


@pytest.mark.asyncio
class TestDeepSeekTimeoutResilience:
    async def test_deepseek_provider_default_timeout_is_60s(self):
        """Verify DeepSeekProvider defaults to 60.0s read timeout and 10.0s connect timeout."""
        settings = Settings(llm_read_timeout=60.0, llm_connect_timeout=10.0)
        with patch("core.config.get_settings", return_value=settings):
            provider = DeepSeekProvider(api_key="nvapi-testkey1234567890")
            assert provider.timeout == 60.0
            assert provider.connect_timeout == 10.0

            client = await provider._get_client()
            assert client.timeout.read == 60.0
            assert client.timeout.connect == 10.0
            await provider.aclose()

    async def test_deepseek_provider_custom_timeout_override(self):
        """Verify custom timeout override is respected."""
        provider = DeepSeekProvider(
            api_key="nvapi-testkey1234567890",
            timeout=45.0,
        )
        assert provider.timeout == 45.0
        client = await provider._get_client()
        assert client.timeout.read == 45.0
        await provider.aclose()

    async def test_classify_deepseek_read_timeout_error(self):
        """Verify httpx.ReadTimeout is classified as ProviderErrorType.TIMEOUT."""
        exc = httpx.ReadTimeout("The read operation timed out")
        error = classify_deepseek_error(exc, "deepseek")
        assert error.error_type == ProviderErrorType.TIMEOUT
        assert "timed out" in error.message.lower()

    async def test_classify_deepseek_connect_timeout_error(self):
        """Verify httpx.ConnectTimeout is classified as ProviderErrorType.TIMEOUT."""
        exc = httpx.ConnectTimeout("Connection timed out")
        error = classify_deepseek_error(exc, "deepseek")
        assert error.error_type == ProviderErrorType.TIMEOUT

    async def test_deepseek_stream_handles_slow_first_token(self):
        """Verify streaming succeeds when first token arrives after normal processing."""
        provider = DeepSeekProvider(
            api_key="nvapi-mock-key",
            base_url="https://integrate.api.nvidia.com/v1",
            model="deepseek-ai/deepseek-v4-flash-0731",
        )

        mock_lines = [
            'data: {"choices":[{"delta":{"content":"Slow "}}]}',
            'data: {"choices":[{"delta":{"content":"token stream."}}]}',
            "data: [DONE]",
        ]

        def mock_aiter_lines():
            async def _gen():
                for line in mock_lines:
                    yield line

            return _gen()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.aiter_lines = mock_aiter_lines
        mock_resp.raise_for_status = MagicMock()

        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)

        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)
        mock_client.is_closed = False
        mock_client.aclose = AsyncMock()

        with patch("httpx.AsyncClient", return_value=mock_client):
            chunks = []
            async for chunk in provider.stream("Test prompt"):
                chunks.append(chunk)

            assert "".join(chunks) == "Slow token stream."

    async def test_failover_when_primary_gemini_fails_and_deepseek_times_out(self):
        """Verify failover behavior when Gemini fails and DeepSeek times out."""
        mock_gemini = MagicMock()
        mock_gemini.model = "gemini-3.1-flash-lite"

        async def gemini_stream_fail(*args, **kwargs):
            if False:
                yield ""
            raise RuntimeError("Gemini 401 UNAUTHENTICATED")

        mock_gemini.stream = gemini_stream_fail

        mock_deepseek = MagicMock()
        mock_deepseek.model = "deepseek-ai/deepseek-v4-flash-0731"

        async def deepseek_stream_timeout(*args, **kwargs):
            if False:
                yield ""
            raise httpx.ReadTimeout("The read operation timed out")

        mock_deepseek.stream = deepseek_stream_timeout

        e1 = ProviderEntry(name="gemini", provider=mock_gemini, priority=1)
        e2 = ProviderEntry(name="deepseek", provider=mock_deepseek, priority=2)

        manager = ProviderManager(providers=[e1, e2])

        with pytest.raises(RuntimeError) as exc_info:
            async for _ in manager.stream("Test prompt"):
                pass

        assert "All LLM providers failed" in str(exc_info.value)
        telemetry = manager.get_last_telemetry()
        assert telemetry["fallback_used"] is True
        assert len(telemetry["provider_failures"]) == 2
        assert telemetry["provider_failures"][0]["provider"] == "gemini"
        assert telemetry["provider_failures"][1]["provider"] == "deepseek"
        assert telemetry["provider_failures"][1]["error_type"] == "timeout"

    async def test_gemini_primary_success_leaves_deepseek_untouched(self):
        """Verify Gemini success does not invoke DeepSeek."""
        mock_gemini = MagicMock()
        mock_gemini.model = "gemini-3.1-flash-lite"

        async def gemini_stream_ok(*args, **kwargs):
            yield "Gemini "
            yield "response"

        mock_gemini.stream = gemini_stream_ok

        mock_deepseek = MagicMock()
        mock_deepseek.model = "deepseek-ai/deepseek-v4-flash-0731"
        mock_deepseek.stream = MagicMock()

        e1 = ProviderEntry(name="gemini", provider=mock_gemini, priority=1)
        e2 = ProviderEntry(name="deepseek", provider=mock_deepseek, priority=2)

        manager = ProviderManager(providers=[e1, e2])

        tokens = []
        async for token, name in manager.stream("Test prompt"):
            tokens.append(token)
            assert name == "gemini"

        assert "".join(tokens) == "Gemini response"
        assert mock_deepseek.stream.call_count == 0
        assert e1.circuit_breaker.state == CircuitState.CLOSED

    async def test_deepseek_529_failover_to_tertiary_nvidia_model(self):
        """Verify 529 overload on DeepSeek cleanly fails over to tertiary NVIDIA candidate."""
        mock_gemini = MagicMock()
        mock_gemini.model = "gemini-3.1-flash-lite"

        async def gemini_stream_fail(*args, **kwargs):
            if False:
                yield ""
            raise RuntimeError("Gemini 401 UNAUTHENTICATED")

        mock_gemini.stream = gemini_stream_fail

        mock_deepseek = MagicMock()
        mock_deepseek.model = "deepseek-ai/deepseek-v4-flash-0731"

        async def deepseek_529(*args, **kwargs):
            if False:
                yield ""
            request = httpx.Request(
                "POST", "https://integrate.api.nvidia.com/v1/chat/completions"
            )
            response = httpx.Response(529, request=request)
            raise httpx.HTTPStatusError(
                "Server error 529", request=request, response=response
            )

        mock_deepseek.stream = deepseek_529

        mock_backup = MagicMock()
        mock_backup.model = "meta/llama-3.2-11b-vision-instruct"

        async def backup_stream_ok(*args, **kwargs):
            yield "Backup "
            yield "NVIDIA "
            yield "response"

        mock_backup.stream = backup_stream_ok

        e1 = ProviderEntry(name="gemini", provider=mock_gemini, priority=1)
        e2 = ProviderEntry(name="deepseek", provider=mock_deepseek, priority=2)
        e3 = ProviderEntry(name="nvidia_backup", provider=mock_backup, priority=3)

        manager = ProviderManager(providers=[e1, e2, e3])

        tokens = []
        async for token, name in manager.stream("Test prompt"):
            tokens.append(token)
            assert name == "nvidia_backup"

        assert "".join(tokens) == "Backup NVIDIA response"
        telemetry = manager.get_last_telemetry()
        assert telemetry["selected_provider"] == "nvidia_backup"
        assert telemetry["fallback_used"] is True
        assert len(telemetry["provider_failures"]) == 2
        assert telemetry["provider_failures"][0]["provider"] == "gemini"
        assert telemetry["provider_failures"][1]["provider"] == "deepseek"
        assert telemetry["provider_failures"][1]["error_type"] == "rate_limit_error"

    async def test_deepseek_read_timeout_failover_to_tertiary_nvidia_model(self):
        """Verify ReadTimeout on DeepSeek cleanly fails over to tertiary NVIDIA candidate."""
        mock_gemini = MagicMock()
        mock_gemini.model = "gemini-3.1-flash-lite"

        async def gemini_stream_fail(*args, **kwargs):
            if False:
                yield ""
            raise RuntimeError("Gemini quota exceeded")

        mock_gemini.stream = gemini_stream_fail

        mock_deepseek = MagicMock()
        mock_deepseek.model = "deepseek-ai/deepseek-v4-flash-0731"

        async def deepseek_timeout(*args, **kwargs):
            if False:
                yield ""
            raise httpx.ReadTimeout("Read operation timed out after 60s")

        mock_deepseek.stream = deepseek_timeout

        mock_backup = MagicMock()
        mock_backup.model = "meta/llama-3.2-11b-vision-instruct"

        async def backup_stream_ok(*args, **kwargs):
            yield "Recovered "
            yield "response"

        mock_backup.stream = backup_stream_ok

        e1 = ProviderEntry(name="gemini", provider=mock_gemini, priority=1)
        e2 = ProviderEntry(name="deepseek", provider=mock_deepseek, priority=2)
        e3 = ProviderEntry(name="nvidia_backup", provider=mock_backup, priority=3)

        manager = ProviderManager(providers=[e1, e2, e3])

        tokens = []
        async for token, name in manager.stream("Test prompt"):
            tokens.append(token)
            assert name == "nvidia_backup"

        assert "".join(tokens) == "Recovered response"
        telemetry = manager.get_last_telemetry()
        assert telemetry["selected_provider"] == "nvidia_backup"
        assert telemetry["fallback_used"] is True
        assert telemetry["provider_failures"][1]["error_type"] == "timeout"

    async def test_provider_manager_loads_fallback_candidates_from_settings(self):
        """Verify Settings.deepseek_fallback_models are correctly registered as tertiary entries."""
        settings = Settings(
            llm_provider="gemini",
            gemini_api_key="AQ.testkey1234567890",
            deepseek_api_key="nvapi-testkey1234567890",
            deepseek_fallback_models="meta/llama-3.2-11b-vision-instruct,minimaxai/minimax-m3",
        )
        manager = ProviderManager(settings=settings)
        entries = manager._providers
        names = [e.name for e in entries]
        assert "gemini" in names
        assert "deepseek" in names
        assert any("llama_3_2_11b" in n for n in names)
        assert any("minimax_m3" in n for n in names)
        assert entries[0].priority < entries[1].priority < entries[2].priority

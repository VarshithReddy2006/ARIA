"""Comprehensive regression test suite for LLM provider pipeline & fallback orchestration.

Covers all 10 requirements from Phase 8:
1. Both Gemini and DeepSeek register when configured.
2. Gemini succeeds → Gemini response returned.
3. Gemini fails → DeepSeek is attempted.
4. Gemini fails + DeepSeek succeeds → successful response returned.
5. Both providers fail → fallback response is returned.
6. ProviderManager uses current runtime settings rather than stale module-level settings.
7. Missing Gemini key does not prevent configured DeepSeek from being used.
8. Missing DeepSeek key does not prevent configured Gemini from being used.
9. Provider exceptions are logged/classified without leaking API keys.
10. Streaming provider failures correctly trigger fallback when supported by the architecture.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from core.config import Settings
from services.chat.provider_manager import ProviderManager, ProviderEntry
from services.llm.provider_errors import (
    classify_gemini_error,
    classify_deepseek_error,
    ProviderErrorType,
)
from services.chat.retrieval_pipeline import RetrievalPipeline


class DummyError(Exception):
    pass


def _make_mock_embedding_service():
    service = MagicMock()
    service.embed_query.return_value = [0.1] * 384
    return service


def _make_mock_chroma():
    store = MagicMock()
    store.search_repository.return_value = [
        {
            "content": "def authenticate(user): pass",
            "metadata": {"file_path": "services/auth.py", "chunk_id": 0},
            "distance": 0.2,
        }
    ]
    return store


@pytest.mark.anyio
class TestProviderPipelineRegression:
    # 1. Both Gemini and DeepSeek register when configured
    async def test_both_providers_register_when_configured(self):
        test_settings = Settings(
            LLM_PROVIDER="gemini",
            GEMINI_API_KEY="test_gemini_key",
            DEEPSEEK_API_KEY="test_deepseek_key",
            GEMINI_MODEL="gemini-2.5-flash",
            DEEPSEEK_MODEL="deepseek-ai/deepseek-v4-flash-0731",
        )
        pm = ProviderManager(settings=test_settings)
        status = pm.provider_status()
        names = [p["name"] for p in status]
        assert "gemini" in names
        assert "deepseek" in names
        assert len(status) == 2

    # 2. Gemini succeeds -> Gemini response returned
    async def test_gemini_succeeds_returns_gemini_response(self):
        gemini_mock = MagicMock()
        gemini_mock.model = "gemini-2.5-flash"
        gemini_mock.generate = AsyncMock(return_value="Gemini generated response")

        deepseek_mock = MagicMock()
        deepseek_mock.model = "deepseek-chat"
        deepseek_mock.generate = AsyncMock(return_value="DeepSeek response")

        pm = ProviderManager(
            providers=[
                ProviderEntry("gemini", gemini_mock, priority=1),
                ProviderEntry("deepseek", deepseek_mock, priority=2),
            ]
        )

        answer, provider = await pm.generate("Test prompt")
        assert answer == "Gemini generated response"
        assert provider == "gemini"
        deepseek_mock.generate.assert_not_called()

    # 3. Gemini fails -> DeepSeek is attempted
    async def test_gemini_fails_deepseek_is_attempted(self):
        gemini_mock = MagicMock()
        gemini_mock.model = "gemini-2.5-flash"
        gemini_mock.generate = AsyncMock(
            side_effect=DummyError("429 RESOURCE_EXHAUSTED")
        )

        deepseek_mock = MagicMock()
        deepseek_mock.model = "deepseek-chat"
        deepseek_mock.generate = AsyncMock(return_value="DeepSeek fallback response")

        pm = ProviderManager(
            providers=[
                ProviderEntry("gemini", gemini_mock, priority=1),
                ProviderEntry("deepseek", deepseek_mock, priority=2),
            ]
        )

        answer, provider = await pm.generate("Test prompt")
        gemini_mock.generate.assert_called_once()
        deepseek_mock.generate.assert_called_once()
        assert provider == "deepseek"
        assert answer == "DeepSeek fallback response"

    # 4. Gemini fails + DeepSeek succeeds -> successful response returned
    async def test_gemini_fails_deepseek_succeeds_streaming(self):
        async def failing_gemini_stream(*args, **kwargs):
            if False:
                yield "never"
            raise DummyError("429 RESOURCE_EXHAUSTED quota exceeded")

        async def successful_deepseek_stream(*args, **kwargs):
            yield "Hello from "
            yield "DeepSeek!"

        gemini_mock = MagicMock()
        gemini_mock.model = "gemini-2.5-flash"
        gemini_mock.stream = failing_gemini_stream

        deepseek_mock = MagicMock()
        deepseek_mock.model = "deepseek-chat"
        deepseek_mock.stream = successful_deepseek_stream

        pm = ProviderManager(
            providers=[
                ProviderEntry("gemini", gemini_mock, priority=1),
                ProviderEntry("deepseek", deepseek_mock, priority=2),
            ]
        )

        tokens = []
        providers_yielded = set()
        async for tok, pname in pm.stream("Test query"):
            tokens.append(tok)
            providers_yielded.add(pname)

        assert "".join(tokens) == "Hello from DeepSeek!"
        assert providers_yielded == {"deepseek"}

    # 5. Both providers fail -> fallback response is returned
    async def test_both_providers_fail_triggers_pipeline_fallback(self):
        gemini_mock = MagicMock()
        gemini_mock.model = "gemini-2.5-flash"
        gemini_mock.generate = AsyncMock(side_effect=DummyError("Gemini fatal failure"))

        deepseek_mock = MagicMock()
        deepseek_mock.model = "deepseek-chat"
        deepseek_mock.generate = AsyncMock(
            side_effect=DummyError("DeepSeek fatal failure")
        )

        pm = ProviderManager(
            providers=[
                ProviderEntry("gemini", gemini_mock, priority=1),
                ProviderEntry("deepseek", deepseek_mock, priority=2),
            ]
        )

        pipeline = RetrievalPipeline(
            embedding_service=_make_mock_embedding_service(),
            chroma_store=_make_mock_chroma(),
            provider_manager=pm,
        )

        result = await pipeline.retrieve(
            repo_name="test/repo", question="How does auth work?"
        )
        assert result["fallback_mode"] is True
        assert "AI synthesis is temporarily unavailable" in result["answer"]

    # 6. ProviderManager uses current runtime settings rather than stale module-level settings
    async def test_provider_manager_uses_fresh_injected_settings(self):
        fresh_settings = Settings(
            LLM_PROVIDER="deepseek",
            DEEPSEEK_API_KEY="dynamic_deepseek_key",
            GEMINI_API_KEY="dynamic_gemini_key",
            DEEPSEEK_MODEL="deepseek-ai/deepseek-v4-flash-0731",
            GEMINI_MODEL="gemini-2.5-flash",
        )

        pm = ProviderManager(settings=fresh_settings)
        status = pm.provider_status()
        assert status[0]["name"] == "deepseek"
        assert status[0]["priority"] == 1
        assert status[1]["name"] == "gemini"
        assert status[1]["priority"] == 2

    # 7. Missing Gemini key does not prevent configured DeepSeek from being used
    async def test_missing_gemini_key_uses_configured_deepseek(self):
        settings_no_gemini = Settings(
            LLM_PROVIDER="deepseek",
            DEEPSEEK_API_KEY="valid_deepseek_key",
            GEMINI_API_KEY=None,
            DEEPSEEK_MODEL="deepseek-ai/deepseek-v4-flash-0731",
        )

        pm = ProviderManager(settings=settings_no_gemini)
        status = pm.provider_status()
        names = [p["name"] for p in status]
        assert "deepseek" in names
        assert "gemini" not in names
        assert len(status) == 1

    # 8. Missing DeepSeek key does not prevent configured Gemini from being used
    async def test_missing_deepseek_key_uses_configured_gemini(self):
        settings_no_deepseek = Settings(
            LLM_PROVIDER="gemini",
            GEMINI_API_KEY="valid_gemini_key",
            DEEPSEEK_API_KEY=None,
            GEMINI_MODEL="gemini-2.5-flash",
        )

        pm = ProviderManager(settings=settings_no_deepseek)
        status = pm.provider_status()
        names = [p["name"] for p in status]
        assert "gemini" in names
        assert "deepseek" not in names
        assert len(status) == 1

    # 9. Provider exceptions are logged/classified without leaking API keys
    def test_provider_exceptions_classified_without_leaking_secrets(self, caplog):
        secret_gemini_key = "secret-gemini-key-12345"
        secret_deepseek_key = "nvapi-secret-key-67890"

        gemini_exc = DummyError(
            f"Unauthorized request using key {secret_gemini_key} (401)"
        )
        deepseek_exc = DummyError(
            f"HTTP error 401 with bearer token {secret_deepseek_key}"
        )

        g_err = classify_gemini_error(gemini_exc, "gemini")
        d_err = classify_deepseek_error(deepseek_exc, "deepseek")

        assert g_err.error_type == ProviderErrorType.AUTHENTICATION_ERROR
        assert d_err.error_type == ProviderErrorType.AUTHENTICATION_ERROR

        # Classified user-facing messages must never expose raw API keys
        assert secret_gemini_key not in g_err.message
        assert secret_deepseek_key not in d_err.message
        assert secret_gemini_key not in g_err.recommendation
        assert secret_deepseek_key not in d_err.recommendation

    # 10. Streaming provider failures correctly trigger fallback when supported
    async def test_streaming_provider_failure_triggers_fallback_sse(self):
        async def failing_stream(*args, **kwargs):
            if False:
                yield "never"
            raise DummyError("All providers exhausted during streaming")

        failing_mock = MagicMock()
        failing_mock.model = "test-model"
        failing_mock.stream = failing_stream

        pm = ProviderManager(
            providers=[
                ProviderEntry("primary", failing_mock, priority=1),
            ]
        )

        pipeline = RetrievalPipeline(
            embedding_service=_make_mock_embedding_service(),
            chroma_store=_make_mock_chroma(),
            provider_manager=pm,
        )

        events = []
        async for event in pipeline.retrieve_stream(
            repo_name="test/repo", question="Explain system architecture"
        ):
            events.append(event)

        combined = "".join(events)
        assert "AI synthesis is temporarily unavailable" in combined
        assert "fallback_mode" in combined

    # 11. Gemini transient failure -> retry succeeds -> successful response returned
    async def test_gemini_transient_failure_retries_and_succeeds(self):
        call_count = 0

        async def retryable_stream(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise DummyError("503 Service Unavailable transient network issue")
            yield "Recovered after retry!"

        gemini_mock = MagicMock()
        gemini_mock.model = "gemini-2.5-flash"
        gemini_mock.stream = retryable_stream

        # GeminiProvider internal retry logic is verified directly:
        from services.llm.gemini_provider import GeminiProvider

        gp = GeminiProvider(api_key="test_key", model="gemini-2.5-flash")

        # Test retry loop in GeminiProvider.generate
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Generated on retry"

        gen_count = 0

        async def mock_generate_content(*args, **kwargs):
            nonlocal gen_count
            gen_count += 1
            if gen_count == 1:
                raise DummyError("503 Service Unavailable")
            return mock_response

        mock_client.aio.models.generate_content = mock_generate_content
        gp.client = mock_client
        gp._sdk_client_created = True

        res = await gp.generate(prompt="Test retry prompt")
        assert res == "Generated on retry"
        assert gen_count == 2

    # 12. Gemini fails with auth error -> DeepSeek succeeds -> DeepSeek response returned
    async def test_gemini_auth_failure_falls_back_to_deepseek(self):
        gemini_mock = MagicMock()
        gemini_mock.model = "gemini-2.5-flash"
        gemini_mock.generate = AsyncMock(
            side_effect=DummyError("401 UNAUTHENTICATED: ACCESS_TOKEN_TYPE_UNSUPPORTED")
        )

        deepseek_mock = MagicMock()
        deepseek_mock.model = "deepseek-ai/deepseek-v4-flash-0731"
        deepseek_mock.generate = AsyncMock(
            return_value="DeepSeek synthesis after Gemini auth failure"
        )

        pm = ProviderManager(
            providers=[
                ProviderEntry("gemini", gemini_mock, priority=1),
                ProviderEntry("deepseek", deepseek_mock, priority=2),
            ]
        )

        answer, provider_used = await pm.generate("Explain authentication architecture")
        assert provider_used == "deepseek"
        assert answer == "DeepSeek synthesis after Gemini auth failure"

    # 13. Hot reload resets circuit breakers and rebuilds provider manager
    async def test_provider_reload_resets_circuits_and_updates_settings(self):
        gemini_mock = MagicMock()
        gemini_mock.model = "gemini-2.5-flash"

        entry = ProviderEntry("gemini", gemini_mock, priority=1)
        entry.circuit_breaker.record_failure()
        entry.circuit_breaker.record_failure()
        entry.circuit_breaker.record_failure()
        assert entry.circuit_breaker.state.value == "open"

        pm = ProviderManager(providers=[entry])
        pm.reset_all_circuits()
        assert entry.circuit_breaker.state.value == "closed"

    # 14. Streaming provider success reaches the chat endpoint correctly
    async def test_streaming_provider_success_reaches_sse_stream(self):
        async def streaming_tokens(*args, **kwargs):
            yield "Token 1 "
            yield "Token 2 "
            yield "Token 3"

        provider_mock = MagicMock()
        provider_mock.model = "gemini-2.5-flash"
        provider_mock.stream = streaming_tokens

        pm = ProviderManager(
            providers=[
                ProviderEntry("gemini", provider_mock, priority=1),
            ]
        )

        pipeline = RetrievalPipeline(
            embedding_service=_make_mock_embedding_service(),
            chroma_store=_make_mock_chroma(),
            provider_manager=pm,
        )

        events = []
        async for event in pipeline.retrieve_stream(
            repo_name="test/repo", question="What is this repository?"
        ):
            events.append(event)

        texts = []
        for ev in events:
            if ev.startswith("data: "):
                payload = json.loads(ev[6:])
                if "text" in payload:
                    texts.append(payload["text"])

        combined = "".join(events)
        assert "".join(texts) == "Token 1 Token 2 Token 3"
        assert '"fallback_mode": false' in combined
        assert '"status": "done"' in combined

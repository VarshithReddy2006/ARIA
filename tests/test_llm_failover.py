"""Regression tests for automatic LLM failover in ProviderManager.

Verifies:
  - Gemini quota exceeded → DeepSeek succeeds → No fallback renderer
  - Gemini timeout → DeepSeek succeeds → Streaming works
  - Gemini authentication failure → DeepSeek succeeds
  - Gemini and DeepSeek both fail → FallbackRenderer executes
  - Mid-stream failure → No provider switching → Graceful termination
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import AsyncIterator

from services.chat.provider_manager import ProviderManager, ProviderEntry, CircuitState
from services.chat.retrieval_pipeline import RetrievalPipeline
from services.chat.conversation_memory import ConversationMemoryStore


class ClientError(Exception):
    """Mock exception resembling google.genai.errors.ClientError."""

    pass


class TimeoutErrorCustom(Exception):
    """Mock exception resembling TimeoutError."""

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
class TestLLMFailover:
    async def test_gemini_quota_exceeded_deepseek_succeeds(self):
        """Gemini returns 429 RESOURCE_EXHAUSTED quota error.

        Expect:
          - Logged Gemini quota exhausted (warning/error logs)
          - Gemini circuit breaker state set to OPEN
          - DeepSeek called and succeeds
          - Fallback renderer NOT executed (it returns normal LLM output)
        """
        gemini_provider = MagicMock()
        # Mock generate to raise 429 quota error
        quota_exc = ClientError("ClientError 429 RESOURCE_EXHAUSTED quota exceeded")
        gemini_provider.generate = AsyncMock(side_effect=quota_exc)
        gemini_provider.model = "gemini-2.5-flash"

        deepseek_provider = MagicMock()
        deepseek_provider.generate = AsyncMock(return_value="DeepSeek response text")
        deepseek_provider.model = "deepseek-chat"

        e1 = ProviderEntry(name="gemini", provider=gemini_provider, priority=1)
        e2 = ProviderEntry(name="deepseek", provider=deepseek_provider, priority=2)

        manager = ProviderManager(providers=[e1, e2])

        # Execute
        res, provider_used = await manager.generate("Hello")

        # Assertions
        assert res == "DeepSeek response text"
        assert provider_used == "deepseek"
        assert e1.circuit_breaker.state == CircuitState.OPEN

    async def test_gemini_timeout_deepseek_succeeds(self):
        """Gemini timeout on first attempt. Gemini Provider handles retry policy,
        retries once, and then fails. Switch to DeepSeek, which succeeds.
        """
        # We want to test the full integration with GeminiProvider's generate method
        from services.llm.gemini_provider import GeminiProvider

        # We mock client.aio.models.generate_content to raise TimeoutError
        mock_client = MagicMock()
        mock_aio = MagicMock()
        mock_models = MagicMock()

        # We need generate_content to raise TimeoutError twice (first try, then one retry)
        mock_models.generate_content = AsyncMock(
            side_effect=TimeoutErrorCustom("request timed out")
        )
        mock_aio.models = mock_models
        mock_client.aio = mock_aio

        with patch(
            "services.llm.gemini_provider.genai.Client", return_value=mock_client
        ):
            gemini_provider = GeminiProvider(
                api_key="valid-key", model="gemini-2.5-flash"
            )

            # Since deepseek is the second provider, let's mock it
            deepseek_provider = MagicMock()
            deepseek_provider.generate = AsyncMock(
                return_value="DeepSeek response text"
            )
            deepseek_provider.model = "deepseek-chat"

            e1 = ProviderEntry(name="gemini", provider=gemini_provider, priority=1)
            e2 = ProviderEntry(name="deepseek", provider=deepseek_provider, priority=2)

            manager = ProviderManager(providers=[e1, e2])

            # Execute
            res, provider_used = await manager.generate("Hello")

            # Assertions
            assert res == "DeepSeek response text"
            assert provider_used == "deepseek"

            # Verify that client's generate_content was called for candidate models before failover
            assert mock_models.generate_content.call_count >= 2

            # Gemini circuit breaker is NOT open because a timeout failure was recorded
            # only once at the circuit breaker level (consecutive failure threshold is 3)
            assert e1.circuit_breaker.state == CircuitState.CLOSED

    async def test_gemini_auth_failure_deepseek_succeeds(self):
        """Gemini returns 401 unauthenticated. Gemini Provider skips retry.
        Switch to DeepSeek, which succeeds.
        """
        from services.llm.gemini_provider import GeminiProvider

        mock_client = MagicMock()
        mock_aio = MagicMock()
        mock_models = MagicMock()

        # Generate content raises auth error (ClientError 401)
        auth_exc = ClientError("ClientError 401 UNAUTHENTICATED")
        mock_models.generate_content = AsyncMock(side_effect=auth_exc)
        mock_aio.models = mock_models
        mock_client.aio = mock_aio

        with patch(
            "services.llm.gemini_provider.genai.Client", return_value=mock_client
        ):
            gemini_provider = GeminiProvider(
                api_key="bad-key", model="gemini-2.5-flash"
            )

            deepseek_provider = MagicMock()
            deepseek_provider.generate = AsyncMock(
                return_value="DeepSeek response text"
            )
            deepseek_provider.model = "deepseek-chat"

            e1 = ProviderEntry(name="gemini", provider=gemini_provider, priority=1)
            e2 = ProviderEntry(name="deepseek", provider=deepseek_provider, priority=2)

            manager = ProviderManager(providers=[e1, e2])

            # Execute
            res, provider_used = await manager.generate("Hello")

            # Assertions
            assert res == "DeepSeek response text"
            assert provider_used == "deepseek"

            # Auth error should not be retried, call_count should be exactly 1
            assert mock_models.generate_content.call_count == 1

    async def test_gemini_and_deepseek_both_fail_fallback_executes(self):
        """Gemini and DeepSeek both fail.

        Expect:
          - RuntimeError raised by ProviderManager
          - RetrievalPipeline catches and invokes render_fallback
        """
        gemini_provider = MagicMock()
        gemini_provider.generate = AsyncMock(
            side_effect=ClientError("ClientError 429 quota exceeded")
        )
        gemini_provider.model = "gemini-2.5-flash"

        deepseek_provider = MagicMock()
        deepseek_provider.generate = AsyncMock(
            side_effect=Exception("DeepSeek auth failed")
        )
        deepseek_provider.model = "deepseek-chat"

        e1 = ProviderEntry(name="gemini", provider=gemini_provider, priority=1)
        e2 = ProviderEntry(name="deepseek", provider=deepseek_provider, priority=2)

        pm = ProviderManager(providers=[e1, e2])

        pipeline = RetrievalPipeline(
            embedding_service=_make_mock_embedding_service(),
            chroma_store=_make_mock_chroma(),
            provider_manager=pm,
            memory_store=ConversationMemoryStore(),
        )

        # Execute
        result = await pipeline.retrieve("owner/repo", "How to query data?")

        # Assertions
        assert result["fallback_mode"] is True
        assert "AI synthesis is temporarily unavailable" in result["answer"]

    async def test_mid_stream_failure_no_provider_switching(self):
        """Mid-stream failure after at least one token is yielded.

        Expect:
          - Stream terminates cleanly or yields termination message
          - NO retry/provider switching (DeepSeek must NOT be called)
        """
        gemini_provider = MagicMock()

        async def fake_gemini_stream(*args, **kwargs) -> AsyncIterator[str]:
            yield "Hello"
            yield " world"
            raise RuntimeError("Gemini connection lost mid-stream")

        gemini_provider.stream = fake_gemini_stream
        gemini_provider.model = "gemini-2.5-flash"

        deepseek_provider = MagicMock()
        deepseek_provider.stream = MagicMock()  # should not be called
        deepseek_provider.model = "deepseek-chat"

        e1 = ProviderEntry(name="gemini", provider=gemini_provider, priority=1)
        e2 = ProviderEntry(name="deepseek", provider=deepseek_provider, priority=2)

        pm = ProviderManager(providers=[e1, e2])

        pipeline = RetrievalPipeline(
            embedding_service=_make_mock_embedding_service(),
            chroma_store=_make_mock_chroma(),
            provider_manager=pm,
            memory_store=ConversationMemoryStore(),
        )

        # Collect stream output
        events = []
        async for sse in pipeline.retrieve_stream("owner/repo", "test question"):
            events.append(sse)

        # Parse text chunks from SSE format
        text_chunks = []
        fallback_done_received = False
        for sse in events:
            assert sse.startswith("data: ")
            payload = sse[6:].strip()
            import json as json_lib

            data = json_lib.loads(payload)
            if "text" in data:
                text_chunks.append(data["text"])
            if data.get("status") == "done":
                fallback_done_received = data.get("fallback_mode")

        full_response = "".join(text_chunks)

        # Verify that Gemini's tokens are there
        assert "Hello" in full_response
        assert "world" in full_response

        # Verify that the mid-stream failure notice was appended
        assert "became unavailable mid-response" in full_response

        # Verify fallback mode is true in the done packet
        assert fallback_done_received is True

        # Verify DeepSeek stream was never accessed
        assert deepseek_provider.stream.call_count == 0

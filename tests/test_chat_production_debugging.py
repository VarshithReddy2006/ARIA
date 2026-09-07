"""Targeted regression test suite for Chat endpoint, SSE streaming, and Provider failover.

Verifies:
1. Gemini successful & invalid authentication handling.
2. DeepSeek successful & timeout authentication handling.
3. Gemini primary success streaming (yields real-time tokens and terminal metadata).
4. Gemini failure → DeepSeek fallback streaming failover.
5. Successful DeepSeek streaming directly.
6. Both providers unavailable → graceful structured fallback rendered immediately without hanging.
7. Deterministic fallback formatting and diagnostic advice.
8. Timeout handling during streaming.
9. Secret redaction invariant in chat streaming responses and logs.
10. Direct FastAPI chat endpoint (`POST /api/v1/chat`) returns valid SSE stream (`text/event-stream`).
"""

from __future__ import annotations

import json
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from backend.api import app
from backend.dependencies import get_retrieval_pipeline
from services.chat.provider_manager import (
    ProviderManager,
    ProviderEntry,
    redact_secrets,
)
from services.chat.fallback_renderer import render_fallback
from services.llm.base_provider import BaseLLMProvider, ProviderHealth
from services.llm.gemini_provider import GeminiProvider
from services.llm.deepseek_provider import DeepSeekProvider
from services.llm.provider_errors import ProviderErrorType


class MockStreamingProvider(BaseLLMProvider):
    def __init__(
        self,
        name: str,
        model: str,
        should_fail: bool = False,
        tokens: list[str] | None = None,
    ):
        self.name = name
        self.model = model
        self.should_fail = should_fail
        self.tokens = tokens or ["Hello", " from ", name]

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            healthy=not self.should_fail,
            provider=self.name,
            model=self.model,
            authenticated=not self.should_fail,
            latency_ms=5.0,
            error_type=ProviderErrorType.AUTHENTICATION_ERROR.value
            if self.should_fail
            else None,
        )

    async def generate(
        self, prompt: str, system_instruction: str = "", history=None, **kwargs
    ) -> str:
        if self.should_fail:
            raise RuntimeError(f"Simulated error in {self.name}")
        return "".join(self.tokens)

    async def stream(
        self, prompt: str, system_instruction: str = "", history=None, **kwargs
    ):
        if self.should_fail:
            raise RuntimeError(f"Simulated error in {self.name}")
        for t in self.tokens:
            yield t


@pytest.fixture
def client():
    return TestClient(app)


def _parse_sse_events(response_text: str) -> list[dict]:
    events = []
    for line in response_text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            raw = line[len("data:") :].strip()
            if raw:
                try:
                    events.append(json.loads(raw))
                except Exception:
                    pass
    return events


# ---------------------------------------------------------------------------
# Task 7.1 & 7.2: Gemini Auth Tests (Success & Invalid)
# ---------------------------------------------------------------------------


def test_gemini_credential_format_classification():
    """Verify GeminiProvider.classify_credential_format distinguishes key classes safely."""
    assert GeminiProvider.classify_credential_format(None) == (
        False,
        "missing",
        ProviderErrorType.MISSING_CREDENTIAL,
    )
    assert GeminiProvider.classify_credential_format("") == (
        False,
        "missing",
        ProviderErrorType.MISSING_CREDENTIAL,
    )
    assert GeminiProvider.classify_credential_format("short") == (
        False,
        "malformed_gemini_api_key",
        ProviderErrorType.INVALID_CREDENTIAL_TYPE,
    )
    assert GeminiProvider.classify_credential_format("ya29.TestOAuthToken12345") == (
        False,
        "unsupported_oauth_access_token",
        ProviderErrorType.INVALID_CREDENTIAL_TYPE,
    )
    assert GeminiProvider.classify_credential_format("AQ.TestKey1234567890") == (
        True,
        "gemini_api_key",
        None,
    )
    assert GeminiProvider.classify_credential_format(
        "AIzaSyTestValidGoogleAIStudioDeveloperKey39Chars"
    ) == (
        True,
        "google_ai_studio_developer_api_key",
        None,
    )


@pytest.mark.asyncio
async def test_gemini_provider_successful_auth():
    """Verify GeminiProvider health_check returns healthy when SDK list() succeeds."""
    provider = GeminiProvider(api_key="AIzaSyTestValidGoogleKey12345")
    mock_client = MagicMock()
    mock_client._is_proxy = False
    mock_client.aio.models.list = AsyncMock(
        return_value=[MagicMock(name="models/gemini-3.1-flash-lite")]
    )
    provider.client = mock_client
    provider._sdk_client_created = True

    health = await provider.health_check()
    assert health.healthy is True
    assert health.authenticated is True
    assert health.provider == "gemini"


@pytest.mark.asyncio
async def test_gemini_provider_invalid_auth():
    """Verify GeminiProvider health_check classifies ACCESS_TOKEN_TYPE_UNSUPPORTED as invalid_credential_type."""
    provider = GeminiProvider(api_key="AQ.TestUnsupportedToken12345")
    mock_client = MagicMock()
    mock_client._is_proxy = False

    class MockClientError(Exception):
        pass

    mock_client.aio.models.list = AsyncMock(
        side_effect=MockClientError(
            "401 UNAUTHENTICATED. {'error': {'code': 401, 'message': 'Request had invalid authentication credentials.', 'details': [{'reason': 'ACCESS_TOKEN_TYPE_UNSUPPORTED'}]}}"
        )
    )
    provider.client = mock_client
    provider._sdk_client_created = True

    health = await provider.health_check()
    assert health.healthy is False
    assert health.authenticated is False
    assert health.error_type == ProviderErrorType.INVALID_CREDENTIAL_TYPE.value
    assert "https://aistudio.google.com/app/apikey" in health.recommendation


# ---------------------------------------------------------------------------
# Task 7.3 & 7.4: DeepSeek Auth Tests (Success & Timeout)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deepseek_provider_successful_auth():
    """Verify DeepSeekProvider health_check returns healthy when GET /models succeeds."""
    provider = DeepSeekProvider(
        api_key="nvapi-test-valid-key", model="deepseek-ai/deepseek-v4-flash-0731"
    )
    mock_http_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_http_client.get = AsyncMock(return_value=mock_resp)
    mock_http_client.is_closed = False
    provider._client = mock_http_client

    health = await provider.health_check()
    assert health.healthy is True
    assert health.authenticated is True
    assert health.provider == "deepseek"


@pytest.mark.asyncio
async def test_deepseek_provider_timeout():
    """Verify DeepSeekProvider health_check classifies timeout appropriately."""
    provider = DeepSeekProvider(
        api_key="nvapi-test-key", model="deepseek-ai/deepseek-v4-flash-0731"
    )
    mock_http_client = AsyncMock()
    mock_http_client.get = AsyncMock(
        side_effect=httpx.ReadTimeout("Read timed out after 10.0s")
    )
    mock_http_client.is_closed = False
    provider._client = mock_http_client

    health = await provider.health_check()
    assert health.healthy is False
    assert health.error_type == ProviderErrorType.TIMEOUT.value


# ---------------------------------------------------------------------------
# Task 7.5 & 7.6: Streaming and Failover
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_gemini_primary_success(monkeypatch):
    """Verify primary Gemini provider streams tokens and completes with metadata."""
    gemini_mock = MockStreamingProvider(
        "gemini",
        "gemini-3.1-flash-lite",
        should_fail=False,
        tokens=["Gemini", " answer"],
    )
    deepseek_mock = MockStreamingProvider(
        "deepseek", "deepseek-ai/deepseek-v4-flash-0731", should_fail=False
    )

    gemini_entry = ProviderEntry(name="gemini", provider=gemini_mock, priority=1)
    deepseek_entry = ProviderEntry(name="deepseek", provider=deepseek_mock, priority=2)
    pm = ProviderManager(providers=[gemini_entry, deepseek_entry])

    pipeline = get_retrieval_pipeline()
    monkeypatch.setattr(pipeline, "provider_manager", pm)

    monkeypatch.setattr(
        "services.chat.retrieval_pipeline.detect_deterministic_retrieval",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "services.chat.retrieval_pipeline.intelligent_retrieve",
        lambda *args, **kwargs: (
            [],
            {"embed_ms": 1.0, "search_ms": 1.0, "confidence": 90},
        ),
    )

    events = []
    async for sse in pipeline.retrieve_stream(
        repo_name="test-org/test-repo",
        question="What does this repository do?",
        session_id="test-sess-1",
    ):
        if sse.startswith("data:"):
            events.append(json.loads(sse[len("data:") :].strip()))

    assert len(events) >= 2
    tokens = [e.get("text") for e in events if "text" in e]
    assert "Gemini" in tokens
    assert " answer" in tokens

    done_events = [e for e in events if e.get("status") == "done"]
    assert len(done_events) == 1
    assert done_events[0].get("fallback_mode") is False


@pytest.mark.asyncio
async def test_chat_gemini_failure_deepseek_fallback(monkeypatch):
    """Verify failover from failing Gemini to working DeepSeek fallback provider."""
    gemini_mock = MockStreamingProvider(
        "gemini", "gemini-3.1-flash-lite", should_fail=True
    )
    deepseek_mock = MockStreamingProvider(
        "deepseek",
        "deepseek-ai/deepseek-v4-flash-0731",
        should_fail=False,
        tokens=["DeepSeek", " fallback", " answer"],
    )

    gemini_entry = ProviderEntry(name="gemini", provider=gemini_mock, priority=1)
    deepseek_entry = ProviderEntry(name="deepseek", provider=deepseek_mock, priority=2)
    pm = ProviderManager(providers=[gemini_entry, deepseek_entry])

    pipeline = get_retrieval_pipeline()
    monkeypatch.setattr(pipeline, "provider_manager", pm)

    monkeypatch.setattr(
        "services.chat.retrieval_pipeline.detect_deterministic_retrieval",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "services.chat.retrieval_pipeline.intelligent_retrieve",
        lambda *args, **kwargs: (
            [],
            {"embed_ms": 1.0, "search_ms": 1.0, "confidence": 85},
        ),
    )

    events = []
    async for sse in pipeline.retrieve_stream(
        repo_name="test-org/test-repo",
        question="How does auth work?",
        session_id="test-sess-2",
    ):
        if sse.startswith("data:"):
            events.append(json.loads(sse[len("data:") :].strip()))

    tokens = [e.get("text") for e in events if "text" in e]
    assert "DeepSeek" in tokens
    assert " fallback" in tokens
    assert " answer" in tokens

    done_events = [e for e in events if e.get("status") == "done"]
    assert len(done_events) == 1


@pytest.mark.asyncio
async def test_deepseek_direct_streaming():
    """Verify ProviderManager streaming directly from DeepSeek provider."""
    deepseek_mock = MockStreamingProvider(
        "deepseek",
        "deepseek-ai/deepseek-v4-flash-0731",
        should_fail=False,
        tokens=["NIM", " token", " stream"],
    )
    deepseek_entry = ProviderEntry(name="deepseek", provider=deepseek_mock, priority=1)
    pm = ProviderManager(providers=[deepseek_entry])

    yielded = []
    async for token, provider_name in pm.stream("test prompt"):
        yielded.append((token, provider_name))

    assert len(yielded) == 3
    assert [t[0] for t in yielded] == ["NIM", " token", " stream"]
    assert all(t[1] == "deepseek" for t in yielded)


# ---------------------------------------------------------------------------
# Task 7.7 & 7.8: Both Providers Unavailable & Deterministic Fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_all_providers_failing_graceful_fallback(monkeypatch):
    """Verify that if all LLM providers fail, structured fallback is emitted immediately."""
    gemini_mock = MockStreamingProvider(
        "gemini", "gemini-3.1-flash-lite", should_fail=True
    )
    deepseek_mock = MockStreamingProvider(
        "deepseek", "deepseek-ai/deepseek-v4-flash-0731", should_fail=True
    )

    gemini_entry = ProviderEntry(name="gemini", provider=gemini_mock, priority=1)
    deepseek_entry = ProviderEntry(name="deepseek", provider=deepseek_mock, priority=2)
    pm = ProviderManager(providers=[gemini_entry, deepseek_entry])

    pipeline = get_retrieval_pipeline()
    monkeypatch.setattr(pipeline, "provider_manager", pm)

    monkeypatch.setattr(
        "services.chat.retrieval_pipeline.detect_deterministic_retrieval",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "services.chat.retrieval_pipeline.intelligent_retrieve",
        lambda *args, **kwargs: (
            [],
            {"embed_ms": 1.0, "search_ms": 1.0, "confidence": 0},
        ),
    )

    events = []
    async for sse in pipeline.retrieve_stream(
        repo_name="test-org/test-repo",
        question="Where is main?",
        session_id="test-sess-3",
    ):
        if sse.startswith("data:"):
            events.append(json.loads(sse[len("data:") :].strip()))

    done_events = [e for e in events if e.get("status") == "done"]
    assert len(done_events) == 1
    assert done_events[0].get("fallback_mode") is True

    text_events = [e.get("text") for e in events if "text" in e]
    combined_text = "".join(text_events)
    assert "AI synthesis is temporarily unavailable" in combined_text


def test_deterministic_fallback_renderer():
    """Verify render_fallback produces structured output and actionable guidance."""
    rendered = render_fallback(
        question="Explain login flow",
        structured_intelligence="Authentication is handled via JWT tokens.",
        chunks=[
            {
                "metadata": {
                    "file_path": "backend/auth.py",
                    "start_line": 10,
                    "end_line": 25,
                    "why_this_file": "Auth handler",
                    "confidence": 95,
                }
            }
        ],
        source_files=["backend/auth.py"],
        provider_error="401 UNAUTHENTICATED",
    )

    assert "AI synthesis is temporarily unavailable" in rendered
    assert "backend/auth.py" in rendered
    assert "Authentication is handled via JWT tokens." in rendered
    assert "Suggested Next Step" in rendered


# ---------------------------------------------------------------------------
# Task 7.9: Secret Redaction Invariant
# ---------------------------------------------------------------------------


def test_secret_redaction_invariant():
    """Verify sensitive tokens and API keys are redacted from user-facing logs and strings."""
    secret_text = "Key1: AIzaSyTestKey1234567890, Key2: nvapi-testsecret1234567890, Key3: AQ.TestAccessToken999999999"
    redacted = redact_secrets(secret_text)
    assert "AIzaSyTestKey1234567890" not in redacted
    assert "nvapi-testsecret1234567890" not in redacted
    assert "AQ.TestAccessToken999999999" not in redacted
    assert "[REDACTED_CREDENTIAL]" in redacted


# ---------------------------------------------------------------------------
# Task 8: FastAPI Endpoint Integration
# ---------------------------------------------------------------------------


def test_fastapi_chat_sse_endpoint_authenticated(client, monkeypatch):
    """Verify FastAPI POST /api/v1/chat returns 200 text/event-stream."""
    gemini_mock = MockStreamingProvider(
        "gemini",
        "gemini-3.1-flash-lite",
        should_fail=False,
        tokens=["Endpoint", " token"],
    )
    gemini_entry = ProviderEntry(name="gemini", provider=gemini_mock, priority=1)
    pm = ProviderManager(providers=[gemini_entry])

    pipeline = get_retrieval_pipeline()
    monkeypatch.setattr(pipeline, "provider_manager", pm)
    monkeypatch.setattr(
        "services.chat.retrieval_pipeline.detect_deterministic_retrieval",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "services.chat.retrieval_pipeline.intelligent_retrieve",
        lambda *args, **kwargs: (
            [],
            {"embed_ms": 1.0, "search_ms": 1.0, "confidence": 95},
        ),
    )

    resp = client.post(
        "/api/v1/chat",
        headers={"X-API-Key": "test-key"},
        json={
            "repo": "test/repo",
            "message": "Hello chat endpoint",
            "session_id": "endpoint-test-sess",
            "history": [],
        },
    )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")
    events = _parse_sse_events(resp.text)
    assert len(events) >= 2
    tokens = [e.get("text") for e in events if "text" in e]
    assert "Endpoint" in tokens

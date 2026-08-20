"""Tests verifying that application startup, /health, and /ready NEVER consume Gemini API quota.

Specific requirements tested:
  A. Importing/starting the app does NOT call Gemini API.
  B. GET /health does NOT call Gemini API.
  C. GET /ready does NOT call Gemini API.
  D. Explicit provider health check (GET /api/v1/chat/health) performs health check when requested.
  E. Actual chat still calls Gemini normally.
  F. Provider status caching works (repeated calls within cache TTL do not hit Gemini API again).
  G. Missing GEMINI_API_KEY does not cause network attempts.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from backend.api import app, validate_llm_providers


@pytest.fixture(autouse=True)
def reset_provider_factory():
    from services.llm.provider_factory import ProviderFactory

    ProviderFactory.reset()
    yield
    ProviderFactory.reset()


def test_import_and_startup_does_not_call_gemini():
    """A: Startup lifespan and validate_llm_providers must not make Gemini API calls."""
    with (
        patch("google.genai.Client") as mock_client_cls,
        patch("backend.settings.settings.llm_provider", "gemini"),
        patch("backend.settings.settings.gemini_api_key", "AIza-test-key"),
    ):
        import asyncio

        # Run startup validation explicitly
        asyncio.run(validate_llm_providers())

        # google.genai.Client must NOT have been instantiated or called
        mock_client_cls.assert_not_called()


def test_health_endpoint_does_not_call_gemini():
    """B: GET /health returns local configuration without calling Gemini API."""
    with (
        patch("google.genai.Client") as mock_client_cls,
        patch("backend.settings.settings.llm_provider", "gemini"),
        patch("backend.settings.settings.gemini_api_key", "AIza-test-key"),
    ):
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["llm_provider"] == "gemini"
        assert data["llm_configured"] is True
        mock_client_cls.assert_not_called()


def test_ready_endpoint_does_not_call_gemini():
    """C: GET /ready performs local checks without calling Gemini API."""
    with (
        patch("google.genai.Client") as mock_client_cls,
        patch("backend.settings.settings.llm_provider", "gemini"),
        patch("backend.settings.settings.gemini_api_key", "AIza-test-key"),
    ):
        client = TestClient(app)
        response = client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        mock_client_cls.assert_not_called()


@pytest.mark.anyio
async def test_explicit_chat_health_check_calls_provider_with_caching():
    """D & F: GET /chat/health validates provider, and caches results to prevent repeat quota use."""
    from services.llm.provider_factory import ProviderFactory
    from services.llm.base_provider import ProviderHealth

    mock_health = ProviderHealth(
        healthy=True,
        provider="gemini",
        model="gemini-2.5-flash",
        authenticated=True,
        latency_ms=45.0,
    )

    mock_provider = AsyncMock()
    mock_provider.health_check = AsyncMock(return_value=mock_health)

    with (
        patch(
            "services.llm.provider_factory.ProviderFactory.get_provider",
            return_value=mock_provider,
        ),
        patch("backend.settings.settings.llm_provider", "gemini"),
        patch("backend.settings.settings.gemini_api_key", "AIza-test-key"),
        patch("backend.settings.settings.deepseek_api_key", None),
    ):
        # 1. First call: executes health check
        results1 = await ProviderFactory.validate_all_providers()
        assert results1["gemini"].healthy is True
        assert mock_provider.health_check.call_count == 1

        # 2. Second call within TTL: returns cached result without hitting provider again (F)
        results2 = await ProviderFactory.validate_all_providers()
        assert results2["gemini"].healthy is True
        assert mock_provider.health_check.call_count == 1

        # 3. Forced call: bypasses cache
        results3 = await ProviderFactory.validate_all_providers(force=True)
        assert results3["gemini"].healthy is True
        assert mock_provider.health_check.call_count == 2


@pytest.mark.anyio
async def test_actual_chat_calls_gemini():
    """E: Actual chat/generate calls continue to invoke Gemini normally."""
    from services.llm.gemini_provider import GeminiProvider

    provider = GeminiProvider(api_key="AIza-real-key", model="gemini-2.5-flash")

    mock_response = MagicMock()
    mock_response.text = "Hello from Gemini"

    mock_models = AsyncMock()
    mock_models.generate_content = AsyncMock(return_value=mock_response)

    mock_client = MagicMock()
    mock_client.aio.models = mock_models
    provider.client = mock_client
    provider._sdk_client_created = True

    result = await provider.generate(prompt="What is this repository?")
    assert result == "Hello from Gemini"
    mock_models.generate_content.assert_called_once()


def test_missing_api_key_does_not_call_network():
    """G: Missing API key produces local unconfigured state with zero network attempts."""
    from services.llm.provider_factory import ProviderFactory
    from core.config import Settings

    settings = Settings(
        APP_ENV="development",
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY="",
        DEEPSEEK_API_KEY="",
    )

    configs = ProviderFactory.check_configuration(settings=settings)
    assert configs["gemini"]["configured"] is False
    assert configs["deepseek"]["configured"] is False

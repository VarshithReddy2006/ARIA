"""Integration tests for ProviderFactory.validate_all_providers().

Verifies the startup policy:
  - All healthy     → returns results, no exception
  - Primary bad, fallback good  → returns results, no exception
  - All unhealthy   → returns results (caller decides to abort)

All provider network calls are mocked.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.llm.base_provider import ProviderHealth
from services.llm.provider_errors import ProviderErrorType


def _make_health(
    healthy: bool, provider: str, error_type: str = None
) -> ProviderHealth:
    return ProviderHealth(
        healthy=healthy,
        provider=provider,
        model=f"{provider}-model",
        authenticated=healthy,
        latency_ms=100.0 if healthy else 0.0,
        error_type=error_type,
        error_message="bad" if not healthy else None,
        recommendation="fix it" if not healthy else None,
    )


# ---------------------------------------------------------------------------
# Helpers: patch at canonical locations where the classes are defined,
# not where they are locally imported inside validate_all_providers().
# ---------------------------------------------------------------------------


def _provider_patches(
    primary_health: ProviderHealth,
    secondary_health: ProviderHealth = None,
    gemini_api_key: str = "AIza-key",
    deepseek_api_key: str = "nvapi-key",
):
    """Context manager stack that patches providers and settings."""
    from contextlib import ExitStack

    stack = ExitStack()
    mock_primary = AsyncMock()
    mock_primary.health_check = AsyncMock(return_value=primary_health)

    mock_secondary = AsyncMock()
    mock_secondary.health_check = AsyncMock(
        return_value=secondary_health or _make_health(True, "deepseek")
    )

    # Patch ProviderFactory.get_provider to return mock primary
    stack.enter_context(
        patch(
            "services.llm.provider_factory.ProviderFactory.get_provider",
            return_value=mock_primary,
        )
    )

    # Patch the provider classes inside their own modules,
    # as they are imported with `from .xxx_provider import XxxProvider` inside the function.
    stack.enter_context(
        patch(
            "services.llm.deepseek_provider.DeepSeekProvider",
        )
    )
    stack.enter_context(
        patch(
            "services.llm.gemini_provider.GeminiProvider",
        )
    )

    # Patch Settings at backend.settings to control api keys
    settings_mock = MagicMock()
    settings_mock.llm_provider = "gemini"
    settings_mock.gemini_api_key = gemini_api_key
    settings_mock.gemini_model = "gemini-2.5-flash"
    settings_mock.deepseek_api_key = deepseek_api_key
    settings_mock.deepseek_base_url = "https://integrate.api.nvidia.com/v1"
    settings_mock.deepseek_model = "deepseek-ai/deepseek-v4-flash"

    stack.enter_context(patch("backend.settings.Settings", return_value=settings_mock))

    return stack, mock_secondary


class TestValidateAllProviders:
    @pytest.fixture(autouse=True)
    def reset_factory(self):
        from services.llm.provider_factory import ProviderFactory

        ProviderFactory.reset()
        yield
        ProviderFactory.reset()

    @pytest.mark.anyio
    async def test_both_providers_healthy(self):
        """Happy path: both Gemini (primary) and DeepSeek (secondary) are healthy."""
        from services.llm.provider_factory import ProviderFactory

        gemini_health = _make_health(True, "gemini")
        deepseek_health = _make_health(True, "deepseek")

        mock_primary = AsyncMock()
        mock_primary.health_check = AsyncMock(return_value=gemini_health)

        mock_deepseek_instance = AsyncMock()
        mock_deepseek_instance.health_check = AsyncMock(return_value=deepseek_health)

        mock_deepseek_cls = MagicMock(return_value=mock_deepseek_instance)

        settings_mock = MagicMock()
        settings_mock.llm_provider = "gemini"
        settings_mock.gemini_api_key = "AIza-key"
        settings_mock.gemini_model = "gemini-2.5-flash"
        settings_mock.deepseek_api_key = "nvapi-key"
        settings_mock.deepseek_base_url = "https://integrate.api.nvidia.com/v1"
        settings_mock.deepseek_model = "deepseek-ai/deepseek-v4-flash"

        with (
            patch.object(ProviderFactory, "get_provider", return_value=mock_primary),
            patch("services.llm.provider_factory.DeepSeekProvider", mock_deepseek_cls),
            patch("services.llm.provider_factory.GeminiProvider"),
            patch("services.llm.provider_factory.Settings", return_value=settings_mock),
        ):
            results = await ProviderFactory.validate_all_providers()

        assert results["gemini"].healthy is True
        assert results["deepseek"].healthy is True

    @pytest.mark.anyio
    async def test_primary_unhealthy_fallback_healthy(self):
        """Primary (Gemini) fails auth — fallback (DeepSeek) is healthy.
        Should NOT raise — ProviderManager will handle failover."""
        from services.llm.provider_factory import ProviderFactory

        gemini_health = _make_health(
            False,
            "gemini",
            error_type=ProviderErrorType.INVALID_CREDENTIAL_TYPE.value,
        )
        deepseek_health = _make_health(True, "deepseek")

        mock_primary = AsyncMock()
        mock_primary.health_check = AsyncMock(return_value=gemini_health)

        mock_deepseek_instance = AsyncMock()
        mock_deepseek_instance.health_check = AsyncMock(return_value=deepseek_health)
        mock_deepseek_cls = MagicMock(return_value=mock_deepseek_instance)

        settings_mock = MagicMock()
        settings_mock.llm_provider = "gemini"
        settings_mock.gemini_api_key = "bad-key"
        settings_mock.gemini_model = "gemini-2.5-flash"
        settings_mock.deepseek_api_key = "nvapi-good"
        settings_mock.deepseek_base_url = "https://integrate.api.nvidia.com/v1"
        settings_mock.deepseek_model = "deepseek-ai/deepseek-v4-flash"

        with (
            patch.object(ProviderFactory, "get_provider", return_value=mock_primary),
            patch("services.llm.provider_factory.DeepSeekProvider", mock_deepseek_cls),
            patch("services.llm.provider_factory.GeminiProvider"),
            patch("services.llm.provider_factory.Settings", return_value=settings_mock),
        ):
            results = await ProviderFactory.validate_all_providers()

        assert results["gemini"].healthy is False
        assert (
            results["gemini"].error_type
            == ProviderErrorType.INVALID_CREDENTIAL_TYPE.value
        )
        assert results["deepseek"].healthy is True

    @pytest.mark.anyio
    async def test_both_providers_unhealthy(self):
        """All providers fail — returns results dict, does NOT raise."""
        from services.llm.provider_factory import ProviderFactory

        gemini_health = _make_health(
            False, "gemini", ProviderErrorType.AUTHENTICATION_ERROR.value
        )
        deepseek_health = _make_health(
            False, "deepseek", ProviderErrorType.AUTHENTICATION_ERROR.value
        )

        mock_primary = AsyncMock()
        mock_primary.health_check = AsyncMock(return_value=gemini_health)

        mock_deepseek_instance = AsyncMock()
        mock_deepseek_instance.health_check = AsyncMock(return_value=deepseek_health)
        mock_deepseek_cls = MagicMock(return_value=mock_deepseek_instance)

        settings_mock = MagicMock()
        settings_mock.llm_provider = "gemini"
        settings_mock.gemini_api_key = "invalid"
        settings_mock.gemini_model = "gemini-2.5-flash"
        settings_mock.deepseek_api_key = "invalid"
        settings_mock.deepseek_base_url = "https://integrate.api.nvidia.com/v1"
        settings_mock.deepseek_model = "deepseek-ai/deepseek-v4-flash"

        with (
            patch.object(ProviderFactory, "get_provider", return_value=mock_primary),
            patch("services.llm.provider_factory.DeepSeekProvider", mock_deepseek_cls),
            patch("services.llm.provider_factory.GeminiProvider"),
            patch("services.llm.provider_factory.Settings", return_value=settings_mock),
        ):
            # Must NOT raise — caller handles the abort decision
            results = await ProviderFactory.validate_all_providers()

        assert results["gemini"].healthy is False
        assert results["deepseek"].healthy is False

    @pytest.mark.anyio
    async def test_only_primary_configured(self):
        """No secondary API key set — only primary is validated."""
        from services.llm.provider_factory import ProviderFactory

        gemini_health = _make_health(True, "gemini")

        mock_primary = AsyncMock()
        mock_primary.health_check = AsyncMock(return_value=gemini_health)

        settings_mock = MagicMock()
        settings_mock.llm_provider = "gemini"
        settings_mock.gemini_api_key = "good-key"
        settings_mock.gemini_model = "gemini-2.5-flash"
        settings_mock.deepseek_api_key = None  # no secondary configured
        settings_mock.deepseek_base_url = "https://integrate.api.nvidia.com/v1"
        settings_mock.deepseek_model = "deepseek-ai/deepseek-v4-flash"

        with (
            patch.object(ProviderFactory, "get_provider", return_value=mock_primary),
            patch("services.llm.provider_factory.Settings", return_value=settings_mock),
        ):
            results = await ProviderFactory.validate_all_providers()

        assert "gemini" in results
        assert "deepseek" not in results

    @pytest.mark.anyio
    async def test_primary_init_error_handled(self):
        """ProviderFactory.get_provider() raises — result is unhealthy, no crash."""
        from services.llm.provider_factory import ProviderFactory

        settings_mock = MagicMock()
        settings_mock.llm_provider = "gemini"
        settings_mock.gemini_api_key = "key"
        settings_mock.gemini_model = "gemini-2.5-flash"
        settings_mock.deepseek_api_key = None
        settings_mock.deepseek_base_url = "https://integrate.api.nvidia.com/v1"
        settings_mock.deepseek_model = "deepseek-ai/deepseek-v4-flash"

        with (
            patch.object(
                ProviderFactory,
                "get_provider",
                side_effect=ValueError("Unknown provider"),
            ),
            patch("services.llm.provider_factory.Settings", return_value=settings_mock),
        ):
            results = await ProviderFactory.validate_all_providers()

        assert "gemini" in results
        assert results["gemini"].healthy is False
        assert results["gemini"].error_type == "configuration_error"


# ===========================================================================
# Startup policy (pure logic, no mocks needed)
# ===========================================================================


class TestStartupPolicy:
    """Verify the startup policy: only fail when ALL providers are unhealthy."""

    def test_policy_all_unhealthy_means_abort(self):
        results = {
            "gemini": _make_health(False, "gemini", "authentication_error"),
            "deepseek": _make_health(False, "deepseek", "authentication_error"),
        }
        healthy = [n for n, h in results.items() if h.healthy]
        assert len(healthy) == 0  # caller should abort

    def test_policy_primary_bad_fallback_good_means_continue(self):
        results = {
            "gemini": _make_health(False, "gemini", "invalid_credential_type"),
            "deepseek": _make_health(True, "deepseek"),
        }
        healthy = [n for n, h in results.items() if h.healthy]
        assert len(healthy) > 0  # caller should continue

    def test_policy_all_healthy_means_continue(self):
        results = {
            "gemini": _make_health(True, "gemini"),
            "deepseek": _make_health(True, "deepseek"),
        }
        healthy = [n for n, h in results.items() if h.healthy]
        assert len(healthy) == 2

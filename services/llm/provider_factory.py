"""Provider factory — single entry-point for obtaining the configured LLM provider.

Usage::

    from services.llm import ProviderFactory
    provider = ProviderFactory.get_provider()
    answer = await provider.generate(prompt, system_instruction=...)

Startup validation::

    results = await ProviderFactory.validate_all_providers()
    # returns Dict[str, ProviderHealth] — one entry per configured provider
"""

import logging
from typing import Dict, Optional

from .base_provider import BaseLLMProvider, ProviderHealth
from .gemini_provider import GeminiProvider
from .deepseek_provider import DeepSeekProvider
from core.config import Settings

logger = logging.getLogger(__name__)

_cached_provider: Optional[BaseLLMProvider] = None
# Track the key that was used to build the cached provider so we can detect
# when the .env changes without a process restart.
_cached_api_key: Optional[str] = None
_last_validation_time: float = 0.0
_cached_validation_results: Optional[Dict[str, ProviderHealth]] = None
_validation_cache_ttl: float = 30.0  # seconds


class ProviderFactory:
    """Creates and caches the globally configured LLM provider instance."""

    @classmethod
    def get_provider(cls, settings: Optional[Settings] = None) -> BaseLLMProvider:
        """Return the singleton provider instance, creating it if necessary.

        Re-creates the provider automatically if the API key in the environment
        has changed since the last build (handles hot-.env-reload without restart).
        """
        global _cached_provider, _cached_api_key

        # Reload settings fresh from env each call (cheap — pydantic reads os.environ)
        current_settings = settings or Settings()
        provider_name = current_settings.llm_provider.lower().strip()

        # Pick the relevant API key for the active provider
        if provider_name == "gemini":
            current_key = current_settings.gemini_api_key or ""
        else:
            current_key = current_settings.deepseek_api_key or ""

        # Invalidate cache if key changed
        if _cached_provider is not None and current_key != _cached_api_key:
            logger.info(
                "ProviderFactory: API key changed — rebuilding %s provider",
                provider_name,
            )
            _cached_provider = None
            _cached_api_key = None

        if _cached_provider is not None:
            return _cached_provider

        if provider_name == "deepseek":
            _cached_provider = DeepSeekProvider(
                api_key=current_settings.deepseek_api_key,
                base_url=current_settings.deepseek_base_url,
                model=current_settings.deepseek_model,
            )
            logger.info(
                "LLM provider initialised: DeepSeek (%s) via NVIDIA NIM",
                current_settings.deepseek_model,
            )
        elif provider_name == "gemini":
            _cached_provider = GeminiProvider(
                api_key=current_settings.gemini_api_key,
                model=current_settings.gemini_model,
            )
            logger.info(
                "LLM provider initialised: Gemini (%s)",
                current_settings.gemini_model,
            )
        else:
            raise ValueError(
                f"Unknown LLM_PROVIDER '{provider_name}'. Supported values: 'deepseek', 'gemini'."
            )

        _cached_api_key = current_key
        return _cached_provider

    @classmethod
    def reset(cls) -> None:
        """Clear the cached provider (useful for testing or reconfiguration)."""
        global \
            _cached_provider, \
            _cached_api_key, \
            _last_validation_time, \
            _cached_validation_results
        _cached_provider = None
        _cached_api_key = None
        _last_validation_time = 0.0
        _cached_validation_results = None

    @classmethod
    async def validate_all_providers(
        cls, settings: Optional[Settings] = None
    ) -> Dict[str, ProviderHealth]:
        """Run health checks on every configured LLM provider.

        Called once at application startup.  Results are used to decide
        whether the backend can serve chat requests.

        Startup policy (matches ProviderManager resilience):
          - If ALL providers are unhealthy → caller should abort startup.
          - If at least one provider is healthy → startup proceeds with
            a WARNING logged for every unhealthy provider.
          - Never raises — always returns a dict.

        Returns:
            Dict mapping provider_name → ProviderHealth for every provider
            that is configured (regardless of health status).
        """
        import time
        import sys

        global _last_validation_time, _cached_validation_results

        now = time.time()
        is_testing = "pytest" in sys.modules or "pytest" in sys.argv[0]
        if (
            not is_testing
            and _cached_validation_results is not None
            and (now - _last_validation_time) < _validation_cache_ttl
            and settings is None
        ):
            return _cached_validation_results

        current_settings = settings or Settings()
        results: Dict[str, ProviderHealth] = {}

        # ── Primary provider ────────────────────────────────────────────
        primary_name = current_settings.llm_provider.lower().strip()
        try:
            primary = cls.get_provider(settings=current_settings)
            health = await primary.health_check()
            results[primary_name] = health
        except Exception as exc:
            logger.error(
                "ProviderFactory.validate: failed to instantiate primary provider %s: %s",
                primary_name,
                exc,
            )
            results[primary_name] = ProviderHealth(
                healthy=False,
                provider=primary_name,
                model="unknown",
                authenticated=False,
                error_message=f"Failed to initialise provider: {exc}",
                error_type="configuration_error",
                recommendation="Check LLM_PROVIDER and the corresponding API key in .env",
            )

        # ── Secondary provider (if configured and different from primary) ─
        if primary_name == "gemini" and current_settings.deepseek_api_key:
            try:
                secondary = DeepSeekProvider(
                    api_key=current_settings.deepseek_api_key,
                    base_url=current_settings.deepseek_base_url,
                    model=current_settings.deepseek_model,
                )
                health = await secondary.health_check()
                results["deepseek"] = health
            except Exception as exc:
                logger.warning(
                    "ProviderFactory.validate: secondary provider deepseek failed: %s",
                    exc,
                )
                results["deepseek"] = ProviderHealth(
                    healthy=False,
                    provider="deepseek",
                    model=current_settings.deepseek_model,
                    authenticated=False,
                    error_message=str(exc),
                    error_type="configuration_error",
                )

        elif primary_name == "deepseek" and current_settings.gemini_api_key:
            try:
                secondary = GeminiProvider(
                    api_key=current_settings.gemini_api_key,
                    model=current_settings.gemini_model,
                )
                health = await secondary.health_check()
                results["gemini"] = health
            except Exception as exc:
                logger.warning(
                    "ProviderFactory.validate: secondary provider gemini failed: %s",
                    exc,
                )
                results["gemini"] = ProviderHealth(
                    healthy=False,
                    provider="gemini",
                    model=current_settings.gemini_model,
                    authenticated=False,
                    error_message=str(exc),
                    error_type="configuration_error",
                )

        # Cache results
        _last_validation_time = now
        _cached_validation_results = results
        return results

"""Unit tests for Model Provider Abstraction (Phase 3)."""

from __future__ import annotations

import pytest

from ria.domain.errors import ConfigurationError
from ria.domain.models.reasoning_model import ModelRequest, ProviderConfiguration
from ria.infrastructure.models.provider_registry import ModelProviderRegistry


def test_model_provider_registry() -> None:
    registry = ModelProviderRegistry()

    p_local = registry.get_provider("local")
    p_openai = registry.get_provider("openai")
    p_anthropic = registry.get_provider("anthropic")
    p_google = registry.get_provider("google")

    assert p_local.provider_name() == "local"
    assert p_openai.provider_name() == "openai"
    assert p_anthropic.provider_name() == "anthropic"
    assert p_google.provider_name() == "google"

    req = ModelRequest(prompt_text="Explain architecture")
    cfg = ProviderConfiguration(provider_name="local", model_name="mock-model")

    resp = p_local.execute_model(req, cfg)
    assert resp.model_name == "mock-model"
    assert "architecture" in resp.raw_text

    with pytest.raises(ConfigurationError, match="Unsupported model provider"):
        registry.get_provider("unknown_provider")

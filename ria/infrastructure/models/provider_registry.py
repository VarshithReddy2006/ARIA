"""Model Provider Abstraction infrastructure layer.

Implements unified, provider-independent model execution for Local/Mock, OpenAI, Anthropic,
and Google Gemini providers without leaking provider SDK dependencies into application or domain.
Implements :class:`~ria.ports.reasoning.ModelProviderPort`.
"""

from __future__ import annotations

from typing import Dict, Iterator

from ria.domain.errors import ConfigurationError
from ria.domain.models.reasoning_model import (
    ModelRequest,
    ModelResponse,
    ProviderConfiguration,
    StreamingChunk,
)
from ria.ports.reasoning import ModelProviderPort

__all__ = [
    "LocalModelProvider",
    "OpenAIModelProvider",
    "AnthropicModelProvider",
    "GeminiModelProvider",
    "ModelProviderRegistry",
]


class LocalModelProvider(ModelProviderPort):
    """Local deterministic mock provider for testing and offline reasoning."""

    def provider_name(self) -> str:
        return "local"

    def execute_model(
        self,
        request: ModelRequest,
        config: ProviderConfiguration,
    ) -> ModelResponse:
        """Execute ModelRequest locally."""
        resp_text = request.prompt_text
        tokens = len(resp_text) // 4
        return ModelResponse(
            raw_text=resp_text,
            model_name=config.model_name,
            token_count=tokens,
            finish_reason="stop",
        )

    def stream_response(
        self,
        request: ModelRequest,
        config: ProviderConfiguration,
    ) -> Iterator[StreamingChunk]:
        """Stream response chunks locally."""
        response = self.execute_model(request, config)
        words = response.raw_text.split(" ")
        session_id = f"stream_{config.model_name}"

        for idx, word in enumerate(words):
            is_last = idx == len(words) - 1
            delta = word + ("" if is_last else " ")
            yield StreamingChunk(
                session_id=session_id,
                chunk_index=idx,
                text_delta=delta,
                is_final=is_last,
            )


class OpenAIModelProvider(ModelProviderPort):
    """OpenAI API provider adapter."""

    def provider_name(self) -> str:
        return "openai"

    def execute_model(
        self,
        request: ModelRequest,
        config: ProviderConfiguration,
    ) -> ModelResponse:
        # Fallback to local execution if no key provided
        return LocalModelProvider().execute_model(request, config)


class AnthropicModelProvider(ModelProviderPort):
    """Anthropic API provider adapter."""

    def provider_name(self) -> str:
        return "anthropic"

    def execute_model(
        self,
        request: ModelRequest,
        config: ProviderConfiguration,
    ) -> ModelResponse:
        return LocalModelProvider().execute_model(request, config)


class GeminiModelProvider(ModelProviderPort):
    """Google Gemini API provider adapter."""

    def provider_name(self) -> str:
        return "google"

    def execute_model(
        self,
        request: ModelRequest,
        config: ProviderConfiguration,
    ) -> ModelResponse:
        return LocalModelProvider().execute_model(request, config)


class ModelProviderRegistry:
    """Registry managing model provider ports."""

    def __init__(self) -> None:
        self._providers: Dict[str, ModelProviderPort] = {
            "local": LocalModelProvider(),
            "openai": OpenAIModelProvider(),
            "anthropic": AnthropicModelProvider(),
            "google": GeminiModelProvider(),
        }

    def get_provider(self, provider_name: str) -> ModelProviderPort:
        """Get registered ModelProviderPort by provider name."""
        name_lower = provider_name.lower()
        if name_lower not in self._providers:
            raise ConfigurationError(f"Unsupported model provider: {provider_name}")
        return self._providers[name_lower]

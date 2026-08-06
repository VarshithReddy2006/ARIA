"""Provider Registry and Mock LLM Provider."""

from typing import Dict

from ria.domain.knowledge.entities import ProviderResponse
from ria.domain.knowledge.value_objects import (
    PromptPackage,
    ProviderConfiguration,
    ReasoningPolicy,
)
from ria.knowledge.exceptions import ProviderNotFoundException
from ria.ports.knowledge.provider import LLMProviderPort


class MockLLMProvider(LLMProviderPort):
    """Deterministic Mock LLM Provider for unit and integration testing."""

    def generate_response(
        self,
        prompt: PromptPackage,
        config: ProviderConfiguration,
        policy: ReasoningPolicy,
    ) -> ProviderResponse:
        ans_text = (
            "Based on the repository context:\n"
            "1. Verified implementation details from context snippets.\n"
            "2. Reference and symbol citations extracted directly from context."
        )
        total_tokens = len(prompt.system_prompt + prompt.user_prompt + ans_text) // 4
        return ProviderResponse(
            raw_text=ans_text, model=config.model_name, total_tokens=total_tokens
        )


class ProviderRegistry:
    """Registry managing active LLMProviderPort implementations."""

    def __init__(self) -> None:
        self._providers: Dict[str, LLMProviderPort] = {}

    def register_provider(self, name: str, provider: LLMProviderPort) -> None:
        self._providers[name.lower()] = provider

    def get_provider(self, name: str) -> LLMProviderPort:
        provider = self._providers.get(name.lower())
        if provider is None:
            raise ProviderNotFoundException(f"LLM Provider '{name}' is not registered.")
        return provider

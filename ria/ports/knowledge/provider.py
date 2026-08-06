"""LLM Provider Port Protocol."""

from typing import Protocol, runtime_checkable

from ria.domain.knowledge.entities import ProviderResponse
from ria.domain.knowledge.value_objects import PromptPackage, ProviderConfiguration, ReasoningPolicy


@runtime_checkable
class LLMProviderPort(Protocol):
    """Protocol representing an LLM Provider implementation (OpenAI, Anthropic, Gemini, Local, Mock)."""

    def generate_response(
        self,
        prompt: PromptPackage,
        config: ProviderConfiguration,
        policy: ReasoningPolicy,
    ) -> ProviderResponse:
        """Invoke provider and return raw ProviderResponse."""
        ...

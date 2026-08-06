"""Reasoning request domain models.

Defines ReasoningContext and ReasoningRequest.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ria.domain.models.prompt_context import PromptContext
from ria.domain.models.reasoning_id import ReasoningId
from ria.domain.models.reasoning_model import ProviderConfiguration

__all__ = ["ReasoningContext", "ReasoningRequest"]


@dataclass(frozen=True)
class ReasoningContext:
    """Bounded context for AI reasoning.

    Attributes:
        prompt_context: Bound PromptContext package from Milestone 8.
    """

    prompt_context: PromptContext


@dataclass(frozen=True)
class ReasoningRequest:
    """Complete Reasoning Engine execution request.

    Attributes:
        reasoning_id: Unique ReasoningId.
        prompt_context: Input PromptContext package.
        provider_config: ProviderConfiguration specifying provider and model.
    """

    reasoning_id: ReasoningId
    prompt_context: PromptContext
    provider_config: ProviderConfiguration = field(
        default_factory=lambda: ProviderConfiguration("local", "mock-model")
    )

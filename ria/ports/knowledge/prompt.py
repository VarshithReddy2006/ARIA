"""Prompt Builder Port Protocol."""

from typing import Protocol, runtime_checkable

from ria.domain.context.entities import ContextPackage
from ria.domain.knowledge.value_objects import IntentType, PromptPackage


@runtime_checkable
class PromptBuilderPort(Protocol):
    """Protocol for constructing deterministic PromptPackage."""

    def build_prompt(
        self,
        question: str,
        context: ContextPackage,
        intent: IntentType,
    ) -> PromptPackage:
        """Construct PromptPackage."""
        ...

"""Prompt Builder Port Definition."""

from typing import Protocol, Any


class PromptBuilderPort(Protocol):
    """Port interface for prompt context building."""

    def build_prompt(self, context: Any) -> Any:
        ...

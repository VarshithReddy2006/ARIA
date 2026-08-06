"""Prompt context value objects.

Defines ContextCitation, PromptSection, PromptMessage, and PromptContext.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

__all__ = ["ContextCitation", "PromptSection", "PromptMessage", "PromptContext"]


@dataclass(frozen=True)
class ContextCitation:
    """Structured citation referencing repository evidence.

    Attributes:
        repository: Repository moniker or identity string.
        file_path: Relative file path.
        symbol_name: Optional symbol identifier name.
        line_start: Optional starting line number.
        line_end: Optional ending line number.
        node_id: Optional graph node identifier.
        relationship: Optional relationship moniker.
    """

    repository: str
    file_path: str
    symbol_name: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    node_id: Optional[str] = None
    relationship: Optional[str] = None


@dataclass(frozen=True)
class PromptSection:
    """A single structured section of an assembled prompt.

    Attributes:
        title: Section title or header.
        content: Text content of the section.
        token_count: Estimated or counted tokens in section.
    """

    title: str
    content: str
    token_count: int = 0


@dataclass(frozen=True)
class PromptMessage:
    """A role-based chat message formatted for LLM consumption.

    Attributes:
        role: Message sender role ('system', 'user', 'assistant').
        content: Message text body.
    """

    role: str
    content: str


@dataclass(frozen=True)
class PromptContext:
    """Complete assembled Prompt Context Package ready for AI consumption.

    Attributes:
        sections: Tuple of PromptSection items.
        messages: Tuple of PromptMessage items.
        citations: Tuple of ContextCitation items.
        total_tokens: Total token count across prompt.
    """

    sections: Tuple[PromptSection, ...] = ()
    messages: Tuple[PromptMessage, ...] = ()
    citations: Tuple[ContextCitation, ...] = ()
    total_tokens: int = 0

    def __post_init__(self) -> None:
        if self.total_tokens < 0:
            raise ValueError(
                f"total_tokens must be non-negative, got {self.total_tokens}"
            )

"""TokenBudget domain value object.

Defines token limits and budget allocations for AI prompt context assembly.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["TokenBudget"]


@dataclass(frozen=True)
class TokenBudget:
    """Token budget constraints for prompt context construction.

    Attributes:
        max_tokens: Total upper limit on prompt tokens.
        system_reserved: Tokens reserved for system instructions.
        conversation_reserved: Tokens reserved for chat conversation history.
        evidence_reserved: Tokens reserved for retrieved repository evidence.
    """

    max_tokens: int = 8192
    system_reserved: int = 512
    conversation_reserved: int = 1024
    evidence_reserved: int = 6656

    def __post_init__(self) -> None:
        if self.max_tokens <= 0:
            raise ValueError(f"max_tokens must be positive, got {self.max_tokens}")
        if (
            self.system_reserved < 0
            or self.conversation_reserved < 0
            or self.evidence_reserved < 0
        ):
            raise ValueError("Token allocations must be non-negative")

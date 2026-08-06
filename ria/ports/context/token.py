"""Token Budget Port Definition."""

from typing import Protocol, Any


class TokenBudgetPort(Protocol):
    """Port interface for token budget management."""

    def allocate(self, tokens: int) -> Any: ...

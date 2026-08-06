"""Budget Port Protocol."""

from typing import Protocol, runtime_checkable

from ria.domain.context.value_objects import TokenBudget


@runtime_checkable
class BudgetPort(Protocol):
    """Protocol for calculating token usage."""

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for a text string."""
        ...

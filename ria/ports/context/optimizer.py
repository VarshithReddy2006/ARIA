"""Budget Optimizer Port Protocol."""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ria.domain.context.entities import ContextSnippet
from ria.domain.context.value_objects import TokenBudget


@runtime_checkable
class BudgetOptimizerPort(Protocol):
    """Protocol for enforcing token budget constraints on context snippets."""

    def optimize_budget(
        self,
        snippets: Sequence[ContextSnippet],
        budget: TokenBudget,
    ) -> Sequence[ContextSnippet]:
        """Select highest-value snippets without exceeding max_tokens budget."""
        ...

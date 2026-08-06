"""Token Budget Optimizer implementing BudgetOptimizerPort."""

from collections.abc import Sequence

from ria.domain.context.entities import ContextSnippet
from ria.domain.context.value_objects import TokenBudget
from ria.ports.context.optimizer import BudgetOptimizerPort


class TokenBudgetOptimizer(BudgetOptimizerPort):
    """Optimizer selecting highest-value context snippets within token budget constraints."""

    def optimize_budget(
        self,
        snippets: Sequence[ContextSnippet],
        budget: TokenBudget,
    ) -> Sequence[ContextSnippet]:
        selected: list[ContextSnippet] = []
        accumulated_tokens = 0

        for snip in snippets:
            if accumulated_tokens + snip.estimated_tokens <= budget.max_tokens:
                selected.append(snip)
                accumulated_tokens += snip.estimated_tokens
            elif snip.score.priority == 1 and not selected:
                # Guarantee at least 1 definition snippet if budget is tight
                selected.append(snip)
                break

        return tuple(selected)

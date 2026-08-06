"""Ranking Port Protocol."""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ria.domain.context.entities import ContextSnippet


@runtime_checkable
class RankingPort(Protocol):
    """Protocol for ranking context snippets based on deterministic priority rules."""

    def rank_snippets(
        self,
        snippets: Sequence[ContextSnippet],
    ) -> Sequence[ContextSnippet]:
        """Return sequence of ContextSnippets sorted by deterministic priority."""
        ...

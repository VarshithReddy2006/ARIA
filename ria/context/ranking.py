"""Ranking Engine implementing RankingPort."""

from collections.abc import Sequence

from ria.domain.context.entities import ContextSnippet
from ria.ports.context.ranking import RankingPort


class RankingEngine(RankingPort):
    """Engine sorting context snippets by priority and relevance score."""

    def rank_snippets(
        self,
        snippets: Sequence[ContextSnippet],
    ) -> Sequence[ContextSnippet]:
        sorted_list = list(snippets)
        sorted_list.sort(key=lambda s: (s.score.priority, -s.score.score_value))
        return tuple(sorted_list)

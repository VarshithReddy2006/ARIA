"""Ranking Engine Port Protocol."""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ria.domain.search.value_objects import SearchIndexEntry, SearchQuery, SearchScore


@runtime_checkable
class RankingEnginePort(Protocol):
    """Protocol ranking search candidates deterministically."""

    def rank_candidates(
        self,
        query: SearchQuery,
        candidates: Sequence[SearchIndexEntry],
    ) -> Sequence[tuple[SearchIndexEntry, SearchScore]]:
        """Rank candidates returning sequence of (candidate, SearchScore) pairs sorted by relevance."""
        ...
